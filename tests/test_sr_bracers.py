"""Real WeiDU tests. Never writes to or launches the user's game."""
from __future__ import annotations

import dataclasses
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, make_spl, SplFile
from tests.test_flail_of_ages import tlk
from tests.test_tempus_holy_power_installer import _write_key_and_bif

ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
CAPTURES = ROOT / ".worktrees/sr-bracers-captures"
ADAPTER = ROOT / "live-patch/CBR_SR_BRACERS"
LIB = ROOT / "chriz-bg-rebalance/lib/sr_bracers.tpa"


def capture_effective_resources(source: Path):
    """Read only: capture all effective SPLs plus the one item and symbol table.

    Includes BIFF-only resources, so local full-sweep evidence exercises the same
    discovery namespace as the live game without copying or writing its data.
    """
    from research.scripts.extract_key_resource import (
        KEY_HEADER, KEY_BIF_ENTRY, KEY_RESOURCE_ENTRY, RESOURCE_INDEX_MASK,
        _decode_ascii, _resolve_bif_path, _read_biff_resource,
    )
    resources = {p.name.upper(): p.read_bytes() for p in (source / "override").glob("*.spl")}
    key = (source / "chitin.key").read_bytes()
    sig, ver, nb, nr, bo, ro = KEY_HEADER.unpack_from(key)
    assert (sig, ver) == (b"KEY ", b"V1  ")
    bifs = []
    for i in range(nb):
        _, offset, length, _ = KEY_BIF_ENTRY.unpack_from(key, bo + i * KEY_BIF_ENTRY.size)
        bifs.append(_resolve_bif_path(source, _decode_ascii(key[offset:offset+length], "BIF")))
    for i in range(nr):
        raw, kind, loc = KEY_RESOURCE_ENTRY.unpack_from(key, ro + i * KEY_RESOURCE_ENTRY.size)
        if kind != 1006: continue
        name = _decode_ascii(raw, "resource").upper() + ".SPL"
        if name not in resources:
            resources[name] = _read_biff_resource(bifs[loc >> 20], loc & RESOURCE_INDEX_MASK, kind)[0]
    for name in ("BRAC16.ITM", "SPELL.IDS"):
        resources[name] = (source / "override" / name).read_bytes()
    return resources


def effects(blob: bytes, stride=40):
    ab, = struct.unpack_from("<I", blob, 0x64)
    na, = struct.unpack_from("<H", blob, 0x68)
    fx, = struct.unpack_from("<I", blob, 0x6a)
    for h in range(na):
        count, first = struct.unpack_from("<HH", blob, ab + h * stride + 30)
        yield [blob[fx + (first + i)*48:fx + (first+i+1)*48] for i in range(count)]


def res(raw):
    return raw[20:28].split(b"\0")[0].decode("latin1").upper()


def op(raw): return struct.unpack_from("<H", raw)[0]


