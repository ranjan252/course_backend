"""
Quiz scoring logic.

Handles both warmup scoring (derives starting level)
and concept quiz scoring (pass/fail against threshold).
"""
import logging
from config.settings import PASS_THRESHOLD, LEVELS

logger = logging.getLogger(__name__)


def score_answers(questions: list, answers: list) -> dict:
    """
    Score student answers against question set.

    Args:
        questions: list of question dicts with "correct_answer" field
        answers: list of dicts with "question_id" (index) and "selected" (A/B/C/D)

    Returns:
        {
            "score": int,
            "total": int,
            "passed": bool,
            "details": [{ question_index, correct, selected, is_correct }]
        }
    """
    # Build answer lookup: question index → selected option
    answer_map = {}
    for ans in answers:
        idx = ans.get("question_id", ans.get("question_index"))
        if idx is not None:
            answer_map[int(idx)] = ans.get("selected", "")

    score = 0
    details = []

    for i, q in enumerate(questions):
        correct = q.get("correct_answer", "")
        selected = answer_map.get(i, "")
        is_correct = selected.upper() == correct.upper() if selected else False

        if is_correct:
            score += 1

        details.append({
            "question_index": i,
            "correct": correct,
            "selected": selected,
            "is_correct": is_correct,
        })

    total = len(questions)
    passed = score >= PASS_THRESHOLD if total >= PASS_THRESHOLD else score == total

    return {
        "score": score,
        "total": total,
        "passed": passed,
        "details": details,
    }


def derive_starting_level(warmup_score: int, warmup_total: int) -> str:
    """
    Derive starting level from warmup performance.

    Warmup: 3 easy (L0_L1) + 2 medium (L1_L2) = 5 questions

    Scoring logic:
      - 0-2 correct → L0_L1 (start from basics)
      - 3-4 correct → L1_L2 (skip fundamentals, start intermediate)
      - 5   correct → L2_L3 (advanced start)

    This determines starting POSITION, not ceiling.
    All content is accessible regardless of level.
    """
    if warmup_total == 0:
        return LEVELS[0]

    ratio = warmup_score / warmup_total

    if ratio < 0.6:
        return "L0_L1"
    elif ratio < 1.0:
        return "L1_L2"
    else:
        return "L2_L3"


def build_feedback(result: dict, questions: list) -> list:
    """
    Build per-question feedback for the student.

    Returns list of feedback dicts:
    [{ question_index, is_correct, explanation, tests_concept }]
    """
    feedback = []
    for detail in result.get("details", []):
        idx = detail["question_index"]
        q = questions[idx] if idx < len(questions) else {}

        fb = {
            "question_index": idx,
            "is_correct": detail["is_correct"],
        }

        # Only show explanation for wrong answers (learning opportunity)
        if not detail["is_correct"]:
            fb["explanation"] = q.get("explanation", "")
            fb["correct_answer"] = detail["correct"]

        fb["tests_concept"] = q.get("tests_concept", "")
        feedback.append(fb)

    return feedback