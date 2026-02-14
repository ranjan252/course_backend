"""
GET /course/next

The heart of the learning system. Determines what to show the student next.

Flow:
1. Load student state + curriculum
2. If concept specified → validate prerequisites → serve it
3. If no concept → walk DAG → find next unlocked concept
4. If entering new subtopic → serve foundation first
5. Load concept content → apply teacher style → return

Query params:
  course_id (required)
  concept (optional — override auto-progression)

Response types:
  - "foundation": student needs foundation content before this subtopic
  - "concept": student is ready for concept videos + quiz
  - "course_complete": all concepts done
  - "warmup_required": student hasn't done warmup yet
"""
import logging
from core.response import success, error, not_found, extract_query_param
from core.content_loader import load_curriculum, load_foundation, load_concept
from core.progress_tracker import (
    get_student_state, get_completed_concepts, set_current_concept,
)
from core.teacher_picker import get_style, apply_style

logger = logging.getLogger(__name__)


def handle_next(event: dict) -> dict:
    user_id = event["_user_id"]
    course_id = extract_query_param(event, "course_id")
    requested_concept = extract_query_param(event, "concept")

    if not course_id:
        return error("Missing required parameter: course_id")

    # ─── Load state ──────────────────────────────
    state = get_student_state(user_id, course_id)
    if not state or not state.get("warmup_done"):
        return success({
            "content_type": "warmup_required",
            "message": "Please complete the warmup first.",
            "redirect": f"/course/warmup?course_id={course_id}",
        })

    # ─── Load curriculum ─────────────────────────
    curriculum = load_curriculum(course_id)
    if not curriculum:
        return not_found(f"Curriculum not found for course: {course_id}")

    completed = get_completed_concepts(state)
    style = get_style(state)
    starting_level = state.get("starting_level")

    # ─── Resolve concept ─────────────────────────
    if requested_concept:
        concept_id = requested_concept
        # Validate it exists
        if not curriculum.get_concept(concept_id):
            return not_found(f"Concept not found: {concept_id}")
        # Check prerequisites
        if not curriculum.concept_unlocked(concept_id, completed):
            return error(
                f"Prerequisites not met for: {concept_id}",
                403,
                details={"concept_id": concept_id},
            )
        # Already completed?
        if concept_id in completed:
            return success({
                "content_type": "already_completed",
                "concept_id": concept_id,
                "message": "You've already completed this concept.",
            })
    else:
        concept_id = curriculum.next_concept(completed, starting_level)
        if not concept_id:
            return success({
                "content_type": "course_complete",
                "message": "Congratulations! You've completed the entire course.",
                "stats": curriculum.estimate_path(completed),
            })

    # ─── Check foundation needed ─────────────────
    if curriculum.is_first_concept_in_subtopic(concept_id):
        subtopic_id = curriculum.get_subtopic_id_for_concept(concept_id)
        if subtopic_id:
            # Check if we've already served foundation for this subtopic
            # by looking at whether any concept in this subtopic is completed
            location = curriculum.get_concept_location(concept_id)
            if location:
                topic_id, sub_id = location
                sub = curriculum.get_subtopic(topic_id, sub_id)
                sub_concepts = set(sub.get("concepts", {}).keys()) if sub else set()
                any_started = bool(sub_concepts & completed)

                if not any_started:
                    # Try to load foundation content
                    foundation = load_foundation(course_id, subtopic_id)
                    if foundation:
                        styled = apply_style(foundation, style)
                        return success({
                            "content_type": "foundation",
                            "course_id": course_id,
                            "subtopic_id": subtopic_id,
                            "next_concept": concept_id,
                            "foundation": styled,
                            "sathi_message": _foundation_sathi_message(
                                foundation.get("foundation_title", ""),
                                style,
                            ),
                        })

    # ─── Serve concept content ───────────────────
    concept_data = curriculum.get_concept(concept_id)
    concept_content = load_concept(course_id, concept_id)

    # Track current concept
    set_current_concept(user_id, course_id, concept_id)

    # Build response
    response = {
        "content_type": "concept",
        "course_id": course_id,
        "concept_id": concept_id,
        "display_name": concept_data.get("display_name", concept_id),
        "level": concept_data.get("level", "L0_L1"),
    }

    if concept_content:
        # concept content from course_finder: videos + questions
        response["videos"] = concept_content.get("videos", [])
        response["questions"] = _strip_answers(concept_content.get("questions", []))
        response["total_questions"] = len(concept_content.get("questions", []))
    else:
        # No content yet (course_finder hasn't run for this concept)
        response["videos"] = []
        response["questions"] = []
        response["total_questions"] = 0
        response["notice"] = "Content for this concept is being prepared."

    response["sathi_message"] = _concept_sathi_message(
        concept_data.get("display_name", concept_id), style
    )

    return success(response)


def _strip_answers(questions: list) -> list:
    """Remove correct_answer and explanation from questions sent to frontend."""
    stripped = []
    for i, q in enumerate(questions):
        stripped.append({
            "question_index": i,
            "question": q.get("question", ""),
            "options": q.get("options", {}),
            "tests_concept": q.get("tests_concept", ""),
        })
    return stripped


def _foundation_sathi_message(title: str, style: str) -> str:
    """Sathi encouragement before foundation content."""
    if style == "funny":
        return f"Before we dive in, let me set the scene for '{title}'. Think of this as the trailer before the movie."
    elif style == "experiential":
        return f"Let's build the foundation for '{title}'. This connects to things you already experience every day."
    return f"Let's start with the foundation: '{title}'. This will give you the context to understand what comes next."


def _concept_sathi_message(display_name: str, style: str) -> str:
    """Sathi encouragement for concept content."""
    if style == "funny":
        return f"Time for '{display_name}'! Watch the videos, take notes if that's your thing, then we'll see what stuck."
    elif style == "experiential":
        return f"Here's '{display_name}'. Pay attention to how this connects to real-world applications — that's where it clicks."
    return f"Here's '{display_name}'. Watch the videos carefully, then take the quiz when you're ready."