def synthetic():
    def fx(opcode, p1=0, p2=0, resource="", duration=60, timing=0):
        return SplEffect(opcode=opcode, target=2, power=6, parameter1=p1,
                         parameter2=p2, resource=resource, duration=duration,
                         timing=timing, resist_dispel=3)
    payload = (fx(176, 6), fx(1, 1), fx(54, 2), fx(0, 2), fx(36, 2),
               fx(101, p2=40), fx(206, resource="SPWI355"),
               fx(174, resource="EFF_M29", timing=4), fx(206, resource="SPWI677"))
    donor = make_spl((SplAbility(1, 4, 158, payload),)).to_bytes()
    haste = make_spl(tuple(SplAbility(level, 4, 1, (
        dataclasses.replace(fx(1, 6), duration=60+6*level),
        dataclasses.replace(fx(206, resource="SPWI677"), duration=60+6*level)))
        for level in (1, 10))).to_bytes()
    # A protection spell must not be mistaken for haste merely because of op206.
    unrelated = make_spl((SplAbility(1, 1, 1, (fx(206, resource="SPWI677"),)),)).to_bytes()
    raw = bytearray(56)
    raw[0] = 3
    raw[12] = 5
    struct.pack_into("<H", raw, 34, 1)
    struct.pack_into("<I", raw, 38, 2048)
    item = ItmFile(abilities=(ItmAbility(raw=bytes(raw), effects=(
        dataclasses.replace(fx(324, 138, 110, "BRAC16", duration=0), target=1),
        dataclasses.replace(fx(16, p2=1, duration=20), target=1),
        dataclasses.replace(fx(139, 14023, duration=0, timing=1), target=1),
        dataclasses.replace(fx(174, resource="EFF_M29", duration=20, timing=4), target=1),
        dataclasses.replace(fx(139, 1234, duration=0, timing=1), target=1),
        dataclasses.replace(fx(61, 1234, duration=0, timing=1), target=1),
    )),)).to_bytes()
    return {"SPWI677.SPL": donor, "SPWI355.SPL": haste, "ALTFAST.SPL": haste,
            "NOTHASTE.SPL": unrelated, "BRAC16.ITM": item,
            "SPELL.IDS": b"2677 WIZARD_IMPROVED_HASTE\n2355 WIZARD_HASTE\n"}


class Game:
    def __init__(self, root, resources):
        self.root = root
        self.override = root / "override"
        self.override.mkdir(parents=True)
        shutil.copytree(ADAPTER, root / "CBR_SR_BRACERS")
        (root / "CBR_SR_BRACERS/lib").mkdir()
        shutil.copy2(LIB, root / "CBR_SR_BRACERS/lib/sr_bracers.tpa")
        for name, raw in resources.items(): (self.override / name).write_bytes(raw)
        self.bif = _write_key_and_bif(root, (("OH6000", "ARE", b"BG2EE marker"),))
        self.tlk = root / "lang/en_us/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(tlk(["unchanged"]))
        (root / "dialog.tlk").write_bytes(self.tlk.read_bytes())
        self.original = self.snapshot()
        self.stable = {p: p.read_bytes() for p in (self.bif, root / "chitin.key", self.tlk)}

    def snapshot(self): return {p.name.upper(): p.read_bytes() for p in self.override.iterdir() if p.is_file()}

    def run(self, uninstall=False, repeat=False):
        if repeat:
            # An independent tail wrapper invokes the exact same production
            # function, without uninstalling anything below it.
            wrapper = (self.root / "CBR_SR_BRACERS/setup-cbr_sr_bracers.tp2").read_text()
            folder = self.root / "CBR_BRACERS_REPEAT"
            folder.mkdir(exist_ok=True)
            (folder / "CBR_BRACERS_REPEAT.tp2").write_text(wrapper.replace(
                "BACKUP ~CBR_SR_BRACERS/backup~", "BACKUP ~CBR_BRACERS_REPEAT/backup~"))
            target = "CBR_BRACERS_REPEAT/CBR_BRACERS_REPEAT.tp2"
        else:
            target = "CBR_SR_BRACERS/setup-cbr_sr_bracers.tp2"
        p = subprocess.run([str(WEIDU), target,
            "--force-uninstall-list" if uninstall else "--force-install-list", "0",
            "--use-lang", "en_us", "--no-exit-pause", "--quick-log"],
            cwd=self.root, capture_output=True, text=True, timeout=60)
        return p, p.stdout + p.stderr


