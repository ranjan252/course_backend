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
