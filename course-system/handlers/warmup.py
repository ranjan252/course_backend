"""
GET /course/warmup

Serve warmup session questions. First thing a new student sees.
Warmup is real content (3 easy + 2 medium), not a placement test.

If student already completed warmup, returns redirect to /course/next.
"""
import logging
from core.response import success, error, extract_query_param
from core.content_loader import load_warmup
from core.progress_tracker import get_student_state

logger = logging.getLogger(__name__)


def handle_warmup(event: dict) -> dict:
    user_id = event["_user_id"]
    course_id = extract_query_param(event, "course_id")

    if not course_id:
        return error("Missing required parameter: course_id")

    # Check if warmup already done
    state = get_student_state(user_id, course_id)
    if state and state.get("warmup_done"):
        return success({
            "status": "already_completed",
            "message": "Warmup already done. Use /course/next to continue.",
            "starting_level": state.get("starting_level"),
        })

    # Load warmup content
    warmup = load_warmup(course_id)
    if not warmup:
        return error(f"Warmup not found for course: {course_id}", 404)

    # Return questions only (not answers)
    questions = []
    for i, q in enumerate(warmup.get("questions", [])):
        questions.append({
            "question_index": i,
            "question": q.get("question", ""),
            "options": q.get("options", {}),
            "difficulty": q.get("difficulty", "easy"),
            "tests_concept": q.get("tests_concept", ""),
        })

    return success({
        "status": "ready",
        "course_id": course_id,
        "course_name": warmup.get("course_name", course_id),
        "total_questions": len(questions),
        "questions": questions,
        "sathi_message": warmup.get("sathi_greeting",
            "Welcome! Let's see what you already know. "
            "Don't worry about getting everything right — "
            "this helps me understand where to start."),
    })