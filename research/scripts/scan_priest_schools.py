"""Scan effective priest spells (SPPR1xx-7xx) and report school distribution.

Effective resolution order: override copy wins, else KEY/BIF payload.
Prints one line per spell: school byte, level dword, resref, name strref, name text.
Used as recon evidence for chriz-bg-rebalance component 405 (Tempus Divination downside).
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from extract_key_resource import (  # type: ignore
    BIFF_HEADER,
    BIFF_VARIABLE_ENTRY,
    KEY_BIF_ENTRY,
    KEY_HEADER,
    KEY_RESOURCE_ENTRY,
    RESOURCE_TYPES,
    _decode_ascii,
    _resolve_bif_path,
)

SPPR_PATTERN = re.compile(r"^SPPR[1-7]\d\d$", re.IGNORECASE)


def read_tlk_strings(tlk_path: Path) -> list[str]:
    data = tlk_path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise SystemExit(f"not a TLK V1 file: {tlk_path}")
    count = struct.unpack_from("<I", data, 0x0A)[0]
    str_off = struct.unpack_from("<I", data, 0x0E)[0]
    out = []
    for i in range(count):
        entry = 0x12 + i * 26
        off, length = struct.unpack_from("<II", data, entry + 18)
        out.append(data[str_off + off : str_off + off + length].decode("utf-8", "replace"))
    return out


def collect_biffed_payloads(game_root: Path) -> dict[str, bytes]:
    key_data = (game_root / "chitin.key").read_bytes()
    signature, version, bif_count, resource_count, bif_offset, resource_offset = (
        KEY_HEADER.unpack_from(key_data)
    )
    if signature != b"KEY " or version != b"V1  ":
        raise SystemExit(f"unsupported KEY signature/version: {signature!r} {version!r}")

    bif_names: list[str] = []
    for index in range(bif_count):
        _size, name_offset, name_length, _loc = KEY_BIF_ENTRY.unpack_from(
            key_data, bif_offset + index * KEY_BIF_ENTRY.size
        )
        bif_names.append(_decode_ascii(key_data[name_offset : name_offset + name_length], "bif"))

    spl_type = RESOURCE_TYPES["SPL"]
    wanted: dict[int, list[tuple[str, int]]] = {}
    for index in range(resource_count):
        raw_resref, rtype, locator = KEY_RESOURCE_ENTRY.unpack_from(
            key_data, resource_offset + index * KEY_RESOURCE_ENTRY.size
        )
        if rtype != spl_type:
            continue
        resref = _decode_ascii(raw_resref, "resref")
        if not SPPR_PATTERN.match(resref):
            continue
        wanted.setdefault(locator >> 20, []).append((resref.upper(), locator & 0x3FFF))

    payloads: dict[str, bytes] = {}
    for bif_index, entries in wanted.items():
        bif_path = _resolve_bif_path(game_root, bif_names[bif_index])
        data = bif_path.read_bytes()
        sig, ver, variable_count, _fixed, table_offset = BIFF_HEADER.unpack_from(data)
        if sig != b"BIFF" or ver != b"V1  ":
            raise SystemExit(f"unsupported BIFF {bif_path}: {sig!r} {ver!r}")
        for resref, res_index in entries:
            entry_offset = table_offset + res_index * BIFF_VARIABLE_ENTRY.size
            _loc, payload_offset, payload_size, rtype, _unknown = (
                BIFF_VARIABLE_ENTRY.unpack_from(data, entry_offset)
            )
            if rtype == spl_type:
                payloads[resref] = data[payload_offset : payload_offset + payload_size]
    return payloads


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-root", required=True)
    ap.add_argument("--tlk", required=True)
    ap.add_argument("--school", type=int, help="only print spells with this school byte")
    args = ap.parse_args()

    root = Path(args.game_root)
    strings = read_tlk_strings(Path(args.tlk))

    payloads = collect_biffed_payloads(root)
    override_count = 0
    for p in (root / "override").glob("SPPR*.SPL"):
        if SPPR_PATTERN.match(p.stem):
            payloads[p.stem.upper()] = p.read_bytes()
            override_count += 1

    rows = []
    for resref in sorted(payloads):
        data = payloads[resref]
        if data[:8] != b"SPL V1  " or len(data) < 0x38:
            continue
        name_ref = struct.unpack_from("<I", data, 0x08)[0]
        school = data[0x25]
        level = struct.unpack_from("<I", data, 0x34)[0]
        name = strings[name_ref] if 0 <= name_ref < len(strings) else "<no name>"
        rows.append((school, level, resref, name_ref, name))

    shown = 0
    for school, level, resref, name_ref, name in sorted(rows):
        if args.school is not None and school != args.school:
            continue
        shown += 1
        print(f"school={school} L{level} {resref} strref={name_ref} {name!r}")
    print(
        f"-- total priest spells: {len(rows)} (override copies: {override_count}); shown: {shown}"
    )


if __name__ == "__main__":
    main()
