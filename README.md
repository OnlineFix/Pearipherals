# MagicSuite

**Make an Apple Magic Keyboard + Magic Trackpad 2 feel at home on Windows — one portable exe, no install, free.**

Windows pairs Apple's Bluetooth peripherals fine, but leaves them half-broken:
the trackpad acts as a dumb 2-button mouse and the keyboard's F-row does
nothing Mac-like. The paid tools fix this behind a license. MagicSuite is the
free, open-source alternative.

## What it does

**Magic Keyboard — Mac-style function row**

| Key | Action |
|-----|--------|
| F1 / F2 | Display brightness down / up (Apple Studio Display USB → DDC/CI → software dim, first that works) |
| F3 | Task View (Mission Control) |
| F4 | Search (Spotlight) |
| F5 / F6 | Passthrough |
| F7 / F8 / F9 | Previous / Play-Pause / Next |
| F10 / F11 / F12 | Mute / Volume down / Volume up |

Hold **any modifier** (Ctrl/Alt/Shift/Win) to get the raw F-key —
Alt+F4, Ctrl+F5 etc. all work unchanged. Toggle the whole layer from the
tray icon.

**Magic Trackpad — three-finger gestures that actually work**

The Magic Trackpad 2's Bluetooth driver reports contacts one at a time, which
breaks Windows' native 3-finger gesture detection entirely. MagicSuite
reassembles the touch data itself (Raw Input + per-contact tracking) and
gives you a choice of 3-finger behavior from the tray:

- **Swipes** (default, mac-like navigation):
  - swipe **down** → minimize all windows
  - swipe **up** → restore them back
  - swipe **left/right** → app switcher (Task View)
- **Drag** — macOS-style three-finger drag: move windows, select text,
  with a grace period so you can lift and reposition mid-drag
- **Off** — hand the gesture back to Windows

Plus a **natural scrolling** toggle (note: Windows applies scroll direction
when the trackpad connects — flip the trackpad's power switch off/on after
toggling, or reboot).

**App behavior**

- Single portable exe, config sits next to it (`magicsuite.json`)
- First run: enables autostart + applies the touchpad settings the gestures
  need (originals backed up, restorable from the tray)
- Tray icon: every feature can be toggled or reverted; **Quit** stops everything
- Crash-resilient: auto-retries at logon, errors logged to `magicsuite.err.log`
- Single-instance guard — safe to double-launch
- Moving the exe? Run it once from the new location — autostart re-points itself

## Requirements

1. **Windows 10/11**, Magic Keyboard / Magic Trackpad 2 paired over Bluetooth
2. For the trackpad: the open-source
   [mac-precision-touchpad](https://github.com/imbushuo/mac-precision-touchpad)
   driver (signed, free) — this is what turns the trackpad into a real
   Windows Precision Touchpad with pointer + 2-finger scrolling. MagicSuite
   builds on top of it for everything the driver can't deliver.
   The keyboard features work without any driver.

## Quick start

1. Install the mac-precision-touchpad driver (trackpad only, once)
2. Download `MagicSuite.exe` from [Releases](../../releases) and put it
   anywhere (USB stick, Dropbox, `C:\Tools`, …)
3. Run it — done. It sets up autostart and the right touchpad settings on
   first launch, and lives in your tray.

> Windows SmartScreen may warn on first run (unsigned exe) — click
> "More info" → "Run anyway". You can always build it from source instead.

## Uninstall

Tray → untick **Start with Windows** → **Touchpad settings → Restore Windows
defaults** → **Quit** → delete the exe. Nothing else is left behind.

## Building from source

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pyinstaller --onefile --windowed --name MagicSuite --icon magicsuite.ico --hidden-import pystray._win32 magicsuite.py
```

The exe lands in `dist\MagicSuite.exe`. Or just run `build.bat`.

## How it works (for the curious)

- **F-row**: a low-level keyboard hook (`WH_KEYBOARD_LL`) intercepts F1–F12,
  swallows them, and injects media/brightness actions. Modifier-held presses
  pass through untouched. Injected events are tagged so the hook never loops.
- **Brightness**: tries Apple Studio Display USB HID (protocol from
  [asdbctl](https://github.com/juliuszint/asdbctl)), then DDC/CI via
  `dxva2.dll`, then falls back to GPU gamma-ramp dimming — so it works on
  basically any monitor.
- **Gestures**: registers Raw Input for the Precision Touchpad usage
  (0x0D/0x05) with `RIDEV_INPUTSINK` and parses per-contact X/Y/tip through
  `HidP_*`. Because the Bluetooth driver reports one contact per HID report
  (which is why native Windows 3-finger gestures never fire), contacts are
  reassembled in a rolling table keyed by contact ID with freshness/age
  gates against ghost contacts. A state machine
  (idle → armed → fired / dragging → grace) turns that into swipes or drag,
  and a low-level mouse hook freezes the leaked pointer motion while 3
  fingers are down. Actions go out via `SendInput`. No kernel code, no
  admin rights.

## Known limitations

- Scroll direction changes need a trackpad reconnect (Windows caches the
  setting at device init — nothing an app can do about it)
- 4-finger gestures aren't handled (yet)
- The Fn key itself is invisible to Windows (Apple vendor-page only over
  Bluetooth) — that's why the F-row layer exists

## License

MIT
