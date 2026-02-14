#!/bin/bash
# bootstrap.sh
# Run ONCE before first `terraform apply` for course-system.
# Creates a seed Lambda zip so Terraform can create the Lambda resource.
# The real code gets deployed on first pipeline run (git push to main).
#
# Usage:
#   chmod +x bootstrap.sh
#   ./bootstrap.sh

set -euo pipefail

S3_BUCKET="aiastro-lambda-artifacts"
S3_KEY="course-system/lambda_package.zip"

echo "============================================="
echo "  Course System Bootstrap"
echo "============================================="
echo ""

# Check if zip already exists
if aws s3 ls "s3://${S3_BUCKET}/${S3_KEY}" > /dev/null 2>&1; then
    echo "[OK] Lambda artifact already exists at s3://${S3_BUCKET}/${S3_KEY}"
    echo "     Skipping bootstrap. Run terraform apply."
    exit 0
fi

echo "[1/3] Creating seed Lambda package..."

TMPDIR=$(mktemp -d)
mkdir -p "${TMPDIR}/handlers"
mkdir -p "${TMPDIR}/core"

cat > "${TMPDIR}/handlers/__init__.py" << 'PYEOF'
PYEOF

cat > "${TMPDIR}/handlers/course_handler.py" << 'PYEOF'
import json

def lambda_handler(event, context):
    return {
        "statusCode": 503,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "error": "Course system not yet deployed. Waiting for first pipeline build."
        })
    }
PYEOF

cat > "${TMPDIR}/handlers/health_check.py" << 'PYEOF'
def lambda_handler(event, context):
    return {"statusCode": 200, "message": "health_check seed — not yet deployed"}
PYEOF

cat > "${TMPDIR}/core/__init__.py" << 'PYEOF'
PYEOF

cat > "${TMPDIR}/core/settings.py" << 'PYEOF'
# Seed file — replaced on first pipeline deploy
PYEOF

echo "[2/3] Creating zip..."
cd "${TMPDIR}" && zip -r seed_package.zip . > /dev/null && cd -

echo "[3/3] Uploading to s3://${S3_BUCKET}/${S3_KEY}..."
aws s3 cp "${TMPDIR}/seed_package.zip" "s3://${S3_BUCKET}/${S3_KEY}"

rm -rf "${TMPDIR}"

echo ""
echo "============================================="
echo "  [OK] Bootstrap complete!"
echo "============================================="
echo ""
echo "Next steps:"
echo "  1. terraform apply    (creates Lambdas, S3 content bucket, pipeline)"
echo "  2. git push to main   (triggers pipeline → deploys real code + content)"
echo ""