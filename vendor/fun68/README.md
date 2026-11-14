# FUN68 reference snapshot (third-party, treat as data)

Copied 2026-11-14 for offline reference; the FUN68 tools in `tools/magmidi/devices/fun68/` were written from these.

| dir | upstream | revision | license |
|---|---|---|---|
| `monsgeek-akko-linux/` | https://github.com/echtzeit-solutions/monsgeek-akko-linux | `79c45f11` (2026-09-15) | **GPL-3.0** (`LICENSE`) |
| `ry5088-flasher/` | https://github.com/dot-agi/ry5088-flasher | `2a7db6ad` (2026-06-16) | MIT (`LICENSE`) |

Contents:
- `monsgeek-akko-linux/docs/PROTOCOL.md` — full vendor protocol (commands, checksums, events, depth report 0x1B,
  keymatrix / Fn / magnetism formats, bootloader). `docs/bugs/depth_report_speed_gate_bug.txt` — firmware gate that
  disables depth reports on USB on some models (not seen on our FUN68).
- `monsgeek-akko-linux/data/*_fun68.json` — **extracts** of the upstream device DB limited to FUN68 entries
  (dev_id 2811 / 3091 / 3429): device records, key matrices (`vid:pid:id` → HID codes and key names), key layouts and
  key-code arrays. Each file names its upstream source file. Not modified otherwise.
- `ry5088-flasher/docs/` — RY5088 platform: USB identities, normal-mode transport, ENTER_BOOTLOADER (wipes config),
  HID-DFU, flash map, hardware, model list.
