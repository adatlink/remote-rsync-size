import pytest

from remote_rsync_size.core import human_size, normalize_source_path, parse_rsync_stats


@pytest.mark.parametrize("sample,expected", [
    (
        "Number of files: 208,425 (reg: 176,546, dir: 31,879)\n"
        "Total file size: 1,234,567,890 bytes\n",
        (1234567890, 176546, 31879),
    ),
    (
        "Number of files: 1,111 (reg: 1,000, dir: 100, link: 11)\r\n"
        "Total file size: 1,234 bytes\r\n",
        (1234, 1000, 100),
    ),
    (
        "Number of files: 2 (dir: 1, link: 1)\nTotal file size: 0 bytes\n",
        (0, 0, 1),
    ),
    (
        "Number of files: 24\nTotal file size: 5 bytes\n",
        (5, 24, None),
    ),
    (
        "Total file size: 0 bytes\n",
        (0, None, None),
    ),
])
def test_parse_rsync_stats(sample, expected):
    assert parse_rsync_stats(sample) == expected


def test_parse_missing_size_raises():
    with pytest.raises(ValueError, match="Total file size"):
        parse_rsync_stats("Number of files: 2")


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(1024) == "1.00 KiB"
    assert human_size(123456789) == "117.74 MiB"


@pytest.mark.parametrize("raw,want", [
    ("/", "/"),
    ("/tmp/data", "/tmp/data/"),
    ("/tmp/data///", "/tmp/data/"),
    ("relative", "relative/"),
])
def test_normalize(raw, want):
    assert normalize_source_path(raw) == want


def test_normalize_empty():
    with pytest.raises(ValueError):
        normalize_source_path("")
