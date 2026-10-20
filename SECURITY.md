# Security policy

Report vulnerabilities privately to the repository maintainer using GitHub's
**Report a vulnerability** feature under the repository's Security tab, if enabled.
Otherwise contact the maintainer privately rather than posting sensitive details
in a public issue.

The CLI verifies SSH host keys strictly by default. Use `--accept-new-host-key`
only when trust-on-first-use is acceptable; avoid
`--no-strict-host-key-checking`. Do not place passwords or private-key
passphrases on command lines: prefer SSH agent/key auth or interactive prompts.

The tool runs `rsync --dry-run --stats` and does not intentionally transfer
file contents. A remote rsync binary is required; use only trusted SSH peers.
