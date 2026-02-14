#!/bin/bash
# ============================================
# Course System — Directory Structure Generator
# Run: chmod +x create_structure.sh && ./create_structure.sh
# ============================================

set -e

ROOT="course-system"

echo "Creating course-system directory structure..."

# ── Handlers (Lambda entry points) ──
mkdir -p $ROOT/handlers

# ── Core business logic ──
mkdir -p $ROOT/core

# ── Rescue layer (LLM) ──
mkdir -p $ROOT/rescue/templates
mkdir -p $ROOT/rescue/persona

# ── Content: Phase 1 ──
for concept in atomic_structure electron_shells valence_electrons why_atoms_bond ionic_bonding; do
  mkdir -p $ROOT/content/phase_1/$concept/questions
done

# ── Content: Phase 2 ──
for concept in covalent_bonding lewis_structures electronegativity periodic_trends; do
  mkdir -p $ROOT/content/phase_2/$concept/questions
done

# ── Content: Phase 3 ──
for concept in naming_compounds polyatomic_ions moles_molar_mass chemical_reactions; do
  mkdir -p $ROOT/content/phase_3/$concept/questions
done

# ── Content: Phase 4 ──
for concept in balancing_equations stoichiometry acids_bases solutions_dissolving gas_laws thermochemistry; do
  mkdir -p $ROOT/content/phase_4/$concept/questions
done

# ── Config ──
mkdir -p $ROOT/config

# ── Build tools ──
mkdir -p $ROOT/tools

# ── Tests ──
mkdir -p $ROOT/tests/fixtures

# ============================================
# HANDLERS
# ============================================

cat > $ROOT/handlers/__init__.py << 'EOF'
EOF

cat > $ROOT/handlers/course_handler.py << 'EOF'
# course_handler.py
# Lambda entry point for: GET /course/next, POST /course/submit, POST /course/rescue
# Routes based on httpMethod + path, delegates to core/

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """API Gateway proxy handler — routes to appropriate function."""
    http_method = event.get("httpMethod", "")
    path = event.get("path", "")

    logger.info(f"COURSE_API method={http_method} path={path}")

    try:
        if path.endswith("/next") and http_method == "GET":
            return handle_next(event)
        elif path.endswith("/submit") and http_method == "POST":
            return handle_submit(event)
        elif path.endswith("/rescue") and http_method == "POST":
            return handle_rescue(event)
        else:
            return response(404, {"error": f"Unknown route: {http_method} {path}"})
    except Exception as e:
        logger.error(f"COURSE_API_ERROR: {str(e)}", exc_info=True)
        return response(500, {"error": "Internal server error"})


def handle_next(event):
    # TODO: implement — reads profile, picks teacher, returns video + quiz
    return response(200, {"message": "GET /course/next — not yet implemented"})


def handle_submit(event):
    # TODO: implement — scores quiz, writes progress, returns next_action
    return response(200, {"message": "POST /course/submit — not yet implemented"})


def handle_rescue(event):
    # TODO: implement — builds handoff prompt, invokes LLM engine
    return response(200, {"message": "POST /course/rescue — not yet implemented"})


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=str),
    }
EOF

cat > $ROOT/handlers/health_check.py << 'EOF'
# health_check.py
# Lambda entry point for: EventBridge weekly trigger
# Pings YouTube oEmbed for each active video, marks inactive on 404

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """EventBridge scheduled handler — checks all active video URLs."""
    logger.info("HEALTH_CHECK starting")
    # TODO: implement — scan video_lessons, HEAD each URL, update active flag
    return {"statusCode": 200, "checked": 0, "broken": 0}
EOF

cat > $ROOT/handlers/learning_profile_deriver.py << 'EOF'
# learning_profile_deriver.py
# Computes STUDENT#PROFILE#LEARNING from D24 + Moon data
# Triggered by batch_soul_analyzer or on_user_registration
# Writes to vedic-charts table: PK=user_id, SK=STUDENT#PROFILE#LEARNING

