# Phase 4 result — Frozen build, deployment, and acceptance

## Status

**PASS_AWAITING_PHYSICAL_TESTS.** Phase 4 was executed directly from clean commit
`ec5103dbf8760d4027f154665691c3f9b451d0f2`. The source gate, staged frozen
build, artifact inspection, rollback preservation, targeted app stop,
deployment, restart, process/tray/error-log/single-instance/autostart checks all
passed. No device was restarted, power-cycled, or modified by this phase. The
only remaining checks require the user to physically operate the keyboard and
trackpad.

## Pre-build gate

From `C:/Users/keksa/Desktop/MagicSuite`:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

Result: exit `0`; `Ran 74 tests in 1.637s` — `OK`.

```text
.venv/Scripts/python.exe -m py_compile pearipherals.py pearipherals_core.py tests/test_core.py
```

Result: exit `0`; no output.

```text
git diff --check
git diff --cached --check
```

Result: exit `0`; no output. Initial Git state was clean on `main` at exact
commit `ec5103dbf8760d4027f154665691c3f9b451d0f2`.

Environment used: Python 3.11.15, PyInstaller 6.21.0, pystray 0.19.5,
Pillow 12.3.0, hidapi 0.15.0.

## Packaging inspection

- `build.bat` invokes PyInstaller with `--noconfirm --onefile --windowed`, name
  `Pearipherals`, `pearipherals.ico`, and hidden import `pystray._win32`.
- The generated ignored `Pearipherals.spec` confirmed one-file `EXE`,
  `console=False`, icon embedding, and hidden import `pystray._win32`.
- `requirements.txt` contains pystray 0.19.5, Pillow >=10.0, hidapi >=0.14,
  and PyInstaller >=6.0; installed versions are listed above.
- Frozen path handling is explicit: when `sys.frozen` is true, `APP_DIR` is the
  directory of `sys.executable`; `pearipherals.json` and
  `pearipherals.err.log` are siblings of the EXE. Source mode instead uses the
  source directory.
- Autostart in frozen mode quotes the absolute `sys.executable` path.
- The app uses named mutexes `Pearipherals_single_instance_v1` and legacy
  `MagicSuite_single_instance_v2`.
- Crash tracebacks append beside the EXE and startup retries `main()` up to five
  times. No console is requested.
- The tray image is generated at runtime with Pillow; `pearipherals.ico` is the
  embedded executable icon, so no runtime image sidecar is required.

## Staged build

An initial staging attempt used relative source/icon paths together with a
separate `--specpath`. PyInstaller resolved the icon relative to that spec
folder and exited `1` before producing a valid artifact:

```text
FileNotFoundError: Icon input file ...\build\phase4-stage\spec\pearipherals.ico not found
```

This did not touch `dist/Pearipherals.exe` or the running app. The corrected
successful command used absolute source/icon/staging paths:

```text
.venv/Scripts/pyinstaller.exe --noconfirm --clean --onefile --windowed --name Pearipherals --icon 'C:/Users/keksa/Desktop/MagicSuite/pearipherals.ico' --hidden-import pystray._win32 --distpath 'C:/Users/keksa/Desktop/MagicSuite/build/phase4-stage/dist' --workpath 'C:/Users/keksa/Desktop/MagicSuite/build/phase4-stage/work' --specpath 'C:/Users/keksa/Desktop/MagicSuite/build/phase4-stage/spec' 'C:/Users/keksa/Desktop/MagicSuite/pearipherals.py'
```

Result: exit `0`; `Build complete!`.

Verified staged artifact:

- Path: `C:\Users\keksa\Desktop\MagicSuite\build\phase4-stage\dist\Pearipherals.exe`
- Size: `19,197,807` bytes
- SHA-256: `C3C69B89A3A2F9A1E2B46B6396B477408E24A5383EED45B89C9A3A9A09BC5EB0`
- PE: x64 (`machine=0x8664`), PE32+ (`optional_magic=0x020B`), subsystem `2`
  (`WINDOWS_GUI`), confirming the windowed/no-console bootloader.

## Artifact checks before deployment

- Recursive PyInstaller archive inspection found `pearipherals_core`,
  `pystray._win32`, `pystray`, `PIL.Image`, `hid.cp311-win_amd64.pyd`,
  `tkinter`, and `_tkinter.pyd`.
- The PyInstaller warning file contained only expected optional/cross-platform
  misses (POSIX, GTK/X11, macOS, Java, optional Pillow plugins); no required
  Windows application import was missing.
- No `pearipherals.json` or `pearipherals.err.log` existed beside the staged
  artifact.
- Launching the staged EXE while the old live app held the global mutex exited
  `0` after extraction without creating staging sidecars or adding another
  process. This verified the frozen artifact could boot far enough to honor the
  shared single-instance guard without touching the live installation.
- Missing-sidecar and read-only behavior were inspected through the production
  path/persistence code rather than launching a second unmanaged instance:
  missing config selects defaults/first-run handling beside the EXE; an
  existing malformed or unreadable config raises recovery-required state,
  preserves the file, disables automatic writes, and logs beside the EXE.

