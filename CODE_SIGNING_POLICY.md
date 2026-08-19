# Code signing policy

Pearipherals intends official release executables to be built from the public source repository and signed through SignPath.io using a certificate provided by SignPath Foundation if the project is approved and trusted signing is configured.

If approved, free code signing would be provided by [SignPath.io](https://signpath.io/), with a certificate provided by [SignPath Foundation](https://signpath.org/).

## Project roles

- **Committer and reviewer:** [OnlineFix](https://github.com/OnlineFix)
- **Release approver:** [OnlineFix](https://github.com/OnlineFix)

As the project grows, changes from outside contributors must be reviewed before merging. Each release-signing request requires manual approval by the release approver.

## Release provenance

- Source repository: <https://github.com/OnlineFix/Pearipherals>
- Official downloads: <https://github.com/OnlineFix/Pearipherals/releases>
- Release builds run on GitHub-hosted Windows runners.
- If trusted signing is configured, the unsigned artifact is uploaded by the same GitHub Actions workflow before being submitted to SignPath.
- SignPath would then verify the GitHub build origin and return the signed artifact.
- Only the signed artifact is eligible to be attached to an official release once signing is configured.

Local and pull-request builds are development artifacts and are not official signed releases.

## Unsigned prereleases while trusted signing is unavailable

Until trusted code signing is available, Pearipherals may publish an explicitly labeled unsigned GitHub prerelease so users can test the current open-source build and the project can establish public usage. An unsigned prerelease is not an official signed release and must:

- be built from the public repository by the GitHub-hosted release workflow;
- pass the complete automated test and compilation gates;
- contain product and file version metadata matching its release version;
- use GitHub's prerelease flag;
- include `unsigned` in the tag, release title, release notes, and downloadable EXE filename;
- include a SHA-256 checksum;
- verify `Get-AuthenticodeSignature` returns `NotSigned` and that the PE certificate table is empty;
- record the exact workflow run URL and source commit SHA;
- require the release tag to resolve to that same source commit SHA;
- publish only the individually verified EXE;
- explain unknown-publisher, SmartScreen, and Smart App Control limitations;
- explain that SHA-256 detects file mismatch or corruption but does not authenticate the publisher, establish safety, or substitute for a digital signature;
- never describe the artifact as signed, trusted, or an official signed release except in an explicit negation;
- never advise users to disable system-wide Windows security protections.

Once trusted signing is configured, official release tags must continue to fail closed unless SignPath returns exactly one correctly signed, timestamped, and verified executable.

## Privacy

See [PRIVACY.md](PRIVACY.md). Pearipherals does not transfer information to networked systems unless the user explicitly performs an external action, such as downloading an update or sharing a diagnostic file.
