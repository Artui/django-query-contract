"""Render a call site against the working directory."""

from __future__ import annotations

import os


def relative_to_cwd(text: str) -> str:
    """Shorten a rendered call site to a path relative to the working directory.

    Only when it is under it: ``os.path.relpath`` will happily walk out of the
    tree with a row of ``..`` segments, which is longer than the absolute path
    and harder to read.

    Here for the same reason as the frame choice above. Two renderings name a
    call site now -- a finding's block and an attribution's -- and a reader
    shown one path abbreviated and the other absolute would reasonably wonder
    whether they were the same file.
    """
    root = os.getcwd() + os.sep
    if text.startswith(root):
        return text[len(root) :]
    return text


__all__ = ["relative_to_cwd"]
