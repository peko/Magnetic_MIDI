"""Shortcut: python3 tools/viz.py [--device auto|c80|fun68]  (same as python -m magmidi.viz)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from magmidi.viz import main  # noqa: E402

main()
