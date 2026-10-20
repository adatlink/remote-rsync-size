"""PTY authentication smoke tests without requiring an SSH server."""

from pathlib import Path
import sys

import pytest

from remote_rsync_size.core import run_with_pexpect


def fake_auth_script(tmp_path: Path, prompt: str, expected: str) -> str:
    script = tmp_path / "mock_interactive_remote.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.write({!r})\n".format(prompt) +
        "sys.stdout.flush()\n"
        "secret = sys.stdin.readline().strip()\n"
        "if secret != {!r}:\n".format(expected) +
        "    print('authentication failed')\n"
        "    sys.exit(7)\n"
        "print('Number of files: 5 (reg: 3, dir: 2)')\n"
        "print('Total file size: 1,024 bytes')\n"
    )
    return str(script)


@pytest.mark.parametrize("prompt,secret,password,passphrase", [
    ("tester@localhost's password: ", "pass123", "pass123", None),
    ("Enter passphrase for key '/keyfile': ", "key123", None, "key123"),
])
def test_pexpect_auth(tmp_path, prompt, secret, password, passphrase):
    pytest.importorskip("pexpect")
    script = fake_auth_script(tmp_path, prompt, secret)
    code, output = run_with_pexpect(
        [sys.executable, script], 10, password=password, key_passphrase=passphrase
    )
    assert code == 0
    assert "Total file size: 1,024 bytes" in output
    assert secret not in output
