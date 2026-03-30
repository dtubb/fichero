#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_VENV="${ROOT_DIR}/.venv"
HOME_VENV="${HOME}/.venv"
BRIEFCASE_VENV="${ROOT_DIR}/fichero-api/.briefcase-venv"
API_EDITABLE="${ROOT_DIR}/fichero-api[dev]"
PYTHON_VERSION_DEFAULT="3.12.13"
PYTHON_VERSION="${PYTHON_VERSION:-$PYTHON_VERSION_DEFAULT}"

find_python312() {
  if [ -x "/opt/homebrew/bin/python3.12" ]; then
    echo "/opt/homebrew/bin/python3.12"
    return 0
  fi
  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return 0
  fi
  echo "python3.12 not found. Install it first (e.g., brew install python@3.12)." >&2
  return 1
}

create_or_recreate_venv() {
  local py_bin="$1"
  local venv_path="$2"
  if [ -d "$venv_path" ]; then
    trash "$venv_path"
  fi
  "$py_bin" -m venv "$venv_path"
}

sync_project_venv() {
  local py_bin="$1"
  create_or_recreate_venv "$py_bin" "$PROJECT_VENV"
  "$PROJECT_VENV/bin/python" -m pip install --upgrade pip setuptools wheel
  "$PROJECT_VENV/bin/python" -m pip install -e "$API_EDITABLE"
  "$PROJECT_VENV/bin/python" -m pip install briefcase pytest ruff
}

sync_home_venv() {
  local py_bin="$1"
  create_or_recreate_venv "$py_bin" "$HOME_VENV"
  "$HOME_VENV/bin/python" -m pip install --upgrade pip setuptools wheel pytest ruff uv
}

sync_briefcase_venv() {
  local py_bin="$1"
  create_or_recreate_venv "$py_bin" "$BRIEFCASE_VENV"
  "$BRIEFCASE_VENV/bin/python" -m pip install --upgrade pip setuptools wheel
  "$BRIEFCASE_VENV/bin/python" -m pip install -e "$API_EDITABLE"
  "$BRIEFCASE_VENV/bin/python" -m pip install briefcase pytest ruff
}

write_python_version_file() {
  printf "%s\n" "$PYTHON_VERSION" > "${ROOT_DIR}/.python-version"
}

verify() {
  echo "Project venv: $("$PROJECT_VENV/bin/python" --version)"
  echo "Home venv:    $("$HOME_VENV/bin/python" --version)"
  echo "Briefcase venv: $("$BRIEFCASE_VENV/bin/python" --version)"
  "$PROJECT_VENV/bin/python" -m pip check
  "$HOME_VENV/bin/python" -m pip check
  "$BRIEFCASE_VENV/bin/python" -m pip check
}

main() {
  local py_bin
  py_bin="$(find_python312)"
  echo "Using Python: $py_bin ($("$py_bin" --version))"
  sync_project_venv "$py_bin"
  sync_home_venv "$py_bin"
  sync_briefcase_venv "$py_bin"
  write_python_version_file
  verify
  echo "venv sync complete."
}

main "$@"