import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Derives learning profile from vedic chart data."""
    user_id = event.get("user_id")
    logger.info(f"LEARNING_PROFILE_DERIVER user={user_id}")
    # TODO: implement — read D24 + Moon, apply mapping rules, write profile
    return {"statusCode": 200, "user_id": user_id, "derived": False}
EOF

# ============================================
# CORE
# ============================================

cat > $ROOT/core/__init__.py << 'EOF'
EOF

cat > $ROOT/core/teacher_picker.py << 'EOF'
# teacher_picker.py
# Reads STUDENT#PROFILE#LEARNING → scores available teachers → returns best match

# TODO: implement
# - read_learning_profile(student_id) → { pada, processing_style, doorway }
# - score_teachers(profile, available_teachers) → ranked list
# - pick_teacher(student_id, concept, level) → teacher name
EOF

cat > $ROOT/core/quiz_scorer.py << 'EOF'
# quiz_scorer.py
# Scores student answers against correct answers from video_lessons
# Returns: score, passed, misconceptions_triggered

# TODO: implement
# - score_quiz(questions, answers) → { score, total, passed, failed_questions }
# - extract_misconceptions(questions, answers) → [{ q_id, misconception_code }]
EOF

cat > $ROOT/core/progress_tracker.py << 'EOF'
# progress_tracker.py
# Reads/writes student_progress DynamoDB table
# Tracks attempts per concept+level, determines next_action

# TODO: implement
# - get_latest_attempt(student_id, concept, level) → attempt or None
# - get_attempt_count(student_id, concept, level) → int
# - record_attempt(student_id, concept, level, ...) → written item
# - determine_next_action(score, passed, attempt_count) → next_action string
EOF

cat > $ROOT/core/video_fetcher.py << 'EOF'
# video_fetcher.py
# Queries video_lessons DynamoDB table
# Returns video entry matching concept + level + teacher

# TODO: implement
# - get_video(concept, level, teacher) → video item
# - get_available_teachers(concept, level) → [teacher names]
# - get_video_with_questions(concept, level, teacher) → video + questions (sans correct_index)
EOF

# ============================================
# RESCUE
# ============================================

cat > $ROOT/rescue/__init__.py << 'EOF'
EOF

cat > $ROOT/rescue/prompt_builder.py << 'EOF'
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
EOF

cat > $ROOT/rescue/handoff.py << 'EOF'
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
EOF

# ── Rescue Templates ──

cat > $ROOT/rescue/templates/misconception_fix.txt << 'EOF'
You are helping a student who has a specific misconception about {concept}.

MISCONCEPTION: {misconception_description}
The student chose "{student_answer}" because they believe: {misconception_reasoning}
The correct answer is "{correct_answer}" because: {correct_reasoning}

Your job:
1. Don't say "you're wrong." Instead, ask what they think happens and WHY.
2. Gently surface the gap between what they think and what actually happens.
3. Use a concrete analogy matched to their learning style.
4. Give them a quick check question to confirm the fix stuck.

Keep to 3-4 exchanges max. Be {persona_tone}.
EOF

cat > $ROOT/rescue/templates/concept_breakdown.txt << 'EOF'
The student has failed {concept} at {level} twice. They need it broken smaller.

SPECIFIC GAPS: {gap_list}
WHAT THEY DO UNDERSTAND: {understood_list}

Your job:
1. Start from what they DO know (anchor point).
2. Break the gap into 2-3 micro-steps.
3. Teach each micro-step with a concrete example.
4. After each micro-step, ask a quick check question.
5. Once all micro-steps land, connect back to the original concept.

Be {persona_tone}. Match their {processing_style} style.
EOF

cat > $ROOT/rescue/templates/bridge_to_next.txt << 'EOF'
Student mastered {completed_concept} and is moving to {next_concept}.

Your job:
1. Briefly celebrate what they learned (1 sentence).
2. Show how {completed_concept} CONNECTS to {next_concept}.
3. Use an analogy: "{completed_concept} was like learning X. Now {next_concept} is like Y."
4. Set up curiosity for the next video.

Keep it to 2 exchanges max. Be {persona_tone}.
EOF

cat > $ROOT/rescue/templates/synthesis.txt << 'EOF'
Student completed the full learning chain: {concept_chain}

Your job:
1. Help them see the BIG PICTURE — how all these concepts connect.
2. Ask: "If you had to explain {final_concept} to a friend, how would you start?"
3. Fill in any gaps in their explanation.
4. Connect to real life: where does this show up in the world around them?

Be {persona_tone}. This is a celebration moment — they earned it.
EOF

# ── Rescue Personas ──

cat > $ROOT/rescue/persona/sensing_kinesthetic.txt << 'EOF'
You are a patient, hands-on tutor. Think: friendly lab partner who makes things click.

Style rules:
- Lead with CONCRETE examples. "Imagine you're holding a sodium atom in one hand..."
- Use physical analogies: giving/taking, stacking, building, breaking apart.
- Keep sentences short. One idea per sentence.
- After explaining, say: "Now try this..."
- Never say "simply" or "obviously."
- If they're stuck, make it even more concrete, not more abstract.
EOF

cat > $ROOT/rescue/persona/sensing_visual.txt << 'EOF'
You are a clear visual explainer. Think: the person who draws on napkins to explain things.

Style rules:
- Describe what things LOOK LIKE. "Picture the electron cloud as a fuzzy sphere..."
- Reference diagrams, colors, shapes, spatial relationships.
- Use "imagine you can see..." frequently.
- Organize information spatially: "On the left... on the right... in the middle..."
- Keep it grounded in real, observable things.
- If they're stuck, describe it from a different visual angle.
EOF

cat > $ROOT/rescue/persona/thinking_sequential.txt << 'EOF'
You are a precise, logical instructor. Think: the textbook that actually makes sense.

Style rules:
- Number your steps. "Step 1:... Step 2:..."
- State the rule, then show the example.
- Use "because" and "therefore" to connect ideas.
- Be direct and efficient. No fluff.
- If they get it right, move on immediately.
- If they're stuck, identify WHICH step broke and redo just that step.
EOF

cat > $ROOT/rescue/persona/thinking_visual.txt << 'EOF'
You are a structured diagram-first teacher. Think: clean whiteboard with clear labels.

Style rules:
- Start by describing the structure/layout.
- Use tables, comparisons, side-by-side contrasts in words.
- "Compare column A vs column B..."
- Be systematic but visual: organize information in clear categories.
- If they're stuck, reorganize the same information into a different visual structure.
EOF

cat > $ROOT/rescue/persona/intuiting_global.txt << 'EOF'
You are an energetic big-picture guide. Think: Crash Course host who makes you excited.

Style rules:
- Start with WHY this matters. "Here's the wild thing..."
- Connect to the bigger story. "This is the same reason that..."
- Use surprising facts and "did you know" hooks.
- Go big picture FIRST, then zoom into details.
- If they're stuck, zoom OUT, not in. Show the pattern, then the specific case.
- End with a mind-blowing connection.
EOF

cat > $ROOT/rescue/persona/feeling_global.txt << 'EOF'
You are a warm storyteller. Think: favorite teacher who makes everything relatable.

Style rules:
- Start with a story or real-life scenario. "Imagine you're cooking dinner and..."
- Connect to emotions and experiences. "You know that feeling when..."
- Use "we" and "us" — learn together, not lecture.
- Validate confusion: "That's a really common thing to wonder about."
- If they're stuck, tell a different story from a different angle.
- Celebrate small wins genuinely.
EOF

cat > $ROOT/rescue/persona/default.txt << 'EOF'
You are a friendly, clear tutor. Adapt to the student's needs.

Style rules:
- Start with a concrete example.
- Explain the concept, then check understanding.
- If they're stuck, try a different angle.
- Keep it conversational but focused.
- 3-4 exchanges max.
EOF

# ============================================
# CONTENT — Phase-level config files
# ============================================

cat > $ROOT/content/phases.json << 'EOF'
{
  "phase_1": {
    "name": "Ionic Bonding Prerequisite Chain",
    "concepts": ["atomic_structure", "electron_shells", "valence_electrons", "why_atoms_bond", "ionic_bonding"],
    "prerequisite_chain": true,
    "description": "Foundation chain leading to ionic bonding mastery"
  },
  "phase_2": {
    "name": "Covalent Bonding & Periodic Trends",
    "concepts": ["covalent_bonding", "lewis_structures", "electronegativity", "periodic_trends"],
    "prerequisite_chain": true,
    "description": "Extends bonding to covalent, adds periodic table mastery"
  },
  "phase_3": {
    "name": "Chemical Language & Quantities",
    "concepts": ["naming_compounds", "polyatomic_ions", "moles_molar_mass", "chemical_reactions"],
    "prerequisite_chain": true,
    "description": "Naming, counting, and classifying reactions"
  },
  "phase_4": {
    "name": "Quantitative Chemistry",
    "concepts": ["balancing_equations", "stoichiometry", "acids_bases", "solutions_dissolving", "gas_laws", "thermochemistry"],
    "prerequisite_chain": false,
    "description": "Advanced quantitative topics, some can be taken independently"
  }
}
EOF

cat > $ROOT/content/teachers.json << 'EOF'
{
  "tyler_dewitt": {
    "display_name": "Tyler DeWitt",
    "style": "warm",
    "pada_fit": ["sensing", "feeling"],
    "processing_fit": ["kinesthetic", "global"],
    "doorway_fit": ["story", "wonder"],
    "channel_url": "https://www.youtube.com/user/tdewitt451"
  },
  "khan_academy": {
    "display_name": "Khan Academy",
    "style": "methodical",
    "pada_fit": ["thinking"],
    "processing_fit": ["visual", "sequential"],
    "doorway_fit": ["logic"],
    "channel_url": "https://www.khanacademy.org/science/chemistry"
  },
  "organic_chem_tutor": {
    "display_name": "The Organic Chemistry Tutor",
    "style": "practice_heavy",
    "pada_fit": ["thinking", "sensing"],
    "processing_fit": ["sequential"],
    "doorway_fit": ["logic", "challenge"],
    "channel_url": "https://www.youtube.com/@TheOrganicChemistryTutor"
  },
  "professor_dave": {
    "display_name": "Professor Dave Explains",
    "style": "clear",
    "pada_fit": ["thinking", "intuiting"],
    "processing_fit": ["visual", "sequential"],
    "doorway_fit": ["logic"],
    "channel_url": "https://www.youtube.com/@ProfessorDaveExplains"
  },
  "crash_course": {
    "display_name": "Crash Course",
    "style": "energetic",
    "pada_fit": ["intuiting", "feeling"],
    "processing_fit": ["global", "visual"],
    "doorway_fit": ["wonder", "story"],
    "channel_url": "https://www.youtube.com/playlist?list=PL8dPuuaLjXtPHzzYuWy6fYEaX9mQQ8oGr"
  },
  "bozeman_science": {
    "display_name": "Bozeman Science",
    "style": "ap_style",
    "pada_fit": ["thinking"],
    "processing_fit": ["sequential", "visual"],
    "doorway_fit": ["logic"],
    "channel_url": "http://www.bozemanscience.com/chemistry"
  },
  "fuseschool": {
    "display_name": "FuseSchool",
    "style": "animated",
    "pada_fit": ["sensing", "feeling"],
    "processing_fit": ["visual", "global"],
    "doorway_fit": ["story"],
    "channel_url": "https://www.youtube.com/@FuseSchool"
  },
  "amoeba_sisters": {
    "display_name": "Amoeba Sisters",
    "style": "cartoon",
    "pada_fit": ["sensing", "feeling"],
    "processing_fit": ["visual", "global"],
    "doorway_fit": ["story"],
    "channel_url": "https://www.youtube.com/@AmoebaSisters"
  },
  "veritasium": {
    "display_name": "Veritasium",
    "style": "demo",
    "pada_fit": ["intuiting"],
    "processing_fit": ["global"],
    "doorway_fit": ["wonder"],
    "channel_url": "https://www.youtube.com/@veritasium"
  }
}
EOF

cat > $ROOT/content/misconceptions.json << 'EOF'
{
  "_description": "Global misconception registry. Concept-specific misconceptions reference these codes.",
  "MC_PHOTON_ELECTRON_CONFUSION": {
    "label": "Confuses photons with electrons",
    "fix": "Photons = light energy, electrons = matter particles in atoms"
  },
  "MC_ATOM_MOLECULE_CONFUSION": {
    "label": "Confuses atoms with molecules",
    "fix": "Atom = single unit, molecule = two or more atoms bonded"
  },
  "MC_IONIC_COVALENT_CONFUSION": {
    "label": "Confuses ionic and covalent bonding",
    "fix": "Ionic = transfer electrons, covalent = share electrons"
  },
  "MC_SHELL_ORBITAL_CONFUSION": {
    "label": "Confuses shells with orbitals",
    "fix": "Shell = energy level (n=1,2,3), orbital = shape within shell (s,p,d,f)"
  },
  "MC_VALENCE_TOTAL_CONFUSION": {
    "label": "Confuses valence electrons with total electrons",
    "fix": "Valence = outermost shell only, not all electrons"
  },
  "MC_CHARGE_MASS_CONFUSION": {
    "label": "Confuses charge with mass",
    "fix": "Charge = +/- from proton/electron count, mass = protons + neutrons"
  },
  "MC_NOBLE_GAS_UNREACTIVE": {
    "label": "Doesn't understand why noble gases don't bond",
    "fix": "Full outer shell = no need to gain/lose/share electrons"
  },
  "MC_ELECTRON_DESTROY": {
    "label": "Thinks electrons are destroyed in bonding",
    "fix": "Electrons are transferred or shared, never destroyed"
  }
}
EOF

# ── Phase 1 concept placeholders ──

for concept in atomic_structure electron_shells valence_electrons why_atoms_bond ionic_bonding; do

cat > $ROOT/content/phase_1/$concept/videos.json << EOF
[
  {
    "_comment": "Add curated videos here. One entry per teacher per level.",
    "teacher": "",
    "level": "L0_L1",
    "title": "",
    "video_url": "",
    "start_sec": 0,
    "end_sec": 0,
    "style": "",
    "active": true
  }
]
EOF

for level in L0_L1 L1_L2 L2_L3; do
cat > $ROOT/content/phase_1/$concept/questions/$level.json << EOF
{
  "_comment": "Questions per teacher for $concept at $level. Generated by tools/generate_questions.py, then human-reviewed.",
  "tyler_dewitt": [],
  "khan_academy": [],
  "professor_dave": [],
  "crash_course": [],
  "organic_chem_tutor": [],
  "bozeman_science": [],
  "fuseschool": []
}
EOF
done

cat > $ROOT/content/phase_1/$concept/misconceptions.json << EOF
{
  "_comment": "Misconceptions specific to $concept. Reference global codes from content/misconceptions.json or add concept-specific ones here."
}
EOF

done

# ── Phase 2/3/4 concept placeholders ──

for phase_dir in phase_2 phase_3 phase_4; do
  for concept_dir in $ROOT/content/$phase_dir/*/; do
    concept=$(basename $concept_dir)

cat > $concept_dir/videos.json << EOF
[
  {
    "_comment": "Add curated videos for $concept",
    "teacher": "",
    "level": "L0_L1",
    "title": "",
    "video_url": "",
    "start_sec": 0,
    "end_sec": 0,
    "style": "",
    "active": true
  }
]
EOF

cat > $concept_dir/misconceptions.json << EOF
{
  "_comment": "Misconceptions specific to $concept"
}
EOF

  done
done

# ============================================
# CONFIG
# ============================================

cat > $ROOT/config/__init__.py << 'EOF'
EOF

cat > $ROOT/config/settings.py << 'EOF'
# settings.py
# Reads all configuration from environment variables

import os


# DynamoDB tables
VIDEO_LESSONS_TABLE = os.environ.get("VIDEO_LESSONS_TABLE", "course-video-lessons")
STUDENT_PROGRESS_TABLE = os.environ.get("STUDENT_PROGRESS_TABLE", "course-student-progress")
VEDIC_CHARTS_TABLE = os.environ.get("VEDIC_CHARTS_TABLE", "vedic-charts")
LEARNING_PROFILE_SK = "STUDENT#PROFILE#LEARNING"

# Course thresholds
PASS_THRESHOLD = int(os.environ.get("PASS_THRESHOLD", "4"))
MAX_ATTEMPTS_BEFORE_RESCUE = int(os.environ.get("MAX_ATTEMPTS_BEFORE_RESCUE", "2"))
QUESTIONS_PER_QUIZ = 5

# LLM engine
LLM_ENGINE_ENDPOINT = os.environ.get("LLM_ENGINE_ENDPOINT", "")

# Health check
ALERT_WEBHOOK_URL = os.environ.get("ALERT_WEBHOOK_URL", "")

# Environment
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "aiastro")

# Defaults for students without a learning profile
DEFAULT_PROFILE = {
    "pada": "sensing",
    "processing_style": "visual",
    "doorway": "story",
}
DEFAULT_TEACHER = "tyler_dewitt"
EOF

cat > $ROOT/config/teacher_style_map.py << 'EOF'
# teacher_style_map.py
# Maps pada × processing_style → teacher preference ranking
# Used by core/teacher_picker.py

# TODO: implement scoring matrix
# pada + processing_style → list of preferred teachers in order
EOF

cat > $ROOT/config/level_progression.py << 'EOF'
# level_progression.py
# Defines level order and progression rules per concept

LEVELS = ["L0_L1", "L1_L2", "L2_L3"]

def next_level(current_level):
    """Returns the next level, or None if already at max."""
    idx = LEVELS.index(current_level)
    if idx + 1 < len(LEVELS):
        return LEVELS[idx + 1]
    return None

def is_final_level(level):
    return level == LEVELS[-1]
EOF

# ============================================
# TOOLS (build-time, never deployed to Lambda)
# ============================================

cat > $ROOT/tools/generate_questions.py << 'EOF'
#!/usr/bin/env python3
"""
Generate MC questions from YouTube video transcripts using LLM.
Run: python tools/generate_questions.py --concept atomic_structure --level L0_L1

