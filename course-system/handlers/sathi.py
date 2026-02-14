"""
POST /course/sathi

Sathi chat interface. Proxies to the Sathi Lambda when available,
falls back to lightweight concept-specific help otherwise.

Phase 0: Lightweight — returns pre-built encouragement + concept hints.
Phase 1 (Week 2): Proxies to ROI team's Sathi Lambda with context.
Phase 2: Full Sathi with long-term memory + astro context.

Request body:
{
    "course_id": "general_chemistry",
    "concept_id": "states_of_matter",      // optional — current concept context
    "message": "I don't understand why gases have mass"
}
"""
import json
import logging
import boto3
from core.response import success, error, extract_body
from core.content_loader import load_curriculum
from core.progress_tracker import get_student_state, get_completed_concepts
from core.teacher_picker import get_style
from core.settings import SATHI_LAMBDA_ARN

logger = logging.getLogger(__name__)

_lambda_client = None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def handle_sathi(event: dict) -> dict:
    user_id = event["_user_id"]
    body = extract_body(event)

    course_id = body.get("course_id")
    concept_id = body.get("concept_id")
    message = body.get("message", "").strip()

    if not course_id:
        return error("Missing required field: course_id")
    if not message:
        return error("Missing required field: message")

    # Load state
    state = get_student_state(user_id, course_id)
    if not state or not state.get("warmup_done"):
        return error("Warmup not completed", 403)

    style = get_style(state)

    # ─── If Sathi Lambda is deployed, proxy to it ─────
    if SATHI_LAMBDA_ARN:
        return _proxy_to_sathi(user_id, course_id, concept_id, message, state)

    # ─── Phase 0 fallback: lightweight responses ──────
    return _lightweight_response(course_id, concept_id, message, style, state)


def _proxy_to_sathi(user_id: str, course_id: str, concept_id: str,
                     message: str, state: dict) -> dict:
    """
    Invoke the ROI team's Sathi Lambda with full student context.
    Sathi Lambda handles the AI conversation, persona, astro context.
    """
    try:
        payload = {
            "user_id": user_id,
            "course_id": course_id,
            "concept_id": concept_id,
            "message": message,
            "context": {
                "starting_level": state.get("starting_level"),
                "teacher_style": state.get("teacher_style"),
                "warmup_score": state.get("warmup_score"),
                "current_concept": state.get("current_concept"),
                "concepts_completed": list(get_completed_concepts(state)),
            },
        }

        client = _get_lambda_client()
        resp = client.invoke(
            FunctionName=SATHI_LAMBDA_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        resp_payload = json.loads(resp["Payload"].read())

        if resp.get("FunctionError"):
            logger.error(f"Sathi Lambda error: {resp_payload}")
            return _fallback_response()

        # Sathi Lambda returns { "response": "...", "suggestions": [...] }
        return success({
            "source": "sathi",
            "response": resp_payload.get("response", ""),
            "suggestions": resp_payload.get("suggestions", []),
        })

    except Exception as e:
        logger.error(f"Failed to invoke Sathi Lambda: {e}")
        return _fallback_response()


def _lightweight_response(course_id: str, concept_id: str, message: str,
                           style: str, state: dict) -> dict:
    """
    Phase 0 lightweight Sathi. No LLM — returns context-aware
    encouragement and concept-specific hints.
    """
    # Get concept info if available
    concept_hint = ""
    if concept_id:
        curriculum = load_curriculum(course_id)
        if curriculum:
            concept = curriculum.get_concept(concept_id)
            if concept:
                concept_hint = (
                    f"You're working on '{concept.get('display_name', concept_id)}'. "
                    f"Key things to understand: {', '.join(concept.get('must_cover', [])[:3])}."
                )

    # Detect question type and give appropriate response
    msg_lower = message.lower()
    if any(w in msg_lower for w in ["don't understand", "confused", "lost", "help"]):
        response = _confused_response(concept_hint, style)
    elif any(w in msg_lower for w in ["too hard", "difficult", "can't do"]):
        response = _encouragement_response(concept_hint, style)
    elif any(w in msg_lower for w in ["skip", "next", "move on"]):
        response = _pacing_response(style)
    else:
        response = _general_response(concept_hint, style)

    return success({
        "source": "lightweight",
        "response": response,
        "concept_hint": concept_hint,
        "suggestions": [
            "Rewatch the videos",
            "Try the quiz again",
            "Tell me what specifically confuses you",
        ],
    })


def _fallback_response() -> dict:
    """When Sathi Lambda is down, return a graceful fallback."""
    return success({
        "source": "fallback",
        "response": (
            "I'm having a moment — my full brain isn't available right now. "
            "But you can rewatch the videos or try the quiz again. "
            "I'll be back to full capacity soon!"
        ),
        "suggestions": ["Rewatch videos", "Try quiz again"],
    })


# ─── Response templates by style ─────────────────

def _confused_response(concept_hint: str, style: str) -> str:
    base = {
        "common": "That's completely normal — this is new territory. Let's break it down.",
        "experiential": "I get it. Sometimes concepts need to be approached from a different angle. Think about it like this.",
        "funny": "Welcome to the club! Every chemist has been confused by this. The trick is to keep poking at it.",
    }
    resp = base.get(style, base["common"])
    if concept_hint:
        resp += f" {concept_hint}"
    resp += " Try rewatching the video that covers the part you're stuck on."
    return resp


def _encouragement_response(concept_hint: str, style: str) -> str:
    base = {
        "common": "You're further along than you think. The fact that you're wrestling with this means you're learning.",
        "experiential": "Struggling is the feeling of your brain building new connections. This is literally how learning works.",
        "funny": "If chemistry were easy, everyone would do it. You're doing the hard thing — respect.",
    }
    resp = base.get(style, base["common"])
    if concept_hint:
        resp += f" {concept_hint}"
    return resp


def _pacing_response(style: str) -> str:
    return {
        "common": "Each concept builds on the last, so it's best to make sure you've got this one solid before moving on. Review the parts that tripped you up.",
        "experiential": "I know the urge to move forward is real, but this concept is a building block. Spending a bit more time here will save you time later.",
        "funny": "I admire the ambition! But skipping ahead in chemistry is like skipping leg day — it catches up with you. Let's nail this first.",
    }.get(style, "Let's make sure you've got this concept solid before moving on.")


def _general_response(concept_hint: str, style: str) -> str:
    base = {
        "common": "I'm here to help! Right now I can point you to the right videos and encourage you through the quiz.",
        "experiential": "Good question! I'm still learning to have full conversations, but I can help point you in the right direction.",
        "funny": "I'm working on becoming a full conversationalist, but right now I'm more of a cheerleader with chemistry knowledge. Ask me something about the material!",
    }
    resp = base.get(style, base["common"])
    if concept_hint:
        resp += f" {concept_hint}"
    return resp