## Preservation and rollback evidence

Before stopping or replacing the live app, these hash-verified rollback copies
were created:

`C:\Users\keksa\Desktop\MagicSuite\dist\rollback-phase4-ec5103d-20260806`

- Old `Pearipherals.exe`: `18,662,513` bytes; SHA-256
  `5DCE01DD546FA35F61C39FA329DA38202D4F9B0EF6F18F64DE59958004B89C43`.
- Original `pearipherals.json`: `374` bytes; SHA-256
  `14D4722B1B01F8E1897CD7D02D5B886D8D50776ADBE568D0E726D1A6843130E2`.
- No live crash log or legacy config/recovery sidecar existed to copy.

The original sidecar contained config version 4, mode `off`, classic scrolling,
`setup_done=true`, and the existing touchpad recovery backup. It was never
deleted or overwritten by deployment. On first start of the new executable,
the production v5 migration updated the live sidecar to 435 bytes, SHA-256
`5133FF6DB0AA3FB3245A1631BA638F7B7CBD5639F382558008E3D70757EC5D1C`,
while the exact pre-migration copy remains in the rollback directory. The
current mode remains `off`; no user preference was silently switched to drag or
swipes.

Rollback procedure if a physical test finds a critical regression: stop only
the current Pearipherals instance, copy the rollback EXE and JSON above back to
`dist`, and restart that EXE. The preserved hashes above provide verification.

## Stop, deploy, and runtime evidence

The previous logical app consisted of the expected PyInstaller parent/child
process pair at the intended live path: PIDs `12676` and `12696`. It was stopped
only by posting pystray's private `WM_STOP` (`1034`) to top-level windows owned
by those exact-path PIDs. Eleven targeted window posts were accepted, the pair
reached zero remaining processes within the 15-second bound, and no unrelated
process was selected.

The staged artifact was copied through a temporary sibling, hash-checked before
and after replacement, then installed at:

`C:\Users\keksa\Desktop\MagicSuite\dist\Pearipherals.exe`

Deployed evidence:

- Size: `19,197,807` bytes
- SHA-256: `C3C69B89A3A2F9A1E2B46B6396B477408E24A5383EED45B89C9A3A9A09BC5EB0`
- The original live config hash was still
  `14D4722B1B01F8E1897CD7D02D5B886D8D50776ADBE568D0E726D1A6843130E2`
  immediately after EXE replacement and before restart.

After restart and delayed re-check:

- Stable PyInstaller logical instance: parent PID `15980`, child PID `8532`,
  both from the intended deployed path, created 0.569 seconds apart during the
  same one-file launch, responding, and still present on the delayed check.
- Tray backend evidence: child PID `8532` owns two hidden windows of class
  `Pearipherals2463544391568SystemTrayIcon`, plus the expected
  `PearipheralsTFD` Raw Input window. The two pystray windows are the notification
  and menu windows created only after the Win32 tray backend initialized.
- Crash/error log: `dist/pearipherals.err.log` does not exist; no startup,
  battery-worker, config-recovery, or retry traceback was emitted.
- Single instance: launching `dist/Pearipherals.exe` again exited `0` in one
  second; process PIDs remained exactly `15980,8532` before and after.
- HKCU Run value `Pearipherals` is exactly
  `"C:\Users\keksa\Desktop\MagicSuite\dist\Pearipherals.exe"`.
- Live EXE hash and size remained identical to the staged artifact.

No `pnputil`, device restart, driver action, reconnect, power-cycle, or reboot
was invoked.

## Remaining user-assisted physical acceptance checks

These are the only remaining Phase 4 checks. The current saved gesture mode is
`off`, so enable **Swipes** before testing custom three-finger mappings.

### Smart App Control signing blocker

The deployed local PyInstaller executable is unsigned. Windows Code Integrity
event 3077 confirmed that Smart App Control rejected this exact EXE because it
did not meet signing-level requirements; this was not a malware detection.
Smart App Control has no per-app **Run anyway** exception. The user disabled SAC
to launch this build, and Windows now reports `SmartAppControlState=Off`,
`SAC_PreviousState=1`.

The selected permanent distribution path is free open-source signing through
SignPath Foundation. Repository preparation now includes an OSS code-signing
policy, privacy policy, a complete hash-locked release dependency set,
deterministic Windows version metadata, release metadata/security tests, and a
GitHub-hosted build/sign workflow that uploads the unsigned artifact before
SignPath submission. The hardened preparation passed an independent fail-closed
review, 81 tests, `py_compile`, clean isolated hash-locked install/build,
`actionlint`, and `zizmor` with no findings. Actual trusted signing remains
blocked on SignPath Foundation approval plus the organization/project/policy
configuration and API token issued after approval.

### Acceptance progress after reboot

- **Passed:** tray menu opens normally.
- **Passed:** separate keyboard and trackpad battery labels are visible; the user
  observed keyboard `100%` and trackpad `99%`.
