#!/bin/bash
# IceWarp LDAP test lab deployer
# Usage:
#   SITE=infralab ./deploy.sh                                 # prepared EL9 hosts, native 389-ds
#   SITE=infralab PLATFORM=kvm ./deploy.sh                    # create Infralab EL9 VM first
#   SITE=infralab LDAP_MODE=docker ./deploy.sh                # 389-ds in a container
#   IW_SYNC_MODE=crossdomain IW_SYNC_DOMAIN=iwldaptest.loc SITE=infralab ./deploy.sh
#   SKIP_PROVISION=1 SKIP_ICEWARP=1 SITE=infralab ./deploy.sh
#
# Resume unfinished stages (skips stages recorded in inventory/<SITE>/.deploy-state):
#   RESUME=1 SITE=infralab ./deploy.sh
#
# Clear progress and start fresh:
#   RESET_DEPLOY_STATE=1 SITE=infralab ./deploy.sh
#
# Secrets: copy group_vars/all/vault.yml.example → vault.yml, fill, ansible-vault encrypt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

SITE="${SITE:-infralab}"
INVENTORY="inventory/${SITE}"
VAULT_PASS="${VAULT_PASS:-../.vault-pass}"
STATE_FILE="${INVENTORY}/.deploy-state"
RESUME="${RESUME:-0}"
RESET_DEPLOY_STATE="${RESET_DEPLOY_STATE:-0}"
SKIP_PROVISION="${SKIP_PROVISION:-0}"
SKIP_DOCKER="${SKIP_DOCKER:-0}"
SKIP_LDAP="${SKIP_LDAP:-0}"
SKIP_LDAP_DATA="${SKIP_LDAP_DATA:-0}"
SKIP_ICEWARP="${SKIP_ICEWARP:-0}"
EXTRA_VARS=()

if [[ -n "${PLATFORM:-}" ]]; then
  EXTRA_VARS+=(-e "cluster_platform=${PLATFORM}")
fi

if [[ -n "${LDAP_MODE:-}" ]]; then
  EXTRA_VARS+=(-e "ldap_install_mode=${LDAP_MODE}")
fi

if [[ -n "${IW_SYNC_MODE:-}" ]]; then
  EXTRA_VARS+=(-e "icewarp_sync_mode=${IW_SYNC_MODE}")
fi

if [[ -n "${IW_SYNC_DOMAIN:-}" ]]; then
  EXTRA_VARS+=(-e "icewarp_sync_domain=${IW_SYNC_DOMAIN}")
fi

if [[ ! -d "${INVENTORY}" ]]; then
  echo "Inventory not found: ${INVENTORY}"
  echo "Available sites:"
  ls -1 inventory/ 2>/dev/null || true
  exit 1
fi

# shellcheck disable=SC1090
source "${HOME}/ansible-venv/bin/activate"

AP="ansible-playbook -i ${INVENTORY}"
if [[ -f "${VAULT_PASS}" ]]; then
  AP="${AP} --vault-password-file=${VAULT_PASS}"
fi

if [[ "${RESET_DEPLOY_STATE}" == "1" ]]; then
  if [[ -f "${STATE_FILE}" ]]; then
    rm -f "${STATE_FILE}"
    echo "==== Cleared deploy state: ${STATE_FILE} ===="
  else
    echo "==== No deploy state to clear (${STATE_FILE}) ===="
  fi
fi

stage_done() {
  [[ -f "${STATE_FILE}" ]] || return 1
  grep -Fxq "$1" "${STATE_FILE}"
}

mark_stage_ok() {
  stage_done "$1" && return 0
  echo "$1" >> "${STATE_FILE}"
}

run_stage() {
  local stage="$1"
  shift
  if [[ "${RESUME}" == "1" ]] && stage_done "${stage}"; then
    echo "==== Skipping ${stage} (already ok) ===="
    return 0
  fi
  echo "==== Running ${stage}: $* ===="
  # shellcheck disable=SC2086
  ${AP} "${EXTRA_VARS[@]}" "$@"
  mark_stage_ok "${stage}"
}

PLATFORM_EFFECTIVE="${PLATFORM:-}"
if [[ -z "${PLATFORM_EFFECTIVE}" ]] && [[ -f "${INVENTORY}/group_vars/all.yml" ]]; then
  PLATFORM_EFFECTIVE="$(
    grep -E '^[[:space:]]*cluster_platform:' "${INVENTORY}/group_vars/all.yml" \
      | head -1 \
      | sed -E 's/^[[:space:]]*cluster_platform:[[:space:]]*["'\'']?([^"'\'']+)["'\'']?.*/\1/' \
      | tr -d '[:space:]'
  )"
fi
PLATFORM_EFFECTIVE="${PLATFORM_EFFECTIVE:-linux}"

if [[ "${RESUME}" == "1" ]]; then
  echo "==== RESUME=1 — skipping finished stages from ${STATE_FILE} ===="
fi

case "${PLATFORM_EFFECTIVE}" in
  linux) PROVISION_PB="playbooks/provision_linux.yml" ;;
  kvm) PROVISION_PB="playbooks/provision_kvm.yml" ;;
  *)
    echo "Unknown cluster_platform/PLATFORM: ${PLATFORM_EFFECTIVE} (expected linux|kvm)"
    exit 1
    ;;
esac

if [[ "${SKIP_PROVISION}" == "1" ]]; then
  echo "==== Skipping provision (SKIP_PROVISION=1) ===="
else
  run_stage provision "${PROVISION_PB}"
fi

if [[ "${SKIP_DOCKER}" == "1" ]]; then
  echo "==== Skipping docker (SKIP_DOCKER=1) ===="
else
  run_stage docker playbooks/docker.yml
fi

if [[ "${SKIP_LDAP}" == "1" ]]; then
  echo "==== Skipping ldap (SKIP_LDAP=1) ===="
else
  run_stage ldap playbooks/ldap.yml
fi

if [[ "${SKIP_LDAP_DATA}" == "1" ]]; then
  echo "==== Skipping ldap_data (SKIP_LDAP_DATA=1) ===="
else
  run_stage ldap_data playbooks/ldap_data.yml
fi

if [[ "${SKIP_ICEWARP}" == "1" ]]; then
  echo "==== Skipping icewarp (SKIP_ICEWARP=1) ===="
else
  run_stage icewarp playbooks/icewarp.yml
fi

echo "Deploy finished for site=${SITE}."
