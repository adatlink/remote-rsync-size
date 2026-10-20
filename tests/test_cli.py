import json
import os
from pathlib import Path
import stat
import sys

from remote_rsync_size.cli import main


def fake_rsync(tmp_path):
    """Stand-in local executable, verifies argv JSON remains parseable."""
    script = tmp_path / "fake-rsync"
    script.write_text(
        "#!{}\n".format(sys.executable) +
        "import sys\n"
        "path = sys.argv[-2]\n"
        "if '/bad/' in path:\n"
        "    print('rsync: link_stat failed: No such file or directory')\n"
        "    sys.exit(23)\n"
        "elif '/one/' in path:\n"
        "    print('Number of files: 5 (reg: 3, dir: 2)')\n"
        "    print('Total file size: 1,024 bytes')\n"
        "else:\n"
        "    print('Number of files: 9 (reg: 7, dir: 2)')\n"
        "    print('Total file size: 2,048 bytes')\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_cli_multiple_results_and_times(tmp_path, capsys):
    rsync = fake_rsync(tmp_path)
    status = main([
        "/one", "/two", "--host", "example.com", "--username", "tester",
        "--rsync-binary", rsync,
        "--ssh-binary", sys.executable,
        "--json",
    ])
    assert status == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["directory_count"] == 2
    assert obj["success_count"] == 2
    assert obj["failure_count"] == 0
    assert obj["total_file_size_bytes"] == 3072
    assert obj["total_number_of_files"] == 10
    assert obj["total_number_of_dirs"] == 4
    assert isinstance(obj["elapsed_seconds"], float)
    assert all(isinstance(r["elapsed_seconds"], float) for r in obj["directories"])
    assert [r["number_of_files"] for r in obj["directories"]] == [3, 7]
    assert [r["number_of_dirs"] for r in obj["directories"]] == [2, 2]


def test_cli_partial_failure_still_produces_complete_json(tmp_path, capsys):
    rsync = fake_rsync(tmp_path)
    status = main([
        "/one", "/bad", "--host", "example.com", "--username", "tester",
        "--rsync-binary", rsync, "--ssh-binary", sys.executable,
    ])
    assert status == 1
    obj = json.loads(capsys.readouterr().out)
    assert obj["success_count"] == 1
    assert obj["failure_count"] == 1
    assert obj["total_file_size_bytes"] == 1024
    assert obj["directories"][1]["success"] is False
    assert obj["directories"][1]["number_of_dirs"] is None
    assert obj["directories"][1]["exit_code"] == 23


def test_cli_always_exit_zero(tmp_path, capsys):
    rsync = fake_rsync(tmp_path)
    status = main([
        "/bad", "--host", "x", "--username", "y",
        "--rsync-binary", rsync, "--ssh-binary", sys.executable,
        "--always-exit-zero", "--compact",
    ])
    assert status == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["failure_count"] == 1


def test_cli_missing_binary_json(capsys):
    status = main([
        "/one", "--host", "x", "--username", "y",
        "--rsync-binary", "/not/a/real/rsync",
    ])
    assert status == 2
    data = json.loads(capsys.readouterr().out)
    assert data["success"] is False


def test_show_rsync_goes_to_stderr(tmp_path, capsys):
    rsync = fake_rsync(tmp_path)
    status = main([
        "/one", "--host", "x", "--username", "y",
        "--rsync-binary", rsync, "--ssh-binary", sys.executable,
        "--show-rsync-output",
    ])
    assert status == 0
    captures = capsys.readouterr()
    assert "Number of files" in captures.err
    json.loads(captures.out)