Steps:
1. Reads content/phase_N/concept/videos.json for video URLs
2. Pulls transcript via youtube-transcript-api
3. Sends transcript segment to LLM with question generation prompt
4. Writes draft questions to content/phase_N/concept/questions/level.json
5. Human reviews and edits before committing

Cost: ~$0.10 per video (27 videos = ~$2-3 total)
"""
# TODO: implement
print("generate_questions.py — not yet implemented")
EOF

cat > $ROOT/tools/tag_misconceptions.py << 'EOF'
#!/usr/bin/env python3
"""
Tag each wrong answer choice with a misconception code using LLM.
Run: python tools/tag_misconceptions.py --concept atomic_structure

Reads questions from content/, sends to LLM with misconception tagging prompt,
writes misconception codes back to the question files.
"""
# TODO: implement
print("tag_misconceptions.py — not yet implemented")
EOF

cat > $ROOT/tools/seed_dynamodb.py << 'EOF'
#!/usr/bin/env python3
"""
Load content/ JSON files into DynamoDB video_lessons table.
Run: python tools/seed_dynamodb.py --phase 1
     python tools/seed_dynamodb.py --phase 1 --concept atomic_structure
     python tools/seed_dynamodb.py --all

Reads videos.json + questions/*.json for each concept,
combines into DynamoDB items, writes via batch_write_item.
"""
# TODO: implement
print("seed_dynamodb.py — not yet implemented")
EOF

cat > $ROOT/tools/validate_videos.py << 'EOF'
#!/usr/bin/env python3
"""
Bulk check all YouTube URLs in content/ are still live.
Run: python tools/validate_videos.py

Same logic as health_check.py but runs locally against content/ files,
not DynamoDB. Use before seeding to catch dead videos early.
"""
# TODO: implement
print("validate_videos.py — not yet implemented")
EOF

cat > $ROOT/tools/export_content.py << 'EOF'
#!/usr/bin/env python3
"""
Export DynamoDB video_lessons table back to content/ JSON files.
Run: python tools/export_content.py --phase 1

Useful for backup, version control sync, or migrating between environments.
"""
# TODO: implement
print("export_content.py — not yet implemented")
EOF

chmod +x $ROOT/tools/*.py

# ============================================
# TESTS
# ============================================

cat > $ROOT/tests/__init__.py << 'EOF'
EOF

cat > $ROOT/tests/test_teacher_picker.py << 'EOF'
# TODO: test teacher selection logic
# - sensing + kinesthetic → tyler_dewitt
# - thinking + sequential → khan_academy
# - no profile → default (tyler_dewitt)
EOF

cat > $ROOT/tests/test_quiz_scorer.py << 'EOF'
# TODO: test scoring logic
# - 5/5 → passed, next_level
# - 3/5 → failed, retry
# - 3/5 second time → failed, llm_rescue
# - misconception extraction from wrong answers
EOF

cat > $ROOT/tests/test_progress_tracker.py << 'EOF'
# TODO: test DynamoDB read/write patterns
# - first attempt writes correctly
# - attempt_number increments
# - latest attempt query returns most recent
EOF

cat > $ROOT/tests/test_prompt_builder.py << 'EOF'
# TODO: test rescue prompt assembly
# - persona file loads correctly
# - template placeholders filled
# - full profile data injected
# - misconception details included
EOF

cat > $ROOT/tests/test_course_handler.py << 'EOF'
# TODO: integration test — full flow
# - GET /course/next → returns video + quiz
# - POST /course/submit (pass) → next_level
# - POST /course/submit (fail x2) → llm_rescue
# - POST /course/rescue → returns LLM response
EOF

# ── Test fixtures ──

cat > $ROOT/tests/fixtures/sample_learning_profile.json << 'EOF'
{
  "PK": "test_user_001",
  "SK": "STUDENT#PROFILE#LEARNING",
  "data": {
    "pada": "sensing",
    "processing_style": "kinesthetic",
    "doorway": "story",
    "confidence": 0.85,
    "dasha_context": {
      "md_lord": "JUPITER",
      "ad_lord": "MERCURY",
      "pd_lord": "SATURN",
      "moon_nakshatra": "Rohini"
    },
    "soul_qualities": {
      "patience": { "natal": 7.52, "activated": 7.98 },
      "self_study": { "natal": 6.98, "activated": 7.41 }
    },
    "material_qualities": {
      "analytical_ability": { "natal": 7.76, "activated": 8.24 },
      "communication": { "natal": 8.29, "activated": 8.87 }
    }
  }
}
EOF

cat > $ROOT/tests/fixtures/sample_video_lesson.json << 'EOF'
{
  "id": "vl_001",
  "concept": "atomic_structure",
  "level": "L0_L1",
  "teacher": "tyler_dewitt",
  "style": "warm",
  "video_url": "https://youtu.be/h6LPAwAmnCQ",
  "start_sec": 0,
  "end_sec": 480,
  "questions": [
    {
      "q_id": "AS_L01_TD_Q1",
      "text": "What are the three main parts of an atom?",
      "choices": ["Protons, neutrons, electrons", "Protons, neutrons, photons", "Atoms, molecules, elements", "Nucleus, shell, bond"],
      "correct_index": 0,
      "misconceptions": [null, "MC_PHOTON_ELECTRON_CONFUSION", "MC_ATOM_MOLECULE_CONFUSION", "MC_STRUCTURE_VS_PROPERTY"]
    }
  ],
  "active": true
}
EOF

cat > $ROOT/tests/fixtures/sample_progress.json << 'EOF'
{
  "student_id": "test_user_001",
  "concept_level_attempt": "atomic_structure#L0_L1#001",
  "session_id": "sess_abc123",
  "concept": "atomic_structure",
  "level": "L0_L1",
  "teacher_used": "tyler_dewitt",
  "attempt_number": 1,
  "answers": [
    { "q_id": "AS_L01_TD_Q1", "chosen_index": 0 },
    { "q_id": "AS_L01_TD_Q2", "chosen_index": 2 },
    { "q_id": "AS_L01_TD_Q3", "chosen_index": 1 },
    { "q_id": "AS_L01_TD_Q4", "chosen_index": 0 },
    { "q_id": "AS_L01_TD_Q5", "chosen_index": 3 }
  ],
  "score": 4,
  "total": 5,
  "passed": true,
  "next_action": "next_level",
  "created_at": "2026-02-11T12:00:00Z"
}
EOF

# ============================================
# ROOT FILES
# ============================================

cat > $ROOT/requirements.txt << 'EOF'
boto3>=1.34.0
EOF

cat > $ROOT/buildspec.yml << 'EOF'
# CI/CD: Install deps, zip, upload to S3 artifacts bucket
version: 0.2
phases:
  install:
    runtime-versions:
      python: 3.12
    commands:
      - pip install -r requirements.txt -t ./package
  build:
    commands:
      - cp -r handlers core rescue config content ./package/
      - cd package && zip -r ../lambda_package.zip . -x "tools/*" "tests/*" "*.pyc" "__pycache__/*"
  post_build:
    commands:
      - aws s3 cp lambda_package.zip s3://${ARTIFACTS_BUCKET}/${ARTIFACTS_KEY}
EOF

cat > $ROOT/README.md << 'EOF'
# Course System

Video-based teaching + quiz layer with LLM rescue for failed students.

## Architecture

- **Layer 1 (deterministic)**: Student watches YouTube video → answers MC quiz → pass/fail
- **Layer 2 (LLM rescue)**: Triggered on 2+ failures → scoped prompt using student's learning profile

## Quick Start

```bash
# Install deps
pip install -r requirements.txt

# Seed Phase 1 content to DynamoDB
python tools/seed_dynamodb.py --phase 1

# Test locally
python -c "from handlers.course_handler import lambda_handler; print(lambda_handler({'httpMethod': 'GET', 'path': '/course/next', 'queryStringParameters': {'concept': 'atomic_structure'}}, None))"
```

## Adding Content

```bash
# 1. Add videos to content/phase_N/concept/videos.json
# 2. Generate questions
python tools/generate_questions.py --concept covalent_bonding --level L0_L1
# 3. Review + edit questions
# 4. Seed to DynamoDB
python tools/seed_dynamodb.py --phase 2 --concept covalent_bonding
```

No code changes needed to add new concepts/phases.
EOF

# ============================================
# DONE
# ============================================

echo ""
echo "✅ course-system/ created successfully"
echo ""
echo "Structure:"
find $ROOT -type f | sort | head -80
echo ""
TOTAL_FILES=$(find $ROOT -type f | wc -l)
TOTAL_DIRS=$(find $ROOT -type d | wc -l)
echo "Total: $TOTAL_FILES files in $TOTAL_DIRS directories"
echo ""
echo "Next steps:"
echo "  1. cd course-system/"
echo "  2. Fill in content/phase_1/*/videos.json with curated videos"
echo "  3. I'll implement the handler + core + rescue code"