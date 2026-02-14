#!/usr/bin/env python3
"""
course_finder.py — Automated Content Pipeline for AiAstro Course System

Reads curriculum JSON → searches YouTube → filters by stats →
pulls transcripts → scores with LLM → generates questions → writes to S3.

Usage:
    # Full run for all concepts in general chemistry
    python course_finder.py --curriculum curriculum.json

    # Single concept (for testing)
    python course_finder.py --curriculum curriculum.json --concept states_of_matter

    # Dry run (search + filter only, no LLM calls)
    python course_finder.py --curriculum curriculum.json --dry-run

    # Resume from where you left off
    python course_finder.py --curriculum curriculum.json --resume

Requirements:
    pip install google-api-python-client youtube-transcript-api anthropic boto3

Environment:
    YOUTUBE_API_KEY     — YouTube Data API v3 key (free from Google Cloud Console)
    ANTHROPIC_API_KEY   — Claude API key
    AWS_PROFILE         — (optional) AWS profile for S3 uploads
    S3_BUCKET           — (optional) S3 bucket name, defaults to local output
"""

import json
import os
import sys
import time
import re
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional
from transcript_prefilter import passes_transcript_filter


class QuotaExceededError(Exception):
    """Raised when YouTube API daily quota is exhausted."""
    pass


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

@dataclass
class Config:
    """Pipeline configuration — tune these knobs."""

    # YouTube search filters
    min_views: int = 20_000
    min_like_ratio: float = 0.008  # likes/views — educational content: 0.8-3% is normal
    min_likes: int = 500  # absolute minimum likes
    min_subscribers: int = 5_000
    max_video_age_years: int = 10  # chemistry doesn't change
    max_results_per_query: int = 15
    duration_buffer_pct: float = 0.50  # allow 50% over curriculum's max duration

    # Transcript / scoring
    min_coverage_score: float = 0.60  # fraction of must_cover items hit
    min_videos_per_concept: int = 3
    max_videos_per_concept: int = 6

    # LLM
    llm_provider: str = "anthropic"  # "anthropic" or "openai"
    llm_model: str = "claude-sonnet-4-20250514"
    llm_max_tokens: int = 4096
    questions_per_video: int = 5

    # Rate limiting
    youtube_delay_sec: float = 0.5  # between YouTube Data API calls (search, stats)
    llm_delay_sec: float = 1.0  # between LLM calls
    transcript_delay_sec: float = 3.0  # BEFORE each transcript pull (YouTube throttles this hard)
    transcript_max_retries: int = 3  # retry on 429 with exponential backoff
    transcript_backoff_base: float = 10.0  # first retry: 10s, then 20s, then 40s
    video_cooldown_sec: float = 120.0  # wait between fully processing videos (transcript → prefilter → LLM)
    # ↑ YouTube transcript endpoint rate-limits aggressively.
    #   120s cooldown means ~3 min per video including Claude analysis time.
    #   For 113 concepts × ~4 videos each ≈ 7-8 hours of pipeline time.
    #   But zero 429s and zero wasted quota.

    # Output
    output_dir: str = "./course_finder_output"
    s3_bucket: Optional[str] = None
    s3_prefix: str = "curriculum"
    version_tag: str = ""  # Set dynamically in __post_init__

    def __post_init__(self):
        if not self.version_tag:
            self.version_tag = datetime.now(timezone.utc).strftime("v%Y%m%d_%H%M%S")


# ---------------------------------------------------------------------------
# DATA MODELS
# ---------------------------------------------------------------------------

@dataclass
class VideoCandidate:
    video_id: str
    title: str
    channel_title: str
    channel_id: str
    description: str = ""
    published_at: str = ""
    duration_sec: int = 0
    view_count: int = 0
    like_count: int = 0
    like_ratio: float = 0.0
    has_captions: bool = False
    definition: str = ""
    thumbnail_url: str = ""
    tags: list = field(default_factory=list)
    subscriber_count: int = 0


@dataclass
class ScoredVideo:
    """A video that passed LLM scoring."""
    video_id: str
    title: str
    channel_title: str
    channel_id: str
    video_url: str
    thumbnail_url: str
    duration_sec: int
    view_count: int
    like_ratio: float
    subscriber_count: int
    published_at: str

    # Concept scoring
    concept_id: str
    coverage_score: float  # 0.0 - 1.0
    covered_items: list = field(default_factory=list)
    missing_items: list = field(default_factory=list)
    detected_style: str = ""
    detected_level: str = ""

    # Timestamps (for multi-concept videos)
    start_sec: int = 0
    end_sec: int = 0

    # Additional concepts this video covers
    also_covers: dict = field(default_factory=dict)  # concept_id -> coverage_score

    # Generated questions
    questions: list = field(default_factory=list)

    active: bool = True
    found_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# YOUTUBE CLIENT
# ---------------------------------------------------------------------------

