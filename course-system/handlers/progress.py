"""
GET /course/progress

Return student's progress through the course DAG.
Powers the frontend progress dashboard / map.

Query params:
  course_id (required)
"""
import logging
from core.response import success, error, extract_query_param
from core.content_loader import load_curriculum
from core.progress_tracker import get_student_state, get_completed_concepts

logger = logging.getLogger(__name__)


def handle_progress(event: dict) -> dict:
    user_id = event["_user_id"]
    course_id = extract_query_param(event, "course_id")

    if not course_id:
        return error("Missing required parameter: course_id")

    # Load state
    state = get_student_state(user_id, course_id)
    if not state:
        return success({
            "status": "not_started",
            "message": "Course not started. Complete warmup first.",
            "redirect": f"/course/warmup?course_id={course_id}",
        })

    # Load curriculum
    curriculum = load_curriculum(course_id)
    if not curriculum:
        return error(f"Curriculum not found: {course_id}", 404)

    completed = get_completed_concepts(state)
    path = curriculum.estimate_path(completed)

    # Build detailed concept-level status
    concept_statuses = {}
    for con_id in curriculum.all_concept_ids():
        if con_id in completed:
            comp_data = state.get("concepts_completed", {}).get(con_id, {})
            concept_statuses[con_id] = {
                "status": "completed",
                "score": comp_data.get("score"),
                "attempts": comp_data.get("attempts"),
            }
        elif curriculum.concept_unlocked(con_id, completed):
            attempt_data = state.get("concepts_attempted", {}).get(con_id, {})
            if attempt_data.get("attempts", 0) > 0:
                concept_statuses[con_id] = {
                    "status": "attempted",
                    "attempts": attempt_data.get("attempts"),
                    "last_score": attempt_data.get("last_score"),
                }
            else:
                concept_statuses[con_id] = {"status": "unlocked"}
        else:
            concept_statuses[con_id] = {"status": "locked"}

    return success({
        "status": "active",
        "course_id": course_id,
        "warmup_score": state.get("warmup_score"),
        "starting_level": state.get("starting_level"),
        "teacher_style": state.get("teacher_style"),
        "current_concept": state.get("current_concept"),
        "path_estimate": path,
        "concepts": concept_statuses,
    })