# Phase 2 result — Battery integration and safe tray refresh

## Status

**PASSED.** Phase 2 battery polling and tray integration now refresh every complete immutable snapshot through a bounded Win32 UI dispatcher. The dispatcher's `PostMessageW` call has an explicit pointer-safe x64 ctypes ABI. No Phase 3 work, build, deployment, hardware interaction, device restart, or commit was performed.

## Files changed

- `pearipherals_core.py`
  - immutable battery result/snapshot/store types;
  - exact Apple HID report parsing and device filtering;
  - per-query open/query/close HID adapter;
  - fresh enumeration each poll cycle, multi-minute normal polling, longer failure backoff, explicit unsupported/offline/not-detected/stale states, and interruptible shutdown.
- `pearipherals.py`
  - dynamic keyboard/trackpad tray labels and isolated battery worker lifecycle;
  - `publish_battery_snapshot` publishes the complete snapshot before scheduling a tray refresh;
  - `WindowsTrayMenuRefreshDispatcher` posts one private `WM_APP` message to pystray 0.19.5's Windows HWND and registers its handler in the backend message-handler table;
  - the handler alone calls `icon.update_menu()` on the tray message-loop context;
  - a lock and one pending bit coalesce bursts to at most one outstanding callback; failed posts are retryable and shutdown makes an already-posted callback a no-op;
  - battery polling starts only after pystray has created its HWND, preserving the visible loading-to-first-result transition;
  - Quit closes the dispatcher before stopping/joining the battery worker.
  - `user32.PostMessageW` declares `(HWND, UINT, WPARAM, LPARAM) -> BOOL` before the dispatcher receives it, preventing default `c_int` conversion of x64 HWND values.
- `tests/test_core.py`
  - 19 deterministic battery tests, including Windows-backend-style marshalling/coalescing/UI-context behavior, safe pending-refresh shutdown, every publication requesting refresh, dynamic state labels, successful and failed HID handle closure, fresh path enumeration on repeated cycles, app-level worker shutdown, and pointer-safe high-bit HWND conversion.
- `.hermes/plans/handoffs/phase-2-result.md`
  - this handoff.

## Blocking review defect disposition

The HID worker never calls pystray directly. `BatteryPoller` publishes through `publish_battery_snapshot`; that function first stores the complete immutable snapshot and then calls the dispatcher. The dispatcher only uses thread-safe `PostMessageW` from the publisher thread. Its private message is consumed by pystray's existing Windows window procedure, where `icon.update_menu()` runs. Percentage, charging, offline/unavailable, malformed/unsupported, stale, and initial loading transitions all use this same publication path.

Frequent publications cannot queue unbounded callbacks: while one refresh message is pending, further schedule requests are coalesced. The UI handler clears the pending bit before rebuilding, allowing at most one follow-up message during a rebuild. Closing the dispatcher blocks new posts and drops an already-posted refresh without touching the icon.

The final x64 ABI review blocker is resolved. `user32.PostMessageW.argtypes` is `(w.HWND, w.UINT, w.WPARAM, w.LPARAM)` and its `restype` is `w.BOOL`, declared with the other process-wide ctypes prototypes before any dispatcher use. The regression invokes a callback through an undeclared stdcall function pointer with HWND `0x8000000000001234`: ctypes raises `ArgumentError` during its default `c_int` conversion and delivers nothing. Applying the production signature makes the same call succeed and preserves the full HWND value. The test also asserts that both production declarations exist.

## TDD evidence

The three tray-refresh regressions were run first and failed with `StopIteration` because `publish_battery_snapshot` and `WindowsTrayMenuRefreshDispatcher` did not yet exist. After the minimal implementation, all six focused refresh/lifecycle/HID regressions passed. The success-path close, repeated fresh enumeration, and app-level stop regressions also pass. For the final ABI fix, `test_post_message_declaration_preserves_high_bit_hwnd_on_x64` was added first and failed because the production `PostMessageW` declaration was absent; after the two declaration lines were added, the focused regression passed.

## Exact verification results

Pinned backend confirmation:

```text
.venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('pystray'))"
```

Result: `0.19.5`.

Full suite:

```text
PYTHONPATH='C:/Users/keksa/Desktop/MagicSuite' 'C:/Users/keksa/Desktop/MagicSuite/.venv/Scripts/python.exe' -m unittest discover -s 'C:/Users/keksa/Desktop/MagicSuite/tests' -p 'test_*.py' -v
```

Result: `Ran 59 tests in 1.510s` — `OK`.

Compilation:

```text
'C:/Users/keksa/Desktop/MagicSuite/.venv/Scripts/python.exe' -m py_compile 'C:/Users/keksa/Desktop/MagicSuite/pearipherals.py' 'C:/Users/keksa/Desktop/MagicSuite/pearipherals_core.py' 'C:/Users/keksa/Desktop/MagicSuite/tests/test_core.py'
```

Result: exit code 0; no output. A separate AST parse of all three Python files also passed.

Diff/static checks:

```text
git diff --check
```

Result: exit code 0; no whitespace errors. Git emitted only expected LF-to-CRLF working-copy warnings.

Added-line static scan results: hardcoded secrets `0`, shell injection `0`, `eval`/`exec` `0`, unsafe pickle `0`, formatted SQL `0`. AST call-site check found `icon.update_menu()` only in the new dispatcher UI handler and the pre-existing tray menu callback helper; the `start_battery_worker` section contains no `update_menu` call. Static source assertions confirm the exact `PostMessageW` argtypes/restype declarations. `ruff` and `mypy` are not installed in the project venv.

## Scope and commit

- Preserved Phase 1 commit `6ec5bc7` and all intended Phase 2 work.
- No executable was built, replaced, launched, or deployed.
- No physical device, registry effect, or hardware acceptance test was performed.
- No Phase 3 changes were made.
- No commit was created, as required.