class BracersTests(unittest.TestCase):
    def game(self, resources=None):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-sr-bracers-")
        self.addCleanup(temporary.cleanup)
        return Game(Path(temporary.name), resources or synthetic())

    def installed(self, g, **kwargs):
        p, output = g.run(**kwargs)
        self.assertEqual(0, p.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)

    def check(self, g):
        after = g.snapshot()
        helper = SplFile.from_bytes(after["CBRBIH.SPL"])
        ids = g.original["SPELL.IDS"].decode("ascii")
        donor_id = next(int(line.split()[0]) for line in ids.splitlines()
                        if len(line.split()) > 1 and line.split()[1] == "WIZARD_IMPROVED_HASTE")
        donor = g.original[f"SPWI{donor_id - 2000}.SPL"]
        self.assertEqual(donor[0x27], after["CBRBIH.SPL"][0x27])
        self.assertEqual(donor[0x34:0x38], after["CBRBIH.SPL"][0x34:0x38])
        self.assertEqual(1, len(helper.abilities))
        ability = helper.abilities[0]
        self.assertEqual((5, 1, 0), (ability.target, ability.projectile, ability.required_level))
        # One level-zero header is eligible even for a noncaster (CL 0).
        for caster_level in (0, 1, 6, 40):
            self.assertEqual([ability], [a for a in helper.abilities if a.required_level <= caster_level])
        self.assertEqual(1, ability.raw[13])
        self.assertFalse(any(e.opcode in (16, 317) for e in ability.effects))
        apr = [e for e in ability.effects if e.opcode == 1]
        self.assertEqual(1, len(apr))
        self.assertEqual((1, 0, 20), (apr[0].parameter1, apr[0].parameter2, apr[0].duration))
        for e in ability.effects:
            self.assertEqual(1, e.target)
            if e.timing in (0, 4): self.assertEqual(20, e.duration)
        old, new = g.original["BRAC16.ITM"], after["BRAC16.ITM"]
        self.assertEqual(old[:0x6e], new[:0x6e])
        ab, = struct.unpack_from("<I", new, 0x64)
        self.assertEqual(old[ab:ab+30], new[ab:ab+30])
        self.assertEqual(old[ab+34:ab+56], new[ab+34:ab+56])
        nfx = next(effects(new, 56))
        self.assertFalse(any(op(e) in (16, 317) for e in nfx))
        self.assertEqual(1, sum(op(e) == 146 and res(e) == "CBRBIH" for e in nfx))
        cast = next(e for e in nfx if op(e) == 146 and res(e) == "CBRBIH")
        self.assertEqual((0, 1), struct.unpack_from("<II", cast, 4))
        ofx = next(effects(old, 56))
        self.assertEqual([e for e in ofx if op(e) == 324], [e for e in nfx if op(e) == 324])
        guards = {e.resource for e in ability.effects if e.opcode == 206}
        self.assertIn("CBRBIH", guards)
        for name, before in g.original.items():
            if not name.endswith(".SPL"): continue
            newer = after[name]
            if newer == before: continue
            self.assertIn(name[:-4], guards)
            for original_fx, new_fx in zip(effects(before), effects(newer)):
                self.assertEqual(original_fx, [e for e in new_fx if not (op(e) == 206 and res(e) == "CBRBIH")])
                self.assertEqual(1, sum(op(e) == 206 and res(e) == "CBRBIH" for e in new_fx))
        for p, raw in g.stable.items(): self.assertEqual(raw, p.read_bytes())
        self.assertFalse(any(n.endswith(".INSTALLED") for n in after))

    def test_native_transformation_relocated_symbols_and_aliases(self):
        g = self.game()
        self.installed(g)
        self.check(g)
        self.assertEqual(g.original["NOTHASTE.SPL"], g.snapshot()["NOTHASTE.SPL"])
        before = next(effects(g.original["BRAC16.ITM"], 56))
        after = next(effects(g.snapshot()["BRAC16.ITM"], 56))
        for effect in before:
            if op(effect) in (61, 139) and struct.unpack_from("<I", effect, 4)[0] == 1234:
                self.assertIn(effect, after)

    def test_global_only_and_empty_marker_spells_are_untouched(self):
        r = synthetic()
        r["GLOBAL.SPL"] = SplFile(abilities=(), casting_effects=(SplEffect(opcode=206, resource="SPWI677"),)).to_bytes()
        r["EMPTY.SPL"] = SplFile(abilities=()).to_bytes()
        r["PADDED.SPL"] = r["NOTHASTE.SPL"] + b"trailing unrelated metadata"
        g = self.game(r)
        self.installed(g)
        for name in ("GLOBAL.SPL", "EMPTY.SPL", "PADDED.SPL"):
            self.assertEqual(r[name], g.snapshot()[name])

    def test_additive_apr_without_ih_exclusion_is_not_newly_blocked(self):
        r = synthetic()
        r["OTHERAPR.SPL"] = make_spl((SplAbility(1, 1, 1, (
            SplEffect(opcode=1, parameter1=1, duration=60),
            SplEffect(opcode=206, resource="SPWI355", duration=60),
        )),)).to_bytes()
        g = self.game(r)
        self.installed(g)
        self.assertEqual(r["OTHERAPR.SPL"], g.snapshot()["OTHERAPR.SPL"])
        helper = SplFile.from_bytes(g.snapshot()["CBRBIH.SPL"])
        self.assertNotIn("OTHERAPR", {e.resource for e in helper.abilities[0].effects})

    def test_second_tail_application_is_byte_exact(self):
        g = self.game()
        self.installed(g)
        before = g.snapshot()
        self.installed(g, repeat=True)
        self.assertEqual(before, g.snapshot())

    def test_uninstall_restores_exact_resources(self):
        g = self.game()
        self.installed(g)
        p, output = g.run(uninstall=True)
        self.assertEqual(0, p.returncode, output)
        self.assertEqual(g.original, g.snapshot())

    def test_collision_fails_without_changes(self):
        r = synthetic()
        r["CBRBIH.SPL"] = r["NOTHASTE.SPL"]
        g = self.game(r)
        p, out = g.run()
        self.assertNotEqual(0, p.returncode, out)
        self.assertIn("different contents", out)
        self.assertEqual(g.original, g.snapshot())

    def test_non_sr_double_apr_donor_rejected(self):
        r = synthetic()
        donor = SplFile.from_bytes(r["SPWI677.SPL"])
        a = donor.abilities[0]
        r["SPWI677.SPL"] = dataclasses.replace(donor, abilities=(dataclasses.replace(a, effects=tuple(
            dataclasses.replace(e, opcode=16, parameter1=0, parameter2=1) if e.opcode == 1 else e
            for e in a.effects)),)).to_bytes()
        g = self.game(r)
        p, out = g.run()
        self.assertNotEqual(0, p.returncode, out)
        self.assertEqual(g.original, g.snapshot())

    def test_late_alias_failure_rolls_back_already_published_helper(self):
        r = synthetic()
        # A shared effect slice is valid to inspect but deliberately unsupported
        # by the rebuilding publisher. Failure occurs after helper publication.
        blob = bytearray(r["ALTFAST.SPL"])
        ab, = struct.unpack_from("<I", blob, 0x64)
        struct.pack_into("<H", blob, ab+40+32, 0)
        r["ALTFAST.SPL"] = bytes(blob)
        g = self.game(r)
        p, out = g.run()
        self.assertNotEqual(0, p.returncode, out)
        self.assertIn("overlapping or orphaned", out)
        self.assertEqual(g.original, g.snapshot())

    @unittest.skipUnless(CAPTURES.exists(), "private captured resources not present")
    def test_captured_stream_install_and_tempus_helpers(self):
        r = {p.name.upper(): p.read_bytes() for p in CAPTURES.iterdir() if p.is_file()}
        g = self.game(r)
        self.installed(g)
        self.check(g)
        for name in ("CBRAPR1.SPL", "CBRAPR6.SPL", "CBRAPR7.SPL"):
            self.assertEqual(r[name], g.snapshot()[name])
        fx = SplFile.from_bytes(g.snapshot()["CBRBIH.SPL"]).abilities[0].effects
        self.assertEqual([246], [e.parameter2 for e in fx if e.opcode == 328])
        self.assertEqual({"CBRAPR1", "CBRAPR6", "CBRAPR7"}, {e.resource for e in fx if e.opcode == 326})
        before = g.snapshot()
        self.installed(g, repeat=True)
        self.assertEqual(before, g.snapshot())


if __name__ == "__main__": unittest.main()
