import re
from pathlib import Path

from losshound import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_package_and_build_versions_stay_in_sync():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None
    assert match.group(1) == __version__

    major, minor, patch = (int(part) for part in __version__.split("."))
    version_info = (ROOT / "scripts" / "version_info.txt").read_text(
        encoding="utf-8"
    )
    assert f"filevers=({major}, {minor}, {patch}, 0)" in version_info
    assert f"ProductVersion', '{__version__}.0'" in version_info
