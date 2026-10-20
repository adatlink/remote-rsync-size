# remote-rsync-size

[![Python CI](https://github.com/OWNER/REPOSITORY/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPOSITORY/actions/workflows/ci.yml)

Measure the **logical total size** of one or more remote directories using the **local `rsync` binary over SSH**, then report bytes, regular-file count, directory count, elapsed time, and failures as **JSON**.

Designed for remote storage monitoring, backups, and inventory scripts. It only performs `rsync --dry-run --stats` against a temporary empty directory: **no files are copied or deleted**.

## Requirements

- Linux/macOS (or another POSIX environment with OpenSSH).
- Python 3.9 or newer.
- Local `rsync` and `ssh` executables.
- The remote SSH server **must also have `rsync` installed**. Local rsync cannot talk to the remote host via rsync-over-SSH without it.
- Optional `pexpect` for SSH password or encrypted-key passphrase authentication.

> **First edit the CI badge:** replace `OWNER/REPOSITORY` above with your GitHub username and repository name after publishing.

## Quick start

### Run directly after unpacking (no pip install needed for key/agent auth)

```bash
python3 remote_rsync_size_local.py \
  /var/www/site1 /var/www/site2 /home/user/data \
  --host example.com \
  --username myuser \
  --key-file ~/.ssh/id_ed25519 \
  --json
```

### Install as a CLI command

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
remote-rsync-size /var/www/site1 /var/www/site2 \
  --host example.com --username myuser -i ~/.ssh/id_ed25519
```

The JSON output is **the default**. `--json` remains accepted for compatibility with earlier scripts. Use `--compact` for one-line JSON.

### Password authentication

```bash
pip install -e '.[password]'
remote-rsync-size /srv/backups /srv/uploads \
  --host example.com --username backup --ask-password
```

Use `--ask-password`, not `--password SECRET`, to avoid exposing the password in your shell history and process list. Key auth with `ssh-agent` is supported without any extra Python package.

### Existing SSH tunnel

If you already have local port 2222 forwarded to the target host's SSH port:

```bash
remote-rsync-size /var/www/site1 /var/www/site2 \
  --host localhost --port 2222 --username myuser \
  --key-file ~/.ssh/id_ed25519
```

Note: SSH host-key verification checks the tunnel endpoint as seen by the SSH client; register the forwarded server's key appropriately in `known_hosts`.

## Example JSON response

```json
{
  "host": "example.com",
  "port": 22,
  "username": "myuser",
  "method": "local-rsync-over-ssh",
  "directory_count": 2,
  "success_count": 2,
  "failure_count": 0,
  "total_file_size_bytes": 314572800,
  "total_file_size_human": "300.00 MiB",
  "total_number_of_files": 176546,
  "total_number_of_dirs": 31879,
  "elapsed_seconds": 4.322,
  "directories": [
    {
      "directory": "/var/www/site1",
      "success": true,
      "total_file_size_bytes": 209715200,
      "total_file_size_human": "200.00 MiB",
      "number_of_files": 120000,
      "number_of_dirs": 20000,
      "elapsed_seconds": 2.118,
      "exit_code": 0,
      "error": null
    },
    {
      "directory": "/var/www/site2",
      "success": true,
      "total_file_size_bytes": 104857600,
      "total_file_size_human": "100.00 MiB",
      "number_of_files": 56546,
      "number_of_dirs": 11879,
      "elapsed_seconds": 2.204,
      "exit_code": 0,
      "error": null
    }
  ]
}
```

Also see [`examples/sample-output.json`](examples/sample-output.json).

## Options

```text
remote-rsync-size PATH [PATH ...] --host HOST --username USER [options]

Connection:
  --port, -P N                   SSH port; default 22
  --key-file, -i FILE            SSH private key
  --ask-password                Secure password prompt (requires pexpect)
  --password VALUE              SSH password (unsafe on command line)
  --ask-key-passphrase          Secure private-key passphrase prompt
  --key-passphrase VALUE        Private-key passphrase (unsafe on command line)
  --known-hosts FILE            Alternative SSH known_hosts file
  --accept-new-host-key         Accept new hosts, reject changed keys
  --no-strict-host-key-checking Disable host-key checks (unsafe)
  --ssh-option KEY=VALUE        Repeatable OpenSSH option

Processing:
  --timeout N                   Per-directory time limit, default 300s
  --rsync-binary PATH           Override local rsync executable
  --ssh-binary PATH             Override local ssh executable
  --remote-rsync-path PATH      Override remote rsync executable
  --extra-rsync-arg ARG         Repeatable rsync option
  --no-protect-args             For older rsync versions
  --show-rsync-output           Print raw rsync output to stderr

Output:
  --json                        Accepted for backwards compatibility (default)
  --compact                     One-line JSON
  --always-exit-zero            Exit 0 on individual directory failures
```

Run `remote-rsync-size --help` for the full argument reference.

To stay within the same filesystem (if that matches your desired rsync scope):

```bash
remote-rsync-size /srv/data --host host --username backup \
  --extra-rsync-arg=--one-file-system
```

For host alias / jump-host support, pass an SSH config or `--ssh-option ProxyJump=bastion.example.com`.

## Output semantics

- `total_file_size_bytes` uses **rsync's `Total file size`** from `--stats`. It represents logical sizes of file entries, **not actual filesystem block usage** (`du` can differ for sparse files, deduplication, and hard links).
- `number_of_files` parses the `reg:` count in rsync's `Number of files` line; `number_of_dirs` parses `dir:`. Symlink entries are neither regular files nor directories.
- On older rsync versions that only emit a combined item count, `number_of_files` falls back to that combined count, and `number_of_dirs` is `null` (the two types cannot be distinguished reliably).
- The `total_*` values include **successful scans only**; check `failure_count` before trusting them as complete. Nested/overlapping directories are **double-counted** in summary totals by design.
- Each directory triggers a separate rsync-over-SSH execution, sequentially, using an empty temporary local destination. `elapsed_seconds` is measured with a monotonic clock for each directory and the overall batch.
- Errors are included under each path (`success: false`, `exit_code`, `error`), not lost if other directories succeed.
- Normal output goes to **stdout as JSON**. Raw rsync output (when requested) goes to **stderr**.
- Exit code is **0** if all checks succeed; **1** if one or more checks fail; **2** if the local rsync/SSH executable is missing or arguments are invalid. `--always-exit-zero` affects per-directory failures.

## Security and SSH host keys

Host-key verification is **strict by default** (`StrictHostKeyChecking=yes`). Add a trusted host key to `~/.ssh/known_hosts` before the first run, or use `--accept-new-host-key` (trust on first use) if appropriate. Avoid `--no-strict-host-key-checking` on untrusted networks.

`--ask-password` and `--ask-key-passphrase` use `pexpect` to respond to SSH prompts. The tool never embeds a password in the rsync command line. When using automated jobs, prefer an SSH key and agent or a constrained-purpose key.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest -q
python -m remote_rsync_size --help
```

Automated tests mock external rsync/SSH work and **do not require access to any real server**. GitHub Actions runs the suite on Python 3.9, 3.11, and 3.13.

## Publish on GitHub

Create a new **empty** GitHub repository, then from this folder:

```bash
git init
git add .
git commit -m "Initial release: remote rsync directory size tool"
git branch -M main
git remote add origin git@github.com:YOUR-USERNAME/remote-rsync-size.git
git push -u origin main
```

Update the `OWNER/REPOSITORY` placeholders in the CI badge after publishing.

## License

MIT; see [`LICENSE`](LICENSE).
