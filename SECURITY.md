# Security Policy

## Supported versions

Security fixes are considered for the current `main` branch and the newest public release line.

| Version | Security support |
|---|---|
| `1.2.x` unsigned prerelease | Current |
| `1.1` and older | No longer supported |

If a report also affects an older version, please identify every version you have verified. Release executables may currently be unsigned; the absence of an Authenticode signature is documented in the [code-signing policy](CODE_SIGNING_POLICY.md) and is not, by itself, a vulnerability report.

## Report a vulnerability privately

**Do not open a public issue for a suspected vulnerability.** Use [GitHub Security Advisories](https://github.com/OnlineFix/Pearipherals/security/advisories/new) to send the maintainer a private report.

Include only what is needed to understand and reproduce the problem:

- affected Pearipherals version or source commit;
- affected Windows version and relevant hardware class;
- a concise impact description;
- minimal reproduction steps or a proof of concept;
- any conditions required to trigger the issue; and
- suggested remediation, if known.

Please allow coordinated investigation and remediation before public disclosure. The project does not promise a fixed response or resolution time; timing depends on severity, reproducibility and maintainer availability.

## Protect private information

Reports and public issues must not expose credentials, tokens, personal data or device identifiers. Before attaching or quoting diagnostic material, remove usernames, Bluetooth addresses, serial numbers, device instance identifiers and every full local path.

Do not attach a complete `pearipherals.err.log`, `pearipherals.json`, registry export, raw HID trace or crash dump to a public issue. These files can contain system-specific paths, settings or identifiers. Share the smallest redacted excerpt needed, and use the private advisory if the material is security-sensitive. Raw input traces should be collected or shared only after explicit maintainer coordination.

Pearipherals does not upload logs or diagnostics automatically. See the [privacy policy](PRIVACY.md) for the application's data-handling boundaries.

## Scope and safe research

Pearipherals interacts with Windows input hooks, Raw Input, HID devices, display controls, autostart and per-user registry settings. Research must not require disabling Windows security protections, damaging a device, repeatedly stress-testing hardware, or accessing another person's system or data without permission.

Reports about GitHub, Windows, third-party drivers or download infrastructure outside Pearipherals' control may need to be sent to the relevant vendor. If the boundary is unclear, report privately and the maintainer will help route it.
