#!/usr/bin/env bash
# Build the container with Cloud Build and deploy it to Cloud Run.
# All secrets come from .env (never committed) and are passed with --set-env-vars.
set -euo pipefail

set -a
source .env
set +a

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env}"
: "${OPENAI_API_KEY:?Set OPENAI_API_KEY in .env}"
: "${TAVILY_API_KEY:?Set TAVILY_API_KEY in .env}"

SERVICE="csci599-a1"
REGION="${GCP_REGION:-us-west1}"
IMAGE="gcr.io/${GCP_PROJECT_ID}/${SERVICE}"

ENV_VARS="OPENAI_API_KEY=${OPENAI_API_KEY},TAVILY_API_KEY=${TAVILY_API_KEY},MODEL_NAME=${MODEL_NAME:-gpt-5}"
if [[ -n "${OPENAI_BASE_URL:-}" ]]; then
  ENV_VARS="${ENV_VARS},OPENAI_BASE_URL=${OPENAI_BASE_URL}"
fi

gcloud builds submit --project "${GCP_PROJECT_ID}" --tag "${IMAGE}"

gcloud run deploy "${SERVICE}" \
  --project "${GCP_PROJECT_ID}" \
  --image "${IMAGE}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --min-instances 0 \
  --max-instances 1 \
  --set-env-vars "${ENV_VARS}"
