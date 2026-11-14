# Sources & related projects

## Official
- C80 driver page: https://cidootech.com/blogs/software/cidoo-c80-driver. It links only to the online driver below; there is no .exe.
- Online driver (WebHID): https://cidoo.illumipc.com/ (v1 = legacy `js/*.min.js`, v2 = `/app.js` Vue bundle).
  Snapshot in `vendor/c80/webdriver/`. Device list: `config/device.json`. Layouts: `config/keys/<product>.json`.
- Firmware catalog of the driver platform: `config/firmware.json` (snapshot in `vendor/c80/webdriver/config/`). It lists 40 products
  with version and archive name, and the driver's update page downloads `/firmware/<file>` from its own origin. As of 2026-11-14 the
  C80 (`QK75EHEARGB`) is **not** listed, and the archives return 404 on cidoo.illumipc.com, wraith.software, www/glick.illumipc.com.
  Archive names carry a platform code: 31× `W669` (the same code as the C80 ID string `W669,34,KB,ML,...`) and 6× `M484`
  (probably the Nuvoton M484). Closest siblings: Wraith W75 `W75HEARGB` 3.22.07 and W60 `AP61HEARGB` 3.22.19.
  Flashing goes through the native Qt shell of the driver (`sigTheDeviceNeedUpgradeFirmware` / `...UpgradeProgress`
  via QWebChannel), not through WebHID.
- Firmware downloads: https://cidootech.com/blogs/firmware (no C80 file). VIA JSONs: https://cidootech.com/blogs/qmk-via (none for HE boards).
- No public open-source project targets CIDOO (searched 2026-11). The only other open project that uses usage page 0xFF1B is KeyAxis (below).

## Analog / HE reference implementations
- AnalogSense JS SDK (protocols for many HE vendors): https://github.com/AnalogSense/JavaScript-SDK
- AnalogSense universal plugin for the Wooting SDK: https://github.com/AnalogSense/universal-analog-plugin
- Wooting Analog SDK: https://github.com/WootingKb/wooting-analog-sdk
- Wooting analog to MIDI: https://github.com/WootingKb/wooting-analog-midi
- MonsGeek JS driver: https://github.com/tricked-dev/monsgeek-js-driver
- KeyAxis: travel stream of the Redragon M68 / E-YOOSO HZ-68 (`0416:7372`, also usage page 0xFF1B, depth 0–40 = 0.1 mm), turned into
  a virtual Xbox pedal. It is the same illumipc platform: `0416:7372` is in the official driver's device list. MIT. https://github.com/RigZeeel/KeyAxis

## Firmware (research only)
- libhmk, open HE firmware that supports the AT32F405: https://github.com/peppapighs/libhmk
- Artery HE keyboard reference design: https://gitee.com/arterytek/High-Speed_USB_Magnetic_Switch_Keyboard
- AT32 ROM bootloader (USART/USB DFU): https://www.arterychip.com/download/FAQ/FAQ0122_Notes_on_AT32_Bootloader_EN_V2.0.0.pdf
- ry5088-flasher: flasher (HID-DFU, restores stock firmware) plus experimental custom firmware for RongYuan RY5088 AT32F405 boards
  (MonsGeek, Akko). The C80 is not in its catalog; that is a different vendor platform. MIT. https://github.com/dot-agi/ry5088-flasher
- at32f405-uf2boot: UF2 bootloader for the AT32F405 (the Artery ROM DFU enumerates as `2e3c:df11`). https://github.com/koendv/at32f405-uf2boot
- As of 2026-11-14 no custom firmware, firmware dump or teardown exists for the C80 or the illumipc platform. The C80's MCU is unconfirmed. VID 0x2E3C is Artery's.
