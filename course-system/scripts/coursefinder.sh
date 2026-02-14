#!/bin/bash
# coursefinder.sh — Launch script for course finder pipeline
# Supports both Anthropic (Claude) and OpenAI (GPT) providers.
#
# Usage:
#   ./coursefinder.sh                                # dry run (default)
#   ./coursefinder.sh --full                         # full run with Claude
#   ./coursefinder.sh --full --gpt                   # full run with GPT-4o
#   ./coursefinder.sh --full --gpt --model gpt-4o-mini  # specific model
#   ./coursefinder.sh --concept isotopes --full      # specific concept
#   ./coursefinder.sh --resume                       # resume interrupted run

set -euo pipefail

# ——— Resolve script directory ———————————————————————————
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ——— API Keys ———————————————————————————————————————————
export YOUTUBE_API_KEY="AIzaSyCMCDBucRuvA3DuaxE1dM1kcoFOypNciqE"

# ——— Parse arguments ———————————————————————————————————
CURRICULUM="../curriculum/general_chemistry_curriculum.json"
CONCEPT=""
MODE="--dry-run"
EXTRA_ARGS="-v"
PROVIDER="anthropic"
MODEL=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --full)
      MODE=""
      shift
      ;;
    --concept)
      CONCEPT="--concept $2"
      shift 2
      ;;
    --concept=*)
      CONCEPT="--concept ${1#*=}"
      shift
      ;;
    --resume)
      EXTRA_ARGS="$EXTRA_ARGS --resume"
      shift
      ;;
    --oc|--organic)
      CURRICULUM="../curriculum/organic_chemistry_curriculum.json"
      shift
      ;;
    --gpt|--openai)
      PROVIDER="openai"
      shift
      ;;
    --claude|--anthropic)
      PROVIDER="anthropic"
      shift
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --model=*)
      MODEL="${1#*=}"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

# ——— Fetch API keys based on provider ————————————————————
if [ "$PROVIDER" = "openai" ]; then
  if [ -z "${OPENAI_API_KEY:-}" ]; then
    echo "Fetching OpenAI key from SSM..."
    export OPENAI_API_KEY=$(aws ssm get-parameter \
      --name "/dev/llm/openai" \
      --with-decryption \
      --query "Parameter.Value" \
      --output text 2>/dev/null || echo "")
    if [ -z "$OPENAI_API_KEY" ]; then
      echo "ERROR: Failed to fetch OpenAI key. Set OPENAI_API_KEY or store in SSM at /dev/llm/openai"
      exit 1
    fi
  fi
  echo "✓ OpenAI key loaded"
else
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "Fetching Anthropic key from SSM..."
    export ANTHROPIC_API_KEY=$(aws ssm get-parameter \
      --name "/dev/llm/anthropic" \
      --with-decryption \
      --query "Parameter.Value" \
      --output text 2>/dev/null || echo "")
    if [ -z "$ANTHROPIC_API_KEY" ]; then
      echo "ERROR: Failed to fetch Anthropic key. Set ANTHROPIC_API_KEY or store in SSM at /dev/llm/anthropic"
      exit 1
    fi
  fi
  echo "✓ Anthropic key loaded"
fi

# ——— Check dependencies ——————————————————————————————————
python3 -c "import googleapiclient; import youtube_transcript_api; import httpx" 2>/dev/null || {
  echo "Installing dependencies..."
  pip install google-api-python-client youtube-transcript-api httpx boto3
}

# Default: dry run on states_of_matter if no args
if [ -z "$CONCEPT" ] && [ "$MODE" = "--dry-run" ]; then
  CONCEPT="--concept states_of_matter"
fi

# Build model arg
MODEL_ARG=""
if [ -n "$MODEL" ]; then
  MODEL_ARG="--llm-model $MODEL"
fi

# ——— Run ———————————————————————————————————————————————
echo ""
echo "═══════════════════════════════════════════════"
echo "  COURSE FINDER PIPELINE"
echo "  Curriculum: $CURRICULUM"
echo "  Mode:       ${MODE:-FULL RUN}"
echo "  Concept:    ${CONCEPT:-ALL}"
echo "  Provider:   $PROVIDER ${MODEL:+($MODEL)}"
echo "  Output:     $SCRIPT_DIR/course_finder_output"
echo "═══════════════════════════════════════════════"
echo ""

python3 course_finder.py \
  --curriculum "$CURRICULUM" \
  $CONCEPT \
  $MODE \
  --llm-provider "$PROVIDER" \
  $MODEL_ARG \
  $EXTRA_ARGS

echo ""
echo "Done. Output: course_finder_output/"