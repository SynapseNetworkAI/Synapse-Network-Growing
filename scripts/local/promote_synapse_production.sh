#!/usr/bin/env bash
set -euo pipefail

PROJECT_KEY=""
SERVICE=""
REF="main"
COMMIT_SHA=""
STAGING_IMAGE_DIGEST=""
PROJECT_ID="${PROD_GCP_PROJECT_ID:-synapse-network-prod}"
REGION="${PROD_GCP_REGION:-us-central1}"
REPOSITORY="${PROD_ARTIFACT_REGISTRY_REPOSITORY:-synapse-prod}"
IMPERSONATE_SERVICE_ACCOUNT="${LOCAL_DEPLOY_IMPERSONATE_SERVICE_ACCOUNT:-}"
EXPECTED_PROJECT_ID="synapse-network-prod"
gateway_service_name="synapse-prod-gateway"

usage() {
  cat >&2 <<'EOF'
Usage:
  bash scripts/local/promote_synapse_production.sh \
    --project-key synapse-network \
    --service gateway|gateway-admin|user-front|admin-front|docs-front|provider-service \
    --staging-image-digest <image@sha256>

Options:
  --ref <branch|sha>                Source ref label. Default: main.
  --commit-sha <sha>                Source commit sha for manifest evidence.
  --project <gcp-project>           Default: PROD_GCP_PROJECT_ID or synapse-network-prod.
  --region <region>                 Default: PROD_GCP_REGION or us-central1.
  --repository <artifact-repo>       Default: PROD_ARTIFACT_REGISTRY_REPOSITORY or synapse-prod.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-key) PROJECT_KEY="${2:-}"; shift 2 ;;
    --service) SERVICE="${2:-}"; shift 2 ;;
    --ref) REF="${2:-}"; shift 2 ;;
    --commit-sha) COMMIT_SHA="${2:-}"; shift 2 ;;
    --staging-image-digest) STAGING_IMAGE_DIGEST="${2:-}"; shift 2 ;;
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
require_cmd node

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/synapse_gcp_env_guard.sh"

GCLOUD=(gcloud)
if [[ -n "${IMPERSONATE_SERVICE_ACCOUNT}" ]]; then
  GCLOUD=(gcloud "--impersonate-service-account=${IMPERSONATE_SERVICE_ACCOUNT}")
fi

if [[ -z "${PROJECT_KEY}" || -z "${SERVICE}" || -z "${STAGING_IMAGE_DIGEST}" ]]; then
  usage
fi
if [[ ! "${STAGING_IMAGE_DIGEST}" =~ ^.+@sha256:[0-9a-f]{64}$ ]]; then
  echo "expected immutable staging image@sha256 digest, got: ${STAGING_IMAGE_DIGEST}" >&2
  exit 2
fi

synapse_release_env_guard \
  --environment production \
  --project "${PROJECT_ID}" \
  --expected-project "${EXPECTED_PROJECT_ID}" \
  --region "${REGION}" \
  --service "${SERVICE:-synapse-prod-unset}" \
  --repo "/Users/cliff/workspace/agent/Synapse-Network"

prod_image_name() {
  case "$1" in
    provider-service) echo "provider" ;;
    gateway|gateway-admin|user-front|admin-front|docs-front) echo "$1" ;;
    *) echo "unsupported production service: $1" >&2; return 2 ;;
  esac
}

cloud_run_service_name() {
  case "$1" in
    gateway) echo "synapse-prod-gateway" ;;
    gateway-admin) echo "synapse-prod-gateway-admin" ;;
    user-front) echo "synapse-prod-user-front" ;;
    admin-front) echo "synapse-prod-admin-front" ;;
    docs-front) echo "synapse-prod-docs-front" ;;
    provider-service) echo "synapse-prod-provider" ;;
    *) echo "unsupported production service: $1" >&2; return 2 ;;
  esac
}

