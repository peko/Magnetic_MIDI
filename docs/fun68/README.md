# MonsGeek FUN68 HE

- [protocol.md](protocol.md): vendor protocol (transport, commands, depth stream, keymap format), with what was
  verified on this unit.
- Code: `tools/magmidi/devices/fun68/`. Layout and stock HID map: `layout.py` (from monsgeek-akko-linux
  `data/device_matrices.json`, entry `12625:20528:2811`).
- Offline snapshot of the sources (with revisions and licenses): [vendor/fun68](../../vendor/fun68/README.md).
- Sources: [monsgeek-akko-linux](https://github.com/echtzeit-solutions/monsgeek-akko-linux) (protocol, device DB,
  depth monitoring), [ry5088-flasher](https://github.com/dot-agi/ry5088-flasher) (RY5088 platform, bootloader and
  dangerous opcodes).

Calibrated: bottom-out 720 raw, reports every ~1.4 ms while moving (see protocol.md). Open items: confirming the
raw unit in mm, lighting for `magmidi.midi --light`, keymap write.
