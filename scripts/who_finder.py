#!/usr/bin/env python3
"""Run from any cwd. Roster lives in the recipient's working directory."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
