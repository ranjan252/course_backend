# prompt_builder.py
# Builds scoped LLM system prompt from:
#   - student learning profile (pada, dasha, soul/material qualities)
#   - failed questions + misconception tags
#   - rescue template + persona file
#
# Output: a single system prompt string ready for the LLM engine

# TODO: implement
# - load_persona(pada, processing_style) → persona text
# - load_template(rescue_type) → template text
# - build_rescue_prompt(profile, failed_questions, misconceptions) → system prompt
# - build_synthesis_prompt(profile, completed_concepts) → system prompt
