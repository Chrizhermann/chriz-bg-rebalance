"""Real WeiDU cloud-form tests; writes only to disposable synthetic games.

These fixtures are intentionally independent of the implementation's effect
walker. Byte-level expected deltas exercise the public installer and its tail
adapter, including preservation of donor resources and original TLK entries.
They establish installer behavior, not live engine/playthrough acceptance.
"""
from __future__ import annotations

import dataclasses
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import ItmAbility, ItmFile, SplAbility, SplEffect, SplFile, make_spl
from tests.test_flail_of_ages import strings, tlk
from tests.test_tempus_holy_power_installer import _write_key_and_bif


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
ADAPTER = ROOT / "live-patch/CBR_CLOUD_FORMS"
LIB = ROOT / "chriz-bg-rebalance/lib/cloud_forms.tpa"
FORMS = ("DVGASFRM.ITM", "OHBEGASF.SPL", "BDGASFOR.SPL", "OHGASFRM.SPL", "FINBODGF.ITM")
RESISTANCE_OPCODES = (27, 28, 29, 30, 31, 84, 85, 86, 87, 88, 89)
OLD_PHRASE = "immune to almost all forms of damage"
NEW_PHRASE = "75% resistant to physical, elemental and magic damage while retaining poison immunity"
TEXTS = ["Untouched shared sentinel.",
    "Summon Efreeti\nLevel: 7\nSchool: Conjuration\nRange: Long\nDuration: 8 rounds + 1 round/level\nCasting Time: 1 round\nArea of Effect: Special\nSaving Throw: None\n\nWith this spell, the conjurer can cajole an efreeti, a massive genie with powerful abilities, to leave the Elemental Plane of Fire and enter the Prime Material Plane. The gated genie is immune to Banishment and has access to several spell-like abilities which can be cast instantly as a 10th level caster. Once per day an efreeti can turn into gaseous form, becoming immune to almost all forms of damage for a short time. The genie will generally use this ability when badly injured, to either regenerate before attacking again, or to leave the battlefield avoiding further damage. The efreeti will serve for the duration indicated above, attacking the enemies of the conjurer until the duration of the spell runs out.\n\nEfreeti (10 Hit Dice):\nSTR 19, DEX 17, CON 16, INT 13, WIS 14, CHA 15; AL Lawful Evil\nHP 98, AC 1, THAC0 5, Saving Throws 8/11/8/11/11\n2 Attacks Per Round, 1d8+10 Slashing +1d6 Fire Damage (Scimitar +2)\n\nSpecial Qualities:\nFire Resistance 100%\n\nMemorized Spells:\n1. Burning Hands, Magic Missile (x2), Shield\n2. Agannazar's Scorcher, Invisibility (x2)\n3. Fireball (x3)\n4. Fire Shield (x2)\n5. Conjure Lesser Fire Elemental",
    'Summon Djinni\nLevel: 7\nSchool: Conjuration\nRange: Long\nDuration: 8 rounds + 1 round/level\nCasting Time: 1 round\nArea of Effect: Special\nSaving Throw: None\n\nWith this spell, the conjurer can cajole a djinni, a massive genie with powerful abilities, to leave the Elemental Plane of Air and enter the Prime Material Plane. The gated genie is immune to Banishment and has access to several spell-like abilities which can be cast instantly as a 10th level caster. Once per day a djinni can turn into gaseous form, becoming immune to almost all forms of damage for a short time. The genie will generally use this ability when badly injured, to either regenerate before attacking again, or to leave the battlefield avoiding further damage. The djinni will serve for the duration indicated above, attacking the enemies of the conjurer until the duration of the spell runs out.\n\nDjinni (10 Hit Dice):\nSTR 17, DEX 19, CON 15, INT 14, WIS 14, CHA 15; AL Chaotic Good\nHP 89, AC 0, THAC0 7, Saving Throws 11/7/11/7/7\n3 Attacks Per Round, 1d8+5 Slashing Damage (Scimitar +2)\n\nMemorized Spells:\n1. Magic Missile (x3), Shield\n2. Invisibility (x2), Mirror Image\n3. Haste, Lightning Bolt (x2)\n4. Improved Invisibility, Minor Globe of Invulnerability\n5. Conjure Lesser Air Elemental'
]
EXPECTED_TEXTS = [text.replace(OLD_PHRASE, NEW_PHRASE) for text in TEXTS]
CHANNELS = {
    "DVGASFRM.ITM": (27, 28, 29, 30, 31, 86, 87, 88, 89),
    "OHBEGASF.SPL": (27, 28, 31, 85, 86, 87, 88, 89),
    "BDGASFOR.SPL": (27, 28, 31, 85, 86, 87, 88, 89),
    "OHGASFRM.SPL": (27, 28, 31, 85, 86, 87, 88, 89),
    "FINBODGF.ITM": RESISTANCE_OPCODES,
}


