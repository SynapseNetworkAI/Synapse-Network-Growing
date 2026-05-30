#!/usr/bin/env bash
set -euo pipefail

SERVICE=""
REF="main"
PREBUILT_IMAGE_DIGEST=""
TARGET_REPO="${SYNAPSE_NETWORK_REPO:-/Users/cliff/workspace/agent/Synapse-Network}"
PROJECT_ID="${STAGING_GCP_PROJECT_ID:-fabled-archive-494108-k5}"
REGION="${STAGING_GCP_REGION:-us-central1}"
REPOSITORY="${STAGING_ARTIFACT_REGISTRY_REPOSITORY:-synapse-staging}"
EXPECTED_PROJECT_ID="fabled-archive-494108-k5"

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/local/deploy_synapse_staging.sh --service gateway|gateway-admin|user-front|admin-front|docs-front --ref main

Options:
  --service <service>                 Service to deploy.
  --ref <branch|sha>                  Target ref in Synapse-Network. Default: main.
  --prebuilt-image-digest <digest>    Optional frontend image@sha256 digest.
  --target-repo <path>                Default: /Users/cliff/workspace/agent/Synapse-Network
  --project <gcp-project>             Default: STAGING_GCP_PROJECT_ID or fabled-archive-494108-k5
  --region <region>                   Default: STAGING_GCP_REGION or us-central1
  --repository <artifact-repo>         Default: STAGING_ARTIFACT_REGISTRY_REPOSITORY or synapse-staging
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE="${2:-}"
      shift 2
      ;;
    --ref)
      REF="${2:-}"
      shift 2
      ;;
    --prebuilt-image-digest)
      PREBUILT_IMAGE_DIGEST="${2:-}"
      shift 2
      ;;
    --target-repo)
      TARGET_REPO="${2:-}"
      shift 2
      ;;
    --project)
      PROJECT_ID="${2:-}"
      shift 2
      ;;
    --region)
      REGION="${2:-}"
      shift 2
      ;;
    --repository)
      REPOSITORY="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd bash
require_cmd curl
require_cmd docker
require_cmd gcloud
require_cmd git
require_cmd mktemp
require_cmd node

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/synapse_gcp_env_guard.sh"

if [[ ! -d "${TARGET_REPO}/.git" ]]; then
  echo "target repo not found or not a git checkout: ${TARGET_REPO}" >&2
  exit 2
fi
if [[ -z "${PROJECT_ID}" || -z "${REGION}" || -z "${REPOSITORY}" ]]; then
  echo "project, region, and repository are required" >&2
  exit 2
fi

synapse_release_env_guard \
  --environment staging \
  --project "${PROJECT_ID}" \
  --expected-project "${EXPECTED_PROJECT_ID}" \
  --region "${REGION}" \
  --service "${SERVICE:-synapse-staging-unset}" \
  --repo "${TARGET_REPO}"

git_target() {
  git \
    --git-dir="${TARGET_REPO}/.git" \
    --work-tree="${TARGET_REPO}" \
    "$@"
}

run_in_target_worktree() {
  GIT_DIR="${TARGET_REPO}/.git" \
    GIT_WORK_TREE="${TARGET_REPO}" \
    "$@"
}

run_with_timeout() {
  local duration="$1"
  shift
  if command -v timeout >/dev/null 2>&1; then
    timeout "${duration}" "$@"
  else
    "$@"
  fi
}

cloud_run_service_name() {
  case "$1" in
    gateway) echo "synapse-staging-gateway" ;;
    gateway-admin) echo "synapse-staging-gateway-admin" ;;
    user-front) echo "synapse-staging-user-front" ;;
    admin-front) echo "synapse-staging-admin-front" ;;
    docs-front) echo "synapse-staging-docs-front" ;;
    *)
      echo "unsupported local staging service: $1" >&2
      return 2
      ;;
  esac
}

cloud_run_url() {
  gcloud run services describe "$(cloud_run_service_name "$1")" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.url)'
}

cloud_run_revision() {
  gcloud run services describe "$(cloud_run_service_name "$1")" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.latestReadyRevisionName)'
}

