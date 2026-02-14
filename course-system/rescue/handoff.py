# handoff.py
# Constructs the handoff packet and invokes the existing LLM multiturn engine
#
# Handoff packet includes:
#   - student_id, concept, level, attempts
#   - failed_questions with student_picked + correct + misconception
#   - pada, processing_style, doorway
#   - scoped system_prompt (built by prompt_builder)
#   - dasha context + relevant soul/material quality scores

# TODO: implement
# - build_handoff_packet(student_id, concept, level, ...) → dict
# - invoke_llm_engine(handoff_packet) → LLM response (proxied)
