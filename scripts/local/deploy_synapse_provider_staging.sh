#!/usr/bin/env bash
set -euo pipefail

REF="main"
TARGET_REPO="${SYNAPSE_PROVIDER_REPO:-/Users/cliff/workspace/agent/Synapse-Network-Provider}"
HELPER_REPO="${SYNAPSE_NETWORK_HELPER_REPO:-/Users/cliff/workspace/agent/Synapse-Network}"
PROJECT_ID="${STAGING_GCP_PROJECT_ID:-fabled-archive-494108-k5}"
REGION="${STAGING_GCP_REGION:-us-central1}"
REPOSITORY="${STAGING_ARTIFACT_REGISTRY_REPOSITORY:-synapse-staging}"
EXPECTED_PROJECT_ID="fabled-archive-494108-k5"

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/local/deploy_synapse_provider_staging.sh --ref main

Options:
  --ref <branch|sha>           Target ref in Synapse-Network-Provider. Default: main.
  --target-repo <path>         Default: /Users/cliff/workspace/agent/Synapse-Network-Provider
  --project <gcp-project>      Default: STAGING_GCP_PROJECT_ID or fabled-archive-494108-k5
  --region <region>            Default: STAGING_GCP_REGION or us-central1
  --repository <artifact-repo>  Default: STAGING_ARTIFACT_REGISTRY_REPOSITORY or synapse-staging
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ref) REF="${2:-}"; shift 2 ;;
    --target-repo) TARGET_REPO="${2:-}"; shift 2 ;;
    --project) PROJECT_ID="${2:-}"; shift 2 ;;
    --region) REGION="${2:-}"; shift 2 ;;
    --repository) REPOSITORY="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd curl
require_cmd docker
require_cmd gcloud
require_cmd git
require_cmd node

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/synapse_gcp_env_guard.sh"

if ! git -C "${TARGET_REPO}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "target repo not found or not a git checkout: ${TARGET_REPO}" >&2
  exit 2
fi
if [[ ! -d "${HELPER_REPO}/.git" ]]; then
  echo "helper repo not found or not a git checkout: ${HELPER_REPO}" >&2
  exit 2
fi

synapse_release_env_guard \
  --environment staging \
  --project "${PROJECT_ID}" \
  --expected-project "${EXPECTED_PROJECT_ID}" \
  --region "${REGION}" \
  --service "synapse-staging-provider" \
  --repo "${TARGET_REPO}"

git_target() {
  git -C "${TARGET_REPO}" "$@"
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

assert_digest() {
  local digest="$1"
  if [[ ! "${digest}" =~ ^.+@sha256:[0-9a-f]{64}$ ]]; then
    echo "expected immutable image@sha256 digest, got: ${digest}" >&2
    exit 2
  fi
}

cloud_run_url() {
  gcloud run services describe synapse-staging-provider \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.url)'
}

cloud_run_revision() {
  gcloud run services describe synapse-staging-provider \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.latestReadyRevisionName)'
}

write_manifest() {
  local commit="$1"
  local image="$2"
  local path="${LOCAL_DEPLOY_MANIFEST_PATH:-}"
  [[ -n "${path}" ]] || return 0
  mkdir -p "$(dirname "${path}")"
  COMMIT_SHA="${commit}" \
    IMAGE_DIGEST="${image}" \
    SERVICE_URL="$(cloud_run_url)" \
    REVISION="$(cloud_run_revision)" \
    MANIFEST_PATH="${path}" \
    node - <<'NODE'
const fs = require('node:fs')
const manifest = {
  service_key: 'provider-service',
  environment: 'staging',
  commit_sha: process.env.COMMIT_SHA,
  image_digest: process.env.IMAGE_DIGEST,
  cloud_run_service: 'synapse-staging-provider',
  service_url: process.env.SERVICE_URL,
  revision: process.env.REVISION,
  smoke_status: 'passed',
  generated_at: new Date().toISOString(),
}
fs.writeFileSync(process.env.MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`)
NODE
}

target_commit="$(git_target rev-parse "${REF}^{commit}")"
short_sha="${target_commit:0:12}"
timestamp="$(date -u +%Y%m%d%H%M%S)"
tag="staging-local-provider-service-${short_sha}-${timestamp}"
worktree_dir="${TMPDIR:-/tmp}/synapse-provider-build-${short_sha}-${timestamp}-$$"
registry="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
image_tag="${registry}/provider:${tag}"

cleanup_worktree() {
  if git_target worktree list --porcelain | grep -Fqx "worktree ${worktree_dir}"; then
    git_target worktree remove -f "${worktree_dir}" >/dev/null 2>&1 || true
  elif [[ -d "${worktree_dir}" ]]; then
    rm -rf "${worktree_dir}"
  fi
}
trap cleanup_worktree EXIT

echo "[local-deploy] provider-service ref=${REF} commit=${target_commit}"
git_target worktree add --detach "${worktree_dir}" "${target_commit}"
pushd "${worktree_dir}" >/dev/null

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
docker build --platform "${DOCKER_PLATFORM:-linux/amd64}" -t "${image_tag}" .
docker push "${image_tag}"
node - <<NODE
const fs = require('node:fs')
fs.writeFileSync('build-images.json', JSON.stringify({services: {'provider-service': '${image_tag}'}}, null, 2) + '\\n')
NODE
node "${HELPER_REPO}/scripts/deploy/resolve_artifact_registry_image_digests.mjs" \
  --build-images build-images.json \
  --out image-digests.json
image="$(node -e "const fs=require('fs'); const d=JSON.parse(fs.readFileSync('image-digests.json','utf8')); console.log(d['provider-service'] || '')")"
assert_digest "${image}"

echo "[local-deploy] updating provider schema migration job"
run_with_timeout 8m gcloud run jobs update synapse-staging-provider-schema-migrate \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${image}" \
  --quiet

echo "[local-deploy] executing provider schema migration job"
run_with_timeout 8m gcloud run jobs execute synapse-staging-provider-schema-migrate \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --wait

echo "[local-deploy] syncing provider auxiliary job images"
bash "${HELPER_REPO}/scripts/deploy/gcp_sync_staging_jobs.sh" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --service provider \
  --image "${image}" \
  --json-output jobs-provider.json

echo "[local-deploy] deploying synapse-staging-provider with ${image}"
run_with_timeout 8m gcloud run deploy synapse-staging-provider \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${image}" \
  --quiet

provider_url="$(cloud_run_url)"
echo "[local-deploy] smoke provider-service"
for path in /health /ready; do
  curl --fail --silent --show-error "${provider_url}${path}" >/dev/null
done

write_manifest "${target_commit}" "${image}"
echo "[local-deploy] provider-service staging deploy completed"

popd >/dev/null
cleanup_worktree
trap - EXIT
