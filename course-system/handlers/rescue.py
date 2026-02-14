"""
POST /course/rescue

Trigger a rescue session after a student has exhausted quiz attempts.

Phase 0: Builds a rescue context payload and either:
  a) Invokes Sathi Lambda with rescue prompt (if deployed), or
  b) Returns a structured self-study rescue plan (fallback)

Phase 2: Invokes Routing Orchestrator Step Function for
  multi-turn AI-guided rescue with misconception targeting.

Request body:
{
    "course_id": "general_chemistry",
    "concept_id": "states_of_matter"
}
"""
import json
import logging
import boto3
from core.response import success, error, extract_body
from core.content_loader import load_curriculum, load_concept
from core.progress_tracker import (
    get_student_state, get_completed_concepts, get_attempt_count,
    record_session,
)
from core.teacher_picker import get_style
from core.settings import SATHI_LAMBDA_ARN, MAX_ATTEMPTS_BEFORE_RESCUE

logger = logging.getLogger(__name__)

_lambda_client = None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def handle_rescue(event: dict) -> dict:
    user_id = event["_user_id"]
    body = extract_body(event)

    course_id = body.get("course_id")
    concept_id = body.get("concept_id")

    if not course_id or not concept_id:
        return error("Missing required fields: course_id, concept_id")

    # ─── Validate state ──────────────────────────
    state = get_student_state(user_id, course_id)
    if not state or not state.get("warmup_done"):
        return error("Warmup not completed", 403)

    attempts = get_attempt_count(state, concept_id)
    if attempts < MAX_ATTEMPTS_BEFORE_RESCUE:
        return error(
            f"Rescue not available yet. {MAX_ATTEMPTS_BEFORE_RESCUE - attempts} "
            f"attempt(s) remaining.",
            403,
        )

    style = get_style(state)

    # ─── Build rescue context ────────────────────
    curriculum = load_curriculum(course_id)
    concept_data = curriculum.get_concept(concept_id) if curriculum else None
    concept_content = load_concept(course_id, concept_id)

    # Figure out what the student got wrong
    attempted = state.get("concepts_attempted", {}).get(concept_id, {})
    last_score = attempted.get("last_score", 0)

    rescue_context = {
        "user_id": user_id,
        "course_id": course_id,
        "concept_id": concept_id,
        "concept_name": concept_data.get("display_name", concept_id) if concept_data else concept_id,
        "level": concept_data.get("level", "L0_L1") if concept_data else "L0_L1",
        "must_cover": concept_data.get("must_cover", []) if concept_data else [],
        "misconceptions": concept_data.get("misconceptions_to_test", []) if concept_data else [],
        "attempts": attempts,
        "last_score": last_score,
        "teacher_style": style,
        "starting_level": state.get("starting_level"),
    }

    # Record rescue session
    record_session(
        user_id=user_id,
        course_id=course_id,
        concept_id=concept_id,
        session_type="rescue",
        answers=[],
        score=0,
        passed=False,
    )

    # ─── Dispatch rescue ─────────────────────────
    if SATHI_LAMBDA_ARN:
        return _sathi_rescue(rescue_context)

    return _fallback_rescue(rescue_context, concept_content, style)


