"""
POST /course/submit

Score a concept quiz, update student progress.

Flow:
1. Load concept content (has correct answers)
2. Score answers
3. If passed → mark concept completed → return next action
4. If failed → record attempt → check rescue threshold → return feedback

Request body:
{
    "course_id": "general_chemistry",
    "concept_id": "states_of_matter",
    "answers": [{"question_id": 0, "selected": "B"}, ...]
}
"""
import logging
from core.response import success, error, extract_body
from core.content_loader import load_concept, load_curriculum
from core.quiz_scorer import score_answers, build_feedback
from core.progress_tracker import (
    get_student_state, get_completed_concepts, get_attempt_count,
    mark_concept_completed, record_attempt, initialize_attempt_tracking,
    record_session,
)
from core.teacher_picker import get_style
from core.settings import PASS_THRESHOLD, MAX_ATTEMPTS_BEFORE_RESCUE

logger = logging.getLogger(__name__)


def handle_submit(event: dict) -> dict:
    user_id = event["_user_id"]
    body = extract_body(event)

    course_id = body.get("course_id")
    concept_id = body.get("concept_id")
    answers = body.get("answers", [])

    if not course_id or not concept_id:
        return error("Missing required fields: course_id, concept_id")
    if not answers:
        return error("Missing required field: answers")

    # ─── Load state ──────────────────────────────
    state = get_student_state(user_id, course_id)
    if not state or not state.get("warmup_done"):
        return error("Warmup not completed", 403)

    completed = get_completed_concepts(state)
    if concept_id in completed:
        return error("Concept already completed", 409)

    style = get_style(state)

    # ─── Load concept questions ──────────────────
    concept_content = load_concept(course_id, concept_id)
    if not concept_content:
        return error(f"Content not found for concept: {concept_id}", 404)

    questions = concept_content.get("questions", [])
    if not questions:
        return error(f"No questions available for concept: {concept_id}", 404)

    # ─── Score ───────────────────────────────────
    result = score_answers(questions, answers)
    feedback = build_feedback(result, questions)

    # Record session for analytics
    record_session(
        user_id=user_id,
        course_id=course_id,
        concept_id=concept_id,
        session_type="quiz",
        answers=answers,
        score=result["score"],
        passed=result["passed"],
    )

    # ─── Handle result ───────────────────────────
    if result["passed"]:
        # Get attempt count before marking complete
        attempts = get_attempt_count(state, concept_id) + 1

        updated_state = mark_concept_completed(
            user_id, course_id, concept_id,
            score=result["score"],
            attempts=attempts,
        )

        # Determine what's next
        new_completed = get_completed_concepts(updated_state)
        curriculum = load_curriculum(course_id)
        next_concept = curriculum.next_concept(new_completed) if curriculum else None

        return success({
            "status": "passed",
            "score": result["score"],
            "total": result["total"],
            "attempts": attempts,
            "feedback": feedback,
            "next_concept": next_concept,
            "course_complete": next_concept is None,
            "sathi_message": _pass_message(result["score"], result["total"], style),
        })

    else:
        # Failed — record attempt
        initialize_attempt_tracking(user_id, course_id, concept_id)
        updated_state = record_attempt(user_id, course_id, concept_id, result["score"])
        attempts = get_attempt_count(updated_state, concept_id)

        needs_rescue = attempts >= MAX_ATTEMPTS_BEFORE_RESCUE

        response = {
            "status": "failed",
            "score": result["score"],
            "total": result["total"],
            "pass_threshold": PASS_THRESHOLD,
            "attempts": attempts,
            "max_attempts": MAX_ATTEMPTS_BEFORE_RESCUE,
            "feedback": feedback,
            "needs_rescue": needs_rescue,
            "sathi_message": _fail_message(attempts, needs_rescue, style),
        }

        if needs_rescue:
            response["rescue_action"] = {
                "message": "Sathi is ready to help you work through this concept.",
                "endpoint": "/course/rescue",
                "body": {"course_id": course_id, "concept_id": concept_id},
            }

        return success(response)


def _pass_message(score: int, total: int, style: str) -> str:
    if score == total:
        if style == "funny":
            return "Perfect score! You didn't just learn it — you conquered it."
        elif style == "experiential":
            return "Perfect! You've built a solid understanding. This knowledge is yours now."
        return "Perfect score! Excellent work."

    if style == "funny":
        return f"{score}/{total} — passed! Not perfect, but the concepts are in your head. Onward!"
    elif style == "experiential":
        return f"{score}/{total} — well done! The core understanding is there. Let's keep building."
    return f"{score}/{total} — you passed! Great work. Let's move on."


def _fail_message(attempts: int, needs_rescue: bool, style: str) -> str:
    if needs_rescue:
        if style == "funny":
            return "OK, this concept is putting up a fight. Let me step in and we'll crack it together."
        elif style == "experiential":
            return "Some concepts need a different angle. Let's work through this together — I have another way to explain it."
        return "Let's take a different approach. I'll walk through this concept with you step by step."

    remaining = MAX_ATTEMPTS_BEFORE_RESCUE - attempts
    if style == "funny":
        return f"Not quite! Review the videos — the answers are hiding in there. {remaining} more shot(s) before I jump in to help."
    elif style == "experiential":
        return f"Close! Rewatch the tricky parts and try to connect them to what you already know. You've got {remaining} more attempt(s)."
    return f"Not quite. Review the material and try again. {remaining} attempt(s) remaining before additional help."