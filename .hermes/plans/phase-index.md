# Pearipherals Multi-Session Execution Plan

> **For Hermes:** Execute exactly one phase per fresh project session. Do not load later phase detail unless needed for a dependency check.

**Goal:** Finish and safely deploy Pearipherals without forcing the entire audit, implementation, build, and hardware-validation history into one context window.

**Architecture:** The work is split into four independently resumable phases. Shared facts remain in `continuation-2026-08-06.md`; each new session loads that handoff plus only its phase file. Every phase ends with tests, a concise handoff, and preferably a commit so the next context starts from a stable boundary.

**Tech Stack:** Python 3.11, ctypes/Win32 Raw Input and hooks, hidapi, pystray, winreg, unittest, PyInstaller, Git.

---

## Context strategy

1. Start a fresh Hermes Desktop session in the `Pearipherals` project for each phase.
2. At session start read:
   - `.hermes/plans/continuation-2026-08-06.md`
   - only the current phase file.
3. Do not replay the full old transcript unless a specific disputed detail requires `session_search`.
4. Keep phase work in the same Git repository, but commit at each verified phase boundary.
5. End each phase by writing `.hermes/plans/handoffs/phase-N-result.md` containing:
   - files changed;
   - exact test results;
   - commit hash if committed;
   - unresolved risks;
   - the next phase's prerequisites.
6. Start the next phase in a fresh session. Its context is reconstructed from Git + the compact handoff files rather than conversation history.

## Phase order

1. **Phase 1 — Baseline audit and worktree stabilization**
   - File: `phase-1-baseline-audit.md`
   - Outcome: reviewed, tested, internally consistent source baseline.

2. **Phase 2 — Battery production integration**
   - File: `phase-2-battery-integration.md`
   - Outcome: slow/offline-safe battery polling and dynamic tray labels, fully unit-tested.

3. **Phase 3 — Input and settings hardening**
   - File: `phase-3-input-settings-hardening.md`
   - Outcome: contact-reuse guard, gesture regressions, Apply/Restore review, full source gates.

4. **Phase 4 — Build, deploy, and acceptance**
   - File: `phase-4-build-deploy-acceptance.md`
   - Outcome: verified frozen EXE, safe replacement, autostart verification, then user-assisted hardware checks.

## Rules across all phases

- Never discard the current uncommitted worktree.
- Do not deploy an EXE before Phases 1–3 are green.
- Never restart the input device from the daemon or call `pnputil /restart-device`.
- Keep drag opt-in/off by default.
- Preserve user config and registry recovery data.
- Do not claim physical behavior was verified without the user's test.