def _sathi_rescue(context: dict) -> dict:
    """Invoke Sathi Lambda in rescue mode."""
    try:
        payload = {
            "mode": "rescue",
            **context,
        }

        client = _get_lambda_client()
        resp = client.invoke(
            FunctionName=SATHI_LAMBDA_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        resp_payload = json.loads(resp["Payload"].read())

        if resp.get("FunctionError"):
            logger.error(f"Sathi rescue error: {resp_payload}")
            return _error_fallback(context)

        return success({
            "status": "rescue_active",
            "source": "sathi",
            "concept_id": context["concept_id"],
            "response": resp_payload.get("response", ""),
            "rescue_steps": resp_payload.get("rescue_steps", []),
            "follow_up_endpoint": "/course/sathi",
        })

    except Exception as e:
        logger.error(f"Sathi rescue invocation failed: {e}")
        return _error_fallback(context)


def _fallback_rescue(context: dict, concept_content: dict, style: str) -> dict:
    """
    Phase 0 fallback rescue: structured self-study plan.
    No AI — just targeted guidance based on curriculum metadata.
    """
    concept_name = context["concept_name"]
    must_cover = context["must_cover"]
    misconceptions = context["misconceptions"]

    # Build study plan
    study_steps = []

    # Step 1: Identify what to focus on
    study_steps.append({
        "step": 1,
        "title": "Review Key Concepts",
        "description": f"Focus on these core ideas for '{concept_name}':",
        "items": must_cover,
    })

    # Step 2: Common mistakes
    if misconceptions:
        # Convert misconception codes to readable hints
        readable = [_misconception_hint(mc) for mc in misconceptions[:3]]
        study_steps.append({
            "step": 2,
            "title": "Watch Out For Common Mistakes",
            "description": "Students often get tripped up by these:",
            "items": readable,
        })

    # Step 3: Rewatch specific videos
    if concept_content and concept_content.get("videos"):
        video_recs = []
        for v in concept_content["videos"][:3]:
            video_recs.append({
                "title": v.get("title", ""),
                "video_id": v.get("video_id", ""),
                "why": "Rewatch with the key concepts above in mind.",
            })
        study_steps.append({
            "step": 3,
            "title": "Rewatch These Videos",
            "description": "Watch with fresh eyes, focusing on the concepts above:",
            "videos": video_recs,
        })

    # Step 4: Try again
    study_steps.append({
        "step": len(study_steps) + 1,
        "title": "Take the Quiz Again",
        "description": "After reviewing, come back and try the quiz. You've got this.",
    })

    sathi_msg = {
        "common": f"Let's take a different approach to '{concept_name}'. Here's a focused study plan.",
        "experiential": f"Sometimes you just need to see '{concept_name}' from a different angle. Here's a plan to get you there.",
        "funny": f"'{concept_name}' is being stubborn, but we're more stubborn. Here's the battle plan.",
    }

    return success({
        "status": "rescue_active",
        "source": "self_study",
        "concept_id": context["concept_id"],
        "concept_name": concept_name,
        "study_plan": study_steps,
        "sathi_message": sathi_msg.get(style, sathi_msg["common"]),
        "retry_allowed": True,
    })


def _error_fallback(context: dict) -> dict:
    """When Sathi Lambda fails during rescue."""
    return success({
        "status": "rescue_limited",
        "source": "fallback",
        "concept_id": context["concept_id"],
        "sathi_message": (
            "I'm having trouble loading the full rescue session, "
            "but here's what I can tell you: review the videos carefully, "
            "focus on the parts that confused you, and try the quiz again. "
            "You're closer than you think."
        ),
        "retry_allowed": True,
    })


def _misconception_hint(mc_code: str) -> str:
    """
    Convert misconception codes to student-readable hints.
    This is a sampling — in production this could be a separate
    data file or part of curriculum.json.
    """
    hints = {
        "MC_MATTER_IS_ONLY_SOLID": "Matter isn't just solids — liquids and gases are matter too.",
        "MC_GAS_HAS_NO_MASS": "Gases do have mass, even though you can't see them.",
        "MC_COMPOUND_IS_MIXTURE": "Compounds and mixtures are different — compounds are chemically bonded.",
        "MC_ATOM_IS_SOLID_BALL": "Atoms aren't solid balls — they're mostly empty space.",
        "MC_PHOTON_ELECTRON_CONFUSION": "Photons and electrons are different particles with different roles.",
        "MC_PROTON_NEUTRON_SWAP": "Protons are positive, neutrons are neutral — don't swap them.",
        "MC_ISOTOPE_DIFFERENT_ELEMENT": "Isotopes are the same element, just with different neutron counts.",
        "MC_IONIC_COVALENT_CONFUSION": "Ionic = transfer electrons, Covalent = share electrons.",
        "MC_CHANGE_SUBSCRIPTS": "When balancing, change coefficients, never subscripts.",
        "MC_MOLE_IS_MASS": "A mole is a counting number (6.022×10²³), not a unit of mass.",
        "MC_STRONG_MEANS_CONCENTRATED": "Strong vs weak is about dissociation, not concentration.",
        "MC_EXO_ENDO_REVERSED": "Exothermic releases heat (gets hot), endothermic absorbs heat (gets cold).",
        "MC_BREAKING_BONDS_RELEASES_ENERGY": "Breaking bonds requires energy. Forming bonds releases it.",
    }
    return hints.get(mc_code, mc_code.replace("MC_", "").replace("_", " ").lower().capitalize())