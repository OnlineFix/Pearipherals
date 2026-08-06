# Pearipherals continuation plan — 2026-08-06

## Provenance

Continuation of Hermes Desktop session `20260806_002133_eb6a1e` (Pearipherals App Issues and Fixes). Active repository: `C:\Users\keksa\Desktop\MagicSuite`. The old `C:\Users\keksa\magictb` location is legacy/reference only.

Current Git state at handoff:
- Branch: `main`, tracking `origin/main`
- Modified: `pearipherals.py`
- Untracked: `pearipherals_core.py`, `tests/`
- HEAD: `41e4324 Tell the user what first run just did`
- Do not discard the worktree; it contains the previous session's fixes.

## Verified current baseline

The complete suite was rerun correctly from the repository root on 2026-08-06:

```text
python -m unittest discover -s tests -p 'test_*.py' -v
Ran 15 tests — OK
```

`py_compile` passed for `pearipherals.py`, `pearipherals_core.py`, and `tests/test_core.py`. `git diff --check` passed. The previous direct execution of `tests/test_core.py` failed only because it placed `tests/` rather than the repository root on `sys.path`; use module discovery from the repo root.

## Already implemented in source

### Input/lag hardening
- Exactly three fresh, mature contacts are required for suppression.
- Stale contacts expire on an independent Windows timer.
- Parse errors fail open and release suppression/synthetic buttons.
- Temporary 2/4-contact churn does not re-arm duplicate swipes.
- Raw Input uses an event-driven `GetMessageW` loop instead of 4 ms polling.
- Global mouse hook is installed only during confirmed suppression.
- Raw Input is filtered to the Apple Magic Trackpad 2 PTP path.

### Apply/Restore hardening
- Mode-aware ownership of native vs custom three-finger gestures.
- Original registry values are durably backed up before mutation.
- Scroll direction is included in restore state.
- Missing original values are restored by deletion.
- Restore turns custom gestures off and retains failed entries for retry.
- Config writes are atomic; failures are surfaced.
- Tray state refreshes and Apply/Restore report success/failure.

### Battery foundations
- Pure parser/query/result-state/formatting logic for Apple report `0x90`.
- Exact HID vendor collections: VID `0x004c`, keyboard PID `0x0267`, trackpad PID `0x0265`, usage page `0xff00`, usage `0x14`.
- Probe previously returned `90 00 64` (100%) for both devices.
- Four battery tests currently pass.

## Remaining work, in order

1. **Audit the uncommitted diff before extending it**
   - Read `pearipherals.py`, `pearipherals_core.py`, and `tests/test_core.py`.
   - Confirm no duplicate/obsolete direct registry writers or always-on hooks remain.

2. **Finish production battery integration**
   - Add a worker that re-enumerates/opens/closes HID collections each cycle.
   - Poll slowly (multi-minute interval) with offline/backoff handling so devices are not kept awake.
   - Keep valid, not detected, unavailable/offline, malformed, and stale states distinct.
   - Add dynamic keyboard and trackpad tray labels and refresh safely across threads.
   - Add deterministic worker/UI tests with an injected HID backend; do not depend on live hardware in unit tests.

3. **Input edge hardening**
   - Add a large-position-jump guard for reused contact IDs, especially drag mode.
   - Keep drag opt-in/off by default.
   - Add regression tests for contact reuse, all-up debounce, and fail-open cleanup.

4. **Quality gates**
   - Run full unit tests, `py_compile`, `git diff --check`, and a focused static/code review.
   - Inspect dependency and frozen-path handling; config must live beside the EXE.

5. **Build and artifact verification**
   - Build the windowed one-file PyInstaller executable using the repository build process.
   - Verify imports/assets in the frozen artifact and config-sidecar behavior without first replacing the live installation.
   - Confirm no console window and single-instance behavior.

6. **Safe deployment**
   - Preserve user config/recovery data.
   - Replace/restart the installed `dist\Pearipherals.exe` only after artifact checks.
   - Verify the HKCU Run `Pearipherals` entry points to the intended EXE and only one logical app instance is active.
   - Never call `pnputil /restart-device`; if registry-backed PTP settings need refresh, ask the user to power-cycle the trackpad.

7. **User-assisted physical acceptance tests**
   - A/B pointer lag with Pearipherals exited vs running.
   - One-finger cursor movement and scrolling.
   - Three-finger down/up/left/right mappings.
   - Apply and Restore against live registry values.
   - Battery labels across connected/asleep/wake states.

8. **Finish cleanly**
   - Commit only after verified behavior.
   - Report exact test/build/deployment results and any remaining physical-test dependency.

## Safety boundary

Do not claim the currently installed app contains these fixes until a newly built EXE has been verified and deployed. Interactive physical testing must be coordinated with the user before captures or device power-cycles.
