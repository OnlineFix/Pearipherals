# Phase 3 — Input and Settings Hardening

> **For Hermes:** Start in a fresh session after Phase 2. Read the shared continuation and Phase 1–2 result handoffs only.

**Goal:** Close remaining gesture/contact edge cases and prove Apply/Restore and hook lifecycle are safe before freezing the app.

**Architecture:** Extend deterministic state-machine tests first, then make minimal core/runtime changes. Keep gesture recognition, pointer suppression, and registry ownership driven by shared predicates/managers.

**Files:**
- Modify: `pearipherals_core.py`
- Modify: `pearipherals.py`
- Modify: `tests/test_core.py`
- Create: `.hermes/plans/handoffs/phase-3-result.md`

---

### Task 1: Contact-ID reuse and jump guard

1. Write failing tests for a reused ID appearing at a distant coordinate.
2. Ensure a jump cannot synthesize a large drag/cursor movement.
3. Reset/re-anchor safely without rearming duplicate swipes.
4. Keep drag opt-in/off by default.

### Task 2: Touchdown epoch and fail-open regressions

Add tests for:
- transient 2/4-contact churn;
- one action per touchdown;
- all-up debounce before rearm;
- silence timer expiry;
- parser failure;
- mode-off, Restore, disconnect, and shutdown cleanup;
- injected events bypassing suppression.

### Task 3: Apply/Restore consistency review

1. Inventory every registry writer.
2. Confirm desired/status/apply/startup plans agree per mode.
3. Inject persistence and Nth-write failures.
4. Confirm original settings remain recoverable and failed restores remain retryable.
5. Confirm `ScrollDirection=1` is managed/restored as intended.

### Task 4: Full source quality gates

Run:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v
.venv/Scripts/python.exe -m py_compile pearipherals.py pearipherals_core.py tests/test_core.py
git diff --check
```

Then perform focused security/concurrency/code-quality review.

### Task 5: Close the phase

1. Write `handoffs/phase-3-result.md` with exact results and frozen-build prerequisites.
2. Commit the hardened source.
3. Stop; no build/deployment in this session.
