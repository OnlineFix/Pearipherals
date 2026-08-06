# Phase 1 result — Baseline audit and stabilization

## Status

**PASSED.** Extended hardening fixes completed after independent reviews found
additional concurrency, suppressor-lifecycle, hook-removal, config-recovery,
and late-hook cancellation defects. All implementation verification and the
final independent review passed. Pending the verified baseline commit only.

Phase scope was respected: no production battery polling, tray battery integration, build, deployment, device restart, or hardware interaction was performed.

## Files changed

- `pearipherals.py`
  - consolidated Precision Touchpad writes behind `TouchpadSettingsManager`;
  - retained mouse-hook installation only for qualified three-contact suppression;
  - added fail-open release on mode-off, Restore, parser failure, and Quit;
  - validated full Raw Input payloads before parsing;
  - declared pointer-sized Win32 return types for Raw Input window and mutex APIs;
  - corrected the swipe menu label to the implemented mappings.
  - routes mode switches and startup enforcement through durable fail-closed
    mode handling, checks synthetic mouse `SendInput`, keeps a failed LEFTUP
    retryable, and distinguishes a missing registry value from read failure;
  - resets suppression state after failed hook installation/message posting so
    later qualified input can retry; Quit performs bounded LEFTUP-only retries
    and notifies/logs any final shutdown failure;
  - generation-tags suppressor operations, revalidates request ownership and
    deadline before publishing a successful hook install, and immediately
    unhooks cancelled or stale late installs without losing a failed-unhook
    handle;
  - leaves first-run onboarding pending and suppresses its success toast when
    touchpad Apply fails.
- `pearipherals_core.py`
  - pure atomic JSON, battery-foundation, contact-quality, input-release, and reversible settings helpers;
  - persists backups with `tp_settings_applied=false` before registry mutation,
    marks Apply successful only after every write and the final save succeed,
    and rolls mode to off on read/write/enforcement failures without discarding
    recovery data;
  - serializes all in-process JSON saves and gives every save its own unique
    same-directory temporary file while retaining flush/fsync/replace cleanup;
  - performs two bounded LEFTUP retries independently of suppression and hook
    cleanup, returning the final persistent release error to the caller.
- `tests/test_core.py`
  - 44 deterministic tests covering persistence, settings recovery, mode-switch
    and startup write failures, missing registry values vs read errors, failed
    LEFTUP/retry cleanup, battery foundations, contact suppression, Win32 ABI
    source contracts, and fail-open input lifecycle, including concurrent saves,
    bounded Quit retries, hook/message-post retryability, onboarding failure,
    activation-timeout late installation, and disable/install races.
- `.hermes.md`, `.hermes/plans/*.md`
  - project context and multi-phase execution plans preserved in Git.
- `.hermes/plans/handoffs/phase-1-result.md`
  - this handoff.

## Audit findings and disposition

- Registry ownership: the only Precision Touchpad DWORD adapter is `TouchpadSettings._write`/`_delete`; Apply, enforce, natural-scroll changes, startup, and Restore all route through `TouchpadSettingsManager`. Other direct registry writes are limited to the separate HKCU Run autostart key and old-name cleanup.
- Hook lifecycle: `WH_MOUSE_LL` is installed only after exactly three contacts pass freshness and maturity gates. The idle pointer-suppressor thread has no installed mouse hook.
- Fail-open behavior: malformed/partial Raw Input, parser exceptions, mode-off, Restore, and Quit all attempt to clear contacts, disable suppression, and release an injected drag button. Cleanup continues even when an earlier cleanup callback fails.
- Restore/startup: Restore persists `three_finger_mode=off` and `tp_settings_applied=false` before registry replay. Startup enforcement is a no-op after a completed Restore; failed restore entries remain backed up for retry.
- Gesture ownership: custom mode is persisted only through a fail-closed wrapper;
  any Apply/enforce/read/write/final-save failure durably rolls runtime mode to
  `off`. `tp_settings_applied` remains false during mutation and becomes true
  only after complete success. Pre-mutation backups remain durable and intact
  for Restore/retry after partial failure.
- Synthetic release: every mouse `SendInput` must report one accepted event.
  Failed LEFTUP leaves drag state non-idle so later cleanup retries it, while
  suppression cleanup is attempted independently. Quit retries only the pending
  LEFTUP callback up to two additional times after suppression disable and hook
  shutdown have each been attempted once. A final failure is surfaced through
  the tray notification path and appended to `pearipherals.err.log`; termination
  remains bounded.
- Suppressor lifecycle: failed `PostThreadMessageW` activation rolls `_active`
  back to false, and failed `SetWindowsHookExW` does the same on the hook thread;
  both states permit a later activation attempt. Failed uninstallation remains
  fail-open and can be posted again while a hook handle remains.
- First-run lifecycle: failed touchpad Apply returns false without setting
  `setup_done`, so `tray_setup` cannot claim swipes were enabled.
- Config persistence: a process-wide lock serializes saves. Each writer uses a
  unique sibling temp path and removes only that path in `finally`; successful
  writes still flush, fsync, and atomically replace the destination.
- Shared-config concurrency: production reads, mutations, migrations, settings
  transactions, and serialization snapshots share a reentrant lock. Atomic
  writes deep-copy under that lock before taking the independent save lock,
  avoiding both live-dictionary iteration races and lock-order inversion.
- Suppressor startup/removal: readiness timeout, early thread exit, activation
  failure, and hook-install failure leave suppression inactive and retryable.
  Failed unhook retains the hook handle and active state; disable uses bounded
  retries and permits a later attempt.
