from __future__ import annotations

import os


def relative_to_cwd(text: str) -> str:
    """Shorten a rendered call site to a path relative to the working directory."""
    root = os.getcwd() + os.sep
    if text.startswith(root):
        return text[len(root) :]
    return text


__all__ = ["relative_to_cwd"]