smoke_paths() {
  case "$1" in
    gateway) printf '/health\n/readiness\n' ;;
    gateway-admin) printf '/health\n' ;;
    user-front|admin-front|docs-front) printf '/\n' ;;
    provider-service) printf '/health\n/ready\n' ;;
    *) return 2 ;;
  esac
}

is_frontend_service() {
  case "$1" in
    user-front|admin-front|docs-front) return 0 ;;
    *) return 1 ;;
  esac
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

cloud_run_url() {
  "${GCLOUD[@]}" run services describe "$(cloud_run_service_name "$1")" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.url)'
}

cloud_run_revision() {
  "${GCLOUD[@]}" run services describe "$(cloud_run_service_name "$1")" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.latestReadyRevisionName)'
}

write_manifest() {
  local service="$1"
  local image="$2"
  local path="${LOCAL_DEPLOY_MANIFEST_PATH:-}"
  [[ -n "${path}" ]] || return 0
  mkdir -p "$(dirname "${path}")"
  SERVICE="${service}" \
    COMMIT_SHA="${COMMIT_SHA}" \
    IMAGE_DIGEST="${image}" \
    CLOUD_RUN_SERVICE="$(cloud_run_service_name "${service}")" \
    SERVICE_URL="$(cloud_run_url "${service}")" \
    REVISION="$(cloud_run_revision "${service}")" \
    MANIFEST_PATH="${path}" \
    node - <<'NODE'
const fs = require('node:fs')
const manifest = {
  service_key: process.env.SERVICE,
  environment: 'production',
  commit_sha: process.env.COMMIT_SHA || undefined,
  image_digest: process.env.IMAGE_DIGEST,
  cloud_run_service: process.env.CLOUD_RUN_SERVICE,
  service_url: process.env.SERVICE_URL,
  revision: process.env.REVISION,
  smoke_status: 'passed',
  generated_at: new Date().toISOString(),
}
fs.writeFileSync(process.env.MANIFEST_PATH, `${JSON.stringify(manifest, null, 2)}\n`)
NODE
}

gateway_job_env_flags=()

build_gateway_job_env_flags() {
  local gateway_service_url
  gateway_service_url="$("${GCLOUD[@]}" run services describe "${gateway_service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.url)')"
  [[ -n "${gateway_service_url}" ]] || {
    echo "failed to resolve production gateway service URL" >&2
    exit 1
  }
  gateway_job_env_flags=(
    --update-env-vars
    "DEPOSIT_INDEXER_TRIGGER_ENABLED=false,DEPOSIT_INDEXER_TRIGGER_URL=${gateway_service_url}/internal/jobs/deposit-indexer/trigger,NOTIFICATION_OUTBOX_TRIGGER_ENABLED=false,NOTIFICATION_OUTBOX_TRIGGER_URL=${gateway_service_url}/internal/jobs/notification-outbox/trigger,ALCHEMY_DEPOSIT_WEBHOOK_ENABLED=false"
  )
}

update_gateway_prod_jobs() {
  local image="$1"
  local jobs=(
    synapse-prod-db-migrate
    synapse-prod-deposit-indexer
    synapse-prod-consumer-withdraw-chain-recovery
    synapse-prod-withdrawal-expiry-sweeper
    synapse-prod-notification-outbox-drain
    synapse-prod-in-app-notification-cleanup
  )
  local job
  for job in "${jobs[@]}"; do
    echo "[local-prod] updating ${job}"
    run_with_timeout 8m "${GCLOUD[@]}" run jobs update "${job}" \
      --project "${PROJECT_ID}" \
      --region "${REGION}" \
      --image "${image}" \
      "${gateway_job_env_flags[@]}" \
      --quiet
  done
  echo "[local-prod] executing synapse-prod-db-migrate"
  run_with_timeout 8m "${GCLOUD[@]}" run jobs execute synapse-prod-db-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-env-vars POSTGRES_APP_USER=synapse_gateway_migrator \
    --wait
}

