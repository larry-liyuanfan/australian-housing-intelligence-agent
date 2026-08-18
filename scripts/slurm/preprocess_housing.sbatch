#!/usr/bin/env bash
#SBATCH --job-name=housing-preprocess
#SBATCH --partition=physical
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out

set -euo pipefail

: "${PROJECT_DIR:?Set PROJECT_DIR to the GPFS checkout}"
: "${PRIVATE_INPUT:?Set PRIVATE_INPUT to a protected JSONL path}"
: "${OUTPUT_JSONL:?Set OUTPUT_JSONL under protected project storage}"
: "${HOUSING_HASH_SALT:?Export a job-specific salt; never commit it}"

cd "$PROJECT_DIR"
mkdir -p logs "$(dirname "$OUTPUT_JSONL")"

if [[ -n "${APPTAINER_IMAGE:-}" ]]; then
  apptainer exec --cleanenv \
    --env HOUSING_HASH_SALT="$HOUSING_HASH_SALT" \
    "$APPTAINER_IMAGE" \
    python -m housing_agent.preprocess "$PRIVATE_INPUT" "$OUTPUT_JSONL"
else
  python -m housing_agent.preprocess "$PRIVATE_INPUT" "$OUTPUT_JSONL"
fi

sha256sum "$OUTPUT_JSONL" > "${OUTPUT_JSONL}.sha256"
