#!/usr/bin/env bash
set -euo pipefail

FAMILY=""
JOBS=""
RUN_SMOKE_JOBS=false
PROJECT_ID="${PROJECT_ID:-fabled-archive-494108-k5}"
REGION="${REGION:-us-central1}"
TARGET_REPO="${TARGET_REPO:-/Users/cliff/workspace/agent/Synapse-Network}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --family)
      FAMILY="${2:-}"
      shift 2
      ;;
    --jobs)
      JOBS="${2:-}"
      shift 2
      ;;
    --run-smoke-jobs)
      RUN_SMOKE_JOBS=true
      shift
      ;;
    --project)
      PROJECT_ID="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    --target-repo)
      TARGET_REPO="${2:-}"
      shift 2
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

[[ -n "$FAMILY" ]] || { echo "missing --family" >&2; exit 2; }
[[ -n "$JOBS" ]] || { echo "missing --jobs" >&2; exit 2; }
[[ -d "$TARGET_REPO" ]] || { echo "target repo not found: $TARGET_REPO" >&2; exit 2; }

case "$FAMILY" in
  gateway) SERVICE="gateway" ;;
  gateway-admin) SERVICE="gateway-admin" ;;
  provider) SERVICE="provider" ;;
  *) echo "unsupported scheduled job family: $FAMILY" >&2; exit 2 ;;
esac

first_job="${JOBS%%,*}"
echo "[local-scheduled-job] project=$PROJECT_ID region=$REGION family=$FAMILY jobs=$JOBS"
image="$(
  gcloud run jobs describe "$first_job" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --format='value(spec.template.spec.template.spec.containers[0].image)'
)"
[[ -n "$image" ]] || { echo "unable to resolve current image for $first_job" >&2; exit 1; }
echo "[local-scheduled-job] using image from $first_job: $image"

args=(
  bash "$TARGET_REPO/scripts/deploy/gcp_sync_staging_jobs.sh"
  --project "$PROJECT_ID"
  --region "$REGION"
  --service "$SERVICE"
  --image "$image"
  --jobs "$JOBS"
)
if [[ "$RUN_SMOKE_JOBS" == "true" ]]; then
  args+=(--run-smoke-jobs)
fi

"${args[@]}"
