# Phase 3 result — Input and settings hardening

## Status

**PASSED.** Phase 3 was implemented directly from clean commit `0510074`. The full source suite, required source gates, and independent fail-closed review passed. No build, deployment, process restart, device restart, registry mutation, or physical hardware test was performed.

## Files changed

- `pearipherals.py`
  - device-scoped rolling contacts keyed by `(hDevice, contact_id)`;
  - reused-ID gap/large-jump detection with safe anchor/age reset and no synthesized cursor delta;
  - separate fired touchdown-epoch latch reset only after 50 ms continuously all-up;
  - explicit Tip/Confidence matrix handling: all-clear reports remove known contacts and low-confidence tip reports are ineligible;
  - Raw Input device-removal notification and immediate fail-open disconnect cleanup;
  - mode-off, parser callback, Restore, and shutdown cleanup remain wired through input abort/suppression release;
  - low-level hook filtering now uses a pure tested predicate that bypasses injected and app-tagged events.
- `pearipherals_core.py`
  - pure mouse-event suppression predicate;
  - Restore retains the complete in-memory recovery backup if the final prune save fails;
  - off-mode status distinguishes actively managed native settings from an incomplete Restore.
- `tests/test_core.py`
  - deterministic regressions for CID reuse/large jumps, no drag movement, safe re-anchor, no duplicate swipe rearm, 2/4-contact churn, all-up debounce, silence expiry, device-scoped disconnect cleanup, parser lift/confidence matrix, fail-open lifecycle wiring, and injected-event bypass;
  - exhaustive full-plan Apply Nth-write injection, every-entry Restore failure injection, pre/final persistence failures, recovery retention, all-mode wanted/Apply/status/enforce agreement, single Precision Touchpad DWORD writer inventory, and `ScrollDirection=1`.
- `.hermes/plans/handoffs/phase-3-result.md`
  - this handoff.

## TDD evidence

New gesture tests were observed RED before implementation: missing suppression predicate import, absent disconnect handling, absent Raw Input device notifications, unguarded CID jumps, and immediate swipe rearm after transient all-up all failed as expected. The parser matrix then remained RED for Tip=0/Confidence=0 and Tip=1/Confidence=0 until explicit lift emission and confidence eligibility were implemented.

Settings tests were observed RED for final Restore persistence failure dropping the in-memory backup and for off-mode managed status being reported as Restore-incomplete. Minimal production changes made each focused suite green before the complete suite was run.

## Exact verification

From `C:/Users/keksa/Desktop/MagicSuite`:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

Result: `Ran 74 tests in 1.642s` — `OK`.

```text
.venv/Scripts/python.exe -m py_compile pearipherals.py pearipherals_core.py tests/test_core.py
```

Result: exit code 0; no output.

```text
git diff --check
git diff --cached --check
```

Result before and after final staging: both exit code 0; no whitespace errors. Git emitted only expected LF-to-CRLF working-copy warnings.

AST/static review: all three Python files parsed successfully; no bare `except`; production scan found no `subprocess`, `os.system`, `eval`, `pickle`, or `shell=True`; added-line secret/shell/pickle/eval/formatted-SQL scan returned no matches. Static invariants confirmed classic scrolling (`natural_scroll=False` and `ScrollDirection=1`), drag not default, no device-restart command, device-scoped contacts, Raw Input disconnect notification, and injected-event bypass. `ruff`, `mypy`, `bandit`, and `pip-audit` are not installed in the project venv, so those optional tools were not run.

## Focused review

Self-review found and fixed two additional recovery/parser issues before the final gates:

1. A successful registry Restore followed by a failed final config save had pruned the in-memory backup even though durable recovery still retained the full set. The manager now restores the complete in-memory backup and leaves retry recovery conservative.
2. The parser previously discarded all-clear reports and treated low-confidence Tip reports as down. The complete Tip/Confidence matrix is now explicit and tested.

Registry writer inventory found one Precision Touchpad `REG_DWORD` adapter (`TouchpadSettings._write`); Apply, mode enforcement, startup enforcement, natural-scroll changes, and Restore continue through `TouchpadSettingsManager`. Separate `REG_SZ` writes are only for the HKCU Run autostart entry.

Battery polling, immutable snapshots, tray dispatch, and all prior behavior remain covered by the complete suite.

Final independent review: **PASSED** with no blocking logic, security, or quality findings. The reviewer reran the complete suite, compilation, diff/static/security checks, and focused state-machine probes without changing the repository.

## Commit

Pending the verified Phase 3 commit.

## Deferred Phase 4 boundary

- Build/frozen-artifact verification is still required before deployment.
- No EXE was built, replaced, launched, or restarted.
- No registry/device/hardware acceptance test was performed.
- Never use `pnputil /restart-device`; registry-backed settings require user-coordinated reconnect/power-cycle or reboot during Phase 4 acceptance.
