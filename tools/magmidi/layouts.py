"""In-key note layouts for the letter block, independent of the device's key naming.

"thirds" (default): each hand has the tonic under its resting fingers (left S, right J). Adjacent home-row keys go up
in diatonic thirds, so any 3 adjacent home keys are a triad of the scale and 4 a seventh chord. The bottom row sits
between the home keys (QWERTY stagger) and fills in the scale steps; the upper row is the home row an octave up.
The left hand (columns Q/A/Z..T/G/B) plays an octave below the right hand.

    C major, base_note 48:
     up:   Q  W  E  R  T      Y  U  I  O  P  [  ]
           A3 C4 E4 G4 B4     A4 C5 E5 G5 B5 D6 F6
     home: A  S  D  F  G      H  J  K  L  ;  '
           A2 C3 E3 G3 B3     A3 C4 E4 G4 B4 D5
     bott:  Z  X  C  V  B      N  M  ,  .  /
            B2 D3 F3 A3 C4     B3 D4 F4 A4 C5
"""
from __future__ import annotations

SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "mixolydian": [0, 2, 4, 5, 7, 9, 10],
    "harmonic_minor": [0, 2, 3, 5, 7, 8, 11],
}
LAYOUTS = ("thirds", "piano")

UPPER, HOME, BOTTOM = "QWERTYUIOP[]", "ASDFGHJKL;'", "ZXCVBNM,./"
SPLIT = 5  # columns 0..4 of each row belong to the left hand
ANCHOR = {"left": 1, "right": 6}  # home-row column of the tonic: S, J
CANON = set(UPPER + HOME + BOTTOM + "`1234567890-=")


def canonical(name: str) -> str | None:
    """Device key name -> single-character canonical name ('Q', ',', "'"), or None for other keys.

    FUN68 names are already canonical; C80 names carry the shifted glyph too (",<", ";:", '" \\'')."""
    if name in CANON:
        return name
    # "x" + shifted glyph(s), e.g. ",<", "1!", "[{"; or glyphs only ('" \''). Not "F1", "PgUp".
    if len(name) <= 4 and not any(ch.isalnum() for ch in name[1:]):
        for ch in name:
            if ch in CANON:
                return ch
    return None


def thirds() -> dict[str, tuple[int, str]]:
    """canonical name -> (scale degree relative to the hand's tonic, hand)."""
    out = {}
    for row, extra in ((HOME, 0), (BOTTOM, 1), (UPPER, 7)):
        for col, ch in enumerate(row):
            hand = "left" if col < SPLIT else "right"
            out[ch] = (2 * (col - ANCHOR[hand]) + extra, hand)
    return out


def semitones(degree: int, scale: list[int]) -> int:
    return 12 * (degree // len(scale)) + scale[degree % len(scale)]


def build(layout: str, scale_name: str, key_names) -> tuple[dict, dict, dict]:
    """-> (notes, hands, degrees) keyed by the device's key names.

    notes: semitone offset from base_note (right hand +12); hands: "left"/"right"; degrees: 0..6 within the scale."""
    if layout != "thirds":
        raise ValueError(f"unknown layout {layout!r}; known: {', '.join(LAYOUTS)}")
    if scale_name not in SCALES:
        raise ValueError(f"unknown scale {scale_name!r}; known: {', '.join(SCALES)}")
    scale = SCALES[scale_name]
    grid = thirds()
    notes, hands, degrees = {}, {}, {}
    for name in key_names:
        c = canonical(name)
        if c not in grid:
            continue
        deg, hand = grid[c]
        notes[name] = semitones(deg, scale) + (12 if hand == "right" else 0)
        hands[name] = hand
        degrees[name] = deg % len(scale)
    return notes, hands, degrees
