"""
POST /course/warmup-done

Score warmup answers, derive starting level, create student_state,
calculate path + time estimate. This is the "onboarding complete" moment.

Request body:
{
    "course_id": "general_chemistry",
    "answers": [{"question_id": 0, "selected": "B"}, ...],
    "teacher_style": "experiential"  // optional, from UI preference
}

Response:
{
    "score": 4,
    "total": 5,
    "starting_level": "L1_L2",
    "path_estimate": { total_concepts, remaining, estimated_minutes, topics },
    "feedback": [...],
    "sathi_message": "..."
}
"""
import logging
from core.response import success, error, extract_body
from core.content_loader import load_warmup, load_curriculum
from core.quiz_scorer import score_answers, derive_starting_level, build_feedback
from core.progress_tracker import (
    get_student_state, create_student_state, record_session,
)
from core.settings import DEFAULT_TEACHER_STYLE

logger = logging.getLogger(__name__)

# Sathi messages based on level
SATHI_LEVEL_MESSAGES = {
    "L0_L1": (
        "Great start! I can see where your strengths are. "
        "We'll build a strong foundation together — no rushing. "
        "Every expert started exactly where you are right now."
    ),
    "L1_L2": (
        "Nice — you clearly have some solid knowledge! "
        "We'll build on what you already know and fill in the gaps. "
        "This is going to be a great journey."
    ),
    "L2_L3": (
        "Impressive! You've got a strong base. "
        "We'll focus on the deeper concepts and challenging applications. "
        "Let's take your understanding to the next level."
    ),
}


def handle_warmup_done(event: dict) -> dict:
    user_id = event["_user_id"]
    body = extract_body(event)

    course_id = body.get("course_id")
    answers = body.get("answers", [])
    teacher_style = body.get("teacher_style", DEFAULT_TEACHER_STYLE)

    if not course_id:
        return error("Missing required field: course_id")
    if not answers:
        return error("Missing required field: answers")

    # Prevent double-submission
    state = get_student_state(user_id, course_id)
    if state and state.get("warmup_done"):
        return error("Warmup already completed for this course", 409)

    # Load warmup questions
    warmup = load_warmup(course_id)
    if not warmup:
        return error(f"Warmup not found for course: {course_id}", 404)

    questions = warmup.get("questions", [])

    # Score
    result = score_answers(questions, answers)
    starting_level = derive_starting_level(result["score"], result["total"])
    feedback = build_feedback(result, questions)

    # Create student state
    create_student_state(
        user_id=user_id,
        course_id=course_id,
        warmup_score=result["score"],
        starting_level=starting_level,
        teacher_style=teacher_style,
    )

    # Record session for analytics
    record_session(
        user_id=user_id,
        course_id=course_id,
        concept_id="warmup",
        session_type="warmup",
        answers=answers,
        score=result["score"],
        passed=True,  # warmup always "passes" — it's diagnostic
    )

    # Calculate path estimate
    curriculum = load_curriculum(course_id)
    path_estimate = None
    if curriculum:
        path_estimate = curriculum.estimate_path(completed_concepts=set())

    return success({
        "score": result["score"],
        "total": result["total"],
        "starting_level": starting_level,
        "teacher_style": teacher_style,
        "feedback": feedback,
        "path_estimate": path_estimate,
        "sathi_message": SATHI_LEVEL_MESSAGES.get(starting_level, ""),
    })