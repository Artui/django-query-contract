from __future__ import annotations


class PlansUnsupported(Exception):
    """Plan capture was asked for on a connection that cannot produce a plan."""