class YouTubeClient:
    """Handles all YouTube Data API v3 interactions."""

    def __init__(self, api_key: str, config: Config):
        from googleapiclient.discovery import build
        self.youtube = build("youtube", "v3", developerKey=api_key)
        self.config = config
        self._channel_cache = {}
        self._quota_used = 0

    @property
    def quota_used(self):
        return self._quota_used

    def search_videos(self, query: str, duration_range: tuple = (180, 900)) -> list[dict]:
        """Search YouTube for videos matching query. Returns list of video IDs + snippets."""

        # Map duration range to YouTube's duration filter
        # short = <4min, medium = 4-20min, long = >20min
        min_dur, max_dur = duration_range
        if max_dur <= 240:
            video_duration = "short"
        elif min_dur >= 1200:
            video_duration = "long"
        else:
            video_duration = "medium"

        try:
            request = self.youtube.search().list(
                q=query,
                type="video",
                part="snippet",
                videoDuration=video_duration,
                order="relevance",
                maxResults=self.config.max_results_per_query,
                relevanceLanguage="en",
                videoCaption="closedCaption",  # only videos with captions
                safeSearch="strict"
            )
            response = request.execute()
            self._quota_used += 100  # search.list = 100 units

            time.sleep(self.config.youtube_delay_sec)

            results = []
            for item in response.get("items", []):
                results.append({
                    "video_id": item["id"]["videoId"],
                    "title": item["snippet"]["title"],
                    "channel_title": item["snippet"]["channelTitle"],
                    "channel_id": item["snippet"]["channelId"],
                    "description": item["snippet"].get("description", ""),
                    "published_at": item["snippet"]["publishedAt"],
                    "thumbnail_url": item["snippet"]["thumbnails"].get("high", {}).get("url", "")
                })

            return results

        except Exception as e:
            if "quotaExceeded" in str(e) or "403" in str(e):
                logging.error(f"⛔ YouTube quota exceeded! Stopping pipeline.")
                raise QuotaExceededError("YouTube daily quota hit")
            logging.error(f"YouTube search failed for '{query}': {e}")
            return []

    def get_video_details(self, video_ids: list[str]) -> list[VideoCandidate]:
        """Get stats + content details for a batch of video IDs."""

        candidates = []

        # YouTube allows up to 50 IDs per call
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i + 50]

            try:
                request = self.youtube.videos().list(
                    id=",".join(batch),
                    part="statistics,contentDetails,snippet"
                )
                response = request.execute()
                self._quota_used += 1  # videos.list = 1 unit per call

                for item in response.get("items", []):
                    stats = item.get("statistics", {})
                    content = item.get("contentDetails", {})
                    snippet = item.get("snippet", {})

                    views = int(stats.get("viewCount", 0))
                    likes = int(stats.get("likeCount", 0))

                    candidates.append(VideoCandidate(
                        video_id=item["id"],
                        title=snippet.get("title", ""),
                        channel_title=snippet.get("channelTitle", ""),
                        channel_id=snippet.get("channelId", ""),
                        description=snippet.get("description", ""),
                        published_at=snippet.get("publishedAt", ""),
                        duration_sec=self._parse_duration(content.get("duration", "PT0S")),
                        view_count=views,
                        like_count=likes,
                        like_ratio=likes / max(views, 1),
                        has_captions=content.get("caption", "false") == "true",
                        definition=content.get("definition", ""),
                        thumbnail_url=snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                        tags=snippet.get("tags", [])
                    ))

                time.sleep(self.config.youtube_delay_sec)

            except Exception as e:
                if "quotaExceeded" in str(e) or "403" in str(e):
                    raise QuotaExceededError("YouTube daily quota hit")
                logging.error(f"Failed to get video details: {e}")

        return candidates

    def get_channel_subscribers(self, channel_id: str) -> int:
        """Get subscriber count for a channel. Cached."""

        if channel_id in self._channel_cache:
            return self._channel_cache[channel_id]

        try:
            request = self.youtube.channels().list(
                id=channel_id,
                part="statistics"
            )
            response = request.execute()
            self._quota_used += 1

            items = response.get("items", [])
            if items:
                subs = int(items[0]["statistics"].get("subscriberCount", 0))
                self._channel_cache[channel_id] = subs
                return subs
        except Exception as e:
            if "quotaExceeded" in str(e) or "403" in str(e):
                raise QuotaExceededError("YouTube daily quota hit")
            logging.error(f"Failed to get channel info for {channel_id}: {e}")

        self._channel_cache[channel_id] = 0
        return 0

    @staticmethod
    def _parse_duration(iso_duration: str) -> int:
        """Parse ISO 8601 duration (PT8M12S) to seconds."""
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds


# ---------------------------------------------------------------------------
# TRANSCRIPT PULLER
# ---------------------------------------------------------------------------

class TranscriptPuller:
    """Pulls YouTube transcripts using the free youtube-transcript-api library.

    The transcript endpoint (timedtext) is SEPARATE from YouTube Data API v3.
    It has no official quota but rate-limits aggressively — especially on
    repeated hits from the same IP. We use exponential backoff on 429s.
    """

    def __init__(self, max_retries: int = 3, backoff_base: float = 10.0):
        from youtube_transcript_api import YouTubeTranscriptApi
        self.api = YouTubeTranscriptApi()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.consecutive_429s = 0  # track for adaptive slowdown

    def get_transcript(self, video_id: str) -> Optional[dict]:
        """
        Returns {
            "full_text": "the complete transcript as one string",
            "segments": [{"text": "...", "start": 0.0, "duration": 2.5}, ...],
            "char_count": 1234
        }
        or None if unavailable.

        Retries with exponential backoff on 429 / IP-block errors.
        """
        for attempt in range(self.max_retries):
            try:
                transcript = self.api.fetch(video_id)
                segments = [{"text": entry.text, "start": entry.start, "duration": entry.duration}
                            for entry in transcript]
                full_text = " ".join(seg["text"] for seg in segments)

                self.consecutive_429s = 0  # reset on success
                return {
                    "full_text": full_text,
                    "segments": segments,
                    "char_count": len(full_text)
                }
            except Exception as e:
                error_str = str(e)

                # Detect rate limiting (429, IP block, Too Many Requests)
                is_rate_limit = any(sig in error_str for sig in [
                    "429", "Too Many Requests", "IP", "RequestBlocked", "IpBlocked"
                ])

                if is_rate_limit and attempt < self.max_retries - 1:
                    self.consecutive_429s += 1
                    # Exponential backoff: 10s → 20s → 40s, with extra penalty for streaks
                    backoff = self.backoff_base * (2 ** attempt)
                    if self.consecutive_429s > 3:
                        backoff *= 2  # double it if we've been getting hammered
                    backoff = min(backoff, 120)  # cap at 2 min

                    logging.warning(
                        f"    ⏳ Rate limited on {video_id} — "
                        f"waiting {backoff:.0f}s (attempt {attempt + 1}/{self.max_retries}, "
                        f"streak: {self.consecutive_429s})")
                    time.sleep(backoff)
                    continue

                elif is_rate_limit:
                    self.consecutive_429s += 1
                    logging.error(
                        f"    ❌ Rate limited on {video_id} after {self.max_retries} retries. "
                        f"Consecutive 429s: {self.consecutive_429s}")
                    return None

                else:
                    # Genuine error (no captions, video unavailable, etc.)
                    logging.warning(f"No transcript for {video_id}: {e}")
                    return None

        return None


