"""
llm_prompts.py — Prompt templates for course_finder pipeline.

One LLM call per video extracts everything:
  - Coverage scoring
  - Teacher profile classification
  - Content analysis with timestamps
  - Questions with misconception tags
"""


def build_analysis_prompt(transcript_text: str, concept: dict,
                          sibling_concepts: dict = None,
                          max_transcript_chars: int = 14000) -> str:
    """
    Build the unified analysis prompt.

    One call. Everything we need. Strict JSON output.

    Args:
        transcript_text: Full transcript from youtube-transcript-api
        concept: The curriculum concept dict with must_cover, misconceptions, etc.
        sibling_concepts: Other concepts in the same subtopic (for multi-concept tagging)
        max_transcript_chars: Truncate transcript to fit context window

    Returns:
        The complete prompt string to send to Claude.
    """

    # Truncate transcript if needed
    transcript = transcript_text[:max_transcript_chars]
    if len(transcript_text) > max_transcript_chars:
        transcript += "\n\n[TRANSCRIPT TRUNCATED — full video is longer]"

    # Build must_cover section
    must_cover = concept.get("must_cover", [])
    must_cover_text = "\n".join(f"  {i + 1}. {item}" for i, item in enumerate(must_cover))

    # Build misconceptions section
    misconceptions = concept.get("misconceptions_to_test", [])
    misconceptions_text = "\n".join(f"  - {mc}" for mc in misconceptions)

    # Build sibling concepts section
    siblings_text = ""
    if sibling_concepts:
        siblings_text = "\nSIBLING CONCEPTS (also check if this video covers any of these):\n"
        for sid, sdata in sibling_concepts.items():
            items = sdata.get("must_cover", [])
            siblings_text += f"\n  {sid} — {sdata.get('display_name', sid)}:\n"
            for item in items:
                siblings_text += f"    • {item}\n"

    prompt = f"""You are analyzing a YouTube chemistry video for an adaptive learning platform. 

Your job: Extract EVERYTHING we need in ONE pass — coverage, teacher style, content map, and quiz questions.

═══════════════════════════════════════════
TRANSCRIPT
═══════════════════════════════════════════
{transcript}

═══════════════════════════════════════════
CURRICULUM TARGET
═══════════════════════════════════════════
CONCEPT: {concept.get('display_name', 'Unknown')}
TARGET LEVEL: {concept.get('level', 'L0_L1')}

MUST COVER (these specific items — score each YES/NO):
{must_cover_text}

MISCONCEPTIONS TO TARGET IN QUESTIONS:
{misconceptions_text}
{siblings_text}
═══════════════════════════════════════════
YOUR TASK
═══════════════════════════════════════════

Analyze this transcript and return a JSON object with these four sections:

1. **coverage** — Score each must_cover item. Include the approximate timestamp (in seconds) where each covered item appears, and a short quote proving it.

2. **teacher_profile** — Classify the teacher's style across multiple dimensions. This feeds our student-teacher matching system, so be precise:
   - teaching_style: "conceptual" (explains WHY) | "procedural" (step-by-step HOW) | "example_heavy" (lots of worked problems) | "visual" (diagrams/animations focus) | "narrative" (stories, real-life connections)
   - tone: "warm_encouraging" | "energetic_fast" | "calm_methodical" | "funny_casual" | "serious_academic"
   - pacing: "slow_deliberate" | "moderate" | "fast_dense"
   - complexity_level: "L0_L1" (zero assumed knowledge) | "L1_L2" (assumes basics) | "L2_L3" (assumes solid foundation)
   - explanation_approach: "analogy_heavy" | "definition_first" | "experiment_demo" | "build_up_from_simple" | "compare_contrast"
   - engagement_style: "asks_questions" | "straight_lecture" | "interactive_pause" | "problem_solving"
   - production_quality: "high_animation" | "whiteboard" | "talking_head" | "screencast" | "lab_demo"
   - best_for: object with boolean flags — struggling_students, visual_learners, quick_review, exam_prep, first_time_learner

3. **content_analysis** — Map what the video actually teaches:
   - primary_topic: the concept_id this best matches
   - topics_covered: array of objects with topic name, start_sec, end_sec, depth ("thorough" | "mentioned" | "brief")
   - key_terms_used: important chemistry terms the teacher uses
   - real_world_examples: any real-life examples or analogies used
   - prerequisite_assumed: what knowledge the teacher assumes you already have
   - builds_toward: what future topics this sets up
   - content_warnings: has_errors (bool), error_description, outdated_info (bool), has_ads_or_sponsors (bool), sponsor_timestamp_sec

4. **questions** — Generate exactly 5 multiple-choice questions:
   - Test ONLY what THIS video teaches (not general chemistry knowledge)
   - Each question: 4 choices (A/B/C/D), 1 correct
   - Wrong answers should target specific misconceptions from the list above where possible
   - Include bloom_level: "recall" | "understanding" | "application"
   - Include difficulty: "easy" | "medium" | "hard"
   - Include timestamp_sec: approximate point in video where the answer is taught
   - Include a brief explanation (1-2 sentences)
   - Progress from easy recall → harder application

═══════════════════════════════════════════

Respond with ONLY valid JSON. No markdown fences. No commentary. Just the JSON object.

The JSON must follow this exact structure:
{{
  "coverage": {{
    "overall_score": <float 0.0-1.0>,
    "items": [
      {{
        "requirement": "<must_cover item text>",
        "covered": <bool>,
        "start_sec": <int or null>,
        "end_sec": <int or null>,
        "quote": "<short quote from transcript or null>"
      }}
    ]
  }},
  "teacher_profile": {{
    "teaching_style": {{ "primary": "<value>", "secondary": "<value>" }},
    "tone": "<value>",
    "pacing": "<value>",
    "complexity_level": "<value>",
    "explanation_approach": "<value>",
    "engagement_style": "<value>",
    "production_quality": "<value>",
    "best_for": {{
      "struggling_students": <bool>,
      "visual_learners": <bool>,
      "quick_review": <bool>,
      "exam_prep": <bool>,
      "first_time_learner": <bool>
    }}
  }},
  "content_analysis": {{
    "primary_topic": "<concept_id>",
    "topics_covered": [
      {{ "topic": "<name>", "start_sec": <int>, "end_sec": <int>, "depth": "<value>" }}
    ],
    "key_terms_used": ["<term>", ...],
    "real_world_examples": ["<example>", ...],
    "prerequisite_assumed": ["<topic or 'none'>"],
    "builds_toward": ["<future topic>", ...],
    "content_warnings": {{
      "has_errors": <bool>,
      "error_description": <string or null>,
      "outdated_info": <bool>,
      "has_ads_or_sponsors": <bool>,
      "sponsor_timestamp_sec": <int or null>
    }}
  }},
  "questions": [
    {{
      "id": "q1",
      "question_text": "<question>",
      "choices": {{ "A": "<text>", "B": "<text>", "C": "<text>", "D": "<text>" }},
      "correct_answer": "<A|B|C|D>",
      "difficulty": "<easy|medium|hard>",
      "bloom_level": "<recall|understanding|application>",
      "misconception_tags": {{ "<wrong_letter>": "<MC_CODE>", ... }},
      "explanation": "<1-2 sentence explanation>",
      "timestamp_sec": <int>
    }}
  ]
}}"""

    return prompt


