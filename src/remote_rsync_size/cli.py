"""Command line entry point for remote-rsync-size."""

import argparse
import getpass
import json
import shutil
import sys
import time
from dataclasses import asdict
from typing import List, Optional

from .core import build_summary, check_directory_size


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute logical sizes of remote directories with local rsync over SSH."
    )
    parser.add_argument("directories", nargs="+", help="One or more remote directory paths")
    parser.add_argument("--host", required=True, help="SSH hostname, address, or tunnel endpoint")
    parser.add_argument("-P", "--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("-u", "--username", required=True, help="SSH username")

    parser.add_argument("--rsync-binary", default="rsync", help="Local rsync executable")
    parser.add_argument("--ssh-binary", default="ssh", help="Local SSH executable")
    parser.add_argument("--remote-rsync-path", help="Remote rsync executable path")

    auth = parser.add_argument_group("authentication")
    auth.add_argument("--password", help="SSH password (visible in process list; avoid)")
    auth.add_argument("--ask-password", action="store_true", help="Prompt for SSH password")
    auth.add_argument("-i", "--key-file", help="Private SSH key file")
    auth.add_argument("--key-passphrase", help="Private key passphrase (avoid CLI exposure)")
    auth.add_argument("--ask-key-passphrase", action="store_true", help="Prompt for private key passphrase")

    security = parser.add_argument_group("host key verification")
    security.add_argument("--known-hosts", help="Path to known_hosts file")
    host_keys = security.add_mutually_exclusive_group()
    host_keys.add_argument(
        "--accept-new-host-key", action="store_true",
        help="Accept unknown host keys (still reject changed ones)",
    )
    host_keys.add_argument(
        "--no-strict-host-key-checking", action="store_true",
        help="INSECURE: disable host-key verification",
    )

    parser.add_argument(
        "--ssh-option", action="append", metavar="NAME=VALUE",
        help="Pass an extra ssh -o option (repeatable)",
    )
    parser.add_argument(
        "--extra-rsync-arg", action="append", metavar="ARG",
        help="Pass an extra rsync argument (repeatable)",
    )
    parser.add_argument(
        "--no-protect-args", action="store_true",
        help="Disable --protect-args for older rsync peers",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Max seconds for each directory check (default: 300)",
    )
    parser.add_argument("--json", action="store_true", help="Compatibility flag (JSON is the default)")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON")
    parser.add_argument("--show-rsync-output", action="store_true", help="Write raw rsync output to stderr")
    parser.add_argument("--always-exit-zero", action="store_true", help="Exit 0 even if directory scans fail")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error("--timeout must be at least 1 second")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    for command in (args.rsync_binary, args.ssh_binary):
        if not shutil.which(command):
            print(json.dumps({"success": False, "error": "Local executable not found: " + command}),
                  flush=True)
            return 2

    password = args.password
    key_passphrase = args.key_passphrase
    if args.ask_password:
        password = getpass.getpass("SSH password: ")
    if args.ask_key_passphrase:
        key_passphrase = getpass.getpass("SSH key passphrase: ")

    started = time.monotonic()
    results = []
    for directory in args.directories:
        result, raw_output = check_directory_size(args, directory, password, key_passphrase)
        results.append(result)
        if args.show_rsync_output and raw_output:
            print("=== rsync: {} ===\n{}".format(directory, raw_output), file=sys.stderr)

    summary = build_summary(args, results, time.monotonic() - started)
    print(json.dumps(asdict(summary), indent=None if args.compact else 2))
    return 1 if summary.failure_count and not args.always_exit_zero else 0


if __name__ == "__main__":
    sys.exit(main())
