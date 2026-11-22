"""Build the unpublished standalone CBR_DUCAL_PALACE live-patch archive.

Takes its library and English strings from the full mod source.
Does not inspect or write a game installation, invoke WeiDU, or use the network.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.package_sr_hardiness import write_checksum


def version_of(path: Path) -> str:
    versions = re.findall(r"(?m)^VERSION ~([^~\r\n]+)~[ \t]*$", path.read_text(encoding="utf-8"))
    if len(versions) != 1:
        raise ValueError(f"Expected one VERSION in {path.name}")
    return versions[0]


def build(output: Path) -> list[Path]:
    version = version_of(ROOT / "setup-chriz-bg-rebalance.tp2")
    package = "CBR_DUCAL_PALACE"
    tp2 = "setup-cbr_ducal_palace.tp2"
    tail = ROOT / "live-patch" / package
    if version_of(tail / tp2) != version:
        raise ValueError(f"Full and {package} installer versions must agree")
    output.mkdir(parents=True, exist_ok=True)
    source = ROOT / "chriz-bg-rebalance"
    files = {
        "LICENSE": ROOT / "LICENSE",
        "WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt",
        "Setup-cbr_ducal_palace.exe": ROOT / "weidu.exe",
        f"{package}/{tp2}": tail / tp2,
        f"{package}/README.md": tail / "README.md",
        f"{package}/lib/ducal_palace.tpa": source / "lib/ducal_palace.tpa",
        f"{package}/languages/english/setup.tra": source / "languages/english/setup.tra",
    }
    archive = output / f"{package}-{version}-windows.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative, path in sorted(files.items()):
            entry = zipfile.ZipInfo(relative, date_time=(2026, 10, 6, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            bundle.writestr(entry, path.read_bytes())
    write_checksum(archive)
    return [archive]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    for archive in build(parser.parse_args().output):
        print(archive)
