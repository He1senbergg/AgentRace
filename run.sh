#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ -n "${AGENTRACE_PYTHON:-}" ]]; then
    interpreter="$AGENTRACE_PYTHON"
elif [[ -x .venv/bin/python ]]; then
    interpreter=.venv/bin/python
else
    interpreter=python3
fi
exec "$interpreter" src/main3.py "$@"
