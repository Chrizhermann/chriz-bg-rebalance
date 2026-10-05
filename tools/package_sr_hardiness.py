"""Build unpublished full-mod and tail-patch archives from the same source.

Does not inspect or write a game installation, invoke WeiDU, or use the network.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path) -> list[Path]:
    setup = ROOT / "setup-chriz-bg-rebalance.tp2"
    version = re.search(r"VERSION ~([^~]+)~", setup.read_text(encoding="utf-8")).group(1)
    tail = ROOT / "live-patch/CBR_SR_HARDINESS"
    tail_version = re.search(r"VERSION ~([^~]+)~", (tail / "setup-cbr_sr_hardiness.tp2").read_text()).group(1)
    if version != tail_version:
        raise ValueError("Full and standalone installer versions must agree")
    output.mkdir(parents=True, exist_ok=True)

    common = {"WEIDU-LICENSE.txt": ROOT / "WEIDU-LICENSE.txt", "LICENSE": ROOT / "LICENSE"}
    full = {**common, "setup-chriz-bg-rebalance.tp2": setup,
            "Setup-chriz-bg-rebalance.exe": ROOT / "weidu.exe",
            "README.md": ROOT / "README.md", "CHANGELOG.md": ROOT / "CHANGELOG.md"}
    for path in sorted((ROOT / "chriz-bg-rebalance").rglob("*")):
        if path.is_file():
            full[path.relative_to(ROOT).as_posix()] = path
    standalone = {**common,
        "Setup-cbr_sr_hardiness.exe": ROOT / "weidu.exe",
        "CBR_SR_HARDINESS/setup-cbr_sr_hardiness.tp2": tail / "setup-cbr_sr_hardiness.tp2",
        "CBR_SR_HARDINESS/README.md": tail / "README.md",
        "CBR_SR_HARDINESS/lib/sr_hardiness.tpa": ROOT / "chriz-bg-rebalance/lib/sr_hardiness.tpa",
        "CBR_SR_HARDINESS/languages/english/setup.tra": ROOT / "chriz-bg-rebalance/languages/english/setup.tra",
    }
    result = []
    for name, files in ((f"chriz-bg-rebalance-{version}-windows.zip", full),
                        (f"CBR_SR_HARDINESS-{version}-windows.zip", standalone)):
        archive = output / name
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for relative, source in sorted(files.items()):
                entry = zipfile.ZipInfo(relative, date_time=(2026, 10, 6, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o644 << 16
                bundle.writestr(entry, source.read_bytes())
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix(archive.suffix + ".sha256").write_text(f"{digest}  {archive.name}\n")
        result.append(archive)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    for archive in build(args.output):
        print(archive)