write_manifest() {
  local service="$1"
  local commit="$2"
  local image="$3"
  local smoke_status="$4"
  local path="${LOCAL_DEPLOY_MANIFEST_PATH:-}"
  [[ -n "${path}" ]] || return 0
  mkdir -p "$(dirname "${path}")"
  SERVICE="${service}" \
    COMMIT_SHA="${commit}" \
    IMAGE_DIGEST="${image}" \
    CLOUD_RUN_SERVICE="$(cloud_run_service_name "${service}")" \
    SERVICE_URL="$(cloud_run_url "${service}")" \
    REVISION="$(cloud_run_revision "${service}")" \
    SMOKE_STATUS="${smoke_status}" \
    MANIFEST_PATH="${path}" \
    node - <<'NODE'
const fs = require('node:fs')
const manifest = {
  service_key: process.env.SERVICE,
  environment: 'staging',
  commit_sha: process.env.COMMIT_SHA,
  image_digest: process.env.IMAGE_DIGEST,
  cloud_run_service: process.env.CLOUD_RUN_SERVICE,
  service_url: process.env.SERVICE_URL,
  revision: process.env.REVISION,
  smoke_status: process.env.SMOKE_STATUS,
  generated_at: new Date().toISOString(),
}
fs.writeFileSync(process.env.MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`)
NODE
}

assert_digest() {
  local digest="$1"
  if [[ ! "${digest}" =~ ^.+@sha256:[0-9a-f]{64}$ ]]; then
    echo "expected immutable image@sha256 digest, got: ${digest}" >&2
    exit 2
  fi
}

deploy_image_and_smoke() {
  local service="$1"
  local image="$2"
  local cloud_run_name
  cloud_run_name="$(cloud_run_service_name "${service}")"
  assert_digest "${image}"
  echo "[local-deploy] deploying ${cloud_run_name} with ${image}"
  run_with_timeout 8m gcloud run deploy "${cloud_run_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --image "${image}" \
    --quiet
  echo "[local-deploy] smoke ${service}"
  run_with_timeout 5m bash "${TARGET_REPO}/scripts/deploy/gcp_smoke_staging_services.sh" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --services "${service}" \
    --json-output "smoke-${service}.json" \
    --details-output "smoke-${service}-details.json"
}

build_synapse_network_digest() {
  local service="$1"
  local tag="$2"
  local output_key="$3"
  REGION="${REGION}" \
    ARTIFACT_REGISTRY_REPOSITORY="${REPOSITORY}" \
    STAGING_IMAGE_BUILD_BACKEND=local-docker \
    bash scripts/deploy/gcp_cloudbuild_staging_images.sh "${PROJECT_ID}" \
      --services "${service}" \
      --tag "${tag}" \
      --json-output build-images.json >&2
  node "${TARGET_REPO}/scripts/deploy/resolve_artifact_registry_image_digests.mjs" \
    --build-images build-images.json \
    --out image-digests.json >&2
  node -e "const fs=require('fs'); const d=JSON.parse(fs.readFileSync('image-digests.json','utf8')); console.log(d[process.argv[1]] || '')" "${output_key}"
}

build_frontend_digest() {
  local service="$1"
  local target_commit short_sha timestamp tag worktree_dir build_backend image
  target_commit="$(git_target rev-parse "${REF}^{commit}")"
  short_sha="${target_commit:0:12}"
  timestamp="$(date -u +%Y%m%d%H%M%S)"
  tag="staging-local-${service}-${short_sha}-${timestamp}"
  worktree_dir="${TMPDIR:-/tmp}/synapse-build-staging-${service}-${short_sha}-${timestamp}-$$"
  build_backend="${FRONTEND_STAGING_IMAGE_BUILD_BACKEND:-cloudbuild}"
  cleanup_frontend_worktree() {
    if git_target worktree list --porcelain | grep -Fqx "worktree ${worktree_dir}"; then
      git_target worktree remove -f "${worktree_dir}" >/dev/null 2>&1 || true
    elif [[ -d "${worktree_dir}" ]]; then
      rm -rf "${worktree_dir}"
    fi
  }
  trap cleanup_frontend_worktree EXIT

  echo "[local-deploy] ${service} ref=${REF} commit=${target_commit}" >&2
  echo "[local-deploy] ${service} image build backend=${build_backend}" >&2
  git_target worktree add --detach "${worktree_dir}" "${target_commit}" >&2
  pushd "${worktree_dir}" >/dev/null
  REGION="${REGION}" \
    ARTIFACT_REGISTRY_REPOSITORY="${REPOSITORY}" \
    STAGING_IMAGE_BUILD_BACKEND="${build_backend}" \
    bash "${TARGET_REPO}/scripts/deploy/gcp_cloudbuild_staging_images.sh" "${PROJECT_ID}" \
      --services "${service}" \
      --tag "${tag}" \
      --json-output build-images.json >&2
  node "${TARGET_REPO}/scripts/deploy/resolve_artifact_registry_image_digests.mjs" \
    --build-images build-images.json \
    --out image-digests.json >&2
  image="$(node -e "const fs=require('fs'); const d=JSON.parse(fs.readFileSync('image-digests.json','utf8')); console.log(d[process.argv[1]] || '')" "${service}")"
  popd >/dev/null
  cleanup_frontend_worktree
  trap - EXIT
  printf '%s\n' "${image}"
}

deploy_frontend() {
  local service="$1"
  local image="${PREBUILT_IMAGE_DIGEST}"
  local target_commit
  target_commit="$(git_target rev-parse "${REF}^{commit}")"
  if [[ -z "${image}" ]]; then
    image="$(build_frontend_digest "${service}")"
  fi
  deploy_image_and_smoke "${service}" "${image}"
  write_manifest "${service}" "${target_commit}" "${image}" "passed"
}

deploy_gateway() {
  local target_commit short_sha timestamp tag worktree_dir image
  target_commit="$(git_target rev-parse "${REF}^{commit}")"
  short_sha="${target_commit:0:12}"
  timestamp="$(date -u +%Y%m%d%H%M%S)"
  tag="staging-local-gateway-${short_sha}-${timestamp}"
  worktree_dir="${TMPDIR:-/tmp}/synapse-gateway-build-${short_sha}-${timestamp}-$$"
  cleanup_gateway_worktree() {
    if git_target worktree list --porcelain | grep -Fqx "worktree ${worktree_dir}"; then
      git_target worktree remove -f "${worktree_dir}" >/dev/null 2>&1 || true
    elif [[ -d "${worktree_dir}" ]]; then
      rm -rf "${worktree_dir}"
    fi
  }
  trap cleanup_gateway_worktree EXIT

  echo "[local-deploy] gateway ref=${REF} commit=${target_commit}"
  git_target worktree add --detach "${worktree_dir}" "${target_commit}"
  pushd "${worktree_dir}" >/dev/null
  image="$(build_synapse_network_digest gateway "${tag}" gateway)"
  assert_digest "${image}"

  echo "[local-deploy] updating gateway migration job"
  run_with_timeout 8m gcloud run jobs update synapse-staging-db-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --image "${image}" \
    --quiet
  echo "[local-deploy] executing gateway migration job"
  run_with_timeout 8m gcloud run jobs execute synapse-staging-db-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --wait

  echo "[local-deploy] syncing gateway Cloud Run Jobs image"
  bash "${TARGET_REPO}/scripts/deploy/gcp_sync_staging_jobs.sh" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --service gateway \
    --image "${image}" \
    --json-output jobs-gateway.json

  deploy_image_and_smoke gateway "${image}"
  write_manifest gateway "${target_commit}" "${image}" "passed"

  echo "[local-deploy] gateway service and job image sync completed"
  popd >/dev/null
  cleanup_gateway_worktree
  trap - EXIT
}

deploy_gateway_admin() {
  local target_commit short_sha timestamp tag worktree_dir image
  target_commit="$(git_target rev-parse "${REF}^{commit}")"
  short_sha="${target_commit:0:12}"
  timestamp="$(date -u +%Y%m%d%H%M%S)"
  tag="staging-local-gateway-admin-${short_sha}-${timestamp}"
  worktree_dir="${TMPDIR:-/tmp}/synapse-gateway-admin-build-${short_sha}-${timestamp}-$$"
  cleanup_gateway_admin_worktree() {
    if git_target worktree list --porcelain | grep -Fqx "worktree ${worktree_dir}"; then
      git_target worktree remove -f "${worktree_dir}" >/dev/null 2>&1 || true
    elif [[ -d "${worktree_dir}" ]]; then
      rm -rf "${worktree_dir}"
    fi
  }
  trap cleanup_gateway_admin_worktree EXIT

  echo "[local-deploy] gateway-admin ref=${REF} commit=${target_commit}"
  git_target worktree add --detach "${worktree_dir}" "${target_commit}"
  pushd "${worktree_dir}" >/dev/null
  image="$(build_synapse_network_digest gateway-admin "${tag}" gateway-admin)"
  assert_digest "${image}"

  echo "[local-deploy] updating gateway-admin migration job"
  bash "${TARGET_REPO}/scripts/deploy/gcp_sync_staging_jobs.sh" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --service gateway-admin \
    --image "${image}" \
    --json-output jobs-gateway-admin.json

  echo "[local-deploy] executing gateway-admin migration job"
  run_with_timeout 8m gcloud run jobs execute synapse-staging-gateway-admin-db-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --wait

  deploy_image_and_smoke gateway-admin "${image}"
  write_manifest gateway-admin "${target_commit}" "${image}" "passed"

  echo "[local-deploy] gateway-admin service and job image sync completed"
  popd >/dev/null
  cleanup_gateway_admin_worktree
  trap - EXIT
}

case "${SERVICE}" in
  user-front|admin-front|docs-front)
    deploy_frontend "${SERVICE}"
    ;;
  gateway)
    if [[ -n "${PREBUILT_IMAGE_DIGEST}" ]]; then
      echo "prebuilt image digest is not supported for gateway local deploy" >&2
      exit 2
    fi
    deploy_gateway
    ;;
  gateway-admin)
    if [[ -n "${PREBUILT_IMAGE_DIGEST}" ]]; then
      echo "prebuilt image digest is not supported for gateway-admin local deploy" >&2
      exit 2
    fi
    deploy_gateway_admin
    ;;
  *)
    echo "unsupported local staging service: ${SERVICE}" >&2
    exit 2
    ;;
esac

echo "[local-deploy] ${SERVICE} staging deploy completed"
