"""Read-only category-9 ITM/SPL/EFF audit; this does not classify potion identity.

Enumerates every ability and equipped/casting slice, including conditional and
delayed possible payloads. It does not simulate which ability/condition wins,
decide whether an effect is beneficial, or authorize a refresh transformation.
Timing names describe storage, not proof of lifetime: some opcodes terminate
immediately even under permanent timing. Raw effect/ability bytes are retained.

CLI: python -B audit_potion_payloads.py --game-root GAME > outside-game.json
Alternatively --resources DIRECTORY audits loose fixtures without a KEY.
Only stdout is written. No extraction, game execution, installation or save reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Callable, Iterable

import extract_key_resource as keylib

# Explicit resource operands only. These are potential graph edges, not a claim
# that their targets/conditions/frequency are interchangeable with direct effects.
LINKS = {146: "SPL", 148: "SPL", 177: "EFF", 183: "EFF", 232: "SPL",
         248: "EFF", 249: "EFF", 272: "EFF", 283: "EFF", 326: "SPL", 333: "SPL"}
TIMING = {0: "limited_seconds", 1: "instant_or_permanent", 2: "while_equipped",
          3: "delayed_limited_seconds", 4: "delayed_permanent_seconds",
          5: "delayed_equipped_seconds", 6: "limited_after_absolute_tick",
          7: "permanent_after_absolute_tick", 8: "equipped_after_absolute_tick",
          9: "permanent_after_death", 10: "limited_ticks", 4096: "absolute_expiry_tick"}
STAT_GAINS = {0, 1, 6, 10, 15, 18, 19, 27, 28, 29, 30, 31, 33, 34, 35, 36, 37,
              44, 49, 54, 59, 90, 91, 92, 166, 275, 276, 277}


class AuditError(ValueError):
    pass


def checked(data: bytes, start: int, size: int, label: str) -> bytes:
    if start < 0 or size < 0 or start + size > len(data):
        raise AuditError(f"{label} out of bounds: {start:#x}+{size:#x}, file={len(data):#x}")
    return data[start:start + size]


def u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", checked(data, offset, 2, "word"))[0]


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", checked(data, offset, 4, "dword"))[0]


def i32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<i", checked(data, offset, 4, "signed dword"))[0]


def resref(raw: bytes) -> str:
    try:
        value = raw.split(b"\0", 1)[0].rstrip(b" ").decode("ascii").upper()
    except UnicodeDecodeError as exc:
        raise AuditError("non-ASCII resource operand") from exc
    if any(c in value for c in "\\/:") or value in {".", ".."}:
        raise AuditError(f"invalid resource operand {value!r}")
    return value


def effect(raw: bytes, *, external: bool = False) -> dict:
    if external:
        result = dict(opcode=u32(raw, 0x10), target=u32(raw, 0x14), power=u32(raw, 0x18),
                      parameter1=i32(raw, 0x1C), parameter2=u32(raw, 0x20),
                      timing=u16(raw, 0x24), duration=u32(raw, 0x28),
                      probability1=u16(raw, 0x2C), probability2=u16(raw, 0x2E),
                      special=u32(raw, 0x48))
        operand = raw[0x30:0x38]
    else:
        result = dict(opcode=u16(raw, 0), target=raw[2], power=raw[3],
                      parameter1=i32(raw, 4), parameter2=u32(raw, 8),
                      timing=raw[0xC], duration=u32(raw, 0xE),
                      probability1=raw[0x12], probability2=raw[0x13],
                      special=u32(raw, 0x2C))
        operand = raw[0x14:0x1C]
    # Unused operands frequently contain stale binary bytes in shipped files.
    # Validate only an operand that this audit actually traverses; retain raw data.
    result["resource"] = (resref(operand) if result["opcode"] in LINKS else
                          operand.split(b"\0", 1)[0].decode("ascii", "backslashreplace").upper())
    result["raw_hex"] = raw.hex()
    result["timing_class"] = TIMING.get(result["timing"], "unknown")
    notes = []
    if result["opcode"] == 18:
        notes.append("maximum_hp_refresh_requires_engine_review")
        if result["parameter2"] in {0, 1, 2, 6} and not result["special"] & 1:
            notes.append("current_hp_on_first_application")
    if result["opcode"] == 17:
        notes.append("current_hp_operation_not_a_timed_bonus")
    if result["opcode"] in STAT_GAINS and result["timing"] in {1, 4, 7, 9}:
        notes.append("permanent_stat_operation_or_persistent_modifier")
    if result["opcode"] in {206, 318, 321, 324}:
        notes.append("existing_protection_or_removal_requires_semantic_review")
    if result["opcode"] in {232, 248, 249, 272, 333}:
        notes.append("conditional_attack_or_repeating_payload")
    if result["opcode"] >= 400:
        notes.append("extension_opcode_not_interpreted")
    result["review_notes"] = notes
    return result


def parse_resource(name: str, data: bytes) -> dict:
    ext = name.rsplit(".", 1)[1]
    node = {"resource": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "slices": []}
    if ext == "EFF":
        checked(data, 0, 0x110, "EFF V2")
        if data[:8] != b"EFF V2.0":
            raise AuditError("unsupported external EFF format (requires V2)")
        e = effect(data[:0x110], external=True)
        e["offset"] = 0
        node["slices"].append({"kind": "external", "effects": [e]})
        return node
    if ext not in {"ITM", "SPL"}:
        raise AuditError("unsupported payload extension")
    checked(data, 0, 0x72, "header")
    if data[:8] != (ext + " V1  ").encode("ascii"):
        raise AuditError(f"unsupported {ext} format (requires V1)")
    node["raw_header_hex"] = data[:0x72].hex()
    if ext == "ITM":
        node["item_type"] = u16(data, 0x1C)
    aoff, acount, foff = u32(data, 0x64), u16(data, 0x68), u32(data, 0x6A)
    asize = 0x38 if ext == "ITM" else 0x28
    if acount:
        checked(data, aoff, acount * asize, "ability table")
        if aoff < 0x72:
            raise AuditError("ability table overlaps header")

    def add_slice(kind: str, first: int, count: int, ability: bytes | None = None) -> None:
        values = []
        if count:
            start, size = foff + first * 48, count * 48
            checked(data, start, size, f"{kind} effect slice")
            if start < 0x72 or (acount and start < aoff + acount * asize and start + size > aoff):
                raise AuditError(f"{kind} effect slice overlaps header/abilities")
            for idx in range(first, first + count):
                pos = foff + idx * 48
                e = effect(data[pos:pos + 48]); e["offset"] = pos
                values.append(e)
        item = {"kind": kind, "first_effect": first, "effects": values}
        if ability is not None:
            item.update(raw_ability_hex=ability.hex(), ability_type=ability[0],
                        ability_target=ability[0xC])
            if ext == "ITM":
                item.update(charges=u16(ability, 0x22), depletion=u16(ability, 0x24))
        node["slices"].append(item)

    add_slice("equipped" if ext == "ITM" else "casting", u16(data, 0x6E), u16(data, 0x70))
    for i in range(acount):
        a = data[aoff + i * asize:aoff + (i + 1) * asize]
        add_slice(f"ability:{i}", u16(a, 0x20), u16(a, 0x1E), a)
    return node


class ResourceStore:
    """Loose resources override KEY entries; every disk operation is read-only."""

    def __init__(self, directory: Path, *, game: bool = False):
        self.root = directory
        self.loose = {}
        self.index = {}
        self.bifs = []
        self.cache = {}
        folder = directory / "override" if game else directory
        if folder.is_dir():
            for p in folder.iterdir():
                if p.is_file() and p.suffix.upper() in {".ITM", ".SPL", ".EFF"}:
                    name = p.name.upper()
                    if name in self.loose:
                        raise AuditError(f"duplicate case-insensitive resource {name}")
                    self.loose[name] = p
        elif not game:
            raise AuditError(f"resource directory missing: {folder}")
        if game:
            data = (directory / "chitin.key").read_bytes()
            checked(data, 0, keylib.KEY_HEADER.size, "KEY header")
            sig, ver, bc, rc, bo, ro = keylib.KEY_HEADER.unpack_from(data)
            if (sig, ver) != (b"KEY ", b"V1  "):
                raise AuditError("unsupported KEY format")
            checked(data, bo, bc * keylib.KEY_BIF_ENTRY.size, "KEY BIF table")
            checked(data, ro, rc * keylib.KEY_RESOURCE_ENTRY.size, "KEY resource table")
            for i in range(bc):
                _, off, size, _ = keylib.KEY_BIF_ENTRY.unpack_from(data, bo + i * 12)
                filename = checked(data, off, size, "KEY BIF name").rstrip(b"\0").decode("ascii")
                self.bifs.append(keylib._resolve_bif_path(directory, filename))
            wanted = {keylib.RESOURCE_TYPES[ext]: ext for ext in ("ITM", "SPL", "EFF")}
            for i in range(rc):
                raw, typ, locator = keylib.KEY_RESOURCE_ENTRY.unpack_from(data, ro + i * 14)
                if typ in wanted:
                    name = resref(raw) + "." + wanted[typ]
                    if name in self.index:
                        raise AuditError(f"duplicate KEY resource {name}")
                    self.index[name] = (typ, locator)

    def names(self) -> list[str]:
        return sorted(set(self.loose) | set(self.index))

    def read(self, name: str) -> bytes:
        name = name.upper()
        if name not in self.cache:
            if name in self.loose:
                value = self.loose[name].read_bytes()
            elif name in self.index:
                typ, locator = self.index[name]
                bif = locator >> 20
                if bif >= len(self.bifs):
                    raise AuditError(f"KEY BIF index out of bounds: {name}")
                value, *_ = keylib._read_biff_resource(self.bifs[bif], locator & keylib.RESOURCE_INDEX_MASK, typ)
            else:
                raise FileNotFoundError(name)
            self.cache[name] = value
        return self.cache[name]


def audit(names: Iterable[str], read: Callable[[str], bytes], *, max_depth: int = 16,
          max_nodes: int = 256) -> dict:
    if max_depth < 0 or max_nodes < 1:
        raise ValueError("max_depth must be nonnegative and max_nodes positive")
    report = {"schema": 1, "scope": "potential payload graph; not simulation or clone identity",
              "limitations": ["Only listed explicit SPL/EFF link operands are traversed.",
                              "No condition, projectile, actor, script, or Lua execution is simulated.",
                              "No beneficial/adverse/quest classification or semantic clone grouping is inferred.",
                              "Shared payloads may also have consumers outside potion graphs."],
              "supported_link_opcodes": LINKS, "potions": [], "diagnostics": []}
    for name in sorted({n.upper() for n in names if n.upper().endswith(".ITM")}):
        try:
            data = read(name)
            checked(data, 0, 0x1E, "item category")
            if u16(data, 0x1C) != 9:
                continue
        except (OSError, ValueError, keylib.ExtractionError) as exc:
            report["diagnostics"].append({"resource": name, "code": "item_read_error", "detail": str(exc)})
            continue
        item = {"resource": name, "nodes": {}, "edges": [], "diagnostics": []}

        def visit(current: str, ancestors: tuple[str, ...]) -> None:
            def diagnostic(code: str, detail: str = "") -> None:
                item["diagnostics"].append({"resource": current, "code": code,
                                            "path": list(ancestors + (current,)), "detail": detail})
            if current in ancestors:
                diagnostic("cycle"); return
            if current in item["nodes"]:
                return
            if len(ancestors) > max_depth:
                diagnostic("depth_limit"); return
            if len(item["nodes"]) >= max_nodes:
                diagnostic("node_limit"); return
            try:
                node = parse_resource(current, read(current))
            except FileNotFoundError as exc:
                diagnostic("missing_resource", str(exc)); return
            except (OSError, ValueError, keylib.ExtractionError) as exc:
                diagnostic("invalid_resource", str(exc)); return
            item["nodes"][current] = node
            for part in node["slices"]:
                for e in part["effects"]:
                    if e["opcode"] >= 400:
                        diagnostic("extension_opcode_uninterpreted", f"opcode {e['opcode']} at {e['offset']:#x}")
                    typ = LINKS.get(e["opcode"])
                    if typ:
                        if not e["resource"]:
                            diagnostic("empty_or_implicit_link", f"opcode {e['opcode']} at {e['offset']:#x}")
                            continue
                        target = e["resource"] + "." + typ
                        item["edges"].append({"source": current, "slice": part["kind"],
                                               "offset": e["offset"], "opcode": e["opcode"], "target": target})
                        visit(target, ancestors + (current,))
        visit(name, ())
        effects = [e for node in item["nodes"].values() for part in node["slices"] for e in part["effects"]]
        item["timing_counts"] = dict(Counter(e["timing_class"] for e in effects))
        item["hp_review"] = any(e["opcode"] == 18 for e in effects)
        item["current_hp_operation"] = any(e["opcode"] == 17 for e in effects)
        item["incomplete"] = bool(item["diagnostics"])
        report["potions"].append(item)
    report["incomplete"] = bool(report["diagnostics"]) or any(p["incomplete"] for p in report["potions"])
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--game-root", type=Path)
    source.add_argument("--resources", type=Path)
    parser.add_argument("--max-depth", type=int, default=16)
    parser.add_argument("--max-nodes", type=int, default=256)
    args = parser.parse_args(argv)
    try:
        store = ResourceStore(args.game_root or args.resources, game=args.game_root is not None)
        result = audit(store.names(), store.read, max_depth=args.max_depth, max_nodes=args.max_nodes)
    except (OSError, ValueError, keylib.ExtractionError) as exc:
        print(json.dumps({"incomplete": True, "error": str(exc)}))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["incomplete"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
