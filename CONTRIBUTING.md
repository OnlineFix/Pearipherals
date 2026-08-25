# Contributing to Pearipherals

Thank you for helping improve Pearipherals. Changes must preserve safe input behavior, reversible Windows settings and honest release provenance. Small, focused pull requests are easier to verify than broad rewrites.

## Development environment

Use Windows 10 or Windows 11 with Python 3.11 and Git. The project calls Windows APIs through `ctypes`; ordinary source verification does not require administrator rights or connected Apple hardware. A supported Apple device and the signed mac-precision-touchpad driver are needed only for relevant manual hardware checks.

From the repository root in Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install --disable-pip-version-check --no-cache-dir --require-hashes -r requirements-build.txt
```

The hash-locked file is the source of truth for verified builds. Do not hand-edit `requirements-build.txt`. A deliberate dependency update must regenerate every transitive hash from `requirements-build.in`, install cleanly on Windows and pass the build and test gates.

## Test-driven changes

Use strict **RED-GREEN-REFACTOR** for every feature, behavior change, bug fix and refactor:

1. Add one focused test that describes the required behavior.
2. Run it and confirm that it fails for the expected missing behavior, not a test error.
3. Add the minimum production change needed to pass.
4. Run the focused test again, then the complete gate.
5. Refactor only while the tests remain green.

Run the complete source gate from the repository root:

```bat
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.venv\Scripts\python.exe -m py_compile pearipherals.py pearipherals_core.py pearipherals_snipping.py pearipherals_support.py pearipherals_version.py scripts\write_build_manifest.py scripts\write_version_info.py tests\test_core.py tests\test_release.py tests\test_snipping.py tests\test_support.py
```

Also run `git diff --check`. Workflow changes must use immutable full-length action SHAs, least-privilege permissions and non-persisted checkout credentials.

## Input and Windows-setting safety

Pearipherals owns low-level input hooks, Raw Input state, synthetic keyboard/mouse events, HID access, display controls, per-user autostart and touchpad registry values. Treat changes in these areas as safety-sensitive.

- Input features must fail open. Never leave a key, mouse button, suppression flag or gesture ownership state logically held after an exception, shutdown or device transition.
- Preserve modifier passthrough and mark synthetic events so an input hook cannot consume its own output.
- Add regression coverage for cleanup, cancellation, reconnect and malformed-input paths.
- Do not add a registry write without a verified backup, idempotent apply behavior and a tested restore path.
- Keep three-finger drag opt-in; do not change accepted gesture mappings or classic scrolling direction incidentally.
- Do not restart Windows, Bluetooth, a device or a driver without explicit coordination with the person operating the test machine.
- Avoid repetitive hardware stress testing. State exactly which device and scenario a manual check covered.

## Rollback requirements

A change that can alter persistent state, input behavior or a deployed executable must include a practical rollback before physical testing begins. Preserve the previous executable, adjacent configuration and relevant original Windows values; verify copies or artifacts with hashes where appropriate. Keep rollback material outside Git, and verify that restore actions do not overwrite a user's unrelated settings.

Pull requests must explain both the failure boundary and the rollback path. Passing unit tests is not evidence that a frozen executable was built, deployed or physically accepted.

## Privacy and diagnostics

Pearipherals has no telemetry or automatic upload. Tests, issues and pull requests must not include credentials, usernames, Bluetooth addresses, serial numbers, full local paths, registry exports, complete user configuration, raw HID traces or unredacted logs. Collect raw input data only when necessary and with explicit coordination. See [SECURITY.md](SECURITY.md) for private vulnerability reporting.

## Release boundaries

Contributors and ordinary pull requests **do not create or publish a release**, move a release tag, replace release assets or weaken signing checks. Local and pull-request builds are development artifacts.

The current public v1.2 line is an explicitly unsigned prerelease. Never describe an unsigned binary as signed or trusted, and never advise disabling SmartScreen, Smart App Control, Defender or another system-wide protection. Official stable publication remains fail closed until trusted signing produces exactly one verified, timestamped artifact as described in [CODE_SIGNING_POLICY.md](CODE_SIGNING_POLICY.md).

## Commits and pull requests

- Keep each commit coherent and use an imperative, descriptive subject.
- Maintainer commits use the `[verified]` prefix only after the stated checks have actually passed.
- Do not commit generated build output, runtime sidecars, local configuration, traces, rollback binaries or credentials.
- Describe user-visible behavior, focused RED/GREEN evidence, complete tests, manual hardware scope, registry/input risk, rollback, security/privacy impact and release impact in the pull request.
- Update documentation when behavior or limitations change; do not make claims broader than the evidence.

Maintainers may keep local planning and handoff context in ignored `.hermes/` and `.hermes.md` paths. These are local working artifacts: never stage, paste into an issue, attach to a pull request or otherwise publish them. The repository's public tests and documentation must stand on their own.
