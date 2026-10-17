"""Opt-in captured potion graph checks for the quarantined research prototype.

The disposable fixture installer is not part of the released mod. Success here
means resource preservation/idempotence only; native delivery, dispel level,
duration scaling and admission ordering remain independently unproven or broken.

Set CBR_POTION_CAPTURE_ROOT to an explicit read-only game root or flat loose
fixture directory. Multiple roots may be separated by os.pathsep. Set
CBR_POTION_CAPTURE_SR=1 to install a synthetic SR marker in the disposable game.
Optional CBR_POTION_CAPTURE_TLK supplies text for a loose fixture directory.

Only category-9 ITMs and their explicit linked SPL/EFF closure are copied. Whole
game consumers (creatures/scripts/items/spells outside that closure), runtime
inventory/save state, and external original-resource protections are omitted.
This validates captured resources and installer behavior, not that omitted
consumers or native runtime interactions have been playtested. Proprietary bytes
remain in temporary directories; no fixture path is implicit.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_potion_uniqueness_installer import LIBRARY, PotionGame

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/scripts"))
import audit_potion_payloads as audit
import extract_key_resource as keylib

CAPTURE_ROOTS = [Path(p) for p in os.environ.get("CBR_POTION_CAPTURE_ROOT", "").split(os.pathsep) if p]


def read_extra(root: Path, name: str, *, game: bool) -> bytes | None:
    """Effective read for an optional 2DA, without exporting to the source."""
    folder = root / "override" if game else root
    matches = ([p for p in folder.iterdir() if p.is_file() and p.name.upper() == name.upper()]
               if folder.is_dir() else [])
    if len(matches) > 1:
        raise ValueError(f"ambiguous case-insensitive extra resource {name}")
    if matches:
        return matches[0].read_bytes()
    if not game:
        return None
    resref, extension = name.rsplit(".", 1)
    key = (root / "chitin.key").read_bytes()
    try:
        _, locator, bifs = keylib._find_key_resource(key, resref, keylib.RESOURCE_TYPES[extension])
    except keylib.ExtractionError as error:
        if "not found" in str(error).lower():
            return None
        raise
    _, bif_name = bifs[locator >> 20]
    bif = keylib._resolve_bif_path(root, bif_name)
    return keylib._read_biff_resource(bif, locator & keylib.RESOURCE_INDEX_MASK,
                                    keylib.RESOURCE_TYPES[extension])[0]


def capture(root: Path):
    if not root.is_absolute() or not root.is_dir():
        raise ValueError(f"capture root must be an existing absolute directory: {root}")
    is_game = (root / "chitin.key").is_file()
    store = audit.ResourceStore(root, game=is_game)
    report = audit.audit(store.names(), store.read)
    if report["incomplete"]:
        raise ValueError("capture graph is incomplete: " + json.dumps({
            "diagnostics": report["diagnostics"],
            "potions": [{"resource": p["resource"], "diagnostics": p["diagnostics"]}
                        for p in report["potions"] if p["incomplete"]]}, ensure_ascii=True))
    names = {name for potion in report["potions"] for name in potion["nodes"]}
    blobs = {name: store.read(name) for name in sorted(names)}
    prot = read_extra(root, "SPLPROT.2DA", game=is_game)
    if prot is not None:
        blobs["SPLPROT.2DA"] = prot
    text_path = None
    if os.environ.get("CBR_POTION_CAPTURE_TLK"):
        text_path = Path(os.environ["CBR_POTION_CAPTURE_TLK"])
    elif is_game:
        text_path = root / "lang/en_us/dialog.tlk"
    text = text_path.read_bytes() if text_path else None
    return blobs, report, is_game, text_path, text


def tlk_text(blob: bytes, index: int) -> bytes | None:
    count, start = struct.unpack_from("<II", blob, 10)
    if not 0 <= index < count:
        return None
    off, size = struct.unpack_from("<II", blob, 18 + index * 26 + 18)
    return blob[start + off:start + off + size]


@unittest.skipUnless(CAPTURE_ROOTS, "set CBR_POTION_CAPTURE_ROOT for opt-in read-only captures")
class CapturedPotionResearchProfiles(unittest.TestCase):
    def run_profile(self, source: Path, component: int):
        data, report, is_game, text_path, text = capture(source)
        self.assertGreater(len(report["potions"]), 0, "empty capture does not prove coverage")
        with tempfile.TemporaryDirectory(prefix="cbr-potions-captured-") as temporary:
            game = PotionGame(Path(temporary), data, tlk_bytes=text)
            if os.environ.get("CBR_POTION_CAPTURE_SR") == "1":
                result = game.install_sr_marker()
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            result = game.run(component)
            transcript = result.stdout + result.stderr
            self.assertEqual(0, result.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertNotIn("NOT INSTALLED DUE TO ERRORS", transcript)
            after = game.snapshot()
            after_report = audit.audit(after, after.__getitem__)
            self.assertFalse(after_report["incomplete"], json.dumps(after_report["diagnostics"]))
            self.assertEqual({p["resource"] for p in report["potions"]},
                             {p["resource"] for p in after_report["potions"]})
            for name, before in data.items():
                self.assertIn(name, after)
                if not name.endswith(".ITM"):
                    self.assertEqual(before, after[name], f"shared source changed: {name}")
                    continue
                old, new = audit.parse_resource(name, before), audit.parse_resource(name, after[name])
                old_header = bytearray.fromhex(old["raw_header_hex"])
                new_header = bytes.fromhex(new["raw_header_hex"])
                # Owned description and effect-table bookkeeping only.
                old_header[0x54:0x58] = new_header[0x54:0x58]
                old_header[0x64:0x72] = new_header[0x64:0x72]
                self.assertEqual(old_header, new_header, name)
                self.assertEqual(len(old["slices"]), len(new["slices"]), name)
                for old_slice, new_slice in zip(old["slices"], new["slices"]):
                    self.assertEqual(old_slice["kind"], new_slice["kind"], name)
                    if old_slice["kind"] == "equipped":
                        self.assertEqual([e["raw_hex"] for e in old_slice["effects"]],
                                         [e["raw_hex"] for e in new_slice["effects"]], name)
                    else:
                        old_raw = bytearray.fromhex(old_slice["raw_ability_hex"])
                        new_raw = bytes.fromhex(new_slice["raw_ability_hex"])
                        old_raw[30:34] = new_raw[30:34]
                        self.assertEqual(old_raw, new_raw, name)
            if text is not None:
                final_tlk = game.tlk.read_bytes()
                # Existing descriptions and names may be shared by other mods.
                indices = {struct.unpack_from("<i", blob, at)[0]
                           for name, blob in data.items() if name.endswith(".ITM")
                           for at in (8, 12, 80, 84)}
                indices.add(0)
                for index in indices:
                    original = tlk_text(text, index)
                    if original is not None:
                        self.assertEqual(original, tlk_text(final_tlk, index), index)
            repeat = game.repeat(component == 331)
            self.assertEqual(0, repeat.returncode, repeat.stdout + repeat.stderr)
            self.assertIn("SUCCESSFULLY INSTALLED", repeat.stdout + repeat.stderr)
            self.assertEqual(after, game.snapshot(), "second application changed captured output")
            for path, original in game.stable.items():
                self.assertEqual(original, path.read_bytes(), path.name)
            print("CAPTURE_COVERAGE " + json.dumps({
                "source": str(source), "component": component,
                "status": "quarantined research draft; not native acceptance",
                "library_sha256": hashlib.sha256((game.root / LIBRARY).read_bytes()).hexdigest(),
                "category9_items": len(report["potions"]),
                "linked_spl_eff": sum(n.endswith((".SPL", ".EFF")) for n in data),
                "changed_items": sum(n.endswith(".ITM") and after[n] != v for n, v in data.items()),
                "new_resources": len(set(after) - set(game.before)),
                "omitted": "consumers outside potion graph; actor/save/runtime state",
            }, sort_keys=True))
        # Re-read the observed sources independently of the first store's cache.
        fresh = audit.ResourceStore(source, game=is_game)
        for name, before in data.items():
            current = (read_extra(source, name, game=is_game) if name == "SPLPROT.2DA"
                       else fresh.read(name))
            self.assertEqual(before, current, f"read-only input changed: {name}")
        if text_path:
            self.assertEqual(text, text_path.read_bytes(), "read-only TLK changed")

    def test_all_unique_variant(self):
        for root in CAPTURE_ROOTS:
            with self.subTest(root=str(root)):
                self.run_profile(root, 330)

    def test_genius_exception_variant(self):
        for root in CAPTURE_ROOTS:
            with self.subTest(root=str(root)):
                self.run_profile(root, 331)


if __name__ == "__main__":
    unittest.main()
