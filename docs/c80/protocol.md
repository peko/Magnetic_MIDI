# CIDOO C80 vendor HID protocol

Source: static analysis of the official web driver `https://cidoo.illumipc.com/` (v2 `app.js`,
snapshot in `vendor/c80/webdriver/`, formatted copy in `vendor/c80/webdriver/pretty/app.pretty.js`)
plus live tests on firmware `QK75EHEARGB V3.22.00` (build Aug 20 2026).

The same white-label driver platform (internal OEM tag `mile_*`, ID string contains `ML`) is
used by Wraith, Qwerty, VARO, Press Play, AULA, Machenike and others, so this protocol
probably applies to their HE boards too.

## Transport
- Interface 2, usage page `0xFF1B`, usage `0x91`, report ID `1`, 63-byte IN/OUT (interrupt EP 0x84/0x05).
- hidraw write = `0x01` + 63 bytes. hidraw read = `0x01` + 63 bytes.
- Generic packet: `[0] cmd  [1] flag/sub  [2..3] page (BE)  [4] len  [5..] data`.
- The device only sends packets in reply to requests or while a stream is open.

## Key indexing
`index = row * 22 + col`, with 6 rows and 22 columns (132 slots, 82 used on the C80).
The layout (name, HID code, position) is in `vendor/c80/webdriver/config/keys/QK75EHEARGB.json`.
Mask format, used by several commands: 22 bytes, where bit `row` of byte `col` selects `row*22+col`.

## Commands

| cmd | request | reply / behaviour | tested |
|---|---|---|---|
| `0x01` | `[01]` | Device status. `data[0..17]` holds capability bits (see `BD.handle` case 1). The web driver also sends this every few seconds as a heartbeat. | ✅ |
| `0x0D` | `[0D]` | Several pages of ASCII CSV. Page 0 = `W669,34,KB,ML,QK75EHEARGB,V3.22.00` (product = field 4, fw = field 5). Page 1 = build date. | ✅ |
| `0x15` | `[15]` | Serial number, 32 bytes (all zeros on this unit). | ✅ |
| `0x18` flag `0x80`/`0x82` | `[18 80]` default layer, `[18 82]` Fn layer | Keymap read: 10 pages `[18 80 page_hi page_lo len, 4 B × 14 keys]` (last page len 0x18), key index = `14*page + i` (= `row*22+col`). Entry = `code1 hid code3 code4`; **`00000000` = not remapped**. See below. | ✅ read |
| `0x21` sub `0x04` | `[21 00 00 00 18 04]` | Trigger config. `max = d[9]<<8 \| d[6]` = 340, unit raw `d[7]`. With high precision, travel units are 0.01 mm (0–3.40 mm). | ✅ |
| `0x21` sub `0x02` | `[21 00 00 00 18 02 mask[22]]` | **Opens the live travel stream** (trigger test). The keyboard acknowledges with `21 00 00 00 01 00`, then sends `21 .. .. .. 05 01 row col travel_lo travel_hi` each time a key's travel changes. | ✅ |
| `0x21` sub `0x03` | `[21 00 00 00 18 03]` | Closes the trigger test. | ✅ |
| `0x21` sub `0x05` | `[21 00 00 00 18 05 row col]` | Per-key trigger settings (mode, travel, RT intervals). | — |
| `0x23` | `[23 00 00 00 00 01]` / `…00` | Opens / closes the raw ADC stream: 6 packets per frame (`d[3]` = row, **1-based**), 22 × u16 BE values. Idle level is ~2400–2600. One frame every ~20 ms (≈50 Hz). | ✅ |
| `0x0B` | — | **ENTER BOOTLOADER. Do not send.** | blocked |
| `0x14` | — | `[14 00 00 00 01 01]` reboots the keyboard. `[14 02]` is a **factory reset.** `[14 02 ..]` is also the sleep timer. | blocked |

Other command codes seen in the bundle but not yet exercised: `0x02/0x07/0x08/0x09/0x0A` (lighting),
`0x0E` (Fn-editable keys), `0x18` flag 0/2 (keymap write, see below), `0x19` (macros), `0x20` (app function trigger),
`0x22` (advanced keys: DKS/MT/TGL/SOCD), `0x24` (PRCS power), `0x25` (switch type list),
`0x26` (dead band), `0x21` subs `0x07/0x08/0x0F` (calibration), `0x09` (poll rate), `0x11/0x12` (profile).

