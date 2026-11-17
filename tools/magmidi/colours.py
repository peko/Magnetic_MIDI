"""Key colours for --light, shared by the device lighting backends (they only place them by matrix index)."""
from __future__ import annotations

WHITE, BLUE, ORANGE = (150, 150, 150), (0, 40, 255), (255, 40, 0)
QUIT = (255, 0, 0)
PEDAL = (0, 255, 40)  # sustain key: green
CONTROL = (255, 160, 0)  # transpose arrows, shift, sharp modifiers: amber
BLACK_PCS = {1, 3, 6, 8, 10}


def key_colours(cfg: dict) -> dict[str, tuple[int, int, int]]:
    """key name -> RGB; keys not listed stay dark.

    In-key layouts (cfg["degrees"] present) colour notes by scale degree, so the colours stay right after
    transposition: tonic orange, 3rd and 5th white, other steps blue. The piano layout colours by pitch class
    (C orange, white keys white, black keys blue)."""
    out = {}
    degrees = cfg.get("degrees")
    for name, off in cfg["notes"].items():
        if degrees is not None:
            d = degrees[name]
            out[name] = ORANGE if d == 0 else WHITE if d in (2, 4) else BLUE
        else:
            pc = (cfg["base_note"] + off) % 12
            out[name] = ORANGE if pc == 0 else BLUE if pc in BLACK_PCS else WHITE
    if cfg.get("sustain_key"):
        out[cfg["sustain_key"]] = PEDAL
    for name in [*(cfg.get("transpose_keys") or {}), *(cfg.get("shift_keys") or []), *(cfg.get("sharp_keys") or {})]:
        out[name] = CONTROL
    if cfg.get("quit_key"):
        out[cfg["quit_key"]] = QUIT
    return out
