# MonsGeek FUN68 HE vendor protocol (RY5088)

Sources: [monsgeek-akko-linux](https://github.com/echtzeit-solutions/monsgeek-akko-linux) `docs/PROTOCOL.md`
and Rust driver, [ry5088-flasher](https://github.com/dot-agi/ry5088-flasher) `docs/`. Verified live on this unit
on 2026-11-14 as noted.

## Device
- `3151:5030` "Monsgeek Multi-modes Keyboard", bcdDevice 5.04. PID 0x5030 is shared by many RY5088 models;
  the model is identified by `GET_USB_VERSION 0x8F`: reply `8f fb 0a 00 00 00 00 04 05` → dev_id 0x0AFB = 2811
  (`ry5088_akko_fun68_8k_8k_3m`), version 0x0504. ✅
- Interface 0: boot keyboard (hidraw4). Interface 1 (hidraw5): consumer (ID 3), NKRO (ID 1), mouse (ID 6) and
  **vendor input, usage page 0xFFFF usage 1, report ID 5, 31 bytes** (events). Interface 2 (hidraw7): **vendor
  config, usage page 0xFFFF usage 2, 64-byte Feature report, ID 0**.

## Config commands
`SET_FEATURE [cmd a1..a6 chk ...]`, `chk = 0xFF - sum(bytes 0..6)` (LED cmds 0x07/0x08/0x87/0x88: checksum at
byte 8 over bytes 0..7). Read back with `GET_FEATURE`; byte 0 echoes the command for most GETs, but paged reads
(`0x8A`, `0x90`, `0xE5`) return raw data with no echo, so a stale buffer is possible — read twice and compare.
GET = SET | 0x80.

| cmd | meaning | tested |
|---|---|---|
| `0x8F` | dev_id (u16 LE at 1..2) + version (u16 LE at 7..8) | ✅ |
| `0x83` / `0x84` / `0x89` | polling rate (0 = 8 kHz) / active profile (0) / keyboard options | ✅ |
| `0x1B 01` / `0x1B 00` | depth report on / off (runtime, acked by echo `1b 01`) | ✅ |
| `0x8A [profile FF page layer]` | keymatrix, 8 pages × 16 entries × 4 B, index = col·6 + row | ✅ read |
| `0x90 [sys profile FF page]` | Fn table, sys 0 = Win, 1 = Mac | ✅ read |
| `0x01` | **factory reset** — blocked | — |
| `0x7F` / `0xC5` | **enter bootloader (erases config)** / ISP prepare — blocked | — |
| `0x1C` / `0x1E` | min / max calibration — blocked | — |

## Depth stream
After `0x1B 01`, interface 1 sends `05 1B lo hi idx` per change: depth = `hi<<8 | lo` (raw), idx = matrix index.
No reports while idle. Works over USB on this firmware ✅ (monsgeek-akko-linux reports that v407 of model 2949
sends depth only over Bluetooth; this unit is not affected). Raw unit / bottom-out value: TODO, measure with
`viz.py` ("max raw" in the title). Reporting cadence: TODO (`min gap` in the title).

## Keymap (profile 0, 2026-11-14)
- Layers: 0 base (68 entries incl. Fn at slot 65 = `0A 01 00 00`), 1 alternate (Fn+Alt), 2/3 DKS outputs only;
  all of 1–3 empty. Layer 4 reads back a copy of layer 0 (no bounds check) — never use layer ids > 3.
- Fn Win: 41 entries, Fn Mac: 40 entries (see `magmidi.devices.fun68.keymap dump`). Unlike the C80, built-in Fn functions are a
  readable table.
- Entry `[type b1 b2 b3]`: 00 key/chord (up to 3 HID usages), 01 mouse, 03 consumer (b2|b3<<8), 08 profile,
  09 macro, 0A special fn (01 Fn, 02 Game Mode, 03 Win Lock, 05 OS, 08 BT pair, 0B NKRO, 0C Fn Lock, 17 RCtrl mod),
  0D LED control, 0E connection (BT1-3 / 2.4G / USB), 12 extended (seen `12 00 E3 2C` = Cmd+Space), 15 gamepad.
  `00000000` = disabled in layer 0, transparent in layers 1–3 and Fn.