# ---------------------------------------------------------------------------
# VIDEO FILTER
# ---------------------------------------------------------------------------

class VideoFilter:
    """Applies stat-based filters before expensive LLM calls."""

    def __init__(self, config: Config, yt_client: YouTubeClient):
        self.config = config
        self.yt = yt_client

    def filter_candidates(self, candidates: list[VideoCandidate],
                          duration_range: tuple) -> list[VideoCandidate]:
        """Filter videos by stats. Returns passing candidates."""

        min_dur, max_dur = duration_range
        max_dur_buffered = int(max_dur * (1 + self.config.duration_buffer_pct))
        passed = []

        for v in candidates:
            # Duration check (buffer on max — many good edu videos run slightly long)
            if v.duration_sec < min_dur or v.duration_sec > max_dur_buffered:
                logging.debug(
                    f"  SKIP {v.video_id} '{v.title[:40]}' — duration {v.duration_sec}s outside [{min_dur}, {max_dur_buffered}]")
                continue

            # View count
            if v.view_count < self.config.min_views:
                logging.debug(
                    f"  SKIP {v.video_id} '{v.title[:40]}' — {v.view_count:,} views < {self.config.min_views:,}")
                continue

            # Like count (absolute minimum)
            if v.like_count < self.config.min_likes:
                logging.debug(
                    f"  SKIP {v.video_id} '{v.title[:40]}' — {v.like_count:,} likes < {self.config.min_likes:,}")
                continue

            # Engagement rate (likes/views) — YouTube removed dislikes in 2021
            # Good educational videos: 2-5% engagement. Viral junk: <1%.
            if v.view_count > 1000 and v.like_ratio < self.config.min_like_ratio:
                logging.debug(
                    f"  SKIP {v.video_id} '{v.title[:40]}' — engagement {v.like_ratio:.1%} < {self.config.min_like_ratio:.1%}")
                continue

            # Channel subscribers
            subs = self.yt.get_channel_subscribers(v.channel_id)
            v.subscriber_count = subs
            if subs < self.config.min_subscribers:
                logging.debug(f"  SKIP {v.video_id} — {subs} subs < {self.config.min_subscribers}")
                continue

            # Age check
            try:
                pub_year = int(v.published_at[:4])
                current_year = datetime.now().year
                if current_year - pub_year > self.config.max_video_age_years:
                    logging.debug(f"  SKIP {v.video_id} — too old ({pub_year})")
                    continue
            except (ValueError, IndexError):
                pass  # Can't parse date, let it through

            passed.append(v)

        return passed


# ---------------------------------------------------------------------------
# LLM SCORER
# ---------------------------------------------------------------------------

