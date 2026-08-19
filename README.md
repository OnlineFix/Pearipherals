# Pearipherals: Apple Magic Keyboard and Magic Trackpad 2 for Windows

**Pearipherals is a free, open-source Windows tray app for the Apple Magic
Keyboard and Magic Trackpad 2. It adds Mac-style function keys, three-finger
trackpad gestures, battery levels, natural scrolling, and display brightness
controls in one portable EXE.**

Windows can pair Apple's Bluetooth keyboard and trackpad, but support is limited.
The Magic Keyboard function row does not behave like it does on a Mac, Windows
cannot reliably recognize three-finger gestures from the Bluetooth Magic
Trackpad 2, and peripheral battery levels are hard to find. Pearipherals fills
those gaps without a subscription or proprietary driver.

## Features

| Feature | What it does |
|---|---|
| **"Tragic" Keyboard** | Mac-style function row for an Apple Magic Keyboard on Windows |
| **"Tragic" Trackpad** | Three-finger swipes or drag for Magic Trackpad 2 on Windows |
| **"Moodio" Display** | Brightness keys for Apple Studio Display and other monitors |
| **Battery monitoring** | Separate Magic Keyboard and Magic Trackpad battery levels in the tray |
| **Portable Windows app** | One EXE, local configuration, no account, no telemetry |

## "Tragic" Keyboard: Apple function keys on Windows

| Key | Action |
|---|---|
| F1 / F2 | Display brightness down / up through "Moodio" |
| F3 | Task View (Mission Control) |
| F4 | Windows Search (Spotlight) |
| F5 / F6 | Passthrough |
| F7 / F8 / F9 | Previous / Play-Pause / Next |
| F10 / F11 / F12 | Mute / Volume down / Volume up |

Hold **Ctrl, Alt, Shift, or Win** to send the original F-key. Shortcuts such as
Alt+F4 and Ctrl+F5 continue to work. You can turn the entire layer on or off from
the tray menu.

## "Tragic" Trackpad: Magic Trackpad 2 gestures on Windows

The Magic Trackpad 2 Bluetooth driver reports contacts one at a time. That stops
Windows from reliably detecting native three-finger gestures. "Tragic" Trackpad
reassembles the Raw Input contact data and provides three modes:

- **Swipes**
  - swipe **down** to minimize all windows
  - swipe **up** to restore minimized windows
  - swipe **left or right** to open Task View
- **Drag** for macOS-style three-finger dragging and text selection
- **Off** to disable Pearipherals' custom three-finger handling

Two-finger scrolling and normal pointer movement remain with the Windows
Precision Touchpad driver. Pearipherals also has a natural-scrolling toggle.
Windows reads that setting when the trackpad connects, so reconnect the trackpad
or reboot after changing it.

## "Moodio" Display: Apple Studio Display brightness on Windows

F1 and F2 try three brightness methods in order:

1. Apple Studio Display USB HID control
2. DDC/CI for compatible external monitors
3. GPU gamma-ramp dimming as a fallback

This gives the brightness keys a useful fallback on displays that do not expose
normal DDC controls. A video-only USB-C-to-DisplayPort cable cannot carry the
Studio Display's USB control data, so Pearipherals uses the available fallback in
that setup.

## Magic Keyboard and Magic Trackpad battery levels

Pearipherals shows the Apple Magic Keyboard and Magic Trackpad battery levels as
separate entries in the tray menu. Battery polling is slow and isolated, and the
app reopens devices for each poll instead of keeping Bluetooth HID handles open
while a device sleeps.

## Supported hardware and requirements

