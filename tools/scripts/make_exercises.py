#!/usr/bin/env python3
"""Write the trainer's exercises for the "thirds" layout to scores/*.mid (two tracks: Right hand, Left hand).

    .venv/bin/python tools/scripts/make_exercises.py

All in C major except 06 (D major, to show the trainer moving the layout); key names in comments are the computer keys of the thirds layout (docs/layouts.md).
"""
from __future__ import annotations

import pathlib

import mido

OUT = pathlib.Path(__file__).resolve().parents[2] / "scores"
TPB = 480
C3, C4 = 48, 60
# scale degree -> pitch above C (major)
DEG = {d: 12 * (d // 7) + [0, 2, 4, 5, 7, 9, 11][d % 7] for d in range(-14, 22)}


def deg(d, base):
    return base + DEG[d]


def write(name, bpm, right, left, title, key="C"):
    """right/left: [(start_beat, length_beats, [pitches])]."""
    mid = mido.MidiFile(ticks_per_beat=TPB)
    meta = mido.MidiTrack([
        mido.MetaMessage("track_name", name=title, time=0),
        mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0),
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("key_signature", key=key, time=0),
    ])
    mid.tracks.append(meta)
    for tname, part, ch in (("Right hand", right, 0), ("Left hand", left, 1)):
        evs = []
        for start, length, pitches in part:
            for p in pitches:
                evs.append((round(start * TPB), 1, p))
                evs.append((round((start + length) * TPB) - 10, 0, p))  # small gap so repeats re-strike
        evs.sort(key=lambda e: (e[0], e[1]))
        tr = mido.MidiTrack([mido.MetaMessage("track_name", name=tname, time=0)])
        last = 0
        for tick, on, p in evs:
            tr.append(mido.Message("note_on" if on else "note_off", note=p, velocity=80 if on else 0,
                                   channel=ch, time=tick - last))
            last = tick
        mid.tracks.append(tr)
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.mid"
    mid.save(str(path))
    print(path.relative_to(OUT.parent))


def seq(items, start=0.0):
    """[(length, pitches)] laid end to end -> [(start, length, pitches)]."""
    out, t = [], start
    for length, pitches in items:
        if pitches:
            out.append((t, length, pitches))
        t += length
    return out


def triad(d, base):  # root-position triad on scale degree d
    return [deg(d, base), deg(d + 2, base), deg(d + 4, base)]


def main():
    # 01: triads as windows of three home-row keys. Right: J K L (I), H J K (vi), K L ; (iii), L ; ' (V).
    # Left: S D F (I), A S D (vi), D F G (iii), X F G (V as D G B, the left hand has no root-position V).
    r_chords = [triad(0, C4), triad(-2, C4), triad(2, C4), triad(4, C4), triad(0, C4)]
    l_chords = [triad(0, C3), triad(-2, C3), triad(2, C3), [deg(1, C3), deg(4, C3), deg(6, C3)], triad(0, C3)]
    lens = [2, 2, 2, 2, 4]
    right = seq(zip(lens, r_chords)) + seq(zip(lens, r_chords), start=24)
    left = seq(zip(lens, l_chords), start=12) + seq(zip(lens, l_chords), start=24)
    write("01_home_triads", 72, right, left, "Home-row triads: right, left, together")

    # 02: the scale as a zigzag between home and bottom rows: J M K , L . ; / and S X D C F V G B.
    up_down = list(range(0, 8)) + list(range(6, -1, -1))
    right = seq([(1, [deg(d, C4)]) for d in up_down])
    left = seq([(1, [deg(d, C3)]) for d in up_down], start=16)
    right += seq([(1, [deg(d, C4)]) for d in up_down], start=32)
    left += seq([(1, [deg(d, C3)]) for d in up_down], start=32)
    write("02_scale_zigzag", 80, right, left, "C major scale: right, left, both in octaves")

    # 03: broken chords I IV V I. Right: J K L K | , . / . | L ; ' ; | J K L (J).
    # Left: S D F D | C V B V | X F G F | S D F.
    def broken(chord):
        return [(1, [chord[0]]), (1, [chord[1]]), (1, [chord[2]]), (1, [chord[1]])]
    r = [triad(0, C4), triad(3, C4), triad(4, C4)]
    l = [triad(0, C3), triad(3, C3), [deg(1, C3), deg(4, C3), deg(6, C3)]]
    right = seq(sum((broken(c) for c in r), []) + [(4, triad(0, C4))])
    left = seq(sum((broken(c) for c in l), []) + [(4, triad(0, C3))], start=16)
    right += seq(sum((broken(c) for c in r), []) + [(4, triad(0, C4))], start=32)
    left += seq(sum((broken(c) for c in l), []) + [(4, triad(0, C3))], start=32)
    write("03_arpeggios", 80, right, left, "Broken chords I IV V I: right, left, together")

    # 04: voice leading I - IV64 - V6 - I. Right: J K L -> J , . -> N M L -> J K L; left bass S, C, F, S.
    r = [triad(0, C4), [deg(0, C4), deg(3, C4), deg(5, C4)], [deg(-1, C4), deg(1, C4), deg(4, C4)], triad(0, C4)]
    l = [[deg(0, C3)], [deg(3, C3)], [deg(4, C3)], [deg(0, C3)]]
    right, left = [], []
    for rep in range(4):
        right += seq([(2, c) for c in r], start=rep * 8)
        left += seq([(2, c) for c in l], start=rep * 8)
    write("04_cadence", 72, right, left, "Cadence I-IV64-V6-I with bass")

    # 05: Ode to Joy (Beethoven, public domain), first two phrases; left hand holds I / V triads.
    E, F, G, D, C = (deg(d, C4) for d in (2, 3, 4, 1, 0))
    mel = [(1, [E]), (1, [E]), (1, [F]), (1, [G]), (1, [G]), (1, [F]), (1, [E]), (1, [D]),
           (1, [C]), (1, [C]), (1, [D]), (1, [E]), (1.5, [E]), (0.5, [D]), (2, [D]),
           (1, [E]), (1, [E]), (1, [F]), (1, [G]), (1, [G]), (1, [F]), (1, [E]), (1, [D]),
           (1, [C]), (1, [C]), (1, [D]), (1, [E]), (1.5, [D]), (0.5, [C]), (2, [C])]
    I, V = triad(0, C3), [deg(1, C3), deg(4, C3), deg(6, C3)]
    acc = [(4, I), (4, V), (4, I), (4, V), (4, I), (4, V), (4, I), (2, V), (2, I)]
    write("05_ode_to_joy", 96, seq(mel), seq(acc), "Ode to Joy (Beethoven), melody + I/V triads")

    # 06: Canon in D (Pachelbel, public domain), simple version in D major: the trainer moves the tonic D onto S / J.
    # Left hand: the 8-chord ground I V vi iii IV I IV V as home/bottom-row windows, two beats each:
    #   S D F (D) | X F G (A, 2nd inversion) | A S D (Bm) | D F G (F#m) | C V B (G) | S D F | C V B | X F G
    # Right hand: violin line 1 (F# E D C# B A B C#), then line 2 (D C# B A G F# G E), then both together as dyads.
    D3, D4 = 50, 62
    ground = [(0, 2, 4), (1, 4, 6), (-2, 0, 2), (2, 4, 6), (3, 5, 7), (0, 2, 4), (3, 5, 7), (1, 4, 6)]
    line1 = [9, 8, 7, 6, 5, 4, 5, 6]
    line2 = [7, 6, 5, 4, 3, 2, 3, 1]
    left = seq([(2, [deg(d, D3) for d in ch]) for ch in ground] * 4 + [(4, [deg(d, D3) for d in (0, 2, 4)])])
    right = seq([(2, [deg(d, D4)]) for d in line1], start=16)
    right += seq([(2, [deg(d, D4)]) for d in line2], start=32)
    right += seq([(2, [deg(a, D4), deg(b, D4)]) for a, b in zip(line1, line2)], start=48)
    right += seq([(4, [deg(d, D4) for d in (0, 2, 4)])], start=64)
    write("06_canon_in_d", 66, right, left,
          "Canon in D (Pachelbel), simple: ground I-V-vi-iii-IV-I-IV-V, violin lines 1, 2, both", key="D")


if __name__ == "__main__":
    main()