class LLMScorer:
    """
    Uses LLM to analyze video transcripts in a SINGLE call.

    Supports both Anthropic (Claude) and OpenAI (GPT) via raw HTTP.

    Extracts everything at once:
      - Coverage scoring (does it cover must_cover items?)
      - Teacher profile (style, tone, pacing, best_for)
      - Content analysis (topics, timestamps, examples, warnings)
      - Questions (5 MC questions with misconception tags)

    One call per video. Half the cost of two separate calls.
    """

    # Default models per provider
    DEFAULT_MODELS = {
        "anthropic": "claude-sonnet-4-20250514",
        "openai": "gpt-4o",
    }

    # Rough cost per million tokens (blended input+output average)
    COST_PER_M_TOKENS = {
        "anthropic": {"claude-sonnet-4-20250514": 5.0, "claude-haiku-4-5-20251001": 1.0},
        "openai": {"gpt-4o": 7.5, "gpt-4o-mini": 0.6, "gpt-4.1": 6.0, "gpt-4.1-mini": 1.0, "gpt-4.1-nano": 0.3},
    }

    def __init__(self, api_key: str, config: Config):
        import httpx
        self.api_key = api_key
        self.provider = config.llm_provider
        self.http_client = httpx.Client(timeout=120.0)
        self.config = config
        self._calls_made = 0
        self._tokens_used = 0

    @property
    def stats(self):
        return {"calls": self._calls_made, "tokens": self._tokens_used}

    def _call_llm(self, prompt: str, max_tokens: int = None) -> str:
        """Raw HTTP call to LLM API. Supports Anthropic and OpenAI."""
        if max_tokens is None:
            max_tokens = self.config.llm_max_tokens

        if self.provider == "anthropic":
            return self._call_anthropic(prompt, max_tokens)
        elif self.provider == "openai":
            return self._call_openai(prompt, max_tokens)
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _call_anthropic(self, prompt: str, max_tokens: int) -> str:
        """Call Anthropic Claude API."""
        resp = self.http_client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self.config.llm_model,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]
            }
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self._calls_made += 1
        self._tokens_used += usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        return text

    def _call_openai(self, prompt: str, max_tokens: int) -> str:
        """Call OpenAI ChatGPT API."""
        resp = self.http_client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "content-type": "application/json",
            },
            json={
                "model": self.config.llm_model,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system",
                     "content": "You are an expert chemistry education content analyst. Always respond with valid JSON only — no markdown fences, no commentary."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
            }
        )
        resp.raise_for_status()
        data = resp.json()

        usage = data.get("usage", {})
        self._calls_made += 1
        self._tokens_used += usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)

        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return text

    def estimate_cost(self) -> str:
        """Cost estimate based on provider and model."""
        tokens = self._tokens_used
        model = self.config.llm_model
        provider_costs = self.COST_PER_M_TOKENS.get(self.provider, {})
        rate = provider_costs.get(model, 5.0)  # fallback $5/M
        cost = (tokens / 1_000_000) * rate
        return f"${cost:.2f}"

    def analyze_video(self, transcript_text: str, concept: dict,
                      sibling_concepts: dict = None) -> dict:
        """
        Single LLM call that extracts EVERYTHING from a transcript.

        Returns:
        {
            "coverage": {
                "overall_score": 0.8,
                "items": [{"requirement": "...", "covered": true, "start_sec": 12, ...}]
            },
            "teacher_profile": {
                "teaching_style": {"primary": "conceptual", "secondary": "visual"},
                "tone": "warm_encouraging",
                "pacing": "slow_deliberate",
                "complexity_level": "L0_L1",
                "explanation_approach": "analogy_heavy",
                "engagement_style": "asks_questions",
                "production_quality": "high_animation",
                "best_for": {"struggling_students": true, ...}
            },
            "content_analysis": {
                "primary_topic": "states_of_matter",
                "topics_covered": [{"topic": "...", "start_sec": 0, "end_sec": 310, "depth": "thorough"}],
                "key_terms_used": [...],
                "real_world_examples": [...],
                "content_warnings": {...}
            },
            "questions": [
                {
                    "id": "q1",
                    "question_text": "...",
                    "choices": {"A": "...", "B": "...", "C": "...", "D": "..."},
                    "correct_answer": "A",
                    "difficulty": "easy",
                    "bloom_level": "recall",
                    "misconception_tags": {"B": "MC_CODE"},
                    "explanation": "...",
                    "timestamp_sec": 45
                }
            ]
        }
        """
        from llm_prompts import build_analysis_prompt

        prompt = build_analysis_prompt(transcript_text, concept, sibling_concepts)

        try:
            text = self._call_llm(prompt)

            # Parse JSON response
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)
            result = json.loads(text.strip())

            time.sleep(self.config.llm_delay_sec)
            return result

        except json.JSONDecodeError as e:
            logging.error(f"LLM returned invalid JSON: {e}")
            return self._empty_result(concept)
        except Exception as e:
            import traceback
            logging.error(f"LLM analysis failed: {e}")
            logging.error(traceback.format_exc())
            return self._empty_result(concept)

    def quick_coverage_check(self, transcript_text: str, concept: dict) -> dict:
        """
        Lightweight coverage-only check for sibling concept verification.
        Much cheaper — no teacher profiling, no questions.
        """
        from llm_prompts import build_sibling_only_prompt

        prompt = build_sibling_only_prompt(transcript_text, concept)

        try:
            text = self._call_llm(prompt, max_tokens=1024)
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)

            time.sleep(self.config.llm_delay_sec)
            return json.loads(text.strip())

        except Exception as e:
            logging.error(f"Quick coverage check failed: {e}")
            return {"overall_score": 0, "items": []}

    @staticmethod
    def _empty_result(concept: dict) -> dict:
        """Return empty result structure on failure."""
        return {
            "coverage": {
                "overall_score": 0,
                "items": [{"requirement": item, "covered": False, "start_sec": None, "end_sec": None, "quote": None}
                          for item in concept.get("must_cover", [])]
            },
            "teacher_profile": {},
            "content_analysis": {"primary_topic": "", "topics_covered": [], "key_terms_used": []},
            "questions": []
        }


# ---------------------------------------------------------------------------
# OUTPUT WRITER
# ---------------------------------------------------------------------------

