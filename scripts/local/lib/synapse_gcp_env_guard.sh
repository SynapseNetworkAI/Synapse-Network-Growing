#!/usr/bin/env bash
set -euo pipefail

synapse_release_env_guard() {
  local environment=""
  local project_id=""
  local expected_project_id=""
  local region=""
  local service_name=""
  local repo_path=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --environment)
        environment="${2:-}"
        shift 2
        ;;
      --project)
        project_id="${2:-}"
        shift 2
        ;;
      --expected-project)
        expected_project_id="${2:-}"
        shift 2
        ;;
      --region)
        region="${2:-}"
        shift 2
        ;;
      --service)
        service_name="${2:-}"
        shift 2
        ;;
      --repo)
        repo_path="${2:-}"
        shift 2
        ;;
      *)
        echo "unknown synapse_release_env_guard argument: $1" >&2
        return 2
        ;;
    esac
  done

  [[ -n "${environment}" ]] || {
    echo "[local-deploy:preflight] missing environment" >&2
    return 2
  }
  [[ -n "${project_id}" ]] || {
    echo "[local-deploy:preflight] missing project" >&2
    return 2
  }
  [[ -n "${expected_project_id}" ]] || {
    echo "[local-deploy:preflight] missing expected project" >&2
    return 2
  }
  [[ -n "${region}" ]] || {
    echo "[local-deploy:preflight] missing region" >&2
    return 2
  }

  if [[ "${project_id}" != "${expected_project_id}" ]]; then
    echo "[local-deploy:preflight] refusing ${environment} deploy: target project ${project_id} does not match expected ${expected_project_id}" >&2
    return 2
  fi

  if ! command -v gcloud >/dev/null 2>&1; then
    echo "[local-deploy:preflight] missing required command: gcloud" >&2
    return 1
  fi

  local active_account current_project
  active_account="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' | head -n1 || true)"
  if [[ -z "${active_account}" ]]; then
    echo "[local-deploy:preflight] no active gcloud account. Run: gcloud auth login" >&2
    return 1
  fi
  current_project="$(gcloud config get-value project 2>/dev/null || true)"

  echo "[local-deploy:preflight] environment=${environment}"
  echo "[local-deploy:preflight] active_account=${active_account}"
  echo "[local-deploy:preflight] target_project=${project_id}"
  echo "[local-deploy:preflight] current_gcloud_project=${current_project:-<unset>}"
  echo "[local-deploy:preflight] target_region=${region}"
  echo "[local-deploy:preflight] target_service=${service_name:-<not-set>}"
  echo "[local-deploy:preflight] target_repo=${repo_path:-<not-set>}"

  if ! gcloud projects describe "${project_id}" >/dev/null 2>&1; then
    echo "[local-deploy:preflight] active account cannot access target project ${project_id}" >&2
    return 1
  fi

  gcloud config set project "${project_id}" >/dev/null
  echo "[local-deploy:preflight] gcloud project aligned to ${project_id}"
}