def effect(opcode, p1=0, p2=0, *, item=False, resource="", **kwargs):
    fields = dict(opcode=opcode, target=1, parameter1=p1, parameter2=p2,
                  timing=2 if item else 0, duration=0 if item else 20,
                  probability1=100, resource=resource)
    fields.update(kwargs)
    return SplEffect(**fields)


def form(name):
    """Provider-shaped cloud package, including poison and control immunity."""
    item = name.endswith(".ITM")
    fin = name == "FINBODGF.ITM"
    fx = [effect(135, p2=1, resource="GASFORM4", item=True) if fin
          else effect(53, 0x7F39, item=item),
          effect(98, 20 if fin else 3, 2, item=item)]
    for opcode in CHANNELS[name]:
        value = 50 if fin and opcode in (30, 84) else 75 if fin and opcode == 31 else 100
        fx.append(effect(opcode, value, 1, item=item))
    if item:
        fx.append(effect(166, 0 if fin else 100, 1, item=True))
    fx.extend((effect(101, p2=25, item=item),  # poison immunity
               effect(173, 100, item=item),   # poison resistance, not a header byte
               effect(101, p2=40, item=item),  # control immunity
               effect(144, p2=2, item=item),
               effect(142, 100, item=item),    # unrelated parameter1=100
               effect(139, 0, item=item, timing=1, duration=0)))
    if item:
        return ItmFile(abilities=(), global_effects=tuple(fx)).to_bytes()
    duration = 20 if name == "OHGASFRM.SPL" else 18
    fx = [dataclasses.replace(f, duration=duration) if f.timing == 0 else f for f in fx]
    return make_spl((SplAbility(1, 5, 1, tuple(fx)),)).to_bytes()


def donor(extra_effects=(), *, v2=False):
    """CRE V1.0 with real header offsets, empty inventory and poison defenses."""
    raw = bytearray(0x324)
    raw[:8] = b"CRE V1.0"
    struct.pack_into("<HH", raw, 0x24, 8, 8)
    struct.pack_into("<I", raw, 0x28, 0x7F39)
    raw[0x33] = int(v2)
    raw[0x59:0x64] = bytes([100] * 11)
    # Detect illusions lies immediately after missile resistance: never patch it.
    raw[0x64] = 67
    raw[0x248:0x250] = b"ESCAPE\0\0"
    raw[0x268:0x270] = b"WDRUNSGT"
    for offset in (0x2A0, 0x2A8, 0x2B0, 0x2B8):
        struct.pack_into("<I", raw, offset, 0x2D4)
    struct.pack_into("<I", raw, 0x2BC, len(raw))
    struct.pack_into("<I", raw, 0x2C4, len(raw))
    raw[0x2D4:] = bytes([255] * 80)
    effects = (effect(101, p2=25, timing=9, duration=0),
               effect(173, 100, timing=9, duration=0),
               effect(326, resource="FOREIGN", timing=9, duration=0), *extra_effects)
    struct.pack_into("<I", raw, 0x2C8, len(effects))
    for fx in effects:
        if not v2:
            raw.extend(fx.to_bytes())
        else:
            # Embedded CRE effects omit the external EFF's eight-byte prefix.
            embedded = bytearray(264)
            struct.pack_into("<I", embedded, 8, fx.opcode)
            struct.pack_into("<I", embedded, 12, fx.target)
            struct.pack_into("<i", embedded, 20, fx.parameter1)
            struct.pack_into("<i", embedded, 24, fx.parameter2)
            struct.pack_into("<H", embedded, 28, fx.timing)
            embedded[40:48] = fx.resource.encode("ascii").ljust(8, b"\0")
            raw.extend(embedded)
    return bytes(raw)


def vampire(*extra):
    return make_spl((SplAbility(1, 5, 1, (
        effect(297, p2=1, timing=2, duration=0),
        effect(135, p2=0, resource="GASFORM4", duration=18),
        effect(215, resource="SPDISPMA", duration=3), *extra)),)).to_bytes()