update_gateway_admin_prod_jobs() {
  local image="$1"
  run_with_timeout 8m "${GCLOUD[@]}" run jobs update synapse-prod-gateway-admin-db-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --image "${image}" \
    --quiet
  run_with_timeout 8m "${GCLOUD[@]}" run jobs execute synapse-prod-gateway-admin-db-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --wait
}

update_provider_prod_jobs() {
  local image="$1"
  run_with_timeout 8m "${GCLOUD[@]}" run jobs update synapse-prod-provider-schema-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --image "${image}" \
    --quiet
  run_with_timeout 8m "${GCLOUD[@]}" run jobs execute synapse-prod-provider-schema-migrate \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --wait
}

image_name="$(prod_image_name "${SERVICE}")"
registry="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
tag="prod-promote-${image_name}-$(date -u +%Y%m%d%H%M%S)"
prod_tag="${registry}/${image_name}:${tag}"

echo "[local-prod] project_key=${PROJECT_KEY} service=${SERVICE} ref=${REF}"
echo "[local-prod] source=${STAGING_IMAGE_DIGEST}"
if is_frontend_service "${SERVICE}"; then
  # Next.js public environment variables are baked into frontend bundles at
  # build time. Do not promote a staging frontend digest to production, or the
  # production site will keep calling staging APIs.
  synapse_network_repo="${SYNAPSE_NETWORK_REPO:-/Users/cliff/workspace/agent/Synapse-Network}"
  build_ref="${COMMIT_SHA:-${REF}}"
  digest_log="$(mktemp -t synapse-prod-frontend-build.XXXXXX)"
  echo "[local-prod] frontend production build ref=${build_ref}"
  (
    cd "${synapse_network_repo}"
    bash scripts/deploy/local_build_frontend_image.sh \
      --service "${SERVICE}" \
      --environment production \
      --ref "${build_ref}" \
      --project "${PROJECT_ID}" \
      --region "${REGION}" \
      --repository "${REPOSITORY}" \
      --no-attach
  ) | tee "${digest_log}"
  prod_digest="$(tail -n 1 "${digest_log}")"
  rm -f "${digest_log}"
else
  echo "[local-prod] target=${prod_tag}"
  docker pull "${STAGING_IMAGE_DIGEST}"
  docker tag "${STAGING_IMAGE_DIGEST}" "${prod_tag}"
  prod_docker_config=""
  docker_host="$(docker context inspect --format '{{ (index .Endpoints "docker").Host }}' 2>/dev/null || true)"
  cleanup_prod_docker_config() {
    [[ -z "${prod_docker_config}" ]] || rm -rf "${prod_docker_config}"
  }
  trap cleanup_prod_docker_config EXIT
  if [[ -n "${IMPERSONATE_SERVICE_ACCOUNT}" ]]; then
    prod_docker_config="$(mktemp -d -t synapse-prod-docker.XXXXXX)"
    "${GCLOUD[@]}" auth print-access-token --project "${PROJECT_ID}" \
      | DOCKER_CONFIG="${prod_docker_config}" DOCKER_HOST="${docker_host}" docker login \
          -u oauth2accesstoken \
          --password-stdin "https://${REGION}-docker.pkg.dev"
    DOCKER_CONFIG="${prod_docker_config}" DOCKER_HOST="${docker_host}" docker push "${prod_tag}"
  else
    gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
    docker push "${prod_tag}"
  fi

  prod_token="$("${GCLOUD[@]}" auth print-access-token --project "${PROJECT_ID}")"
  PROD_TAG="${prod_tag}" PROD_TOKEN="${prod_token}" node - <<'NODE'