class OutputWriter:
    """Writes pipeline results to local filesystem and optionally S3."""

    def __init__(self, config: Config):
        self.config = config
        self.output_dir = Path(config.output_dir) / config.version_tag
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.s3_client = None

        if config.s3_bucket:
            import boto3
            self.s3_client = boto3.client("s3")

    def write_concept_results(self, course_id: str, topic_id: str,
                              subtopic_id: str, concept_id: str,
                              videos: list[ScoredVideo]):
        """Write videos + questions for a concept."""

        concept_dir = self.output_dir / course_id / topic_id / subtopic_id / concept_id
        concept_dir.mkdir(parents=True, exist_ok=True)

        # videos.json
        video_data = []
        for v in videos:
            entry = {
                "video_id": v.video_id,
                "title": v.title,
                "teacher": v.channel_title,
                "channel_id": v.channel_id,
                "video_url": v.video_url,
                "thumbnail_url": v.thumbnail_url,
                "duration_sec": v.duration_sec,
                "start_sec": v.start_sec,
                "end_sec": v.end_sec,
                "view_count": v.view_count,
                "like_ratio": round(v.like_ratio, 3),
                "subscriber_count": v.subscriber_count,
                "published_at": v.published_at,
                "coverage_score": round(v.coverage_score, 2),
                "covered_items": v.covered_items,
                "missing_items": v.missing_items,
                "detected_style": v.detected_style,
                "detected_level": v.detected_level,
                "also_covers": v.also_covers,
                "active": v.active,
                "found_at": v.found_at
            }
            # Include full LLM analysis if available
            if hasattr(v, '_teacher_profile') and v._teacher_profile:
                entry["teacher_profile"] = v._teacher_profile
            if hasattr(v, '_content_analysis') and v._content_analysis:
                entry["content_analysis"] = v._content_analysis
            if hasattr(v, '_content_warnings') and v._content_warnings:
                entry["content_warnings"] = v._content_warnings
            video_data.append(entry)

        videos_path = concept_dir / "videos.json"
        with open(videos_path, "w") as f:
            json.dump(video_data, f, indent=2)

        # questions.json (all questions from all videos for this concept)
        all_questions = []
        q_counter = 0
        for v in videos:
            for q in v.questions:
                q_counter += 1
                q["id"] = f"{concept_id}_{v.video_id}_{q_counter:03d}"
                q["source_video_id"] = v.video_id
                q["source_teacher"] = v.channel_title
                all_questions.append(q)

        questions_path = concept_dir / "questions.json"
        with open(questions_path, "w") as f:
            json.dump(all_questions, f, indent=2)

        # Upload to S3 if configured
        if self.s3_client and self.config.s3_bucket:
            for fpath in [videos_path, questions_path]:
                s3_key = f"{self.config.s3_prefix}/{self.config.version_tag}/{fpath.relative_to(self.output_dir)}"
                self.s3_client.upload_file(str(fpath), self.config.s3_bucket, s3_key)

        return len(video_data), len(all_questions)

    def write_manifest(self, manifest: dict):
        """Write the run manifest (summary of what happened)."""
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

        if self.s3_client and self.config.s3_bucket:
            s3_key = f"{self.config.s3_prefix}/{self.config.version_tag}/manifest.json"
            self.s3_client.upload_file(str(manifest_path), self.config.s3_bucket, s3_key)

    def write_progress(self, progress: dict):
        """Write checkpoint file for resume capability."""
        progress_path = self.output_dir / "_progress.json"
        with open(progress_path, "w") as f:
            json.dump(progress, f, indent=2)

    def load_progress(self) -> dict:
        """Load checkpoint file if it exists."""
        progress_path = self.output_dir / "_progress.json"
        if progress_path.exists():
            with open(progress_path) as f:
                return json.load(f)
        return {"completed_concepts": []}


# ---------------------------------------------------------------------------
# MAIN PIPELINE
# ---------------------------------------------------------------------------

