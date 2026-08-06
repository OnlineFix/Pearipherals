# Phase 4 — Build, Deploy, and Acceptance

> **For Hermes:** Start in a fresh session only after Phase 3 is green. Read the shared continuation and the three result handoffs.

**Goal:** Produce and safely install a verified windowed `Pearipherals.exe`, then coordinate physical acceptance tests with the user.

**Architecture:** Verify source first, build to a staging artifact, inspect frozen behavior without replacing the live app, preserve sidecar state, then deploy with rollback evidence.

**Files/artifacts:**
- Review: `build.bat`, `Pearipherals.spec`, `requirements.txt`
- Build: staged `dist/Pearipherals.exe`
- Preserve: user config/recovery sidecar and previous EXE backup
- Create: `.hermes/plans/handoffs/phase-4-result.md`

---

### Task 1: Pre-build gate

1. Confirm clean/expected Git state and review Phase 1–3 handoffs.
2. Rerun complete tests, `py_compile`, and `git diff --check`.
3. Verify frozen path resolves config beside `sys.executable`.
4. Verify single-instance, crash log, icons/assets, and windowed/no-console settings.

### Task 2: Build staging artifact

1. Run the repository's PyInstaller build process.
2. Record command, exit code, artifact path, size, and hash.
3. Inspect imports/assets and launch behavior without touching the live installation.
4. Verify source/EXE config-path behavior, including read-only and missing-sidecar cases where practical.

### Task 3: Safe deployment

1. Stop the current Pearipherals process cleanly.
2. Preserve the old EXE and user config/recovery data for rollback.
3. Replace only with the verified artifact.
4. Start it and verify single-instance behavior, tray presence, error log, and process stability.
5. Verify HKCU Run `Pearipherals` points to the intended EXE.
6. Never restart the input device through `pnputil`; ask the user to power-cycle only if registry changes require it.

### Task 4: User-assisted acceptance

Coordinate, one test at a time:
- A/B pointer lag with app exited vs running;
- one-finger pointer movement;
- classic-direction scrolling;
- three-finger down/up/left/right mappings;
- Apply and Restore behavior;
- keyboard/trackpad battery labels across awake/asleep/wake states.

Do not claim these pass until the user reports the result.

### Task 5: Finalize

1. Roll back immediately if critical input behavior regresses.
2. Otherwise write `handoffs/phase-4-result.md` with exact build/deployment/acceptance evidence.
3. Commit remaining verified build metadata/docs as appropriate.
4. Give the user a concise completion report and remaining limitations.
