"""Build unpublished full-mod, Hardiness and anti-magic Windows packages."""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.package_sr_hardiness import build as build_base


def build(output: Path) -> list[Path]:
    setup = ROOT / "setup-chriz-bg-rebalance.tp2"
    tail = ROOT / "live-patch/CBR_SR_ANTIMAGIC"
    version = re.search(r"VERSION ~([^~]+)~", setup.read_text()).group(1)
    tail_setup = tail / "setup-cbr_sr_antimagic.tp2"
    if f"VERSION ~{version}~" not in tail_setup.read_text():
        raise ValueError("Full and anti-magic installer versions must agree")
    result = build_base(output)
    files = {
        "LICENSE": ROOT / "LICENSE",
        "WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt",
        "Setup-cbr_sr_antimagic.exe": ROOT / "weidu.exe",
        "CBR_SR_ANTIMAGIC/setup-cbr_sr_antimagic.tp2": tail_setup,
        "CBR_SR_ANTIMAGIC/README.md": tail / "README.md",
        "CBR_SR_ANTIMAGIC/languages/english/setup.tra": ROOT / "chriz-bg-rebalance/languages/english/setup.tra",
        "CBR_SR_ANTIMAGIC/lua/M_CBRPM.lua": ROOT / "chriz-bg-rebalance/lua/M_CBRPM.lua",
    }
    for library in ("sr_antimagic.tpa", "sr_spellstrike.tpa"):
        files[f"CBR_SR_ANTIMAGIC/lib/{library}"] = ROOT / "chriz-bg-rebalance/lib" / library
    archive = output / f"CBR_SR_ANTIMAGIC-{version}-windows.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative, source in sorted(files.items()):
            entry = zipfile.ZipInfo(relative, date_time=(2026, 10, 6, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            bundle.writestr(entry, source.read_bytes())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
    return result + [archive]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    for archive in build(parser.parse_args().output):
        print(archive)
