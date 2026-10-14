"""Ensure the repo root is on sys.path before any test imports."""

import os
import sys

_REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_SDK = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
for p in (os.path.join(_REPO, "python"), _SDK):
    if p not in sys.path:
        sys.path.insert(0, p)
