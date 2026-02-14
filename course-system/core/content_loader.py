"""
Content loader for S3-stored course content.

S3 layout:
  {course_id}/curriculum.json
  {course_id}/warmup.json
  {course_id}/foundation/{foundation_file}.json
  {course_id}/concepts/{concept_id}.json

Caches curriculum.json and warmup.json in memory across
Lambda warm invocations. Foundation and concept files are
read per-request (they're large and varied).
"""
import json
import logging
import boto3
from botocore.exceptions import ClientError
from config.settings import CONTENT_BUCKET
from core.curriculum import Curriculum

logger = logging.getLogger(__name__)

_s3 = boto3.client("s3")

# ─── In-memory cache (survives Lambda warm starts) ───
_curriculum_cache: dict[str, Curriculum] = {}
_warmup_cache: dict[str, dict] = {}


def _read_s3_json(key: str) -> dict | None:
    """Read and parse a JSON file from S3."""
    try:
        resp = _s3.get_object(Bucket=CONTENT_BUCKET, Key=key)
        return json.loads(resp["Body"].read().decode("utf-8"))
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code == "NoSuchKey":
            logger.warning(f"S3 key not found: {key}")
            return None
        logger.error(f"S3 error reading {key}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error reading S3 key {key}: {e}")
        raise


# ─── Curriculum ──────────────────────────────────

def load_curriculum(course_id: str) -> Curriculum | None:
    """Load curriculum.json for a course (cached)."""
    if course_id not in _curriculum_cache:
        data = _read_s3_json(f"{course_id}/curriculum.json")
        if data is None:
            return None
        _curriculum_cache[course_id] = Curriculum(data)
    return _curriculum_cache[course_id]


def invalidate_curriculum_cache(course_id: str = None):
    """Clear curriculum cache (for testing or hot-reload)."""
    if course_id:
        _curriculum_cache.pop(course_id, None)
    else:
        _curriculum_cache.clear()


# ─── Warmup ──────────────────────────────────────

def load_warmup(course_id: str) -> dict | None:
    """Load warmup.json for a course (cached)."""
    if course_id not in _warmup_cache:
        data = _read_s3_json(f"{course_id}/warmup.json")
        if data is None:
            return None
        _warmup_cache[course_id] = data
    return _warmup_cache[course_id]


# ─── Foundation ──────────────────────────────────

def load_foundation(course_id: str, foundation_file: str) -> dict | None:
    """
    Load a foundation content file.
    foundation_file is the filename without extension (e.g., "atoms_exist").
    """
    return _read_s3_json(f"{course_id}/foundation/{foundation_file}.json")


# ─── Concept Content ─────────────────────────────

def load_concept(course_id: str, concept_id: str) -> dict | None:
    """
    Load concept content (videos + questions).
    This is course_finder output — videos, questions, metadata.
    """
    return _read_s3_json(f"{course_id}/concepts/{concept_id}.json")