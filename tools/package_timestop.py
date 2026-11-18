"""Build unpublished full-mod, Hardiness, anti-magic, True Time Stop and Round Clock packages.

Both clock packages take their library, strings and Lua payloads from the full mod.
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
from tools.package_sr_antimagic import build as build_base
from tools.package_sr_hardiness import write_checksum


def version_of(path: Path) -> str:
    versions = re.findall(r"(?m)^VERSION ~([^~\r\n]+)~[ \t]*$", path.read_text(encoding="utf-8"))
    if len(versions) != 1:
        raise ValueError(f"Expected one VERSION in {path.name}")
    return versions[0]


def build(output: Path) -> list[Path]:
    version = version_of(ROOT / "setup-chriz-bg-rebalance.tp2")
    packages = (("CBR_TRUE_TIMESTOP", "time_stop_haste_clocks", "CBRTC"),
                ("CBR_ROUND_CLOCK", "round_clock", "CBRRC"))
    for name, _, _ in packages:
        if version_of(ROOT / "live-patch" / name / f"setup-{name.lower()}.tp2") != version:
            raise ValueError(f"Full and {name} installer versions must agree")
    result = build_base(output)
    source = ROOT / "chriz-bg-rebalance"
    for name, library, core in packages:
        tail = ROOT / "live-patch" / name
        tp2 = f"setup-{name.lower()}.tp2"
        files = {"LICENSE": ROOT / "LICENSE", "WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt",
                 f"Setup-{name.lower()}.exe": ROOT / "weidu.exe",
                 f"{name}/{tp2}": tail / tp2, f"{name}/README.md": tail / "README.md"}
        for path in ("languages/english/setup.tra", f"lib/{library}.tpa", f"lua/{core}.lua", f"lua/M_{core}.lua"):
            files[f"{name}/{path}"] = source / path
        archive = output / f"{name}-{version}-windows.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for relative, path in sorted(files.items()):
                entry = zipfile.ZipInfo(relative, date_time=(2026, 10, 6, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o644 << 16
                bundle.writestr(entry, path.read_bytes())
        write_checksum(archive)
        result.append(archive)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    for archive in build(parser.parse_args().output):
        print(archive)
