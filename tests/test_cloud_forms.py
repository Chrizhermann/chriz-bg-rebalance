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

from tests.ie_formats import ItmFile, SplAbility, SplEffect, SplFile, make_spl
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
TEXTS = [
    "Untouched shared sentinel.",
    "Summon Efreeti\nOnce per day an efreeti can turn into gaseous form, becoming "
    + OLD_PHRASE + " for a short time.\nUnrelated spell statistics remain unchanged.",
    "Summon Djinni\nOnce per day a djinni can turn into gaseous form, becoming "
    + OLD_PHRASE + " for a short time.\nUnrelated spell statistics remain unchanged.",
]


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
    for opcode in RESISTANCE_OPCODES:
        value = 50 if fin and opcode in (30, 84) else 75 if fin and opcode == 31 else 100
        fx.append(effect(opcode, value, 1, item=item))
    fx.extend((effect(166, 0 if fin else 100, 1, item=item),
               effect(101, p2=25, item=item),  # poison immunity
               effect(173, 100, item=item),   # poison resistance, not a header byte
               effect(101, p2=40, item=item),  # control immunity
               effect(144, p2=2, item=item),
               effect(142, 100, item=item),    # unrelated parameter1=100
               effect(139, 0, item=item, timing=1, duration=0)))
    if item:
        return ItmFile(abilities=(), global_effects=tuple(fx)).to_bytes()
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
    raw = bytearray(blob)
    for offset in referenced_effect_offsets(blob):
        opcode, = struct.unpack_from("<H", blob, offset)
        p1, p2 = struct.unpack_from("<ii", blob, offset + 4)
        if p1 == 100 and p2 == 1:
            if opcode in RESISTANCE_OPCODES:
                struct.pack_into("<i", raw, offset + 4, 75)
            elif opcode == 166:
                struct.pack_into("<ii", raw, offset + 4, 0, 0)
    return bytes(raw)


