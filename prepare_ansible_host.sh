#!/bin/bash
# Bootstrap Ansible control node for IceWarp LDAP test lab.
# Default: Linux EL9 (dnf). Optional: macOS/Darwin (Homebrew).
set -euo pipefail

OS_NAME="$(uname -s)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_os_packages_linux() {
  echo "DNF clean all..."
  sudo dnf clean all

  echo "Updating system packages..."
  sudo dnf update -y

  echo "Installing Python 3.11, pip, git, jq..."
  sudo dnf install -y python3.11 python3.11-pip git jq
}

install_os_packages_darwin() {
  if ! command -v brew >/dev/null 2>&1; then
    echo "ERROR: Homebrew is required on macOS. Install from https://brew.sh then re-run."
    exit 1
  fi

  echo "Installing Python 3.11, git, jq via Homebrew..."
  brew install python@3.11 git jq

  BREW_PREFIX="$(brew --prefix)"
  if [[ -x "${BREW_PREFIX}/opt/python@3.11/bin/python3.11" ]]; then
    export PATH="${BREW_PREFIX}/opt/python@3.11/bin:${PATH}"
  fi
}

case "${OS_NAME}" in
  Linux)
    echo "Detected Linux — using EL9/dnf control-node bootstrap (default)."
    install_os_packages_linux
    ;;
  Darwin)
    echo "Detected macOS (Darwin) — using Homebrew control-node bootstrap."
    install_os_packages_darwin
    ;;
  *)
    echo "ERROR: Unsupported control-node OS: ${OS_NAME} (expected Linux or Darwin)."
    exit 1
    ;;
esac

if ! command -v python3.11 >/dev/null 2>&1; then
  echo "ERROR: python3.11 not found on PATH after package install."
  exit 1
fi

echo "Verifying Python 3.11 installation..."
python3.11 --version

echo "Creating Python 3.11 virtual environment for Ansible..."
python3.11 -m venv ~/ansible-venv

echo "Activating virtual environment..."
# shellcheck disable=SC1090
source "${HOME}/ansible-venv/bin/activate"

echo "Upgrading pip and essential tools in virtual environment..."
pip install --upgrade pip setuptools wheel

echo "Installing Ansible Core 2.19..."
pip install --upgrade "ansible-core==2.19.*"

echo "Installing Ansible collections from requirements.yml..."
ansible-galaxy collection install -r "${SCRIPT_DIR}/requirements.yml" --force --ignore-certs

echo "Verifying Python and Ansible version..."
which python
which ansible
ansible --version

echo "Installation complete. To use Ansible, activate the virtual environment by:"
echo "source ~/ansible-venv/bin/activate"
