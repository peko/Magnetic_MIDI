# CAROTMAS Mars68 PRO Wireless

A 68-key Hall-effect keyboard on the RongYuan RY5088 platform, the same platform as the MonsGeek FUN68. It speaks
the same vendor protocol (see [docs/fun68](../fun68/)), and its backend is `tools/magmidi/devices/mars68`.

| | |
|---|---|
| USB | `3151:5030`, name "CAROTMAS Mars68 PRO Wireless". The FUN68 shares this id. |
| model | dev_id **2431** (0x097F) from the read-only `GET_USB_VERSION 0x8F`; firmware 0x0306 |
| vendor DB | not in the monsgeek-akko-linux device database |
| interfaces | config = vendor 0xFFFF/0x02 (64-byte feature reports), events = vendor 0xFFFF/0x01 |
| depth stream | `0x1B` on/off, `05 1B lo hi idx`: **0..350 raw**, consecutive reports ~0.13 ms apart while a key moves |
| matrix | identical to the FUN68 (index = col·6 + row), checked by key presses and by the keymap dump (2026-11-18) |

The only difference from the FUN68 stock keymap is matrix slot 85 (top right): **Insert** here, Home on the FUN68.
Variants: the "Mars68 SE" has no backlight. The manual says the SE, the plain Mars68 and the Mars68 Pro are
wired-only, while the "Mars68 Pro Wireless" (this one) adds 2.4 GHz and Bluetooth.

## Fn table read from the keyboard

`magmidi.devices.fun68.keymap dump --model mars68` reads GET_FN `0x90` (read-only). Profile 0, Windows table:

| Fn + | stored entry | action (manual) |
|---|---|---|
| Esc | `00 00 35 00` | `` ` `` / `~` |
| 1 … 0, -, = | `00 00 3A..45 00` | F1 … F12 |
| Q / W / E | `0E 00 00..02 00` | Bluetooth device 1 / 2 / 3 (hold 3 s: pair) |
| Y | `0E 00 05 00` | 2.4 GHz (hold 3 s: pair) |
| Space | `0A 08 00 00` | BT pairing (not in the manual) |
| A / S | `0A 05 00/01 00` | Windows / Mac layout (hold 3 s) |
| LWin | `0A 03 00 00` | Win lock (Windows table only) |
| Backspace | `0A 0C 00 00` | **backlight off**; indicator lights stay on |
| [ | `0D 01 00 00` | next lighting effect |
| ] | `0D 05 01 00` | **next single colour** |
| ↑ / ↓ | `0D 02 01/02 00` | brightness + / − |
| ← / → | `0D 03 01/02 00` | effect speed **slower / faster** |
| RAlt | `00 00 01 00` | opens the second Fn layer: Fn+RAlt+key (media, below) |

The Mac table is the same without Win lock.

**Corrections to the labels from monsgeek-akko-linux.** The manual reads three codes differently, and `keymap.py`
now uses the manual's meaning:
- `0A 0C`: manual says backlight off; monsgeek says "Fn Lock".
- `0D 05`: manual says colour; monsgeek says "direction".
- `0D 03 01/02`: manual says slower/faster; monsgeek says faster/slower. The stored speed value is inverted, so
  `01` raises the value and slows the effect.

## From the printed manual (Chinese, translated)

Photos are in [manual/](manual/).

**Fn + RAlt + key (second layer):**

| key | Windows | Mac |
|---|---|---|
| 1 | My Computer | screen brightness − |
| 2 | browser home | screen brightness + |
| 3 | mail | show all windows (Mission Control) |
| 4 | calculator | task control (Launchpad / Mission Control) |
| 5 | media player | media player |
| 6 | stop | stop |
| 7 / 8 / 9 | previous / play-pause / next track | same |
| 0 / - / = | mute / volume − / volume + | same |

**Factory reset.** Hold **Fn + RAlt + Esc for 3 s**. All backlights flash white three times, and every user setting
returns to factory defaults; a Mac-mode keyboard also switches back to Windows. The MIDI bridge uses RAlt as the
right-hand sharp key and Esc as the quit key. Pressing both is harmless on its own, but not while Fn is held.

**OS layout.** Windows is the default.
- Fn+A held 3 s: Windows layout.
- Fn+S held 3 s: Mac layout.

Either switch is confirmed by three white flashes. Holding Fn lights every key that has an Fn function.

**Lighting:**
- **Fn+[:** cycles the effects. The default is "flowing light"; there are 18 effects plus 4 custom ones. After the
  last one the backlight turns off.
- **Fn+]:** single colour.
- **Indicators:** CapsLock (white), and Win lock (Fn+Win, white, off by default).
- **Fn+Backspace:** turns the backlight off; the indicators keep working.
- **Fn+↑ / Fn+↓:** brightness in steps 0-25-50-75-100 % (default 100 %).
- **Fn+← / Fn+→:** effect speed, slower / faster, 5 steps (default step 4).

Hitting a limit is confirmed by three white flashes.

**Connection (Mars68 Pro Wireless).** A 3-position switch selects Bluetooth / wired (middle) / 2.4 GHz.

Bluetooth:
- Fn+Q/W/E selects BT device 1/2/3. The key flashes cyan / pink / yellow slowly.
- Holding Fn+Q/W/E for 3 s pairs; the key flashes fast.
- Pairing stops after 1 min without a connection.
- While reconnecting the key flashes red slowly; the keyboard sleeps after 30 s without a connection.

2.4 GHz:
- With the switch at 2.4 GHz, Y flashes blue slowly while reconnecting.
- Holding Fn+Y for 3 s pairs.
- Pairing stops after 1 min.

After 3 min idle when connected, the keyboard sleeps; any key wakes it.

**General:**
- Settings survive power-off.
- The keyboard sleeps and wakes with the computer.
- It switches between 6-key and N-key rollover automatically.
- The manual recommends a USB 2.0 port.

## Safety

Use only the read-only commands listed as safe in `devices/fun68/transport.py`. Do not send the factory reset or
bootloader commands. LED writes (`0x07`, `0x0C`) go to flash and are not verified on this model, so the Mars68 spec
refuses `--light`.
