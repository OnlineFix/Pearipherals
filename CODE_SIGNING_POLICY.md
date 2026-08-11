# Code signing policy

Official Pearipherals release executables are intended to be built from the public source repository and signed through SignPath.io using a certificate provided by SignPath Foundation.

Free code signing provided by [SignPath.io](https://signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).

## Project roles

- **Committer and reviewer:** [OnlineFix](https://github.com/OnlineFix)
- **Release approver:** [OnlineFix](https://github.com/OnlineFix)

As the project grows, changes from outside contributors must be reviewed before merging. Each release-signing request requires manual approval by the release approver.

## Release provenance

- Source repository: <https://github.com/OnlineFix/Pearipherals>
- Official downloads: <https://github.com/OnlineFix/Pearipherals/releases>
- Release builds run on GitHub-hosted Windows runners.
- The unsigned artifact is uploaded by the same GitHub Actions workflow before being submitted to SignPath.
- SignPath verifies the GitHub build origin and returns the signed artifact.
- Only the signed artifact is eligible to be attached to an official release once signing is configured.

Local and pull-request builds are development artifacts and are not official signed releases.

## Privacy

See [PRIVACY.md](PRIVACY.md). Pearipherals does not transfer information to networked systems unless the user explicitly performs an external action, such as downloading an update or sharing a diagnostic file.