- Suppressor request ownership: every posted operation carries its request
  generation and completion is accepted only by that generation. A successful
  `SetWindowsHookExW` return is published only while the same activation still
  owns the request, remains requested, and is within its bounded deadline.
  Timeout, supersession, and disable invalidate ownership. A stale late hook is
  unhooked immediately; if that
  unhook fails, its handle is retained with suppression inactive for bounded
  later disable/shutdown retry or safe reuse by a newer activation.
- Corrupt config recovery: an existing malformed or unreadable primary config
  raises an explicit recovery-required state. The file is preserved and
  onboarding Apply, startup enforcement, config writes, and automatic migration
  remain disabled rather than destroying possible registry-recovery evidence.
- Raw Input callbacks: maintenance and input callback failures are logged while
  fail-open cleanup remains contained and independently attempted.
- Registry reads: only `FileNotFoundError` maps to an absent value. Other read
  failures abort before any registry write or backup entry can be derived from
  uncertain data, and custom mode fails closed.
- Win32 ABI: pointer-sized results are declared for `GetModuleHandleW`, `CreateWindowExW`, and `CreateMutexW`; Raw Input registration has explicit argument/result declarations.
- Incomplete calls/imports: no unresolved imports or incomplete production calls remained after the audit.

## TDD evidence

The original two audit regressions, seven first-review regressions, six
second-review/lifecycle regressions, and thirteen extended-hardening regressions
were developed RED-first:

1. Input lifecycle tests initially failed because `release_custom_input` and `shutdown_custom_input` did not exist; they passed after fail-open orchestration was implemented and wired into mode-off, Restore, and Quit.
2. The Win32/Raw Input source-contract test initially failed for four missing pointer-sized API declarations, then failed for whole-payload fail-open parsing and the stale tray mapping label; it passed after those defects were corrected.
3. New blocking-review tests first failed because the optional-read,
   checked-`SendInput`, and fail-closed mode helpers did not exist; after the
   helpers were introduced, the registry-read test remained RED until Apply
   explicitly rolled custom mode off without creating backup entries.
4. Deterministic cases now cover mode-switch and startup enforcement failure,
   partial registry writes with durable backup retention, missing vs failed
   registry reads, failed LEFTUP visibility/retry, and independent suppression
   cleanup.
5. The concurrent-save regression deterministically forced the old shared-temp
   writers to overlap and failed with a Windows sharing/replace error; it passed
   after save serialization and unique sibling temp paths were added.
6. Quit retry tests first failed because `shutdown_custom_input` accepted no
   retry policy. They now prove a transient LEFTUP succeeds on a bounded,
   independent retry and a persistent LEFTUP stops after exactly two retries
   while returning the final error.
7. Extracted behavioral tests first failed because hook install/message posting
   left `_active` true and `first_run_setup` returned success after Apply failed.
   They now prove each suppressor failure permits retry and failed onboarding
   neither marks setup complete nor claims success.
8. Extended tests cover same-dictionary mutation during serialization, malformed
   and unreadable primary config recovery, suppressor readiness timeout and early
   exit, duplicate-thread prevention, failed-unhook handle retention and bounded
   retry, and logged Raw Input callback cleanup.
9. The late-install timeout regression was observed RED because the successful
   delayed hook was published active after the caller had timed out. The fix
   revalidates generation ownership under the suppressor lock. Deterministic
   timeout and concurrent-disable cases now prove stale successful installs are
   never published active, immediate cleanup is attempted, failed cleanup keeps
   the handle visible, and later bounded retry remains possible.

## Exact verification commands and results

From `C:/Users/keksa/Desktop/MagicSuite`:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

Result: `Ran 44 tests in 1.432s` — `OK`.

```text
.venv/Scripts/python.exe -m py_compile pearipherals.py pearipherals_core.py tests/test_core.py
```

Result: exit code 0; no output.

```text
git diff --check
```

Result after final staging: exit code 0 for both working-tree and staged checks;
no whitespace errors. Staging emitted only LF-to-CRLF working-copy warnings for
the handoff and the two edited Python files.

Static security scan of staged added lines found no hardcoded-secret,
shell-injection, unsafe-pickle, or formatted-SQL matches. The sole `exec` match
is the test-only AST harness that executes a named class/function extracted from
the trusted local `pearipherals.py`; it does not accept external input. `ruff`
and `mypy` were not installed, so no optional lint/type commands were run.

## Focused review

Final independent review: **PASSED** with no blocking security or logic findings.
The reviewer reran all 44 tests, compilation, staged/working diff checks, static
security checks, and targeted concurrent hook probes. No files were changed.

## Commit

No commit created, as required.

## Deferred risks / hardware boundary

- No physical trackpad, keyboard, registry-effect, pointer-lag, or gesture acceptance test was run because those require user/hardware interaction; these remain deferred to Phase 4.
- No executable was built, replaced, launched, or deployed. The installed app must not be described as containing this baseline.
- No device was restarted or power-cycled; `pnputil /restart-device` remains prohibited.
- Contact-reuse large-jump hardening remains Phase 3 work.
- Battery parser/query foundations exist, but there is intentionally no production battery worker or tray integration yet.

## Prerequisites for Phase 2

1. Phase 1 final review must pass and the baseline commit below must exist.
2. Start Phase 2 in a fresh session and read `.hermes/plans/continuation-2026-08-06.md`, this handoff, and `.hermes/plans/phase-2-battery-integration.md`.
3. Preserve the config/recovery sidecar semantics and keep all battery tests hardware-independent through an injected HID backend.
4. Implement only slow, offline-safe polling: re-enumerate/open/query/close each cycle, use multi-minute polling plus longer failure backoff, and never retain a HID handle across sleep.
5. Marshal immutable battery snapshots safely to pystray; keep valid, not-detected, unavailable/offline, malformed/unsupported, and stale states distinct.
6. Do not begin Phase 3 hardening, build/deployment, or physical acceptance work during Phase 2.
