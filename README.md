# Magnetic MIDI

Reverse-engineered tools for Hall-effect (magnetic) keyboards: read per-key analog travel live and turn the
keyboard into a velocity-sensitive MIDI controller.

| device | id | protocol | travel stream | docs |
|---|---|---|---|---|
| CIDOO C80 | `2e3c:c368`, fw `QK75EHEARGB V3.22.00` | illumipc white-label (usage page 0xFF1B) | cmd `0x21` trigger test, 0.01 mm, ~1 ms | [docs/c80](docs/c80/) |
| MonsGeek FUN68 HE | `3151:5030`, dev_id 2811, fw 0x0504 | RongYuan RY5088 (usage page 0xFFFF, feature reports) | cmd `0x1B` depth report, 0–720 raw, ~1.4 ms | [docs/fun68](docs/fun68/) |
| CAROTMAS Mars68 PRO | `3151:5030`, dev_id 2431, fw 0x0306 | same RY5088 protocol as the FUN68 | cmd `0x1B`, 0–350 raw, ~0.13 ms | `devices/mars68/spec.py` |

The C80 hardware is no longer available (2026-11); its backend is kept but has not been re-tested since the merge.
Active development and testing are on the FUN68.

## Layout
- `tools/magmidi/` — shared core: `midi.py` (MIDI bridge), `layouts.py` (in-key note layouts, see
  [docs/layouts.md](docs/layouts.md)), `tui.py` (bridge view: keyboard + piano), `viz.py` (travel TUI),
  `velocity.py` (strike model), `colours.py` (`--light` colours), `bridge.py` (travel → MIDI core),
  `trainer.py` + `score.py` + `fit.py` (play-along trainer), `paths.py`; device backends in `devices/<name>/` (`spec.py` = common interface, plus transport, stream,
  layout, keymap, and `light.py` for the C80).
- `tools/scripts/c80/` — C80 research scripts (probe, raw stream logger, evdev cross-check, plugin keymap generator,
  SDK harness).
- `plugin/c80/` — Wooting Analog SDK plugin for the C80 (Rust, C ABI); see `plugin/c80/README.md`.
- `docs/<device>/` — USB/HID descriptors, vendor protocol, sources. `captures/<device>/` — logged streams and backups.
- `vendor/<device>/` — third-party snapshots, treat as data: `c80/webdriver/` (official C80 web driver, do not run it),
  `fun68/` (monsgeek-akko-linux protocol doc + FUN68 DB extracts, GPL-3.0; ry5088-flasher docs, MIT; see its README).

## Setup
```sh
python -m venv .venv && .venv/bin/pip install hidapi python-rtmidi evdev pyyaml jsbeautifier mido
```
`viz.py` and the keymap tools need only the standard library. `/dev/hidraw*` must be readable and writable
(udev: `KERNEL=="hidraw*", ATTRS{idVendor}=="2e3c|3151", TAG+="uaccess"`, or one rule per vendor), and grabbing
the keyboard needs the `input` group.