def described_spell(strref):
    raw = bytearray(make_spl((SplAbility(1, 5, 1, (effect(139, 0),)),)).to_bytes())
    struct.pack_into("<I", raw, 0x50, strref)
    return bytes(raw)


def synthetic():
    resources = {name: form(name) for name in FORMS}
    resources.update({
        "DW#VMGAS.SPL": vampire(), "GASFORM4.CRE": donor(),
        # Relocated symbols prove this is not a hard-coded SPWI717/718 patch.
        "SPELL.IDS": b"2677 WIZARD_SUMMON_EFREET\n2678 WIZARD_SUMMON_DJINNI\n",
        "SPWI677.SPL": described_spell(1), "SPWI678.SPL": described_spell(2),
        "SPWI717.SPL": described_spell(1), "SPWI718.SPL": described_spell(2),
        "SHARED.SPL": described_spell(1),
        # Identical animation/defense packages outside the allowlist stay intact.
        "OTHERGAS.SPL": form("OHBEGASF.SPL"),
        "OHHEXAM4.ITM": form("DVGASFRM.ITM"),
        "SPIN964.SPL": make_spl((SplAbility(1, 5, 1, (
            effect(151, resource="GASFORM4"), effect(208, 1))),)).to_bytes(),
        "SPIN803.SPL": make_spl((SplAbility(1, 5, 1, (
            effect(151, resource="DACEMIST"),)),)).to_bytes(),
        "DACEMIST.CRE": donor(), "EFREET01.CRE": donor(),
    })
    return resources


def referenced_effect_offsets(blob):
    """Independent binary oracle; excludes unused/trailing effect records."""
    ability, = struct.unpack_from("<I", blob, 0x64)
    count, = struct.unpack_from("<H", blob, 0x68)
    start, = struct.unpack_from("<I", blob, 0x6A)
    first, size = struct.unpack_from("<HH", blob, 0x6E)
    used = set(range(first, first + size))
    stride = 56 if blob[:3] == b"ITM" else 40
    for index in range(count):
        size, first = struct.unpack_from("<HH", blob, ability + index * stride + 0x1E)
        used.update(range(first, first + size))
    return [start + index * 48 for index in sorted(used)]


def expected_form(blob):
    """Byte oracle for the normal provider fixtures, not an input validator."""
    raw = bytearray(blob)
    offsets = referenced_effect_offsets(blob)
    fin = blob[:3] == b"ITM" and any(struct.unpack_from("<H", blob, o)[0] == 135 for o in offsets)
    for offset in offsets:
        opcode, = struct.unpack_from("<H", blob, offset)
        if opcode in RESISTANCE_OPCODES:
            struct.pack_into("<ii", raw, offset + 4, 50 if fin and opcode in (30, 84) else 75, 1)
        elif opcode == 166:
            struct.pack_into("<ii", raw, offset + 4, 0, int(fin))
    return bytes(raw)


def expected_clone(blob):
    raw = bytearray(blob)
    for offset in range(0x59, 0x64):
        raw[offset] = 0 if offset == 0x5D else 75
    return bytes(raw)


def mutate_effect(blob, match_opcode, **fields):
    raw = bytearray(blob)
    for offset in referenced_effect_offsets(blob):
        if struct.unpack_from("<H", blob, offset)[0] == match_opcode:
            fx = SplEffect.from_bytes(blob[offset:offset + 48])
            raw[offset:offset + 48] = dataclasses.replace(fx, **fields).to_bytes()
            return bytes(raw)
    raise AssertionError(f"fixture lacks opcode {match_opcode}")


