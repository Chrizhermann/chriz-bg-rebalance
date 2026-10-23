"""Spell Revisions' Cloudkill for the Time Clocks lab's area case G, without installing SR.

Usage:
  python -B research/timestop-lab/sr_cloudkill.py describe GAME SR_ROOT
  python -B research/timestop-lab/sr_cloudkill.py build GAME SR_ROOT ABSOLUTE_OUTPUT_DIRECTORY

SR_ROOT is the folder that holds SR 4.19.rc5's spell_rev folder; its three files are read only
and must have the reviewed bytes (SOURCES). GAME is the lab: its stock PROJECTL.IDS is read from
chitin.key and its BIF, never from override. Four files result, under names the stock game does
not use, so the stock Cloudkill (SPWI502, case A) stays as it is:

- DVCKILL.PRO: SR's own Cloudkill projectile, unchanged (it references only stock resources).
- PROJECTL.IDS: the stock list and "N DVCKILL", N one above its highest value, as WeiDU's
  ADD_PROJECTILE does; the projectile's spell value is N + 1.
- CBRTSRCK.SPL: SR's spwi502.spl with that projectile value at 0x98 (SR's installer writes the
  same field), its op177 pointed at CBRTSRCI, and no name or description strings (SR sets them
  from its own TLK entries at install).
- CBRTSRCI.EFF: SR's spwi502i.eff (op206 protection from the spell, for undead targets) with the
  spell renamed to CBRTSRCK.

This is a lab resource, not a game change: it is staged only into the Time Clocks lab
(Stage-Diagnostics.ps1 -SpellRevisionsRoot) and never enters the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qa_menu import MenuError, read_key_resource  # noqa: E402

IDS_TYPE = 0x3F0
# SR 4.19.rc5, as unpacked in the read-only mod archive.
SOURCES = {
    "spl": ("spell_rev/spwi5##/spwi502.spl", "fd8940e237828ccf35539a1ab9a905bb21e622fbc091efd06e690a93b6f86b95"),
    "eff": ("spell_rev/spwi5##/spwi502i.eff", "0ee436a44a925edbfb4adb8010583f7c172347ca8efe1cc53fe8cfef18b81280"),
    "pro": ("spell_rev/projectles/dvckill.pro", "12e06ec4d18553b686097342c95581d27959ed4c479ed96fe2109709b47e9c35"),
}
SPELL, EFFECT, PROJECTILE = "CBRTSRCK", "CBRTSRCI", "DVCKILL"


class CloudkillError(RuntimeError):
    pass


def _resref(data: bytes, offset: int) -> str:
    return data[offset:offset + 8].split(b"\0")[0].decode("latin-1").upper()


def _set_resref(data: bytearray, offset: int, name: str) -> None:
    data[offset:offset + 8] = name.encode("ascii").ljust(8, b"\0")


def read_sources(sr_root: Path, pins: dict | None = None) -> dict[str, bytes]:
    pins = SOURCES if pins is None else pins
    out = {}
    for key, (relative, digest) in pins.items():
        data = (sr_root / relative).read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise CloudkillError(f"{relative} is not the reviewed Spell Revisions 4.19.rc5 file")
        out[key] = data
    return out


def projectile_list(stock: bytes) -> tuple[bytes, int]:
    """The stock PROJECTL.IDS with DVCKILL appended one above its highest value."""
    text = stock.decode("latin-1")
    values = []
    for line in text.splitlines()[1:]:
        match = re.match(r"\s*(0[xX][0-9A-Fa-f]+|\d+)\s+(\S+)", line)
        if match:
            if match.group(2).upper() == PROJECTILE:
                raise CloudkillError("PROJECTL.IDS already lists DVCKILL")
            value = match.group(1)
            values.append(int(value, 16) if value[:2].lower() == "0x" else int(value, 10))
    if not text.startswith("IDS") or not values:
        raise CloudkillError("The stock PROJECTL.IDS has no entries")
    number = max(values) + 1
    newline = "\r\n" if "\r\n" in text else "\n"
    body = text if text.endswith(("\n", "\r")) else text + newline
    return (body + f"{number} {PROJECTILE}{newline}").encode("latin-1"), number


def build_files(sources: dict[str, bytes], stock_ids: bytes) -> tuple[dict[str, bytes], dict]:
    spl, eff, pro = bytearray(sources["spl"]), bytearray(sources["eff"]), sources["pro"]
    if spl[:8] != b"SPL V1  " or eff[:8] != b"EFF V2.0" or pro[:8] != b"PRO V1.0":
        raise CloudkillError("Unexpected file signatures")
    if struct.unpack_from("<H", pro, 0x08)[0] != 3:
        raise CloudkillError("DVCKILL.PRO is not an area projectile")
    ability_offset, abilities, effects_offset = struct.unpack_from("<IHI", spl, 0x64)
    if (ability_offset, abilities) != (0x72, 1):
        raise CloudkillError("spwi502.spl does not have its one ability at 0x72")
    count, first = struct.unpack_from("<HH", spl, ability_offset + 0x1E)
    uses = [effects_offset + 0x30 * (first + k) for k in range(count)
            if struct.unpack_from("<H", spl, effects_offset + 0x30 * (first + k))[0] == 177]
    if len(uses) != 1 or _resref(spl, uses[0] + 0x14) != "SPWI502I":
        raise CloudkillError("spwi502.spl does not use SPWI502I once")
    if _resref(eff, 0x30) != "SPWI502":
        raise CloudkillError("spwi502i.eff does not name SPWI502")
    ids, number = projectile_list(stock_ids)
    struct.pack_into("<H", spl, 0x98, number + 1)
    _set_resref(spl, uses[0] + 0x14, EFFECT)
    for offset in (0x08, 0x0C, 0x50, 0x54):
        struct.pack_into("<i", spl, offset, -1)
    _set_resref(eff, 0x30, SPELL)
    files = {f"{SPELL}.SPL": bytes(spl), f"{EFFECT}.EFF": bytes(eff), f"{PROJECTILE}.PRO": pro, "PROJECTL.IDS": ids}
    return files, {"projectl_value": number, "spell_projectile": number + 1}


def describe(game: Path | str, sr_root: Path | str) -> tuple[dict[str, bytes], dict]:
    stock, source = read_key_resource(Path(game), "PROJECTL", IDS_TYPE)
    files, numbers = build_files(read_sources(Path(sr_root)), stock)
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    digest = hashlib.sha256("".join(f"{name}\t{hashes[name]}\n" for name in sorted(hashes)).encode()).hexdigest()
    return files, {"files": hashes, "digest": digest,
                   "sources": {key: pin for key, (_, pin) in SOURCES.items()},
                   "stock_projectl_sha256": hashlib.sha256(stock).hexdigest(), "stock_source": source, **numbers}


def _reject_linked_path(path: Path) -> None:
    for candidate in (*reversed(path.parents), path):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
                getattr(metadata, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)):
            raise CloudkillError(f"linked/reparse path rejected: {candidate}")


def build(game: Path | str, sr_root: Path | str, output_directory: Path | str) -> dict:
    """Write the four files exclusively into OUTPUT_DIRECTORY, whose parent must exist."""
    output = Path(output_directory)
    if not output.is_absolute() or ".." in output.parts:
        raise CloudkillError("Output directory must be an absolute path without '..'")
    _reject_linked_path(output)
    if not output.parent.is_dir():
        raise CloudkillError("Output directory's parent must already exist")
    files, description = describe(game, sr_root)
    output.mkdir(exist_ok=True)
    existing = {entry.name.casefold() for entry in output.iterdir()}
    if any(name.casefold() in existing for name in files):
        raise FileExistsError(f"Refusing to overwrite files in {output}")
    for name, data in files.items():
        with (output / name).open("xb") as handle:
            handle.write(data)
    return {"output": str(output), **description}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    describe_parser = commands.add_parser("describe")
    describe_parser.add_argument("game", type=Path)
    describe_parser.add_argument("sr_root", type=Path)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("game", type=Path)
    build_parser.add_argument("sr_root", type=Path)
    build_parser.add_argument("output_directory", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "describe":
            print(json.dumps(describe(args.game, args.sr_root)[1], separators=(",", ":")))
        else:
            print(json.dumps(build(args.game, args.sr_root, args.output_directory), separators=(",", ":")))
    except (OSError, CloudkillError, MenuError) as error:
        print(f"CBR_SR_CLOUDKILL_ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
