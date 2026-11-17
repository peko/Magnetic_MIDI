"""MIDI file -> flat note list with times in seconds, bar lines, hand split and key (for magmidi.trainer)."""
from __future__ import annotations

import dataclasses
import pathlib

# Krumhansl–Kessler key profiles (major, minor), index 0 = tonic.
KK_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KK_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]
PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclasses.dataclass
class Note:
    start: float  # seconds
    end: float
    pitch: int
    vel: int
    track: int
    channel: int
    hand: str = "right"  # "left" | "right"


@dataclasses.dataclass
class Score:
    name: str
    notes: list[Note]  # sorted by start, pitch
    bars: list[float]  # bar start times
    beat: float  # seconds per beat at the start
    duration: float
    key: tuple[int, str] | None  # (tonic pitch class, "major" | "minor") from a key signature, if any
    track_names: dict[int, str]

    def detect_key(self) -> tuple[int, str]:
        """Key signature if present. Otherwise: the diatonic collection that covers most of the music (fewest notes
        needing a sharp modifier on an in-key layout), then major vs relative minor by the final bass note, with
        Krumhansl–Kessler correlation as the tie-break."""
        if self.key:
            return self.key
        hist = [0.0] * 12
        for n in self.notes:
            hist[n.pitch % 12] += max(0.05, n.end - n.start)
        last = max(n.start for n in self.notes)
        final_bass = min((n for n in self.notes if n.start >= last - 0.05), key=lambda n: n.pitch).pitch % 12
        major = [0, 2, 4, 5, 7, 9, 11]
        best = None
        for m in range(12):  # major tonic of the collection
            cover = round(sum(hist[(m + i) % 12] for i in major), 6)
            for tonic, mode, prof in ((m, "major", KK_MAJOR), ((m + 9) % 12, "minor", KK_MINOR)):
                r = _corr([hist[(tonic + i) % 12] for i in range(12)], prof)
                cand = (cover, final_bass == tonic, r, tonic, mode)
                best = max(best, cand) if best else cand
        return best[3], best[4]


def _corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def parse_key(name: str) -> tuple[int, str]:
    """mido key_signature name ('C', 'F#', 'Bbm', ...) -> (pc, mode)."""
    mode = "minor" if name.endswith("m") else "major"
    root = name[:-1] if mode == "minor" else name
    pc = PC[root[0].upper()] + root[1:].count("#") - root[1:].count("b")
    return pc % 12, mode


def load(path: str | pathlib.Path) -> Score:
    import mido

    mid = mido.MidiFile(str(path))
    tpb = mid.ticks_per_beat
    tempos, sigs, key = [(0, 500000)], [(0, 4, 4)], None
    names: dict[int, str] = {}
    raw = []  # (on_tick, off_tick, pitch, vel, track, channel)
    for ti, track in enumerate(mid.tracks):
        tick, open_ = 0, {}
        for msg in track:
            tick += msg.time
            if msg.type == "set_tempo":
                tempos.append((tick, msg.tempo))
            elif msg.type == "time_signature":
                sigs.append((tick, msg.numerator, msg.denominator))
            elif msg.type == "key_signature" and key is None:
                key = parse_key(msg.key)
            elif msg.type == "track_name":
                names[ti] = msg.name
            elif msg.type == "note_on" and msg.velocity > 0:
                if msg.channel == 9:  # GM drums
                    continue
                open_.setdefault((msg.channel, msg.note), []).append((tick, msg.velocity))
            elif msg.type in ("note_off", "note_on"):
                stack = open_.get((msg.channel, msg.note))
                if stack:
                    on, vel = stack.pop(0)
                    raw.append((on, tick, msg.note, vel, ti, msg.channel))
    tempos = _dedupe(sorted(tempos))
    sigs = _dedupe(sorted(sigs))

    def secs(tick):
        t, last_tick, last_tempo = 0.0, 0, tempos[0][1]
        for tt, tempo in tempos[1:]:
            if tt >= tick:
                break
            t += (tt - last_tick) * last_tempo / tpb / 1e6
            last_tick, last_tempo = tt, tempo
        return t + (tick - last_tick) * last_tempo / tpb / 1e6

    notes = [Note(secs(a), secs(max(b, a + 1)), p, v, tr, ch) for a, b, p, v, tr, ch in raw]
    notes.sort(key=lambda n: (n.start, n.pitch))
    end_tick = max([b for _, b, *_ in raw] + [0])
    bars, tick, si = [], 0, 0
    while tick <= end_tick:
        while si + 1 < len(sigs) and sigs[si + 1][0] <= tick:
            si += 1
        _, num, den = sigs[si]
        bars.append(secs(tick))
        tick += num * tpb * 4 // den
    return Score(pathlib.Path(path).stem, notes, bars, tempos[0][1] / 1e6, secs(end_tick), key, names)


def _dedupe(events):
    out = {}
    for e in events:
        out[e[0]] = e  # last event at a tick wins
    return [out[k] for k in sorted(out)]


def split_hands(score: Score, split_note: int = 60):
    """Set Note.hand: by track names (right/left, RH/LH, treble/bass), else two tracks by mean pitch, else by pitch."""
    tracks = sorted({n.track for n in score.notes})
    by_name = {}
    for t in tracks:
        nm = score.track_names.get(t, "").lower()
        if any(w in nm for w in ("right", "rh", "treble", "melody", "upper")):
            by_name[t] = "right"
        elif any(w in nm for w in ("left", "lh", "bass", "lower")):
            by_name[t] = "left"
    if len(tracks) >= 2 and len(by_name) == len(tracks):
        hand_of = by_name
    elif len(tracks) == 2:
        mean = {t: sum(n.pitch for n in score.notes if n.track == t) / sum(1 for n in score.notes if n.track == t)
                for t in tracks}
        hi = max(tracks, key=lambda t: mean[t])
        hand_of = {t: ("right" if t == hi else "left") for t in tracks}
    else:
        hand_of = None
    for n in score.notes:
        n.hand = hand_of[n.track] if hand_of else ("right" if n.pitch >= split_note else "left")
