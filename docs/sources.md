# Sources & related projects

## Official
- C80 driver page: https://cidootech.com/blogs/software/cidoo-c80-driver. It links only to the online driver below; there is no .exe.
- Online driver (WebHID): https://cidoo.illumipc.com/ (v1 = legacy `js/*.min.js`, v2 = `/app.js` Vue bundle).
  Snapshot in `vendor/webdriver/`. Device list: `config/device.json`. Layouts: `config/keys/<product>.json`.
- Firmware downloads: https://cidootech.com/blogs/firmware (no C80 file). VIA JSONs: https://cidootech.com/blogs/qmk-via (none for HE boards).
- No public open-source project targets CIDOO or usage page 0xFF1B (searched 2026-11).

## Analog / HE reference implementations
- AnalogSense JS SDK (protocols for many HE vendors): https://github.com/AnalogSense/JavaScript-SDK
- AnalogSense universal plugin for the Wooting SDK: https://github.com/AnalogSense/universal-analog-plugin
- Wooting Analog SDK: https://github.com/WootingKb/wooting-analog-sdk
- Wooting analog to MIDI: https://github.com/WootingKb/wooting-analog-midi
- MonsGeek JS driver: https://github.com/tricked-dev/monsgeek-js-driver

## Firmware (research only)
- libhmk, open HE firmware that supports the AT32F405: https://github.com/peppapighs/libhmk
- Artery HE keyboard reference design: https://gitee.com/arterytek/High-Speed_USB_Magnetic_Switch_Keyboard
- AT32 ROM bootloader (USART/USB DFU): https://www.arterychip.com/download/FAQ/FAQ0122_Notes_on_AT32_Bootloader_EN_V2.0.0.pdf
- The C80's MCU is unconfirmed. VID 0x2E3C is Artery's.