class Game:
    def __init__(self, root, resources, *, public=False, texts=TEXTS, language="en_us"):
        self.root = root
        self.public = public
        self.language = language
        self.override = root / "override"
        self.override.mkdir(parents=True)
        (root / "WeiDU.log").write_text("", encoding="utf-8")
        if public:
            shutil.copy2(ROOT / "setup-chriz-bg-rebalance.tp2", root)
            shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
        else:
            shutil.copytree(ADAPTER, root / "CBR_CLOUD_FORMS")
            (root / "CBR_CLOUD_FORMS/lib").mkdir(exist_ok=True)
            shutil.copy2(LIB, root / "CBR_CLOUD_FORMS/lib/cloud_forms.tpa")
        for name, raw in resources.items():
            (self.override / name).write_bytes(raw)
        self.bif = _write_key_and_bif(root, (("OH6000", "ARE", b"BG2EE marker"),))
        self.tlk = root / f"lang/{language}/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(tlk(list(texts)))
        if language != "en_us":
            english = root / "lang/en_us/dialog.tlk"
            english.parent.mkdir(parents=True)
            english.write_bytes(self.tlk.read_bytes())
        (root / "dialog.tlk").write_bytes(self.tlk.read_bytes())
        self.original = self.snapshot()
        self.original_texts = list(texts)
        self.original_tlk = self.tlk.read_bytes()
        self.stable = {p: p.read_bytes() for p in (self.bif, root / "chitin.key", root / "dialog.tlk")}

    def snapshot(self):
        return {p.name.upper(): p.read_bytes() for p in self.override.iterdir() if p.is_file()}

    def run(self, *, uninstall=False, repeat=False):
        if repeat:
            # Invoke the same action in an independent tail transaction, without
            # implicitly uninstalling/reinstalling the original component.
            wrapper = (self.root / "CBR_CLOUD_FORMS/setup-cbr_cloud_forms.tp2").read_text()
            folder = self.root / "CBR_CLOUD_REPEAT"
            folder.mkdir(exist_ok=True)
            (folder / "CBR_CLOUD_REPEAT.tp2").write_text(wrapper.replace(
                "BACKUP ~CBR_CLOUD_FORMS/backup~", "BACKUP ~CBR_CLOUD_REPEAT/backup~"))
            target, component = "CBR_CLOUD_REPEAT/CBR_CLOUD_REPEAT.tp2", "0"
        elif self.public:
            target, component = "setup-chriz-bg-rebalance.tp2", "320"
        else:
            target, component = "CBR_CLOUD_FORMS/setup-cbr_cloud_forms.tp2", "0"
        completed = subprocess.run([
            str(WEIDU), target,
            "--force-uninstall-list" if uninstall else "--force-install-list", component,
            "--language", "0", "--use-lang", self.language, "--no-exit-pause", "--quick-log",
        ], cwd=self.root, capture_output=True, text=True, timeout=60)
        return completed.returncode, completed.stdout + completed.stderr


