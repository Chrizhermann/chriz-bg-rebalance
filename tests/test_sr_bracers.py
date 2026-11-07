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
from tests.test_sr_hardiness import _strings
from tests.test_tempus_holy_power_installer import _write_key_and_bif

ROOT = Path(__file__).resolve().parents[1]
WEIDU = Path(__import__("os").environ.get("WEIDU", ROOT / "weidu.exe"))
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
    # Like SR's Haste, each level header ends with its own protection. For
    # ALTFAST, which shares these bytes, that record is a Haste exclusion.
    haste = make_spl(tuple(SplAbility(level, 4, 1, (
        dataclasses.replace(fx(1, 6), duration=60+6*level),
        dataclasses.replace(fx(206, resource="SPWI677"), duration=60+6*level),
        dataclasses.replace(fx(206, resource="SPWI355"), duration=60+6*level)))
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
        self.language = "en_us"
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
        (root / "weidu.log").write_text("", encoding="ascii")
        self.original = self.snapshot()
        self.stable = {p: p.read_bytes() for p in (self.bif, root / "chitin.key")}

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
            "--use-lang", self.language, "--no-exit-pause", "--quick-log"],
            cwd=self.root, capture_output=True, text=True, timeout=60)
        return p, p.stdout + p.stderr


class BracersTests(unittest.TestCase):
    def game(self, resources=None):
        (ROOT / "work").mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="cbr-sr-bracers-", dir=ROOT / "work")
        self.addCleanup(temporary.cleanup)
        return Game(Path(temporary.name), resources or synthetic())

    def installed(self, g, **kwargs):
        p, output = g.run(**kwargs)
        self.assertEqual(0, p.returncode, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertNotIn("WARNING", output)

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
        self.assertEqual(old[:0x54] + old[0x58:0x6e], new[:0x54] + new[0x58:0x6e])
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
            if not name.endswith(".SPL") or name == "CBRBIH.SPL": continue
            newer = after[name]
            if newer == before: continue
            self.assertIn(name[:-4], guards)
            for original_fx, new_fx in zip(effects(before), effects(newer)):
                self.assertEqual(original_fx, [e for e in new_fx if not (op(e) == 206 and res(e) == "CBRBIH")])
                self.assertEqual(1, sum(op(e) == 206 and res(e) == "CBRBIH" for e in new_fx))
                own = [i for i, e in enumerate(new_fx) if op(e) == 206 and res(e) == name[:-4]]
                if own:
                    # The engine ignores a spell's records behind its own protection.
                    guard = next(i for i, e in enumerate(new_fx) if op(e) == 206 and res(e) == "CBRBIH")
                    self.assertLess(guard, own[0])
        for p, raw in g.stable.items(): self.assertEqual(raw, p.read_bytes())
        self.assertFalse(any(n.endswith(".INSTALLED") for n in after))

    def test_low_dynamic_haste_slots_are_padded(self):
        original = synthetic()
        resources = {}
        for name, blob in original.items():
            name = name.replace("SPWI677", "SPWI007").replace("SPWI355", "SPWI050")
            resources[name] = blob.replace(b"SPWI677", b"SPWI007").replace(b"SPWI355", b"SPWI050")
        resources["SPELL.IDS"] = b"2007 WIZARD_IMPROVED_HASTE\n2050 WIZARD_HASTE\n"
        game = self.game(resources)
        self.installed(game)
        after = game.snapshot()
        self.assertIn("CBRBIH.SPL", after)
        guards = {f.resource for f in SplFile.from_bytes(after["CBRBIH.SPL"]).all_effects() if f.opcode == 206}
        self.assertTrue({"SPWI007", "SPWI050", "CBRBIH"} <= guards)
        for name in ("SPWI007.SPL", "SPWI050.SPL"):
            for ability in SplFile.from_bytes(after[name]).abilities:
                self.assertEqual(1, sum(f.opcode == 206 and f.resource == "CBRBIH" for f in ability.effects))
        self.installed(game, repeat=True)
        self.assertEqual(after, game.snapshot())

    def test_native_transformation_relocated_symbols_and_aliases(self):
        g = self.game()
        self.installed(g)
        self.check(g)
        self.assertEqual(g.original["NOTHASTE.SPL"], g.snapshot()["NOTHASTE.SPL"])
        after = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"])
        description = _strings(g.tlk)[after.identified_description]
        self.assertIn("Improved Haste once per day", description)
        self.assertIn("20 seconds", description)
        self.assertTrue(description.startswith("Knight Wesic"))
        self.assertEqual("unchanged", _strings(g.tlk)[0])

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

    def test_private_helper_collision_is_overwritten(self):
        r = synthetic()
        r["CBRBIH.SPL"] = r["NOTHASTE.SPL"]
        g = self.game(r)
        self.installed(g)
        self.check(g)

    def test_native_double_apr_donor_becomes_additive(self):
        r = synthetic()
        donor = SplFile.from_bytes(r["SPWI677.SPL"])
        a = donor.abilities[0]
        r["SPWI677.SPL"] = dataclasses.replace(donor, abilities=(dataclasses.replace(a, effects=tuple(
            dataclasses.replace(e, opcode=16, parameter1=0, parameter2=1) if e.opcode == 1 else e
            for e in a.effects)),)).to_bytes()
        g = self.game(r)
        self.installed(g)
        self.check(g)

    def test_shared_alias_slices_are_rebuilt(self):
        r = synthetic()
        # Sharing a slice does not change the alias's intended exclusion.
        blob = bytearray(r["ALTFAST.SPL"])
        ab, = struct.unpack_from("<I", blob, 0x64)
        struct.pack_into("<H", blob, ab+40+32, 0)
        r["ALTFAST.SPL"] = bytes(blob)
        g = self.game(r)
        self.installed(g)
        self.check(g)

    def test_missing_effects_empty_abilities_and_edited_guards_are_rebuilt(self):
        for variation in ("missing_apr", "empty_donor", "empty_item", "no_item_abilities", "edited_guards"):
            with self.subTest(variation=variation):
                r = synthetic()
                donor = SplFile.from_bytes(r["SPWI677.SPL"])
                ability = donor.abilities[0]
                if variation == "missing_apr":
                    r["SPWI677.SPL"] = dataclasses.replace(donor, abilities=(dataclasses.replace(
                        ability, effects=tuple(e for e in ability.effects if e.opcode != 1)),)).to_bytes()
                elif variation == "empty_donor":
                    r["SPWI677.SPL"] = dataclasses.replace(donor, abilities=()).to_bytes()
                elif variation.startswith("empty_item") or variation == "no_item_abilities":
                    item = ItmFile.from_bytes(r["BRAC16.ITM"])
                    abilities = () if variation == "no_item_abilities" else (dataclasses.replace(item.abilities[0], effects=()),)
                    r["BRAC16.ITM"] = dataclasses.replace(item, abilities=abilities).to_bytes()
                else:
                    changed = tuple(dataclasses.replace(e, probability1=2, save_type=1, duration=0, timing=9)
                                    if e.opcode == 206 else e for e in ability.effects)
                    r["SPWI677.SPL"] = dataclasses.replace(donor, abilities=(dataclasses.replace(ability, effects=changed),)).to_bytes()
                g = self.game(r)
                self.installed(g)
                helper = SplFile.from_bytes(g.snapshot()["CBRBIH.SPL"])
                self.assertEqual([(1, 0, 20)], [(e.parameter1, e.parameter2, e.duration)
                                              for e in helper.abilities[0].effects if e.opcode == 1])
                item = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"])
                self.assertEqual(1, sum(e.opcode == 146 and e.resource == "CBRBIH" for e in item.abilities[0].effects))
                for e in helper.abilities[0].effects:
                    if e.opcode == 206 and e.resource in ("SPWI355", "SPWI677", "CBRBIH"):
                        self.assertEqual((1, 0, 20, 100, 0), (e.target, e.timing, e.duration, e.probability1, e.save_type))
                before = g.snapshot()
                self.installed(g, repeat=True)
                self.assertEqual(before, g.snapshot())

    def test_other_language_keeps_description_and_applies_mechanics(self):
        g = self.game()
        g.language = "de_de"
        translated = g.root / "lang/de_de/dialog.tlk"
        translated.parent.mkdir()
        translated.write_bytes(g.tlk.read_bytes())
        before = translated.read_bytes()
        p, out = g.run()
        self.assertEqual(0, p.returncode, out)
        self.assertNotIn("WARNING", out)
        self.assertIn("no translation", out)
        self.assertEqual(before, translated.read_bytes())
        old = ItmFile.from_bytes(g.original["BRAC16.ITM"])
        new = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"])
        self.assertEqual(old.identified_description, new.identified_description)
        self.assertTrue(any(e.opcode == 146 and e.resource == "CBRBIH" for e in new.abilities[0].effects))

    def test_unreadable_donor_or_item_is_logged_without_partial_publication(self):
        for name in ("SPWI677.SPL", "BRAC16.ITM"):
            with self.subTest(name=name):
                r = synthetic()
                r[name] = r[name][:-1]
                g = self.game(r)
                self.installed(g)
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


def _fx(opcode, p1=0, p2=0, resource="", duration=60, timing=0, target=2, **extra):
    return SplEffect(opcode=opcode, target=target, power=6, parameter1=p1, parameter2=p2,
                     resource=resource, duration=duration, timing=timing, resist_dispel=3, **extra)


def _item_ability(effects, target=5):
    raw = bytearray(56)
    raw[0] = 3
    raw[12] = target
    struct.pack_into("<H", raw, 34, 1)
    struct.pack_into("<I", raw, 38, 2048)
    return ItmAbility(raw=bytes(raw), effects=tuple(effects))


def _donor(r):
    return SplFile.from_bytes(r["SPWI677.SPL"])


def _with_donor(r, *, abilities=None, casting=None):
    donor = _donor(r)
    if abilities is not None:
        donor = dataclasses.replace(donor, abilities=tuple(abilities))
    if casting is not None:
        donor = dataclasses.replace(donor, casting_effects=tuple(casting))
    r["SPWI677.SPL"] = donor.to_bytes()
    return r


def _with_item(r, *, abilities=None, global_effects=None):
    item = ItmFile.from_bytes(r["BRAC16.ITM"])
    if abilities is not None:
        item = dataclasses.replace(item, abilities=tuple(abilities))
    if global_effects is not None:
        item = dataclasses.replace(item, global_effects=tuple(global_effects))
    r["BRAC16.ITM"] = item.to_bytes()
    return r


def _expected_payload(effects, spell=60, duration=20, donor="SPWI677"):
    """The helper's copy of one donor header, record by record."""
    out = []
    for e in effects:
        if e.opcode == 206 and e.resource == "CBRBIH":
            continue
        changes = {}
        if e.target > 1:
            changes["target"] = 1
        if e.timing in (0, 4) and e.duration == spell:
            changes["duration"] = duration
        if e.opcode == 321 and e.resource == donor:
            changes["resource"] = "CBRBIH"
        out.append(dataclasses.replace(e, **changes).canonical())
    return out


class BracersVariationTests(unittest.TestCase):
    """Valid alternate layouts (compatibility policy, 2026-10-17)."""
    game = BracersTests.game
    installed = BracersTests.installed

    def helper(self, g):
        helper = SplFile.from_bytes(g.snapshot()["CBRBIH.SPL"])
        self.assertEqual(1, len(helper.abilities))
        ability = helper.abilities[0]
        self.assertEqual((5, 1, 0), (ability.target, ability.projectile, ability.required_level))
        return helper

    def rewritten(self, g):
        self.installed(g)
        fx = self.helper(g).abilities[0].effects
        self.assertTrue(all(e.target in (0, 1) for e in fx))
        self.assertEqual([(1, 0, 20)], [(e.parameter1, e.parameter2, e.duration)
                                      for e in fx if e.opcode == 1])
        item = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"])
        for ability in item.abilities:
            calls = [e for e in ability.effects if e.opcode == 146 and e.resource == "CBRBIH"]
            if calls:
                self.assertEqual(1, len(calls))
                self.assertFalse(any(e.opcode in (16, 317) for e in ability.effects))
        self.repeat_is_exact(g)

    def repeat_is_exact(self, g):
        before = g.snapshot()
        self.installed(g, repeat=True)
        self.assertEqual(before, g.snapshot())

    def test_equipped_bonus_and_unrelated_activation_are_preserved(self):
        r = synthetic()
        item = ItmFile.from_bytes(r["BRAC16.ITM"])
        bonus = SplEffect(opcode=0, target=1, parameter1=1, timing=2)
        extra = _item_ability((SplEffect(opcode=17, target=1, parameter1=5, timing=1),))
        g = self.game(_with_item(r, abilities=item.abilities + (extra,), global_effects=(bonus,)))
        self.installed(g)
        new = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"])
        self.assertEqual([bonus.canonical()], [e.canonical() for e in new.global_effects])
        self.assertEqual(extra.canonical(), new.abilities[1].canonical())
        self.assertEqual(extra.raw[:0x1e], new.abilities[1].raw[:0x1e])
        self.assertEqual(extra.raw[0x22:], new.abilities[1].raw[0x22:])
        self.assertEqual([324, 146], [e.opcode for e in new.abilities[0].effects])
        self.repeat_is_exact(g)

    def test_reordered_abilities_preserve_the_unrelated_activation(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        foreign = _item_ability((SplEffect(opcode=17, target=1, parameter1=5, timing=1),))
        g = self.game(_with_item(r, abilities=(foreign, stock)))
        self.installed(g)
        item = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"])
        self.assertEqual(foreign.canonical(), item.abilities[0].canonical())
        self.assertEqual(1, sum(e.opcode == 146 and e.resource == "CBRBIH" for e in item.abilities[1].effects))
        self.repeat_is_exact(g)

    def test_reordered_item_and_donor_records(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        reordered = dataclasses.replace(stock, effects=tuple(reversed(stock.effects)))
        donor = _donor(r).abilities[0]
        payload = tuple(reversed(donor.effects))
        r = _with_item(r, abilities=(reordered,))
        g = self.game(_with_donor(r, abilities=(dataclasses.replace(donor, effects=payload),)))
        self.installed(g)
        new = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"]).abilities[0].effects
        self.assertEqual([146, 324], [e.opcode for e in new])
        expected = _expected_payload(payload)
        fx = self.helper(g).abilities[0].effects
        self.assertEqual(expected, [e.canonical() for e in fx[:len(expected)]])
        self.repeat_is_exact(g)

    def test_donor_casting_features_are_kept_verbatim(self):
        cast = (SplEffect(opcode=174, target=1, timing=1, resource="CAS_M05"),
                SplEffect(opcode=146, target=1, timing=1, parameter2=1, resource="DWHOOK"))
        g = self.game(_with_donor(synthetic(), casting=cast))
        self.installed(g)
        expected = [e.canonical() for e in cast]
        self.assertEqual(expected, [e.canonical() for e in self.helper(g).casting_effects])
        donor = SplFile.from_bytes(g.snapshot()["SPWI677.SPL"])
        self.assertEqual(expected, [e.canonical() for e in donor.casting_effects])
        self.repeat_is_exact(g)

    def test_casting_features_stored_after_the_payload(self):
        r = synthetic()
        cast = SplEffect(opcode=174, target=1, timing=1, resource="CAS_M05")
        donor = _donor(r)
        blob = bytearray(donor.to_bytes()) + cast.to_bytes()
        struct.pack_into("<HH", blob, 0x6e, len(donor.abilities[0].effects), 1)
        r["SPWI677.SPL"] = bytes(blob)
        g = self.game(r)
        self.installed(g)
        self.assertEqual([cast.canonical()], [e.canonical() for e in self.helper(g).casting_effects])
        self.repeat_is_exact(g)

    def test_level_scaled_donor_headers(self):
        r = synthetic()
        base = _donor(r).abilities[0]

        def scaled(level, seconds):
            return dataclasses.replace(base, required_level=level, effects=tuple(
                dataclasses.replace(e, duration=seconds) if e.timing in (0, 4) else e
                for e in base.effects))
        g = self.game(_with_donor(r, abilities=(scaled(1, 60), scaled(10, 120))))
        self.installed(g)
        expected = _expected_payload(base.effects)
        fx = self.helper(g).abilities[0].effects
        self.assertEqual(expected, [e.canonical() for e in fx[:len(expected)]])
        donor = SplFile.from_bytes(g.snapshot()["SPWI677.SPL"])
        for ability in donor.abilities:
            self.assertEqual(1, sum(e.opcode == 206 and e.resource == "CBRBIH" for e in ability.effects))
        self.repeat_is_exact(g)

    def test_first_donor_header_defines_the_fixed_duration_copy(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        stronger = dataclasses.replace(base, required_level=10, effects=tuple(
            dataclasses.replace(e, parameter1=2) if e.opcode == 1 else e for e in base.effects))
        self.rewritten(self.game(_with_donor(r, abilities=(base, stronger))))

    def test_changed_donor_duration_keeps_independent_timers(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        effects = tuple(dataclasses.replace(e, duration=50) for e in base.effects)
        effects += (_fx(215, resource="SPHASTE", duration=2),)
        g = self.game(_with_donor(r, abilities=(dataclasses.replace(base, effects=effects),)))
        self.installed(g)
        fx = self.helper(g).abilities[0].effects
        self.assertEqual([20], [e.duration for e in fx if e.opcode == 1])
        self.assertEqual([2], [e.duration for e in fx if e.opcode == 215])
        self.assertEqual(_expected_payload(effects, spell=50), [e.canonical() for e in fx[:len(effects)]])
        self.repeat_is_exact(g)

    def test_bracers_duration_follows_their_activation(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        longer = dataclasses.replace(stock, effects=tuple(
            dataclasses.replace(e, duration=30) if e.opcode == 16 or (e.opcode == 174 and e.timing == 4) else e
            for e in stock.effects))
        g = self.game(_with_item(r, abilities=(longer,)))
        p, out = g.run()
        self.assertEqual(0, p.returncode, out)
        self.assertIn("for 30 seconds", out)
        fx = self.helper(g).abilities[0].effects
        self.assertEqual([30], [e.duration for e in fx if e.opcode == 1])
        self.assertTrue(all(e.duration == 30 for e in fx if e.opcode == 206))
        new = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"]).abilities[0].effects
        self.assertEqual([324, 146], [e.opcode for e in new])
        self.repeat_is_exact(g)

    def test_foreign_donor_records_are_carried(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        effects = base.effects + (
            _fx(318, resource="FOOSPELL"),
            _fx(321, resource="SPWI677", duration=0, timing=1),
            _fx(139, p1=777, duration=0, timing=1, probability1=50),
            _fx(174, resource="EFF_X", duration=0, timing=1, target=0),
            _fx(12, p2=0x80000, duration=0, timing=1, dice_number=1, dice_size=4, save_type=1),
        )
        g = self.game(_with_donor(r, abilities=(dataclasses.replace(base, effects=effects),)))
        self.installed(g)
        fx = self.helper(g).abilities[0].effects
        self.assertEqual(_expected_payload(effects), [e.canonical() for e in fx[:len(effects)]])
        self.assertEqual(["CBRBIH"], [e.resource for e in fx if e.opcode == 321])
        self.assertEqual([0], [e.target for e in fx if e.opcode == 174 and e.resource == "EFF_X"])
        self.repeat_is_exact(g)

    def test_group_targeted_donor_effect_is_self_targeted(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        party = _fx(0, p1=1, target=3)
        g = self.game(_with_donor(r, abilities=(dataclasses.replace(base, effects=base.effects + (party,)),)))
        self.rewritten(g)

    def test_item_without_native_improved_haste_is_overwritten(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        normal = dataclasses.replace(stock, effects=tuple(
            dataclasses.replace(e, parameter2=0) if e.opcode == 16 else e for e in stock.effects))
        self.rewritten(self.game(_with_item(r, abilities=(normal,))))

    def test_activation_for_another_target_is_self_targeted(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        other = _item_ability(stock.effects, target=1)
        self.rewritten(self.game(_with_item(r, abilities=(other,))))

    def test_shared_activation_records_are_rebuilt(self):
        r = synthetic()
        item = ItmFile.from_bytes(r["BRAC16.ITM"])
        blob = bytearray(_with_item(r, abilities=item.abilities + (_item_ability(()),))["BRAC16.ITM"])
        ab, = struct.unpack_from("<I", blob, 0x64)
        count, first = struct.unpack_from("<HH", blob, ab + 0x1e)
        struct.pack_into("<HH", blob, ab + 56 + 0x1e, count, first)
        r["BRAC16.ITM"] = bytes(blob)
        self.rewritten(self.game(r))

    def test_transformed_item_without_helper_is_repaired(self):
        g = self.game()
        self.installed(g)
        next(p for p in g.override.iterdir() if p.name.upper() == "CBRBIH.SPL").unlink()
        before = g.snapshot()
        self.installed(g, repeat=True)
        self.assertIn("CBRBIH.SPL", g.snapshot())
        self.assertEqual(before["BRAC16.ITM"], g.snapshot()["BRAC16.ITM"])
        self.repeat_is_exact(g)


class BracersReviewTests(unittest.TestCase):
    """Independent review findings (2026-10-17)."""
    game = BracersTests.game
    installed = BracersTests.installed
    helper = BracersVariationTests.helper
    rewritten = BracersVariationTests.rewritten
    repeat_is_exact = BracersVariationTests.repeat_is_exact

    def test_activation_conditions_carry_over_to_the_helper_call(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        conditional = dataclasses.replace(stock, effects=tuple(
            dataclasses.replace(e, power=4, probability1=50, probability2=10, save_type=1, save_bonus=-2)
            if e.opcode == 16 else e for e in stock.effects))
        g = self.game(_with_item(r, abilities=(conditional,)))
        self.installed(g)
        new = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"]).abilities[0].effects
        cast, = [e for e in new if e.opcode == 146 and e.resource == "CBRBIH"]
        self.assertEqual(
            (1, 4, 0, 1, 1, 3, 0, 50, 10, 1, -2, 0, 0, 0),
            (cast.target, cast.power, cast.parameter1, cast.parameter2, cast.timing,
             cast.resist_dispel, cast.duration, cast.probability1, cast.probability2,
             cast.save_type, cast.save_bonus, cast.dice_number, cast.dice_size, cast.special))
        self.repeat_is_exact(g)

    def test_stock_activation_keeps_full_probability_and_no_save(self):
        g = self.game()
        self.installed(g)
        stock = next(e for e in ItmFile.from_bytes(g.original["BRAC16.ITM"]).abilities[0].effects if e.opcode == 16)
        new = ItmFile.from_bytes(g.snapshot()["BRAC16.ITM"]).abilities[0].effects
        cast, = [e for e in new if e.opcode == 146 and e.resource == "CBRBIH"]
        self.assertEqual((stock.power, 100, 0, 0, 0), (cast.power, cast.probability1, cast.probability2,
                                                      cast.save_type, cast.save_bonus))

    @staticmethod
    def scaled(base, level, seconds, effects):
        return dataclasses.replace(base, required_level=level, effects=tuple(
            dataclasses.replace(e, duration=seconds) if e.timing in (0, 4) else e for e in effects))

    def test_level_headers_storing_the_payload_in_another_order(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        # The stock payload starts with five independent records, then opcode
        # 101, two opcode-206 records and a delayed sound.
        independent, rest = base.effects[:5], base.effects[5:]
        self.assertFalse(any(e.opcode in (101, 206, 321) for e in independent))
        shuffled = tuple(reversed(independent)) + rest
        g = self.game(_with_donor(r, abilities=(
            self.scaled(base, 1, 60, base.effects), self.scaled(base, 10, 120, shuffled))))
        self.installed(g)
        expected = _expected_payload(base.effects)
        fx = self.helper(g).abilities[0].effects
        self.assertEqual(expected, [e.canonical() for e in fx[:len(expected)]])
        self.repeat_is_exact(g)

    def test_later_level_headers_do_not_gate_the_copy(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        protection = next(i for i, e in enumerate(base.effects) if e.opcode == 206)
        moved = (base.effects[protection],) + base.effects[:protection] + base.effects[protection + 1:]
        refresh = base.effects + (_fx(321, resource="SPWI677", duration=0, timing=1),)
        late = (refresh[-1],) + refresh[:-1]
        # Re-review finding: a cure (opcode 11 removes opcode 25) is not on the
        # explicit list of removals, and an unlisted opcode must not move.
        poison, cure = _fx(25, p1=1), _fx(11, duration=0, timing=1)
        # Same stat, set then bonus versus bonus then set.
        set_ac, more_ac = _fx(0, p1=5, p2=16), _fx(0, p1=2)
        cases = {"protection": (base.effects, moved),
                 "refresh": (refresh, late),
                 "cure-after-poison": (base.effects + (poison, cure), base.effects + (cure, poison)),
                 "same-opcode": (base.effects + (set_ac, more_ac), base.effects + (more_ac, set_ac))}
        for name, (first, second) in cases.items():
            with self.subTest(name=name):
                g = self.game(_with_donor(synthetic(), abilities=(
                    self.scaled(base, 1, 60, first), self.scaled(base, 10, 120, second))))
                self.rewritten(g)


def _cast(blob: bytes, name: str) -> list[set[str]]:
    """Engine model of one cast on a fresh target, per level header.

    In-game finding 2026-10-20 (BG2:EE 2.7.3.0 lab): a header's records apply in
    order, and once the target is protected from the spell itself (opcode 206
    naming it), the engine ignores the spell's later records. Returns the
    resources the target is then protected from.
    """
    result = []
    for header in effects(blob):
        held = set()
        for record in header:
            if name in held:
                break
            if op(record) == 206:
                held.add(res(record))
        result.append(held)
    return result


def _guard_last(blob: bytes) -> bytes:
    """The layout of earlier versions: each header's CBRBIH guard at its end."""
    data = bytearray(blob)
    ab, = struct.unpack_from("<I", data, 0x64)
    na, = struct.unpack_from("<H", data, 0x68)
    fx, = struct.unpack_from("<I", data, 0x6a)
    for h in range(na):
        count, first = struct.unpack_from("<HH", data, ab + h * 40 + 30)
        records = [bytes(data[fx + (first + i) * 48:fx + (first + i + 1) * 48]) for i in range(count)]
        guards = [r for r in records if op(r) == 206 and res(r) == "CBRBIH"]
        rest = [r for r in records if not (op(r) == 206 and res(r) == "CBRBIH")]
        data[fx + first * 48:fx + (first + count) * 48] = b"".join(rest + guards)
    return bytes(data)


class BracersGuardOrderTests(unittest.TestCase):
    """In-game finding 2026-10-20 (BG2:EE 2.7.3.0 lab): with SR Haste or Improved
    Haste cast first, the bracers still stacked. Their CBRBIH guard sat behind the
    spells' own protection, where the engine ignores it. Without Spell Revisions
    the component does not install (test_release_components)."""
    game = BracersTests.game
    installed = BracersTests.installed
    check = BracersTests.check

    def test_guard_precedes_the_spells_own_protection(self):
        g = self.game()
        self.installed(g)
        self.check(g)
        after = g.snapshot()
        for name in ("SPWI677", "SPWI355"):
            for header in effects(after[f"{name}.SPL"]):
                kinds = [(op(e), res(e)) for e in header]
                self.assertEqual(kinds.index((206, name)) - 1, kinds.index((206, "CBRBIH")))
                self.assertEqual((206, name), kinds[-1])
        # Without its own protection the guard still goes last.
        for header in effects(after["ALTFAST.SPL"]):
            self.assertEqual((206, "CBRBIH"), (op(header[-1]), res(header[-1])))

    def test_either_cast_order_excludes_the_other(self):
        g = self.game()
        self.installed(g)
        after = g.snapshot()
        aliases = {n[:-4] for n, raw in g.original.items() if n.endswith(".SPL") and after[n] != raw}
        self.assertEqual({"SPWI677", "SPWI355", "ALTFAST"}, aliases)
        bracers, = _cast(after["CBRBIH.SPL"], "CBRBIH")
        for name in sorted(aliases):
            with self.subTest(name=name):
                # Bracers first: the helper protects its wearer from the spell.
                self.assertIn(name, bracers)
                # The spell first: every level header protects from the bracers.
                for held in _cast(after[f"{name}.SPL"], name):
                    self.assertIn("CBRBIH", held)

    def test_other_haste_variants_keep_the_earlier_layout(self):
        r = synthetic()
        # SPRA301-like innate Haste, and a Wish Haste whose first record is an
        # instant opcode 324 check naming itself (as SPWISH36): neither is the
        # spell's own protection, so their guard stays last, as before.
        r["NATIVE.SPL"] = make_spl((SplAbility(1, 4, 1, (
            _fx(16, duration=90), _fx(206, resource="SPWI355", duration=90))),)).to_bytes()
        r["WISHFAST.SPL"] = make_spl((SplAbility(1, 4, 1, (
            _fx(324, p1=138, p2=110, resource="WISHFAST", duration=0, target=4),
            _fx(16, p2=1, duration=138, target=4),
            _fx(206, resource="SPWI355", duration=138, target=4))),)).to_bytes()
        g = self.game(r)
        self.installed(g)
        self.check(g)
        after = g.snapshot()
        for name in ("ALTFAST", "NATIVE", "WISHFAST"):
            with self.subTest(name=name):
                blob = after[f"{name}.SPL"]
                self.assertEqual(_guard_last(blob), blob)
                for header, held in zip(effects(blob), _cast(blob, name)):
                    guard = header[-1]
                    self.assertEqual((206, "CBRBIH"), (op(guard), res(guard)))
                    template = next(e for e in header if op(e) == 206 and res(e) in ("SPWI677", "SPWI355"))
                    self.assertEqual(template[:20] + guard[20:28] + template[28:], guard)
                    self.assertIn("CBRBIH", held)
        bracers, = _cast(after["CBRBIH.SPL"], "CBRBIH")
        self.assertTrue({"NATIVE", "WISHFAST"} <= bracers)

    def test_tail_application_moves_a_guard_behind_the_own_protection(self):
        g = self.game()
        self.installed(g)
        fixed = g.snapshot()
        # What an earlier version left: each header's guard last.
        for name in ("SPWI677.SPL", "SPWI355.SPL"):
            earlier = _guard_last(fixed[name])
            self.assertNotEqual(fixed[name], earlier)
            next(p for p in g.override.iterdir() if p.name.upper() == name).write_bytes(earlier)
        self.installed(g, repeat=True)
        self.assertEqual(fixed, g.snapshot())


if __name__ == "__main__": unittest.main()
