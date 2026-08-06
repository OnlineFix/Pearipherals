# Phase 1 — Baseline Audit and Stabilization

> **For Hermes:** Work only on this phase in a fresh session. Read `continuation-2026-08-06.md` first.

**Goal:** Turn the previous session's uncommitted edits into a reviewed, tested, coherent source baseline without adding new production features.

**Architecture:** Inspect all changed/new files, identify duplicate state-management paths or unsafe hooks, fix only defects in the existing implementation, and lock the baseline with tests and a phase handoff.

**Files:**
- Review/modify: `pearipherals.py`
- Review/modify: `pearipherals_core.py`
- Review/modify: `tests/test_core.py`
- Create: `.hermes/plans/handoffs/phase-1-result.md`

---

### Task 1: Reconstruct the exact worktree

1. Run `git status --short --branch`, `git diff --stat`, `git diff --check`.
2. Read the complete diff and all new test/core files.
3. Map callbacks and state transitions for Raw Input, suppression, config persistence, Apply, Restore, and shutdown.
4. Record any incomplete calls/imports left by the interrupted session.

### Task 2: Audit ownership and fail-open behavior

1. Confirm there is only one active path for each managed registry value.
2. Confirm mouse hooks are idle/off unless suppression is confirmed.
3. Confirm parser errors, shutdown, Restore, and mode-off release suppression and injected buttons.
4. Confirm startup cannot overwrite a completed Restore.
5. Add focused failing tests before fixing any discovered defect.

### Task 3: Verify baseline

Run from repository root:

```text
.venv/Scripts/python.exe -m unittest discover -s tests -p 'test_*.py' -v
.venv/Scripts/python.exe -m py_compile pearipherals.py pearipherals_core.py tests/test_core.py
git diff --check
```

Expected baseline before further feature work: all 15 current tests plus any new audit regressions pass.

### Task 4: Close the phase

1. Perform focused code review for thread safety, hook lifecycle, registry recovery, and error visibility.
2. Write `handoffs/phase-1-result.md` with exact outputs and remaining risks.
3. Commit the verified baseline as one reviewable commit if clean enough.
4. Stop; do not begin battery integration in this session.
