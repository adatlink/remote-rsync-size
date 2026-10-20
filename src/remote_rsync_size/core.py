"""Core implementation for remote-rsync-size.

All scanning uses the local rsync CLI over SSH, with remote rsync as a peer.
No file contents are copied: the destination is empty and --dry-run is set.
"""

import os
import re
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class DirectoryResult:
    directory: str
    success: bool
    total_file_size_bytes: Optional[int]
    total_file_size_human: Optional[str]
    number_of_files: Optional[int]
    number_of_dirs: Optional[int]
    elapsed_seconds: float
    exit_code: int
    error: Optional[str]


@dataclass
class SummaryResult:
    host: str
    port: int
    username: str
    method: str
    directory_count: int
    success_count: int
    failure_count: int
    total_file_size_bytes: int
    total_file_size_human: str
    total_number_of_files: int
    total_number_of_dirs: int
    elapsed_seconds: float
    directories: List[DirectoryResult]


def human_size(num_bytes: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return "{} {}".format(int(size), unit)
            return "{:.2f} {}".format(size, unit)
        size /= 1024
    raise AssertionError("unreachable")


def normalize_source_path(path: str) -> str:
    if not path:
        raise ValueError("Remote directory path must not be empty")
    if path == "/":
        return "/"
    return path.rstrip("/") + "/"


def parse_rsync_stats(output: str) -> Tuple[int, Optional[int], Optional[int]]:
    """Parse rsync's C-locale --stats text into bytes, regular files, directories.

    rsync >=3 outputs e.g. '208,425 (reg: 176,546, dir: 31,879)'.
    Older rsync output may give only a combined entry count; in that case
    number_of_files is the total entry count and number_of_dirs is None.
    """
    output = output.replace("\r\n", "\n").replace("\r", "\n")
    size_match = re.search(
        r"^Total file size:\s*([0-9,]+)\s+bytes\s*$",
        output,
        flags=re.MULTILINE,
    )
    if not size_match:
        raise ValueError("Could not find 'Total file size' in rsync output")
    total_bytes = int(size_match.group(1).replace(",", ""))

    files_match = re.search(r"^Number of files:\s*(.+)$", output, flags=re.MULTILINE)
    if not files_match:
        return total_bytes, None, None

    line = files_match.group(1).strip()
    reg_match = re.search(r"\breg:\s*([0-9,]+)", line)
    dir_match = re.search(r"\bdir:\s*([0-9,]+)", line)
    has_breakdown = "(" in line
    regular = int(reg_match.group(1).replace(",", "")) if reg_match else (0 if has_breakdown else None)
    directories = int(dir_match.group(1).replace(",", "")) if dir_match else (0 if has_breakdown else None)

    if regular is None and not has_breakdown:
        # Older rsync: no distinction between regular files and directories.
        fallback = re.match(r"([0-9,]+)", line)
        if fallback:
            regular = int(fallback.group(1).replace(",", ""))
    return total_bytes, regular, directories


def build_ssh_command(args) -> str:
    """Build the rsync -e shell string, quoting SSH argument boundaries."""
    parts = [args.ssh_binary, "-p", str(args.port)]

    if args.key_file:
        parts.extend(("-i", os.path.expanduser(args.key_file)))

    # Reject unknown/changed host keys unless the caller explicitly opts out.
    if args.no_strict_host_key_checking:
        parts.extend(("-o", "StrictHostKeyChecking=no"))
        parts.extend(("-o", "UserKnownHostsFile=/dev/null"))
    elif args.accept_new_host_key:
        parts.extend(("-o", "StrictHostKeyChecking=accept-new"))
    else:
        parts.extend(("-o", "StrictHostKeyChecking=yes"))

    if args.known_hosts:
        parts.extend(("-o", "UserKnownHostsFile=" + os.path.expanduser(args.known_hosts)))

    has_prompt_auth = (args.password is not None or args.ask_password or
                       args.key_passphrase is not None or args.ask_key_passphrase)
    parts.extend(("-o", "BatchMode=no" if has_prompt_auth else "BatchMode=yes"))
    parts.extend(("-o", "ConnectTimeout={}".format(min(args.timeout, 30))))

    for option in args.ssh_option or []:
        parts.extend(("-o", option))

    return " ".join(shlex.quote(part) for part in parts)


def build_rsync_command(args, directory: str, empty_dest: str) -> List[str]:
    source = normalize_source_path(directory)
    # rsync's remote spec requires brackets around literal IPv6 addresses.
    host = args.host
    if ":" in host and not host.startswith("["):
        host = "[{}]".format(host)
    remote_spec = "{}@{}:{}".format(args.username, host, source)

    cmd = [
        args.rsync_binary,
        "-a",
        "--stats",
        "--numeric-ids",
        "-e",
        build_ssh_command(args),
    ]
    if not args.no_protect_args:
        cmd.append("--protect-args")
    if args.remote_rsync_path:
        cmd.extend(("--rsync-path", args.remote_rsync_path))
    for extra in args.extra_rsync_arg or []:
        cmd.append(extra)
    # Keep dry-run last, so even --extra-rsync-arg=--no-dry-run cannot turn
    # this inventory tool into a file-copy operation.
    cmd.append("--dry-run")
    cmd.extend((remote_spec, empty_dest + "/"))
    return cmd


def run_without_password(cmd: List[str], timeout: int) -> Tuple[int, str]:
    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C")
    completed = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )
    return completed.returncode, completed.stdout