- Windows 10 or Windows 11
- Apple Magic Keyboard connected over Bluetooth
- Apple Magic Trackpad 2 connected over Bluetooth
- For trackpad pointer movement and two-finger scrolling, install the free,
  signed [mac-precision-touchpad](https://github.com/imbushuo/mac-precision-touchpad)
  driver once

The keyboard mappings, battery display, and monitor controls do not require that
trackpad driver.

## Download and quick start

1. For Magic Trackpad 2, install the mac-precision-touchpad driver.
2. Download `Pearipherals.exe` from [GitHub Releases](../../releases).
3. Put it anywhere you control, such as `C:\Tools\Pearipherals`.
4. Run it. Pearipherals enables autostart and applies the touchpad settings its
   gestures need on first launch, then shows a notification explaining what
   changed and where to undo it.

Pearipherals is portable. Its configuration and optional error log sit beside
the EXE as `pearipherals.json` and `pearipherals.err.log`.

## Windows security, unsigned builds, and Smart App Control

The current public Windows build is **unsigned**. Windows may identify it as an
unknown or untrusted publisher, Microsoft Defender SmartScreen may warn about it,
and Smart App Control may block it completely. Smart App Control does not offer a
per-app **Run anyway** exception. Do not disable a system-wide Windows security
feature just to run an unsigned build.

This warning is about publisher identity and software reputation; it is not by
itself a malware verdict. Pearipherals is public so you can inspect the source
and build it locally. Official release provenance is documented in the
[Code signing policy](CODE_SIGNING_POLICY.md).

The project applied for free open-source signing through SignPath Foundation.
The application was not accepted because Pearipherals is still new and does not
yet have enough established public usage. We plan to apply again after the user
base grows. Until trusted signing is available, every downloadable binary will
be labeled clearly as unsigned.

## App behavior and safety

- The tray menu controls the function-key layer, gesture mode, natural
  scrolling, autostart, and touchpad setting recovery.
- **Quit** stops input hooks, Raw Input handling, and battery polling.
- Original Windows touchpad values are backed up before Pearipherals changes
  them and can be restored from the tray.
- A single-instance guard makes accidental double launches safe.
- Startup failures are retried and written to `pearipherals.err.log`.
- Moving the EXE is supported: run it once from the new location and the
  autostart path updates.
- Pearipherals has no account, analytics, telemetry, or automatic uploads. See
  the [privacy policy](PRIVACY.md).

## Upgrade from MagicSuite

Run Pearipherals once from its new location. It imports the old
`magicsuite.json` settings and removes the legacy autostart entry. You can then
delete the old MagicSuite EXE.

## Uninstall

1. In the tray, untick **Start with Windows**.
2. Select **Touchpad settings → Restore original Windows settings**.
3. Select **Quit**.
4. Delete `Pearipherals.exe` and its adjacent runtime files, if present:
   `pearipherals.json` and `pearipherals.err.log`.

This removes Pearipherals, its autostart entry, and its local configuration/log.
The Restore action replays the Windows touchpad values backed up before
Pearipherals first managed them.

## Build Pearipherals from source

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set PEARIPHERALS_VERSION=1.2.0
build.bat
```

The portable Windows executable is written to `dist\Pearipherals.exe`. The
release workflow uses a complete hash-locked dependency set and adds Windows
product/version metadata before signing submission.

## How Pearipherals works

- **Keyboard function row:** a low-level keyboard hook (`WH_KEYBOARD_LL`)
  intercepts F1-F12 and injects the chosen media, brightness, or Windows action.
  Modifier-held presses pass through untouched. Injected events are tagged so
  the hook cannot loop.
- **Display brightness:** Apple Studio Display USB HID is tried first, followed
  by DDC/CI through `dxva2.dll`, then GPU gamma-ramp dimming.
- **Trackpad gestures:** Raw Input is registered for the Precision Touchpad usage
  (`0x0D/0x05`). Pearipherals parses contact data through `HidP_*`, filters
  padding and stale contacts, and feeds stable contacts into its gesture state
  machine. A low-level mouse hook suppresses leaked pointer motion only while a
  valid custom gesture owns the input.
- **Battery monitoring:** Apple vendor HID battery reports are queried separately
  for the keyboard and trackpad, then published to the Windows tray thread.

Pearipherals uses no kernel code and does not require administrator rights.

## FAQ

### Does Apple Magic Trackpad 2 work on Windows 11?

Yes. The mac-precision-touchpad driver provides normal Windows Precision
Touchpad pointer movement and two-finger scrolling. Pearipherals adds the custom
three-finger gestures, natural-scrolling control, and battery display that the
Bluetooth setup does not provide reliably by itself.

### Can Apple Magic Keyboard function keys work like a Mac on Windows?

Pearipherals maps F1-F12 to brightness, Task View, Search, media, and volume.
Holding Ctrl, Alt, Shift, or Win sends the normal F-key instead.

### Can Windows show Magic Keyboard and Magic Trackpad battery levels?

Pearipherals displays separate battery values for supported Apple Magic Keyboard
and Magic Trackpad devices in its tray menu.

### Is Pearipherals free and open source?

Yes. Pearipherals uses the MIT license, has no paid tier, and does not collect or
transmit personal data.

### Why does Windows say the publisher is unknown or untrusted?

The current EXE is not signed by a publicly trusted code-signing certificate.
Windows therefore cannot verify its publisher identity or reputation. Read the
[Windows security section](#windows-security-unsigned-builds-and-smart-app-control)
before downloading it.

## Known limitations

- Natural-scroll changes require a trackpad reconnect or reboot because Windows
  caches the setting when the device initializes.
- Four-finger gestures are not handled yet.
- The Magic Keyboard Fn key is not exposed to Windows over this Bluetooth path,
  so Pearipherals uses modifiers to access the original F-keys.
- Trusted public code signing is not available yet.

## Project links

- [Releases](../../releases)
- [Code signing policy](CODE_SIGNING_POLICY.md)
- [Privacy policy](PRIVACY.md)
- [MIT license](LICENSE)

---

Pearipherals is not affiliated with, endorsed by, or sponsored by Apple Inc.
Apple, Magic Keyboard, Magic Trackpad, and Studio Display are trademarks of
Apple Inc. and are used only to describe supported hardware.
