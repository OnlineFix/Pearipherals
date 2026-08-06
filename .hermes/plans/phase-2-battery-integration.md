# Phase 2 — Battery Production Integration

> **For Hermes:** Start in a fresh session after Phase 1 passes. Read the shared continuation and `handoffs/phase-1-result.md`.

**Goal:** Display reliable Magic Keyboard and Magic Trackpad battery states in the tray without keeping Bluetooth devices awake.

**Architecture:** Keep parsing/query logic pure in `pearipherals_core.py`; inject the HID backend for tests; run slow polling on a worker; communicate immutable snapshots to the tray/UI thread; re-enumerate and close handles each cycle.

**Files:**
- Modify: `pearipherals_core.py`
- Modify: `pearipherals.py`
- Modify: `tests/test_core.py`
- Create: `.hermes/plans/handoffs/phase-2-result.md`

---

### Task 1: Specify worker state with failing tests

Cover keyboard/trackpad independently:
- valid percentage;
- charging/fully charged advisory flags;
- not detected;
- offline/unavailable;
- malformed/unsupported report;
- stale last-known reading;
- exception/backoff behavior;
- clean worker shutdown.

### Task 2: Implement the minimal polling worker

1. Enumerate exact Apple vendor collections each cycle.
2. Open, query report `0x90`, and close every handle in the same cycle.
3. Use a multi-minute normal interval and longer failure backoff.
4. Never busy-poll or retain a HID handle across sleep.
5. Make timing and backend injectable for deterministic tests.

### Task 3: Add dynamic tray presentation

1. Add separate keyboard and trackpad battery menu labels.
2. Marshal state refresh safely; do not mutate pystray UI from an unsafe worker context.
3. Keep stale/offline/malformed labels distinct rather than showing a false percentage.
4. Ensure battery failures cannot crash or block input handling.

### Task 4: Verify and close

1. Run all unit tests, `py_compile`, and `git diff --check`.
2. Review wake behavior, handle lifetime, thread shutdown, and stale-state semantics.
3. Write `handoffs/phase-2-result.md` with exact results.
4. Commit the battery feature.
5. Stop; do not start input hardening in this session.
