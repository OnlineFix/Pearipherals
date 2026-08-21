## Behavior summary

<!-- What user-visible or internal behavior changes? Keep refactors separate from behavior changes. -->

## Test-driven evidence

### RED evidence

<!-- Name the focused test and paste the expected failure reason observed before production code changed. -->

### GREEN evidence

<!-- Name the focused test and result after the minimum implementation. -->

### Complete test gate

- [ ] `python -m unittest discover -s tests -p "test_*.py" -v`
- [ ] `python -m py_compile pearipherals.py pearipherals_core.py scripts/write_version_info.py tests/test_core.py tests/test_release.py`
- [ ] `git diff --check`

## Manual hardware scope

- [ ] Not tested on hardware
- [ ] Tested only the hardware/scenarios listed below

<!-- List Windows version, Apple device model/revision, connection, driver version and exact scenarios. Remove usernames, identifiers and Bluetooth addresses. Do not claim broader compatibility. -->

## Input and registry risk

- [ ] No input-hook, Raw Input, synthetic-event, autostart or registry behavior changes
- [ ] Safety-sensitive behavior changed and failure/cleanup/restore tests are identified below

<!-- Explain fail-open behavior, held-input cleanup, backup/restore semantics and whether reconnect/restart could be required. -->

## Rollback

<!-- Explain how to reverse the source, persistent settings and deployed artifact safely. State what was preserved before any physical test. -->

## Security and privacy

- [ ] No credentials, local planning files, full paths, device identifiers, raw traces, complete logs/configuration or registry exports are included
- [ ] Security-sensitive findings were reported privately rather than in this pull request
- [ ] Documentation does not weaken Windows security guidance or overstate signing/trust

<!-- Describe any remaining security or privacy impact. -->

## Release impact

- [ ] No release/tag/asset impact
- [ ] Release documentation or workflow review is required
- [ ] This must not be published until trusted signing succeeds

<!-- Identify versioning, packaging, provenance, signing or compatibility-matrix effects. Pull requests do not publish releases. -->
