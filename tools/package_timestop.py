"""Build unpublished full-mod, Hardiness, anti-magic and Time Stop/Haste Windows packages.

The Time Stop/Haste package is component 360 on its own: its tp2 and README from
live-patch/CBR_TIMESTOP, the library, strings and both Lua files from chriz-bg-rebalance/.
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


def build(output: Path) -> list[Path]:
    setup = ROOT / "setup-chriz-bg-rebalance.tp2"
    tail = ROOT / "live-patch/CBR_TIMESTOP"
    version = re.search(r"VERSION ~([^~]+)~", setup.read_text(encoding="utf-8")).group(1)
    tail_setup = tail / "setup-cbr_timestop.tp2"
    if f"VERSION ~{version}~" not in tail_setup.read_text(encoding="utf-8"):
        raise ValueError("Full and Time Stop/Haste installer versions must agree")
    result = build_base(output)
    source = ROOT / "chriz-bg-rebalance"
    files = {
        "LICENSE": ROOT / "LICENSE",
        "WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt",
        "Setup-cbr_timestop.exe": ROOT / "weidu.exe",
        "CBR_TIMESTOP/setup-cbr_timestop.tp2": tail_setup,
        "CBR_TIMESTOP/README.md": tail / "README.md",
        "CBR_TIMESTOP/languages/english/setup.tra": source / "languages/english/setup.tra",
        "CBR_TIMESTOP/lib/time_stop_haste_clocks.tpa": source / "lib/time_stop_haste_clocks.tpa",
        # The same file names as component 360, so only one copy can ever be installed.
        "CBR_TIMESTOP/lua/CBRTC.lua": source / "lua/CBRTC.lua",
        "CBR_TIMESTOP/lua/M_CBRTC.lua": source / "lua/M_CBRTC.lua",
    }
    archive = output / f"CBR_TIMESTOP-{version}-windows.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for relative, path in sorted(files.items()):
            entry = zipfile.ZipInfo(relative, date_time=(2026, 10, 6, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            bundle.writestr(entry, path.read_bytes())
    write_checksum(archive)
    return result + [archive]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    for archive in build(parser.parse_args().output):
        print(archive)
