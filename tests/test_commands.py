import shlex

from remote_rsync_size.cli import make_parser
from remote_rsync_size.core import build_rsync_command, build_ssh_command


def args_for(*extras):
    return make_parser().parse_args(
        ["/remote dir", "--host", "example.com", "--username", "tester"] + list(extras)
    )


def test_key_ssh_cmd_quotes_space_in_identity_path():
    args = args_for("--key-file", "/home/me/key with spaces", "--port", "2200")
    ssh = shlex.split(build_ssh_command(args))
    assert ssh[0] == "ssh"
    assert ssh[ssh.index("-p") + 1] == "2200"
    assert ssh[ssh.index("-i") + 1] == "/home/me/key with spaces"
    assert "StrictHostKeyChecking=yes" in ssh
    assert "BatchMode=yes" in ssh


def test_auth_and_keys_options():
    args = args_for("--ask-password", "--accept-new-host-key", "--ssh-option", "ProxyJump=bastion")
    ssh = shlex.split(build_ssh_command(args))
    assert "BatchMode=no" in ssh
    assert "StrictHostKeyChecking=accept-new" in ssh
    assert "ProxyJump=bastion" in ssh


def test_rsync_build_protected_spaces():
    args = args_for("--remote-rsync-path", "/usr/bin/rsync")
    cmd = build_rsync_command(args, "/remote dir", "/tmp/empty-dir")
    assert cmd[0] == "rsync"
    assert "--dry-run" in cmd
    assert "--stats" in cmd
    assert "--protect-args" in cmd
    assert cmd[-2:] == ["tester@example.com:/remote dir/", "/tmp/empty-dir/"]
    assert cmd[cmd.index("--rsync-path") + 1] == "/usr/bin/rsync"


def test_rsync_build_ipv6_and_no_protect():
    args = args_for("--no-protect-args", "--extra-rsync-arg=--one-file-system")
    args.host = "2001:db8::1"
    cmd = build_rsync_command(args, "/a", "/tmp/empty")
    assert "--protect-args" not in cmd
    assert "--one-file-system" in cmd
    assert cmd[-2] == "tester@[2001:db8::1]:/a/"


def test_cannot_disable_dry_run_with_extra_argument():
    args = args_for("--extra-rsync-arg=--no-dry-run")
    cmd = build_rsync_command(args, "/foo", "/tmp/empty")
    assert cmd.index("--dry-run") > cmd.index("--no-dry-run")