- **Needs reproduction:** after one restart the trackpad produced no pointer and
  no cursor was visible until the user power-cycled the trackpad. Current
  post-recovery diagnostics show both Pearipherals processes responsive, the
  autostart process launched nine seconds after Explorer, saved gesture mode
  `off`, no `pearipherals.err.log`, the full Magic Trackpad PnP stack `OK`,
  `AmtPtpHidFilter` attached, and the Apple vendor HID collection enumerable.
  This currently points more strongly to a Bluetooth/PTP initialization race
  than active Pearipherals suppression, but the issue must be reproduced before
  acceptance can pass. If it recurs, exit Pearipherals before power-cycling the
  trackpad: pointer recovery on app exit implicates Pearipherals; no recovery
  until the trackpad reconnects implicates the Bluetooth/driver path.

1. Confirm the Pearipherals tray icon is visible (possibly under the tray
   overflow arrow); open it and confirm keyboard/trackpad battery labels appear.
2. A/B pointer lag: move one finger with Pearipherals running, use tray **Quit**
   and compare, then start `dist\Pearipherals.exe` again. Report whether the app
   adds any pointer lag or jumps.
3. With the app running, verify ordinary one-finger pointer movement and
   two-finger scrolling. Bottom-to-top finger motion must scroll the page down
   (classic direction). If the cached direction has not changed, use the
   trackpad power switch only when ready; the app will not restart it.
4. Tray → **Tragic Trackpad → Swipes**, then test once each:
   down = minimize all; up = restore all minimized windows; left/right = Task
   View. Confirm drag/select does not occur.
5. Tray → **Touchpad settings → Apply recommended settings**; confirm the status
   becomes applied and behavior remains correct after the user-controlled
   reconnect if Windows requires it.
6. Tray → **Touchpad settings → Restore original Windows settings**; confirm
   custom handling turns off and the status becomes original settings. Re-Apply
   and reselect Swipes afterward only if that is the desired final setup.
7. Observe keyboard and trackpad battery labels while awake, after one device
   sleeps, and after it wakes; confirm percentages/state recover without
   restarting the app.

### Two-finger false-third-contact hotfix — 2026-08-14

The user reported that two-finger scrolling was intermittently treated as a
three-finger contact. Two non-invasive Raw Input traces were captured while the
saved gesture mode was safely `off`; no device restart or hardware mutation was
performed. The first trace contained 718 sampled table states and stayed at
exactly two contacts. The transition/reposition trace contained 570 states
(`n=0`: 6, `n=1`: 475, `n=2`: 89) and exposed six retained rows for padding CID
`65535` at `(0, 0)`. Production already described CID 65535 as padding but only
rejected it when its coordinates exceeded 30000, so the zero-coordinate form
entered the rolling contact table and could arm or qualify false three-contact
state alongside two real contacts.

Strict TDD evidence:

1. `test_padding_contact_id_cannot_turn_two_fingers_into_three` was added first.
2. The focused discovery run failed as expected because `(7, 65535)` remained
   in the production touch table.
3. `_frame` now rejects CID `0xFFFF` at ingestion, before it can affect table
   cardinality, gesture arming, or pointer suppression.
4. The focused test passed, followed by the complete suite: `Ran 82 tests in
   1.828s` — `OK`. `py_compile`, working/staged diff checks, and trace replay
   filtering also passed; all six observed padding rows are rejected.

The corrected versioned one-file/windowed build used PyInstaller 6.21.0 and
version `1.2.0`. Staged artifact evidence:

- Path: `build/two-finger-fix-stage/dist/Pearipherals.exe`
- Size: `19,199,047` bytes
- SHA-256: `58DF87838DDB6D1263C804F8661E08221BA97BCDE1B9C2D35A97A9D163399D1B`
- x64 PE32+, subsystem 2 (`WINDOWS_GUI`), version metadata 1.2.0
- Required frozen imports present; warnings remained limited to expected
  optional/cross-platform modules
- Mutex launch against the old live app exited 0 without creating staging
  sidecars or another process

Before replacement, hash-verified rollback copies were saved under
`dist/rollback-two-finger-8a68cd8-20260814`:

- Previous EXE: `19,197,807` bytes, SHA-256
  `C3C69B89A3A2F9A1E2B46B6396B477408E24A5383EED45B89C9A3A9A09BC5EB0`
- Preserved config: `434` bytes, SHA-256
  `9096033E44497FA72E67545CF00CCB418932DA5C3858D93075D02D8BA3D50BFE`

Only the exact live Pearipherals parent/child pair (PIDs 15608/15636) was
stopped through its pystray windows. The verified artifact was deployed to
`dist/Pearipherals.exe`; the config hash stayed unchanged. Restart checks found
the expected responsive parent/child pair (PIDs 6320/7016), two initialized
`Pearipherals...SystemTrayIcon` windows, the `PearipheralsTFD` Raw Input window,
no error log, unchanged HKCU Run target, and no extra processes after a second
launch. Physical confirmation that two-finger scrolling no longer triggers
three-finger behavior remains required; the saved gesture mode is still `off`.

Do not mark these physical checks passed until the user reports their results.