const https = require('node:https')
const image = process.env.PROD_TAG
const token = process.env.PROD_TOKEN
const slashIndex = image.lastIndexOf('/')
const tagIndex = image.lastIndexOf(':')
if (slashIndex < 0 || tagIndex < slashIndex) {
  console.error(`unsupported production image tag: ${image}`)
  process.exit(1)
}
const imageName = image.slice(0, tagIndex)
const tag = image.slice(tagIndex + 1)
const firstSlash = imageName.indexOf('/')
const host = imageName.slice(0, firstSlash)
const path = imageName.slice(firstSlash + 1)
const accept = [
  'application/vnd.oci.image.index.v1+json',
  'application/vnd.oci.image.manifest.v1+json',
  'application/vnd.docker.distribution.manifest.list.v2+json',
  'application/vnd.docker.distribution.manifest.v2+json',
].join(', ')
const req = https.request({
  method: 'HEAD',
  host,
  path: `/v2/${path}/manifests/${encodeURIComponent(tag)}`,
  headers: {Accept: accept, Authorization: `Bearer ${token}`},
}, (res) => {
  res.resume()
  const digest = res.headers['docker-content-digest']
  if (res.statusCode >= 200 && res.statusCode < 300 && digest) {
    console.log(`${imageName}@${digest}`)
    return
  }
  console.error(`failed to resolve production digest: HTTP ${res.statusCode || 'unknown'}`)
  process.exit(1)
})
req.on('error', (error) => {
  console.error(`failed to resolve production digest: ${error.message}`)
  process.exit(1)
})
req.end()
NODE
  prod_digest="$(
    PROD_TAG="${prod_tag}" PROD_TOKEN="${prod_token}" node - <<'NODE'
const https = require('node:https')
const image = process.env.PROD_TAG
const token = process.env.PROD_TOKEN
const slashIndex = image.lastIndexOf('/')
const tagIndex = image.lastIndexOf(':')
const imageName = image.slice(0, tagIndex)
const tag = image.slice(tagIndex + 1)
const firstSlash = imageName.indexOf('/')
const host = imageName.slice(0, firstSlash)
const path = imageName.slice(firstSlash + 1)
const accept = [
  'application/vnd.oci.image.index.v1+json',
  'application/vnd.oci.image.manifest.v1+json',
  'application/vnd.docker.distribution.manifest.list.v2+json',
  'application/vnd.docker.distribution.manifest.v2+json',
].join(', ')
const req = https.request({
  method: 'HEAD',
  host,
  path: `/v2/${path}/manifests/${encodeURIComponent(tag)}`,
  headers: {Accept: accept, Authorization: `Bearer ${token}`},
}, (res) => {
  res.resume()
  const digest = res.headers['docker-content-digest']
  if (res.statusCode >= 200 && res.statusCode < 300 && digest) {
    console.log(`${imageName}@${digest}`)
    return
  }
  console.error(`failed to resolve production digest: HTTP ${res.statusCode || 'unknown'}`)
  process.exit(1)
})
req.on('error', (error) => {
  console.error(`failed to resolve production digest: ${error.message}`)
  process.exit(1)
})
req.end()
NODE
  )"
fi
if [[ ! "${prod_digest}" =~ ^.+@sha256:[0-9a-f]{64}$ ]]; then
  echo "failed to resolve production immutable digest: ${prod_digest}" >&2
  exit 1
fi

case "${SERVICE}" in
  gateway)
    build_gateway_job_env_flags
    update_gateway_prod_jobs "${prod_digest}"
    ;;
  gateway-admin) update_gateway_admin_prod_jobs "${prod_digest}" ;;
  provider-service) update_provider_prod_jobs "${prod_digest}" ;;
esac

cloud_run_name="$(cloud_run_service_name "${SERVICE}")"
echo "[local-prod] deploying ${cloud_run_name} with ${prod_digest}"
run_with_timeout 8m "${GCLOUD[@]}" run deploy "${cloud_run_name}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${prod_digest}" \
  --quiet

service_url="$(cloud_run_url "${SERVICE}")"
while read -r path; do
  [[ -n "${path}" ]] || continue
  echo "[local-prod] smoke ${SERVICE}${path}"
  curl --fail --silent --show-error "${service_url}${path}" >/dev/null
done < <(smoke_paths "${SERVICE}")

write_manifest "${SERVICE}" "${prod_digest}"
echo "[local-prod] ${SERVICE} production deploy completed"