## Usage
`--device` defaults to `auto` (the first connected keyboard); pass `c80`, `fun68` or `mars68` to choose. The FUN68 and the Mars68 share a USB id and are told apart by the
dev_id from the read-only `GET_USB_VERSION 0x8F`; the FUN68 keymap/light tools only ever open dev_id 2811, and
`--light` is refused on the Mars68 (its LED writes are unverified).
```sh
python3 tools/viz.py [--device fun68]                              # live TUI: travel per key + strike velocity
PYTHONPATH=tools .venv/bin/python -m magmidi.midi -v               # virtual MIDI port named after the device
PYTHONPATH=tools .venv/bin/python -m magmidi.midi --tui --to FLUID # keyboard + piano view, output straight to FluidSynth
PYTHONPATH=tools .venv/bin/python -m magmidi.midi --scale minor    # in-key layout in another mode; --layout piano = old map
PYTHONPATH=tools .venv/bin/python -m magmidi.trainer              # list the exercises in scores/
PYTHONPATH=tools .venv/bin/python -m magmidi.trainer 05 --to FLUID [--mode game|demo] [--hands right]  # play-along trainer
.venv/bin/python tools/scripts/make_exercises.py                  # regenerate scores/*.mid
PYTHONPATH=tools .venv/bin/python -m magmidi.midi --light         # note keys lit for the session, restored on exit
PYTHONPATH=tools python3 -m magmidi.devices.c80.keymap dump [--changed] [-o km.yaml]   # read-only
PYTHONPATH=tools python3 -m magmidi.devices.c80.keymap set fn J F13   # remap one key (backup + verify)
PYTHONPATH=tools python3 -m magmidi.devices.c80.light show -v      # C80 lighting (read-only)
PYTHONPATH=tools python3 -m magmidi.devices.fun68.keymap dump [--changed] [--raw] [--profile N]  # read-only
PYTHONPATH=tools python3 -m magmidi.devices.fun68.light show [-v]  # FUN68 LED params + userpic slots (read-only)
.venv/bin/python tools/scripts/c80/probe_readonly.py              # C80 firmware id, status, trigger config
.venv/bin/python tools/scripts/c80/stream_probe.py trigger 20     # C80 raw travel log -> captures/c80/
python3 tools/scripts/depth_probe.py [--device fun68] 40          # record travel, per-key maxima + cadence (calibration)
```
`magmidi.midi` grabs the keyboard's evdev nodes so it doesn't type while you play (`--no-grab` disables this);
Esc on the keyboard quits. The default note layout is **thirds**: in-key, the tonic chord under the resting fingers
(left S D F, right J K L), adjacent home-row keys a third apart (3 adjacent keys = a triad), steps on the diagonals
to the bottom row, upper row = +1 octave, left hand an octave below the right; LAlt/RAlt held raise that hand by a
semitone. Theory and chord charts: [docs/layouts.md](docs/layouts.md). Space is the sustain pedal (`--pedal inverted|normal|off`; use `off` for bowed or
looped sounds such as a violin), inverted by default (sustain on while Space is up, pressing
it damps; `sustain_inverted: false` for a normal pedal). Arrows transpose by a semitone (Up/Right +, Down/Left −),
Shift+arrows by an octave; `--light` colours notes by scale degree (tonic orange, 3rd/5th white, other steps blue,
so they stay right after transposing), Space green, arrows/Shift/Alt amber. Connect the port with `aconnect` or pick it in your DAW. `--config file.yaml` overrides
`velocity.DEFAULTS`, `midi.COMMON` and the device's `spec.DEFAULTS` (note map by layout key name; thresholds
`vel_lo` / `vel_hi` / `release` as fractions of `full_travel`).

## Trainer
`magmidi.trainer` plays a MIDI score as falling notes onto a piano at the bottom of the terminal. Each note is
labelled with the computer key that plays it in the thirds layout, and `♯` means "hold that hand's Alt".

The score is fitted to the layout:
- **Key:** taken from the key signature if there is one. Otherwise it is the diatonic collection that covers the
  most notes, with major vs minor decided by the final bass note.
- **Transposition:** chosen so the layout's tonic matches the key.
- **Out-of-reach notes:** folded by octaves.
- **Hands:** split by track names (`right`/`left`, RH/LH), else two tracks by pitch, else at C4.

Modes (Tab cycles them while playing):
- **practice** waits at every chord until you play it, and counts wrong notes.
- **game** keeps the tempo and judges each note: perfect ≤45 ms, good ≤90, ok ≤150, else miss. Keys that match
  nothing count as wrong.
- **demo** (`--mode demo`) plays the whole score by itself, at the pitches the layout produces, and lights the
  piano keys in hand colours, so you can watch which keys play what.

Parts you don't practise (`--hands right|left`) play by themselves on MIDI channel 2.

Keys:
- ←/→: previous/next bar
- Shift+←: back to the start
- ↑/↓: speed ±10%
- Enter: pause
- Backspace: restart and clear the score
- Esc: quit

`scores/` holds the exercises for the layout, written by `tools/scripts/make_exercises.py`:
- home-row triads
- the scale zigzag
- broken chords
- the I–IV⁶₄–V⁶–I cadence
- Ode to Joy with left-hand triads
- Canon in D (Pachelbel), simplified: the I–V–vi–iii–IV–I–IV–V ground as left-hand triads, then the two
  violin lines, separately and together. It is in D major, so the trainer moves the tonic onto S/J.

## Safety
Each transport refuses commands that reset or brick the keyboard and, by default, allows only verified ones:
- C80 (`devices/c80/transport.py`): blocks `0x0B` (bootloader) and `0x14` (reset / factory reset).
- FUN68 (`devices/fun68/transport.py`): blocks `0x01` (factory reset), `0x7F` (bootloader, wipes config), `0xC5`,
  `0x1C`/`0x1E` (calibration), `0x30`/`0x31`. The only writes allowed are `0x07` (LED params) and `0x0C` (userpic),
  each with range-checked arguments; `--light` uses userpic slot 4 and restores the LED params on exit. Never request FUN68 keymatrix layers > 3 (no bounds check in firmware).

Firmware work is research-only for now.
