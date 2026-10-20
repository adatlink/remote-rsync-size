#!/usr/bin/env python3
"""Backward-compatible launcher, usable directly from an unpacked checkout."""

from pathlib import Path
import sys

# Allow `python remote_rsync_size_local.py` without pip installation.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from remote_rsync_size.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