class CloudFormsTests(unittest.TestCase):
    def game(self, resources=None, **kwargs):
        temporary = tempfile.TemporaryDirectory(prefix="cbr-cloud-forms-")
        self.addCleanup(temporary.cleanup)
        return Game(Path(temporary.name), synthetic() if resources is None else resources, **kwargs)

    def installed(self, game, **kwargs):
        code, output = game.run(**kwargs)
        self.assertEqual(0, code, output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertNotIn("INSTALLED WITH WARNINGS", output)
        self.assertNotIn("WARNING:", output)

    def assert_stable(self, game):
        for path, before in game.stable.items():
            self.assertEqual(before, path.read_bytes(), str(path))

    def assert_exact_install(self, game, *, described=True):
        after = game.snapshot()
        expected = dict(game.original)
        for name in FORMS:
            if name in expected:
                expected[name] = expected_form(expected[name])
        if "DW#VMGAS.SPL" in expected:
            expected["CBRGAS75.CRE"] = expected_clone(expected["GASFORM4.CRE"])
            expected["DW#VMGAS.SPL"] = mutate_effect(
                expected["DW#VMGAS.SPL"], 135, resource="CBRGAS75")
        for name in ("SPWI677.SPL", "SPWI678.SPL"):
            if "DVGASFRM.ITM" not in expected or name not in expected:
                continue
            old_ref, = struct.unpack_from("<I", expected[name], 0x50)
            new_ref, = struct.unpack_from("<I", after[name], 0x50)
            wanted = EXPECTED_TEXTS[1 if name == "SPWI677.SPL" else 2] if described else game.original_texts[old_ref]
            self.assertEqual(wanted, strings(game.tlk)[new_ref])
            if wanted != game.original_texts[old_ref]:
                self.assertGreaterEqual(new_ref, len(game.original_texts))
            raw = bytearray(expected[name])
            struct.pack_into("<I", raw, 0x50, new_ref)
            expected[name] = bytes(raw)
        self.assertEqual(expected.keys(), after.keys())
        for name, wanted in expected.items():
            self.assertEqual(wanted, after[name], name)
        self.assertEqual(game.original_texts, strings(game.tlk)[:len(game.original_texts)])
        self.assert_stable(game)

    def test_exact_allowlisted_delta_poison_regeneration_and_exclusions(self):
        game = self.game()
        self.installed(game)
        self.assert_exact_install(game)

    def test_native_mr_removed_without_changing_finbodgf_existing_zero_or_fifty(self):
        game = self.game()
        self.installed(game)
        for name in FORMS:
            blob = game.snapshot()[name]
            parsed = ItmFile.from_bytes(blob) if name.endswith(".ITM") else SplFile.from_bytes(blob)
            effects = parsed.global_effects if name.endswith(".ITM") else parsed.all_effects()
            mr = [(fx.parameter1, fx.parameter2) for fx in effects if fx.opcode == 166]
            self.assertEqual([(0, int(name == "FINBODGF.ITM"))] if name.endswith(".ITM") else [], mr)
        self.assert_exact_install(game)

    def test_vampire_clone_all_ten_damage_channels_and_zero_mr(self):
        game = self.game({"DW#VMGAS.SPL": vampire(), "GASFORM4.CRE": donor()})
        self.installed(game)
        self.assert_exact_install(game)
        clone = game.snapshot()["CBRGAS75.CRE"]
        self.assertEqual(0, clone[0x5D])
        self.assertEqual(75, clone[0x63])  # missile, never a poison header field
        self.assertEqual(67, clone[0x64])  # adjacent detect-illusion field

    def test_v2_cre_effects_preserved(self):
        game = self.game({"DW#VMGAS.SPL": vampire(), "GASFORM4.CRE": donor(v2=True)})
        self.installed(game)
        self.assert_exact_install(game)

    def test_each_optional_provider_can_install_alone(self):
        for name in FORMS:
            with self.subTest(name=name):
                game = self.game({name: form(name)})
                self.installed(game)
                self.assert_exact_install(game)

    def test_missing_all_providers_logs_and_continues(self):
        game = self.game({"OTHERGAS.SPL": form("OHGASFRM.SPL")})
        self.installed(game)
        self.assertEqual(game.original, game.snapshot())
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_missing_all_providers_public_component_logs_and_continues(self):
        game = self.game({}, public=True)
        code, output = game.run()
        self.assertEqual(0, code, output)
        self.assertNotIn("SKIPPING", output)
        self.assertIn("SUCCESSFULLY INSTALLED", output)
        self.assertIn("absent", output)
        self.assertEqual(game.original, game.snapshot())
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_public_component_matches_tail_adapter(self):
        adapter, public = self.game(), self.game(public=True)
        self.installed(adapter)
        self.installed(public)
        self.assert_exact_install(public)
        self.assertEqual(adapter.snapshot(), public.snapshot())
        self.assertEqual(adapter.tlk.read_bytes(), public.tlk.read_bytes())

    def test_idempotence_in_independent_tail_transaction_including_tlk(self):
        game = self.game()
        self.installed(game)
        first, first_tlk = game.snapshot(), game.tlk.read_bytes()
        self.installed(game, repeat=True)
        self.assertEqual(first, game.snapshot())
        self.assertEqual(first_tlk, game.tlk.read_bytes())
        self.assert_exact_install(game)

    def test_disposable_uninstall_restores_resources_and_original_tlk_entries(self):
        game = self.game()
        self.installed(game)
        code, output = game.run(uninstall=True)
        self.assertEqual(0, code, output)
        self.assertIn("SUCCESSFULLY REMOVED", output)
        self.assertEqual(game.original, game.snapshot())
        self.assertEqual(game.original_texts, strings(game.tlk)[:len(game.original_texts)])
        self.assert_stable(game)

    def test_existing_exact_clone_is_accepted_and_preserved(self):
        resources = synthetic()
        resources["CBRGAS75.CRE"] = expected_clone(resources["GASFORM4.CRE"])
        game = self.game(resources)
        self.installed(game)
        self.assert_exact_install(game)

    def test_private_resref_is_overwritten(self):
        resources = synthetic()
        resources["CBRGAS75.CRE"] = b"a previous private resource"
        game = self.game(resources)
        self.installed(game)
        self.assert_exact_install(game)

    def test_missing_combat_donor_costs_only_that_branch(self):
        resources = synthetic()
        del resources["GASFORM4.CRE"]
        game = self.game(resources)
        self.installed(game)
        after = game.snapshot()
        self.assertNotIn("CBRGAS75.CRE", after)
        self.assertEqual(resources["DW#VMGAS.SPL"], after["DW#VMGAS.SPL"])
        self.assertEqual(expected_form(resources["OHGASFRM.SPL"]), after["OHGASFRM.SPL"])

    def test_donor_animation_inventory_signature_and_resistance_are_not_gates(self):
        resources = synthetic()
        raw = bytearray(resources["GASFORM4.CRE"])
        raw[:8] = b"CRE V9.9"
        struct.pack_into("<I", raw, 0x28, 0x6400)
        struct.pack_into("<I", raw, 0x2C0, 1)
        raw[0x59:0x64] = bytes((125, 80, 206, 60, 40, 99, 0, 75, 20, 50, 110))
        resources["GASFORM4.CRE"] = bytes(raw)
        game = self.game(resources)
        self.installed(game)
        expected = bytearray(expected_clone(raw)); expected[:8] = b"CRE V1.0"
        self.assertEqual(bytes(expected), game.snapshot()["CBRGAS75.CRE"])
        self.assertEqual(bytes(raw), game.snapshot()["GASFORM4.CRE"])

    def test_donor_competing_defenses_removed_in_both_effect_formats(self):
        for v2 in (False, True):
            with self.subTest(v2=v2):
                extra = (effect(208, 1), effect(120, 0, 2), effect(101, p2=12),
                         effect(30, -40, 2), effect(166, 35, 0))
                game = self.game({"DW#VMGAS.SPL": vampire(), "GASFORM4.CRE": donor(extra, v2=v2)})
                self.installed(game)
                self.assertEqual(expected_clone(donor(v2=v2)), game.snapshot()["CBRGAS75.CRE"])
                first = game.snapshot()
                self.installed(game, repeat=True)
                self.assertEqual(first, game.snapshot())

    def package(self, blob, *, item=False):
        parsed = (ItmFile if item else SplFile).from_bytes(blob)
        return parsed.global_effects if item else parsed.abilities[0].effects

    def assert_package(self, effects, name):
        values = {f.opcode: f.parameter1 for f in effects if f.opcode in RESISTANCE_OPCODES}
        expected = {op: 50 if name == "FINBODGF.ITM" and op in (30, 84) else 75 for op in CHANNELS[name]}
        self.assertEqual(expected, values)
        owned = [f for f in effects if f.opcode in RESISTANCE_OPCODES]
        self.assertEqual(len(expected), len(owned))
        duration = 0 if name.endswith(".ITM") else 20 if name == "OHGASFRM.SPL" else 18
        for f in owned:
            self.assertEqual((1, 1, 2 if name.endswith(".ITM") else 0, duration, 100, 0, 0),
                             (f.target, f.parameter2, f.timing, f.duration, f.probability1, f.save_type, f.save_bonus))
        self.assertFalse(any(f.opcode in (120, 208) or (f.opcode == 101 and f.parameter2 == 12) for f in effects))
        mr = [f for f in effects if f.opcode == 166]
        self.assertEqual([(0, int(name == "FINBODGF.ITM"))] if name.endswith(".ITM") else [],
                         [(f.parameter1, f.parameter2) for f in mr])

    def test_added_item_and_spell_defenses_cannot_keep_cloud_invulnerable(self):
        for name in FORMS:
            with self.subTest(name=name):
                item = name.endswith(".ITM")
                parsed = (ItmFile if item else SplFile).from_bytes(form(name))
                extra = (effect(208, 1), effect(120, 0, 2), effect(101, p2=12),
                         effect(166, 40), effect(86, 99, 2), effect(30, 100, 1))
                if item:
                    changed = dataclasses.replace(parsed, global_effects=(*parsed.global_effects, *extra))
                else:
                    a = parsed.abilities[0]
                    changed = dataclasses.replace(parsed, abilities=(dataclasses.replace(a, effects=(*a.effects, *extra)),))
                game = self.game({name: changed.to_bytes()})
                self.installed(game)
                self.assert_package(self.package(game.snapshot()[name], item=item), name)

    def test_vampire_polymorph_replaces_missing_extra_or_changed_effects(self):
        for effects in ((), (effect(135, 7, 1, target=2, timing=2, duration=0, resource="DACEMIST"),),
                        (effect(135, resource="FOREIGN"), effect(135, resource="EXTRA"))):
            with self.subTest(effects=effects):
                foreign = effect(215, resource="SPDISPMA", duration=3)
                original = make_spl((SplAbility(1, 5, 1, (foreign, *effects, effect(166, 40))),)).to_bytes()
                game = self.game({"DW#VMGAS.SPL": original, "GASFORM4.CRE": donor()})
                self.installed(game)
                fx = SplFile.from_bytes(game.snapshot()["DW#VMGAS.SPL"]).all_effects()
                self.assertEqual([foreign], [f for f in fx if f.opcode == 215])
                self.assertEqual([effect(135, resource="CBRGAS75", duration=18)], [f for f in fx if f.opcode == 135])
                self.assertFalse(any(f.opcode == 166 for f in fx))

    def test_unreadable_description_costs_only_that_file(self):
        resources = synthetic()
        resources["SPWI678.SPL"] = resources["SPWI678.SPL"][:70]
        game = self.game(resources)
        self.installed(game)
        self.assertEqual(resources["SPWI678.SPL"], game.snapshot()["SPWI678.SPL"])
        self.assertEqual(expected_form(resources["DVGASFRM.ITM"]), game.snapshot()["DVGASFRM.ITM"])
        self.assertEqual(EXPECTED_TEXTS[1], strings(game.tlk)[SplFile.from_bytes(game.snapshot()["SPWI677.SPL"]).description_strref])

    def test_owned_values_and_delivery_are_written_without_old_value_tests(self):
        for value in (-50, 0, 60, 75, 80, 99, 100, 110):
            with self.subTest(value=value):
                name = "OHBEGASF.SPL"
                raw = mutate_effect(form(name), 86, parameter1=value, parameter2=0, target=2,
                                    timing=2, duration=0, probability1=17, save_type=4, save_bonus=3)
                raw = mutate_effect(raw, 53, parameter1=0x6400)
                game = self.game({name: raw})
                self.installed(game)
                self.assert_package(self.package(game.snapshot()[name]), name)
                # The animation is outside resistance ownership.
                self.assertEqual(0x6400, next(f.parameter1 for f in self.package(game.snapshot()[name]) if f.opcode == 53))

    def test_missing_effects_and_empty_abilities_get_the_decided_package(self):
        for name in FORMS:
            with self.subTest(name=name):
                item = name.endswith(".ITM")
                foreign = effect(142, 71, item=item)
                raw = ItmFile(abilities=(), global_effects=(foreign,)).to_bytes() if item else make_spl((SplAbility(1, 1, 1, (foreign,)),)).to_bytes()
                game = self.game({name: raw})
                self.installed(game)
                effects = self.package(game.snapshot()[name], item=item)
                self.assert_package(effects, name)
                self.assertIn(foreign, effects)
                before = game.snapshot()
                self.installed(game, repeat=True)
                self.assertEqual(before, game.snapshot())

    def test_empty_spell_with_only_casting_hooks_gets_an_ability(self):
        hook = effect(146, resource="FOREIGN", timing=1, duration=0)
        game = self.game({"OHGASFRM.SPL": SplFile(abilities=(), casting_effects=(hook,)).to_bytes()})
        self.installed(game)
        parsed = SplFile.from_bytes(game.snapshot()["OHGASFRM.SPL"])
        self.assertEqual((hook,), parsed.casting_effects)
        self.assertEqual(1, len(parsed.abilities))
        self.assert_package(parsed.abilities[0].effects, "OHGASFRM.SPL")

    def test_item_activation_cannot_substitute_for_equipped_resistance(self):
        fx = effect(89, 100, 1, item=True)
        foreign = effect(139, 3, timing=1, duration=0)
        parsed = ItmFile(abilities=(ItmAbility(raw=bytes(56), effects=(fx, foreign)),), global_effects=())
        game = self.game({"DVGASFRM.ITM": parsed.to_bytes()})
        self.installed(game)
        changed = ItmFile.from_bytes(game.snapshot()["DVGASFRM.ITM"])
        self.assert_package(changed.global_effects, "DVGASFRM.ITM")
        self.assertEqual((foreign,), changed.abilities[0].effects)

    def test_shared_slices_and_effects_before_abilities_are_supported(self):
        a = SplAbility(1, 5, 1, (effect(86, 10), effect(142, 71)))
        raw = bytearray(make_spl((a, dataclasses.replace(a, required_level=5))).to_bytes())
        struct.pack_into("<H", raw, 0x72 + 40 + 0x20, 0)
        ab = bytes(raw[0x72:0x72+80]); fx = bytes(raw[0x72+80:])
        raw[0x72:] = fx + ab
        struct.pack_into("<I", raw, 0x64, 0x72+len(fx)); struct.pack_into("<I", raw, 0x6A, 0x72)
        game = self.game({"OHGASFRM.SPL": bytes(raw)})
        self.installed(game)
        parsed = SplFile.from_bytes(game.snapshot()["OHGASFRM.SPL"])
        self.assertEqual([1, 5], [a.required_level for a in parsed.abilities])
        for a in parsed.abilities:
            self.assert_package(a.effects, "OHGASFRM.SPL")
            self.assertEqual(1, sum(f.opcode == 142 for f in a.effects))

    def test_unreadable_tables_cost_only_that_file(self):
        original = form("OHGASFRM.SPL")
        mutations = [("truncated", original[:70]), ("partial-effect", original[:-1])]
        for name, offset, fmt, value in (("ability-offset", 0x64, "I", len(original) + 1),
                                        ("effect-offset", 0x6A, "I", 3),
                                        ("casting-slice", 0x70, "H", 65535),
                                        ("ability-slice", 0x72 + 0x1E, "H", 65535)):
            raw = bytearray(original); struct.pack_into("<" + fmt, raw, offset, value)
            mutations.append((name, bytes(raw)))
        for name, malformed in mutations:
            with self.subTest(name=name):
                game = self.game({"OHGASFRM.SPL": malformed, "DVGASFRM.ITM": form("DVGASFRM.ITM")})
                self.installed(game)
                self.assertEqual(malformed, game.snapshot()["OHGASFRM.SPL"])
                self.assertEqual(expected_form(form("DVGASFRM.ITM")), game.snapshot()["DVGASFRM.ITM"])

    def test_signature_and_orphan_effect_are_not_install_fingerprints(self):
        raw = b"SPL V2  " + form("OHGASFRM.SPL")[8:] + effect(208, 1).to_bytes()
        game = self.game({"OHGASFRM.SPL": raw})
        self.installed(game)
        self.assertEqual(expected_form(form("OHGASFRM.SPL")), game.snapshot()["OHGASFRM.SPL"])

    def test_unreadable_creature_tables_do_not_stop_other_forms(self):
        for raw in (donor()[:70], donor()[:-1]):
            with self.subTest(size=len(raw)):
                game = self.game({"GASFORM4.CRE": raw, "DW#VMGAS.SPL": vampire(), "OHGASFRM.SPL": form("OHGASFRM.SPL")})
                self.installed(game)
                self.assertNotIn("CBRGAS75.CRE", game.snapshot())
                self.assertEqual(vampire(), game.snapshot()["DW#VMGAS.SPL"])
                self.assertEqual(expected_form(form("OHGASFRM.SPL")), game.snapshot()["OHGASFRM.SPL"])

    def test_full_descriptions_replace_other_english_text_and_ignore_old_poison(self):
        resources = synthetic()
        resources["DVGASFRM.ITM"] = mutate_effect(mutate_effect(resources["DVGASFRM.ITM"], 101, opcode=142), 173, opcode=142)
        texts = [TEXTS[0], "Hand-edited English text.", "Another mod's description."]
        game = self.game(resources, texts=texts)
        self.installed(game)
        self.assert_exact_install(game)
        first, first_tlk = game.snapshot(), game.tlk.read_bytes()
        self.installed(game, repeat=True)
        self.assertEqual(first, game.snapshot()); self.assertEqual(first_tlk, game.tlk.read_bytes())

    def test_other_language_preserves_text_and_still_writes_mechanics(self):
        texts = [TEXTS[0], "Anderer Beschreibungstext.", "Djinni auf Deutsch."]
        game = self.game(texts=texts, language="de_de")
        self.installed(game)
        self.assert_exact_install(game, described=False)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_descriptions_require_shared_genie_form_provider(self):
        resources = synthetic(); del resources["DVGASFRM.ITM"]
        game = self.game(resources)
        self.installed(game); self.assert_exact_install(game)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_missing_description_symbols_are_optional(self):
        resources = synthetic(); resources["SPELL.IDS"] = b"2717 SOMETHING_ELSE\n"
        game = self.game(resources)
        self.installed(game)
        for name in ("SPWI677.SPL", "SPWI678.SPL"):
            self.assertEqual(resources[name], game.snapshot()[name])
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())
        self.assert_stable(game)

    def test_small_dynamic_spell_ids_are_padded(self):
        resources = {"DVGASFRM.ITM": form("DVGASFRM.ITM"), "SPWI007.SPL": described_spell(1),
                     "SPELL.IDS": b"2007 WIZARD_SUMMON_EFREET\n"}
        game = self.game(resources); self.installed(game)
        ref = SplFile.from_bytes(game.snapshot()["SPWI007.SPL"]).description_strref
        self.assertEqual(EXPECTED_TEXTS[1], strings(game.tlk)[ref])


if __name__ == "__main__":
    unittest.main()
