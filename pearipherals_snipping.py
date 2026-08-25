"""Launch Windows' built-in interactive screen-snipping overlay."""

import os


SCREEN_CLIP_URI = "ms-screenclip:"


def open_snipping_overlay(startfile=None):
    """Ask Windows to open its interactive region-selection overlay."""
    if startfile is None:
        startfile = os.startfile
    startfile(SCREEN_CLIP_URI)