def build_sibling_only_prompt(transcript_text: str, concept: dict,
                              max_transcript_chars: int = 14000) -> str:
    """
    Lightweight prompt for scoring a transcript against a single concept.
    Used when a video was found via a sibling and we just need a quick coverage check.

    Much cheaper — no teacher profiling, no questions.
    """

    transcript = transcript_text[:max_transcript_chars]
    must_cover = concept.get("must_cover", [])
    must_cover_text = "\n".join(f"  {i + 1}. {item}" for i, item in enumerate(must_cover))

    prompt = f"""Score this transcript against these curriculum requirements.
For each item, answer YES or NO and give the approximate timestamp.

TRANSCRIPT:
{transcript}

CONCEPT: {concept.get('display_name', 'Unknown')}
REQUIRED ITEMS:
{must_cover_text}

Respond with ONLY valid JSON:
{{
  "overall_score": <float 0.0-1.0>,
  "items": [
    {{
      "requirement": "<item text>",
      "covered": <bool>,
      "start_sec": <int or null>,
      "end_sec": <int or null>
    }}
  ]
}}"""

    return prompt


# ---------------------------------------------------------------------------
# PROMPT COST ESTIMATES
# ---------------------------------------------------------------------------

COST_ESTIMATES = {
    "full_analysis": {
        "description": "Coverage + teacher profile + content + questions",
        "avg_input_tokens": 4500,
        "avg_output_tokens": 2000,
        "calls_per_concept": 3,
        "note": "One call per video, ~3 videos per concept"
    },
    "sibling_check": {
        "description": "Quick coverage check only",
        "avg_input_tokens": 3000,
        "avg_output_tokens": 500,
        "calls_per_concept": 0,
        "note": "Only when a video's sibling score needs verification"
    },
    "total_estimate": {
        "concepts": 252,
        "videos_per_concept": 3,
        "total_full_calls": 756,
        "total_input_tokens": 3_402_000,
        "total_output_tokens": 1_512_000,
        "sonnet_cost_estimate": "$5.40",
        "haiku_cost_estimate": "$0.90",
        "note": "Sonnet for quality, Haiku if you want cheap"
    }
}