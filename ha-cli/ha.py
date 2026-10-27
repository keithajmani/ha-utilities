#!/usr/bin/env python3
"""ha.py: one helper for Home Assistant reads and safe writes. See README.md."""
import os
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "bin", "python")

# Re-run under the private venv (it has the websockets library) when it exists.
if os.path.exists(VENV_PY) and os.path.realpath(sys.prefix) != os.path.realpath(os.path.join(HERE, ".venv")):
    os.execv(VENV_PY, [VENV_PY, os.path.realpath(__file__)] + sys.argv[1:])

sys.path.insert(0, HERE)
from ha_cli.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