## Live travel stream: measurements
- Travel is reported in 0.01 mm, from 0 to 340 at the bottom.
- Packets arrive only when travel changes. During movement they come every ~1 ms (fastest observed gap 0.1 ms).
- Time to go from 0.4 to 2.0 mm across 82 strokes: min ≈ 0 (a single sample jumps past both thresholds), p25 6 ms, median 9 ms, p75 15 ms, slowest ~490 ms.
  That range is wide enough for a usable velocity curve.
- A fast stroke can jump from 0 straight to about 1.5 mm in one sample.
- The stream kept running for 60 s without a heartbeat, but `tools/magmidi/devices/c80/stream.py` sends `0x01` every 2 s anyway.
- While the stream is open, normal HID key reports keep arriving on interfaces 0 and 1.

## Keymap entries (`0x18`)
Each key takes 4 bytes `code1, hid, code3, code4`. `code1` is the action type. The names come from the driver's
`config/keys.json` (snapshot in `vendor/c80/webdriver/config/keys.json`; all fields there are hex).

| code1 | meaning | fields |
|---|---|---|
| `00` | keyboard usage | `hid` = HID usage (the driver's reader also treats `00 FA` as Fn) |
| `01` | **Fn (momentary layer key)** | `01 00 00 00`. Not offered by the driver UI, but writing it to R-Alt in the default layer made R-Alt a second Fn (tested 2026-11-14: R-Alt+J gave the Fn-layer action, R-Alt alone sent nothing). |
| `02`–`06` | lighting mode/brightness/speed/direction/colour | `hid` = sub-action |
| `07` | consumer/media | `hid` = driver-internal media id (e.g. `10` Vol+, `13` Play/Pause) |
| `10` | macro | `code3` = macro slot |
| `11` | lock keyboard / Win / lights | `hid` |
| `12` | mouse | **stored as `12 code3 hid code4`** (button / wheel) |
| `13` | modifier combo | `hid` = modifier usage (E0..E7), `code3` = key usage |
| `18`/`19` | gamepad (classic / XInput) | `hid` = axis/button id |

Write: `[18 layer page_hi page_lo len data≤56]`, where **layer 0 = default and 2 = Fn** (read flag = `0x80 | layer`), sent for
pages 0..9 in turn. The keyboard acks each page with `[18 00|layer ...]`. Afterwards the driver polls `0x01` until bit 1 of
`reply[22]` (the storing flag) clears. The driver always sends the full 132×4-byte buffer (528 B), with zeros for every key that is not
remapped. Implemented in `magmidi.devices.c80.keymap set/restore` (read → backup JSON → write → read-back verify).
Tested on 2026-11-14 with `set fn J F13`: all 10 pages were acked, the storing flag was never observed (status polled for ~300 ms),
the read-back matched, and evdev showed Fn+J → `KEY_F13` while plain J stayed `KEY_J`.
The remap persisted across a USB replug (re-enumerated 19:50, dump still showed `J -> F13`), so the write reaches flash even
though the storing flag was never seen.
On this unit (2026-11-14) both layers are all zeros, so nothing is remapped. Firmware-built-in Fn functions (media on F-keys, etc.)
are not exposed by this command.

## Lighting (`0x07`, `0x09`, `0x0A`), tested 2026-11-14
| request | meaning |
|---|---|
| `[0A 00]` | Mode list: `data[0..n-5]` = mode ids (C80: `2 1 3 9 4 0 14 15 6 7 11 12 16 8`), the last two bytes = max speed and max brightness (4/4). The driver adds mode 10 (custom) if status `data[12]` bit 1 is set, and mode 100 (music) if bit 5 is set. |
| `[07 01]` | Config: `mode bri speed fgR fgG fgB bgR bgG bgB dir fullColor power timer`. **power 0 = on, 1 = off.** |
| `[07 00 00 00 0E <13 bytes>]` | Set config (no reply). |
| `[09 20]` | Current custom layer, in `reply[1]` (0/1). |
| `[09 80]` / `[09 81]` | Read the custom colours of layer 0/1: 8 pages of 18 keys × RGB, key = `18*page + i` (same index as the keymap). |
| `[09 L page_hi page_lo len rgb≤54]` | Write custom colours of layer L, pages 0..7. The keyboard acks each page with `[09 L ...]`. |

Factory custom layers on this unit: layer 0 = W A S D PgDn Down Right + slot 126 in red, layer 1 = all letters in blue.
`magmidi.devices.c80.light` / `magmidi.midi --light` read the config and the active layer, save `captures/c80/light_backup_*.json`, write the note colours, switch to mode 10,
and restore everything on exit. The custom colours are assumed to live in flash, so they are written once per session, not per note.
