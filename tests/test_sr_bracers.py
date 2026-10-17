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
        if e.target == 2:
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

    def failed(self, g, text):
        p, out = g.run()
        self.assertNotEqual(0, p.returncode, out)
        self.assertIn(text, out)
        self.assertEqual(g.original, g.snapshot())

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
        self.assertEqual([324, 146, 139, 61], [e.opcode for e in new.abilities[0].effects])
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
        self.assertEqual([61, 139, 146, 324], [e.opcode for e in new])
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

    def test_donor_headers_with_different_payloads_fail(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        stronger = dataclasses.replace(base, required_level=10, effects=tuple(
            dataclasses.replace(e, parameter1=2) if e.opcode == 1 else e for e in base.effects))
        self.failed(self.game(_with_donor(r, abilities=(base, stronger))), "differ beyond their duration")

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
        self.assertEqual([324, 146, 139, 61], [e.opcode for e in new])
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

    def test_group_targeted_donor_effect_fails(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        party = _fx(0, p1=1, target=3)
        g = self.game(_with_donor(r, abilities=(dataclasses.replace(base, effects=base.effects + (party,)),)))
        self.failed(g, "targets group 3")

    def test_item_without_native_improved_haste_fails(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        normal = dataclasses.replace(stock, effects=tuple(
            dataclasses.replace(e, parameter2=0) if e.opcode == 16 else e for e in stock.effects))
        self.failed(self.game(_with_item(r, abilities=(normal,))), "no native Improved Haste activation")

    def test_activation_for_another_target_fails(self):
        r = synthetic()
        stock = ItmFile.from_bytes(r["BRAC16.ITM"]).abilities[0]
        other = _item_ability(stock.effects, target=1)
        self.failed(self.game(_with_item(r, abilities=(other,))), "does not target its user")

    def test_shared_activation_record_fails(self):
        r = synthetic()
        item = ItmFile.from_bytes(r["BRAC16.ITM"])
        blob = bytearray(_with_item(r, abilities=item.abilities + (_item_ability(()),))["BRAC16.ITM"])
        ab, = struct.unpack_from("<I", blob, 0x64)
        count, first = struct.unpack_from("<HH", blob, ab + 0x1e)
        struct.pack_into("<HH", blob, ab + 56 + 0x1e, count, first)
        r["BRAC16.ITM"] = bytes(blob)
        self.failed(self.game(r), "shared with another ability")

    def test_transformed_item_without_helper_fails(self):
        g = self.game()
        self.installed(g)
        next(p for p in g.override.iterdir() if p.name.upper() == "CBRBIH.SPL").unlink()
        before = g.snapshot()
        p, out = g.run(repeat=True)
        self.assertNotEqual(0, p.returncode, out)
        self.assertIn("CBRBIH.SPL is missing", out)
        self.assertEqual(before, g.snapshot())


class BracersReviewTests(unittest.TestCase):
    """Independent review findings (2026-10-17)."""
    game = BracersTests.game
    installed = BracersTests.installed
    helper = BracersVariationTests.helper
    failed = BracersVariationTests.failed
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

    def test_level_headers_moving_a_removal_or_protection_fail(self):
        r = synthetic()
        base = _donor(r).abilities[0]
        protection = next(i for i, e in enumerate(base.effects) if e.opcode == 206)
        moved = (base.effects[protection],) + base.effects[:protection] + base.effects[protection + 1:]
        refresh = base.effects + (_fx(321, resource="SPWI677", duration=0, timing=1),)
        late = (refresh[-1],) + refresh[:-1]
        for name, (first, second) in {"protection": (base.effects, moved),
                                      "refresh": (refresh, late)}.items():
            with self.subTest(name=name):
                g = self.game(_with_donor(synthetic(), abilities=(
                    self.scaled(base, 1, 60, first), self.scaled(base, 10, 120, second))))
                self.failed(g, "differ beyond their duration")


if __name__ == "__main__": unittest.main()