class CourseFinder:
    """Orchestrates the full pipeline."""

    def __init__(self, config: Config):
        self.config = config
        self.yt = YouTubeClient(os.environ["YOUTUBE_API_KEY"], config)
        self.transcripts = TranscriptPuller(
            max_retries=config.transcript_max_retries,
            backoff_base=config.transcript_backoff_base
        )
        self.filter = VideoFilter(config, self.yt)

        # Pick the right API key based on provider
        if config.llm_provider == "openai":
            llm_key = os.environ.get("OPENAI_API_KEY", "")
        else:
            llm_key = os.environ.get("ANTHROPIC_API_KEY", "")
        self.scorer = LLMScorer(llm_key, config)
        self.writer = OutputWriter(config)

        # Stats
        self.stats = {
            "concepts_processed": 0,
            "concepts_skipped": 0,
            "concepts_insufficient": [],
            "videos_searched": 0,
            "videos_passed_filter": 0,
            "videos_prefilter_rejected": 0,
            "videos_scored": 0,
            "videos_kept": 0,
            "questions_generated": 0,
            "errors": []
        }

    def run(self, curriculum_path: str, single_concept: str = None,
            dry_run: bool = False, resume: bool = False):
        """Run the full pipeline."""

        # Load curriculum
        with open(curriculum_path) as f:
            curriculum = json.load(f)

        course_id = curriculum.get("course", "unknown")
        topics = curriculum.get("topics", {})

        logging.info(f"Pipeline starting for course: {course_id}")
        logging.info(f"Topics: {len(topics)}, Version: {self.config.version_tag}")
        logging.info(f"LLM: {self.config.llm_provider} / {self.config.llm_model}")
        logging.info(f"Throttle: {self.config.video_cooldown_sec:.0f}s cooldown between videos, "
                     f"{self.config.transcript_delay_sec:.0f}s transcript delay")

        # Load progress for resume
        progress = self.writer.load_progress() if resume else {"completed_concepts": []}

        # Walk the curriculum tree
        for topic_id, topic in sorted(topics.items(), key=lambda x: x[1].get("order", 0)):
            logging.info(f"\n{'=' * 60}")
            logging.info(f"TOPIC: {topic.get('display_name', topic_id)}")
            logging.info(f"{'=' * 60}")

            for subtopic_id, subtopic in sorted(topic.get("subtopics", {}).items(),
                                                key=lambda x: x[1].get("order", 0)):
                logging.info(f"\n  SUBTOPIC: {subtopic.get('display_name', subtopic_id)}")

                concepts = subtopic.get("concepts", {})

                for concept_id, concept in concepts.items():
                    # Single concept mode
                    if single_concept and concept_id != single_concept:
                        continue

                    # Resume mode
                    full_id = f"{topic_id}/{subtopic_id}/{concept_id}"
                    if resume and full_id in progress["completed_concepts"]:
                        logging.info(f"    SKIP (already done): {concept_id}")
                        continue

                    logging.info(f"\n    CONCEPT: {concept.get('display_name', concept_id)}")

                    # Get sibling concepts for multi-concept scoring
                    siblings = {cid: cdata for cid, cdata in concepts.items()
                                if cid != concept_id}

                    # Process this concept
                    try:
                        videos = self._process_concept(
                            course_id, topic_id, subtopic_id,
                            concept_id, concept, siblings, dry_run
                        )

                        if not dry_run and videos:
                            n_vids, n_qs = self.writer.write_concept_results(
                                course_id, topic_id, subtopic_id, concept_id, videos
                            )
                            logging.info(f"    WROTE: {n_vids} videos, {n_qs} questions")

                        # Update progress
                        progress["completed_concepts"].append(full_id)
                        self.writer.write_progress(progress)

                    except QuotaExceededError:
                        logging.error("")
                        logging.error("⛔ YouTube quota exceeded! Progress saved.")
                        logging.error(f"   Completed: {len(progress['completed_concepts'])} concepts")
                        logging.error(f"   Run with --resume tomorrow to continue.")
                        self.writer.write_progress(progress)
                        self._write_manifest(course_id, curriculum_path)
                        self._print_summary()
                        return

                    except Exception as e:
                        logging.error(f"    ERROR processing {concept_id}: {e}")
                        self.stats["errors"].append({"concept": concept_id, "error": str(e)})

        # Write manifest
        self._write_manifest(course_id, curriculum_path)

        # Print summary
        self._print_summary()

    @staticmethod
    def _countdown_wait(seconds: float, message: str = ""):
        """Wait with a visible countdown in the log. Shows remaining time every 30s."""
        if seconds <= 0:
            return
        if message:
            logging.info(f"{message} ({seconds:.0f}s)")

        remaining = seconds
        while remaining > 0:
            chunk = min(remaining, 30)
            time.sleep(chunk)
            remaining -= chunk
            if remaining > 0:
                logging.info(f"        ... {remaining:.0f}s remaining")

    def _process_concept(self, course_id, topic_id, subtopic_id,
                         concept_id, concept, siblings, dry_run) -> list[ScoredVideo]:
        """Process a single concept: search → filter → analyze (single LLM call) → output."""

        search_queries = concept.get("search_queries", [])
        duration_range = tuple(concept.get("duration_range", [180, 900]))
        min_needed = concept.get("min_videos_needed", 3)

        # ----- Step 1: Search YouTube -----
        all_video_ids = {}  # video_id -> search snippet

        for query in search_queries:
            logging.info(f"      Searching: '{query}'")
            results = self.yt.search_videos(query, duration_range)
            self.stats["videos_searched"] += len(results)

            for r in results:
                if r["video_id"] not in all_video_ids:
                    all_video_ids[r["video_id"]] = r

        logging.info(f"      Found {len(all_video_ids)} unique videos from {len(search_queries)} queries")

        if not all_video_ids:
            self.stats["concepts_insufficient"].append(concept_id)
            return []

        # ----- Step 2: Get video details + filter -----
        candidates = self.yt.get_video_details(list(all_video_ids.keys()))

        # Merge search snippet data
        for c in candidates:
            snippet = all_video_ids.get(c.video_id, {})
            if not c.thumbnail_url:
                c.thumbnail_url = snippet.get("thumbnail_url", "")

        passed = self.filter.filter_candidates(candidates, duration_range)
        self.stats["videos_passed_filter"] += len(passed)
        logging.info(f"      {len(passed)} passed stat filters (from {len(candidates)})")

        if dry_run:
            for v in passed[:5]:
                logging.info(f"        ✓ {v.title} ({v.channel_title}) — {v.view_count:,} views, {v.duration_sec}s")
            self.stats["concepts_processed"] += 1
            return []

        # ----- Step 3: Pull transcripts + pre-filter + LLM (THROTTLED) -----
        # Flow per video:
        #   1. Wait transcript_delay_sec (3s) — don't hammer YouTube
        #   2. Pull transcript
        #   3. Keyword pre-filter (instant, free)
        #   4. If passes: Claude analysis (~30s, costs money)
        #   5. Wait video_cooldown_sec (120s) — let YouTube cool down
        # Total per video: ~3 min. Slow, but zero 429s.

        scored_videos = []
        videos_attempted = 0

        for vi, v in enumerate(passed):
            if len(scored_videos) >= self.config.max_videos_per_concept:
                break

            videos_attempted += 1
            logging.info(f"        [{vi + 1}/{len(passed)}] Processing: {v.title}")

            # --- Throttle: wait before transcript pull ---
            if vi > 0:  # don't wait before the very first one
                self._countdown_wait(
                    self.config.transcript_delay_sec,
                    f"        ⏳ Waiting before transcript pull"
                )

            # --- Pull transcript ---
            transcript_data = self.transcripts.get_transcript(v.video_id)
            if not transcript_data:
                logging.info(f"        ✗ No transcript: {v.title}")
                continue

            transcript_text = transcript_data["full_text"]
            logging.info(f"        ✓ Transcript: {transcript_data['char_count']:,} chars")

            # --- Cheap pre-filter: keyword check (instant, free) ---
            if not passes_transcript_filter(transcript_text, concept):
                logging.info(f"        ✗ Pre-filter reject: {v.title}")
                self.stats["videos_prefilter_rejected"] += 1
                # Short wait even on reject — don't burst transcript pulls
                time.sleep(self.config.transcript_delay_sec)
                continue

            logging.info(f"        ✓ Pre-filter passed — sending to Claude")

            # === ONE LLM CALL — gets coverage + teacher profile + content + questions ===
            analysis = self.scorer.analyze_video(transcript_text, concept, siblings)
            self.stats["videos_scored"] += 1

            # Extract coverage
            coverage = analysis.get("coverage", {})

            # Extract covered/missing items
            covered_items = [item["requirement"] for item in coverage.get("items", []) if item.get("covered")]
            missing_items = [item["requirement"] for item in coverage.get("items", []) if not item.get("covered")]

            # Validate: recalculate score from actual items (don't trust LLM's number)
            total_items = len(covered_items) + len(missing_items)
            if total_items > 0:
                coverage_score = len(covered_items) / total_items
            else:
                coverage_score = coverage.get("overall_score", 0)

            llm_score = coverage.get("overall_score", 0)
            if abs(llm_score - coverage_score) > 0.15:
                logging.warning(
                    f"        ⚠ Coverage mismatch: LLM said {llm_score:.0%}, actual {coverage_score:.0%} ({len(covered_items)}/{total_items} items)")

            if coverage_score < self.config.min_coverage_score:
                logging.info(f"        ✗ Low coverage ({coverage_score:.0%}): {v.title}")
                # Still wait cooldown — we just did an LLM call + transcript pull
                self._countdown_wait(
                    self.config.video_cooldown_sec,
                    f"        ⏳ Cooldown after LLM call"
                )
                continue

            # Extract teacher profile
            teacher_profile = analysis.get("teacher_profile", {})

            # Extract content analysis
            content = analysis.get("content_analysis", {})
            topics_covered = content.get("topics_covered", [])

            # Determine start/end from content analysis
            start_sec = 0
            end_sec = v.duration_sec
            if topics_covered:
                primary_topic = next(
                    (t for t in topics_covered if t.get("topic") == concept_id),
                    topics_covered[0] if topics_covered else None
                )
                if primary_topic:
                    start_sec = primary_topic.get("start_sec", 0)
                    end_sec = primary_topic.get("end_sec", v.duration_sec)

            # Build also_covers from content analysis (sibling concepts)
            also_covers = {}
            for tc in topics_covered:
                topic_name = tc.get("topic", "")
                if topic_name != concept_id and topic_name in (siblings or {}):
                    depth = tc.get("depth", "mentioned")
                    also_covers[topic_name] = {
                        "depth": depth,
                        "start_sec": tc.get("start_sec", 0),
                        "end_sec": tc.get("end_sec", 0)
                    }

            # Extract questions
            questions = analysis.get("questions", [])
            self.stats["questions_generated"] += len(questions)

            # Detect style from teacher profile
            style = teacher_profile.get("teaching_style", {})
            detected_style = style.get("primary", "") if isinstance(style, dict) else str(style)
            detected_level = teacher_profile.get("complexity_level", "")

            # Build scored video
            scored = ScoredVideo(
                video_id=v.video_id,
                title=v.title,
                channel_title=v.channel_title,
                channel_id=v.channel_id,
                video_url=f"https://youtu.be/{v.video_id}",
                thumbnail_url=v.thumbnail_url,
                duration_sec=v.duration_sec,
                view_count=v.view_count,
                like_ratio=v.like_ratio,
                subscriber_count=v.subscriber_count,
                published_at=v.published_at,
                concept_id=concept_id,
                coverage_score=coverage_score,
                covered_items=covered_items,
                missing_items=missing_items,
                detected_style=detected_style,
                detected_level=detected_level,
                start_sec=start_sec,
                end_sec=end_sec,
                also_covers=also_covers,
                questions=questions,
            )

            # Store the full teacher_profile and content_analysis for output
            scored._teacher_profile = teacher_profile
            scored._content_analysis = content
            scored._content_warnings = content.get("content_warnings", {})

            scored_videos.append(scored)
            self.stats["videos_kept"] += 1

            logging.info(f"        ✓ KEPT: {v.title}")
            logging.info(
                f"          Coverage: {coverage_score:.0%} | Style: {detected_style} | Level: {detected_level}")
            logging.info(
                f"          Tone: {teacher_profile.get('tone', '?')} | Pacing: {teacher_profile.get('pacing', '?')}")
            logging.info(f"          Questions: {len(questions)} | Also covers: {list(also_covers.keys())}")

            # Flag content warnings
            warnings = content.get("content_warnings", {})
            if warnings.get("has_errors"):
                logging.warning(f"          ⚠ CONTENT ERROR: {warnings.get('error_description', 'unknown')}")
            if warnings.get("has_ads_or_sponsors"):
                logging.info(f"          📢 Has sponsor at {warnings.get('sponsor_timestamp_sec', '?')}s")

            # --- Cooldown between videos ---
            # Only wait if there are more videos to process in this concept
            remaining_to_try = len(passed) - (vi + 1)
            remaining_needed = self.config.max_videos_per_concept - len(scored_videos)
            if remaining_to_try > 0 and remaining_needed > 0:
                self._countdown_wait(
                    self.config.video_cooldown_sec,
                    f"        ⏳ Cooldown ({len(scored_videos)}/{min_needed} kept, "
                    f"{remaining_to_try} candidates left)"
                )

        # Check if we have enough
        if len(scored_videos) < min_needed:
            logging.warning(f"      ⚠ INSUFFICIENT: {len(scored_videos)}/{min_needed} videos for {concept_id}")
            self.stats["concepts_insufficient"].append(concept_id)

        self.stats["concepts_processed"] += 1
        return scored_videos

    def _write_manifest(self, course_id, curriculum_path):
        """Write run summary manifest."""
        manifest = {
            "run_at": datetime.now(timezone.utc).isoformat(),
            "version": self.config.version_tag,
            "course": course_id,
            "curriculum_file": curriculum_path,
            "config": {
                "min_views": self.config.min_views,
                "min_coverage_score": self.config.min_coverage_score,
                "llm_provider": self.config.llm_provider,
                "llm_model": self.config.llm_model,
                "questions_per_video": self.config.questions_per_video,
            },
            "stats": self.stats,
            "youtube_quota_used": self.yt.quota_used,
            "llm_stats": self.scorer.stats,
            "estimated_cost": self._estimate_cost()
        }
        self.writer.write_manifest(manifest)

    def _estimate_cost(self) -> str:
        """Cost estimate using provider-aware pricing."""
        return self.scorer.estimate_cost()

    def _print_summary(self):
        """Print pipeline summary."""
        s = self.stats
        print(f"\n{'=' * 60}")
        print(f"PIPELINE COMPLETE")
        print(f"{'=' * 60}")
        print(f"Concepts processed:    {s['concepts_processed']}")
        print(f"Videos searched:       {s['videos_searched']}")
        print(f"Videos passed filter:  {s['videos_passed_filter']}")
        print(f"Videos pre-filter rej: {s['videos_prefilter_rejected']}")
        print(f"Videos LLM scored:     {s['videos_scored']}")
        print(f"Videos kept:           {s['videos_kept']}")
        print(f"Questions generated:   {s['questions_generated']}")
        print(f"YouTube quota used:    {self.yt.quota_used} units")
        print(f"LLM provider:         {self.config.llm_provider}")
        print(f"LLM model:            {self.config.llm_model}")
        print(f"LLM calls:            {self.scorer.stats['calls']}")
        print(f"LLM tokens:           {self.scorer.stats['tokens']:,}")
        print(f"Estimated LLM cost:   {self._estimate_cost()}")
        print(f"Video cooldown:       {self.config.video_cooldown_sec:.0f}s")
        print(f"Transcript delay:     {self.config.transcript_delay_sec:.0f}s")

        if s["concepts_insufficient"]:
            print(f"\n⚠ NEEDS ATTENTION ({len(s['concepts_insufficient'])} concepts):")
            for c in s["concepts_insufficient"]:
                print(f"  - {c}")

        if s["errors"]:
            print(f"\n❌ ERRORS ({len(s['errors'])}):")
            for e in s["errors"]:
                print(f"  - {e['concept']}: {e['error']}")

        print(f"\nOutput: {self.config.output_dir}/{self.config.version_tag}/")
        print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AiAstro Course Finder Pipeline")
    parser.add_argument("--curriculum", required=True, help="Path to curriculum JSON file")
    parser.add_argument("--concept", help="Process single concept only (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Search + filter only, no LLM calls")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--output", default="./course_finder_output", help="Output directory")
    parser.add_argument("--s3-bucket", help="S3 bucket for upload")
    parser.add_argument("--min-views", type=int, default=50000, help="Minimum video views")
    parser.add_argument("--min-coverage", type=float, default=0.60, help="Minimum coverage score")
    parser.add_argument("--llm-provider", default="anthropic", choices=["anthropic", "openai"],
                        help="LLM provider: anthropic or openai")
    parser.add_argument("--llm-model", default=None,
                        help="Model name (default: auto per provider — claude-sonnet-4-20250514 or gpt-4o)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--cooldown", type=int, default=120,
                        help="Seconds to wait between videos (default: 120). "
                             "Higher = safer from 429s. Lower = faster but riskier.")
    parser.add_argument("--fast", action="store_true",
                        help="Shortcut: set cooldown=5 for testing (WILL get 429'd on full run)")

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

    # Resolve model default based on provider
    if args.llm_model is None:
        args.llm_model = LLMScorer.DEFAULT_MODELS.get(args.llm_provider, "claude-sonnet-4-20250514")

    # Check environment
    if not os.environ.get("YOUTUBE_API_KEY"):
        print("ERROR: Set YOUTUBE_API_KEY environment variable")
        print("  Get one free at: https://console.cloud.google.com/apis/credentials")
        sys.exit(1)

    if not args.dry_run:
        if args.llm_provider == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
            print("ERROR: Set ANTHROPIC_API_KEY environment variable (or use --dry-run)")
            sys.exit(1)
        elif args.llm_provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            print("ERROR: Set OPENAI_API_KEY environment variable (or use --dry-run)")
            sys.exit(1)

    # Build config
    version_tag = ""
    if args.resume:
        # Find latest version folder to resume from
        output_path = Path(args.output)
        if output_path.exists():
            versions = sorted([d.name for d in output_path.iterdir()
                               if d.is_dir() and d.name.startswith("v")], reverse=True)
            if versions:
                version_tag = versions[0]
                print(f"Resuming from: {version_tag}")

    config = Config(
        output_dir=args.output,
        s3_bucket=args.s3_bucket,
        min_views=args.min_views,
        min_coverage_score=args.min_coverage,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        version_tag=version_tag,
        video_cooldown_sec=5.0 if args.fast else float(args.cooldown),
        transcript_delay_sec=1.0 if args.fast else 3.0,
    )

    # Run pipeline
    finder = CourseFinder(config)
    finder.run(
        curriculum_path=args.curriculum,
        single_concept=args.concept,
        dry_run=args.dry_run,
        resume=args.resume,
    )


if __name__ == "__main__":
    main()