def run_with_pexpect(
    cmd: List[str], timeout: int, password: Optional[str],
    key_passphrase: Optional[str],
) -> Tuple[int, str]:
    try:
        import pexpect
    except ImportError as exc:
        raise RuntimeError("Password/passphrase auth requires: pip install pexpect") from exc

    env = os.environ.copy()
    env.update(LC_ALL="C", LANG="C")
    child = pexpect.spawn(
        cmd[0], cmd[1:], encoding="utf-8", codec_errors="replace",
        timeout=timeout, env=env,
    )
    # Ensure typed secrets cannot be echoed back into captured output.
    child.setecho(False)
    output_parts = []
    password_attempts = 0
    passphrase_attempts = 0
    deadline = time.monotonic() + timeout
    patterns = [
        r"(?i)[^\r\n]*password:\s*",
        r"(?i)passphrase for key[^\r\n]*:\s*",
        pexpect.EOF,
        pexpect.TIMEOUT,
    ]
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("rsync command timed out")
            index = child.expect(patterns, timeout=remaining)
            output_parts.append(child.before)
            if index == 0:
                password_attempts += 1
                if password is None or password_attempts > 3:
                    raise RuntimeError("SSH password required or rejected")
                child.sendline(password)
            elif index == 1:
                passphrase_attempts += 1
                if key_passphrase is None or passphrase_attempts > 3:
                    raise RuntimeError("SSH key passphrase required or rejected")
                child.sendline(key_passphrase)
            elif index == 2:
                break
            else:
                raise TimeoutError("rsync command timed out")
        child.close()
        return child.exitstatus if child.exitstatus is not None else 1, "".join(output_parts)
    finally:
        if child.isalive():
            child.close(force=True)


def check_directory_size(args, directory: str, password: Optional[str],
                         key_passphrase: Optional[str]) -> Tuple[DirectoryResult, Optional[str]]:
    start_time = time.monotonic()
    output = None
    try:
        with tempfile.TemporaryDirectory(prefix="rsync-size-empty-") as empty_dest:
            cmd = build_rsync_command(args, directory, empty_dest)
            if password is not None or key_passphrase is not None:
                exit_code, output = run_with_pexpect(cmd, args.timeout, password, key_passphrase)
            else:
                exit_code, output = run_without_password(cmd, args.timeout)

        elapsed = round(time.monotonic() - start_time, 3)
        if exit_code:
            return DirectoryResult(
                directory, False, None, None, None, None, elapsed, exit_code,
                output.strip() if output else "rsync command failed",
            ), output

        bytes_total, files, dirs = parse_rsync_stats(output)
        return DirectoryResult(
            directory, True, bytes_total, human_size(bytes_total),
            files, dirs, elapsed, 0, None,
        ), output
    except (subprocess.TimeoutExpired, TimeoutError):
        return DirectoryResult(
            directory, False, None, None, None, None,
            round(time.monotonic() - start_time, 3), 124, "rsync command timed out",
        ), output
    except Exception as exc:
        return DirectoryResult(
            directory, False, None, None, None, None,
            round(time.monotonic() - start_time, 3), 1, str(exc),
        ), output


def build_summary(args, results: List[DirectoryResult], elapsed: float) -> SummaryResult:
    success = [item for item in results if item.success]
    total_bytes = sum(item.total_file_size_bytes or 0 for item in success)
    return SummaryResult(
        host=args.host,
        port=args.port,
        username=args.username,
        method="local-rsync-over-ssh",
        directory_count=len(results),
        success_count=len(success),
        failure_count=len(results) - len(success),
        total_file_size_bytes=total_bytes,
        total_file_size_human=human_size(total_bytes),
        total_number_of_files=sum(item.number_of_files or 0 for item in success),
        total_number_of_dirs=sum(item.number_of_dirs or 0 for item in success),
        elapsed_seconds=round(elapsed, 3),
        directories=results,
    )