def expected_clone(blob):
    raw = bytearray(blob)
    # CRE V1: 0x5D is MR; 0x63 is MISSILE, not poison resistance.
    raw[0x59:0x64] = bytes([75, 75, 75, 75, 0, 75, 75, 75, 75, 75, 75])
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
    def __init__(self, root, resources, *, public=False, texts=TEXTS):
        self.root = root
        self.public = public
        self.override = root / "override"
        self.override.mkdir(parents=True)
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
        self.tlk = root / "lang/en_us/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(tlk(list(texts)))
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
            "--language", "0", "--use-lang", "en_us", "--no-exit-pause", "--quick-log",
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

    def failed_unchanged(self, game, expected_message=None):
        code, output = game.run()
        self.assertNotEqual(0, code, output)
        self.assertIn("NOT INSTALLED DUE TO ERRORS", output)
        if expected_message:
            self.assertIn(expected_message, output)
        self.assertEqual(game.original, game.snapshot(), output)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes(), output)
        self.assert_stable(game)

    def assert_stable(self, game):
        for path, before in game.stable.items():
            self.assertEqual(before, path.read_bytes(), str(path))

    def assert_exact_install(self, game):
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
            wanted = game.original_texts[old_ref].replace(OLD_PHRASE, NEW_PHRASE)
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
            mr = next(fx for fx in effects if fx.opcode == 166)
            self.assertEqual((0, 1 if name == "FINBODGF.ITM" else 0), (mr.parameter1, mr.parameter2))
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

    def test_missing_all_providers_is_adapter_failure_without_mutations(self):
        self.failed_unchanged(self.game({"OTHERGAS.SPL": form("OHGASFRM.SPL")}),
                              "No supported combat cloud form is installed.")

    def test_missing_all_providers_public_component_skips(self):
        game = self.game({}, public=True)
        code, output = game.run()
        self.assertEqual(0, code, output)
        self.assertIn("SKIPPING", output)
        self.assertNotIn("SUCCESSFULLY INSTALLED", output)
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

    def test_private_resref_collision_fails_without_touching_any_provider(self):
        resources = synthetic()
        resources["CBRGAS75.CRE"] = expected_clone(resources["GASFORM4.CRE"]) + b"foreign"
        self.failed_unchanged(self.game(resources), "reserved CBRGAS75.CRE")

    def test_missing_combat_donor_fails_transactionally(self):
        resources = synthetic()
        del resources["GASFORM4.CRE"]
        self.failed_unchanged(self.game(resources), "combat mist donor is missing")

    def test_unsupported_donor_header_resistance_or_inventory_fails(self):
        mutations = ((0, b"CRE V9.9"), (0x28, struct.pack("<I", 0x6400)),
                     (0x59, bytes([125])), (0x5D, bytes([0])), (0x63, bytes([75])),
                     (0x2C0, struct.pack("<I", 1)), (0x33, bytes([2])))
        for offset, replacement in mutations:
            with self.subTest(offset=hex(offset)):
                resources = synthetic()
                raw = bytearray(resources["GASFORM4.CRE"])
                raw[offset:offset + len(replacement)] = replacement
                resources["GASFORM4.CRE"] = bytes(raw)
                self.failed_unchanged(self.game(resources))

    def test_donor_additional_damage_defenses_rejected_in_both_effect_formats(self):
        for v2 in (False, True):
            for fx in (effect(208, 1), effect(120, 0, 2), effect(101, p2=12),
                       effect(30, 100, 1), effect(166, 100, 1)):
                with self.subTest(v2=v2, opcode=fx.opcode):
                    resources = synthetic()
                    resources["GASFORM4.CRE"] = donor((fx,), v2=v2)
                    self.failed_unchanged(self.game(resources))

    def test_unreviewed_form_invulnerability_fails_before_any_publication(self):
        for fx in (effect(208, 1), effect(120, 0, 2), effect(101, p2=12)):
            with self.subTest(opcode=fx.opcode):
                resources = synthetic()
                parsed = ItmFile.from_bytes(resources["FINBODGF.ITM"])
                resources["FINBODGF.ITM"] = dataclasses.replace(
                    parsed, global_effects=(*parsed.global_effects, fx)).to_bytes()
                self.failed_unchanged(self.game(resources))

    def test_unreviewed_combat_vampire_immunity_fails(self):
        for fx in (effect(208, 1), effect(120, 0, 2), effect(101, p2=12),
                   effect(30, 100, 1), effect(166, 100, 1)):
            with self.subTest(opcode=fx.opcode):
                resources = synthetic()
                resources["DW#VMGAS.SPL"] = vampire(fx)
                self.failed_unchanged(self.game(resources))

    def test_late_description_failure_rolls_back_already_patched_resources(self):
        resources = synthetic()
        # Regression: without description preflight this second description
        # failed after resource writes and the first description's new strref;
        # WeiDU restored the resources but left the appended TLK entry behind.
        resources["SPWI678.SPL"] = resources["SPWI678.SPL"][:70]
        self.failed_unchanged(self.game(resources), "invalid summon description resource")

    def test_unreviewed_resistance_delivery_or_missing_form_signature_fails(self):
        changes = ((86, {"parameter2": 0}), (86, {"parameter1": 50}),
                   (86, {"target": 2}), (86, {"timing": 2}), (86, {"duration": 0}),
                   (98, {"opcode": 142}), (53, {"parameter1": 0x6400}))
        for opcode, fields in changes:
            with self.subTest(opcode=opcode, fields=fields):
                resources = synthetic()
                resources["OHBEGASF.SPL"] = mutate_effect(resources["OHBEGASF.SPL"], opcode, **fields)
                self.failed_unchanged(self.game(resources))

    def test_unreviewed_combat_polymorph_shape_fails(self):
        for fields in ({"parameter2": 1}, {"target": 2}, {"timing": 2},
                       {"duration": 0}, {"resource": "DACEMIST"}, {"opcode": 142}):
            with self.subTest(fields=fields):
                resources = synthetic()
                resources["DW#VMGAS.SPL"] = mutate_effect(resources["DW#VMGAS.SPL"], 135, **fields)
                self.failed_unchanged(self.game(resources))

    def test_malformed_resource_tables_fail_transactionally(self):
        original = form("OHGASFRM.SPL")
        mutations = [("truncated", original[:70]), ("wrong-version", b"SPL V2  " + original[8:]),
                     ("partial-effect", original[:-1])]
        for name, offset, fmt, value in (("ability-offset", 0x64, "I", len(original) + 1),
                                        ("effect-offset", 0x6A, "I", 3),
                                        ("casting-slice", 0x70, "H", 65535),
                                        ("ability-slice", 0x72 + 0x1E, "H", 65535)):
            raw = bytearray(original)
            struct.pack_into("<" + fmt, raw, offset, value)
            mutations.append((name, bytes(raw)))
        for name, malformed in mutations:
            with self.subTest(name=name):
                resources = synthetic()
                resources["OHGASFRM.SPL"] = malformed
                self.failed_unchanged(self.game(resources))

    def test_unused_effect_record_is_not_treated_as_cloud_owned(self):
        resources = synthetic()
        resources["OHGASFRM.SPL"] += effect(30, 100, 1).to_bytes()
        game = self.game(resources)
        self.installed(game)
        self.assert_exact_install(game)

    def test_global_spell_effect_partition_is_supported(self):
        resources = synthetic()
        parsed = SplFile.from_bytes(resources["OHGASFRM.SPL"])
        resources["OHGASFRM.SPL"] = SplFile(
            abilities=(), casting_effects=parsed.all_effects()).to_bytes()
        game = self.game(resources)
        self.installed(game)
        self.assert_exact_install(game)

    def test_partial_existing_75_values_do_not_compound(self):
        resources = synthetic()
        for name in FORMS:
            resources[name] = mutate_effect(resources[name], 86, parameter1=75)
            resources[name] = mutate_effect(resources[name], 27, parameter1=75)
        game = self.game(resources)
        self.installed(game)
        self.assert_exact_install(game)

    def test_alternate_description_warns_without_rewriting_or_touching_shared_tlk(self):
        texts = [TEXTS[0], "Different or translated description.", TEXTS[2].replace(OLD_PHRASE, NEW_PHRASE)]
        game = self.game(texts=texts)
        code, output = game.run()
        # WeiDU distinguishes successful installation with PATCH_WARN (3) from
        # both clean success (0) and transactional failure.
        self.assertEqual(3, code, output)
        self.assertIn("INSTALLED WITH WARNINGS", output)
        self.assertIn("different or untranslated text; description unchanged", output)
        self.assert_exact_install(game)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_descriptions_require_shared_genie_form_provider(self):
        resources = synthetic()
        del resources["DVGASFRM.ITM"]
        game = self.game(resources)
        self.installed(game)
        self.assert_exact_install(game)
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())

    def test_missing_description_symbols_are_optional(self):
        resources = synthetic()
        resources["SPELL.IDS"] = b"2717 SOMETHING_ELSE\n"
        game = self.game(resources)
        self.installed(game)
        for name in ("SPWI677.SPL", "SPWI678.SPL"):
            self.assertEqual(resources[name], game.snapshot()[name])
        self.assertEqual(game.original_tlk, game.tlk.read_bytes())
        self.assert_stable(game)


if __name__ == "__main__":
    unittest.main()
