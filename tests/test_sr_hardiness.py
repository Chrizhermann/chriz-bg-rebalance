"""Hardiness's four final combinations, using real WeiDU and synthetic resources.

No live game files are read. Uninstall assertions run only in disposable games.
These tests prove installer/binary behavior, not live-engine acceptance.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests.ie_formats import SplAbility, SplEffect, SplFile
from tests.test_emotion_hope_courage_installer import _write_key_and_bif


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
SETUP = ROOT / "setup-chriz-bg-rebalance.tp2"
LIBRARY = ROOT / "chriz-bg-rebalance/lib/sr_hardiness.tpa"
HARNESS = ROOT / "tests/weidu/sr_hardiness_harness.tp2"
TAIL = ROOT / "live-patch/CBR_SR_HARDINESS"
CHOICES = {(200,): (40, 0), (201,): (30, 0), (200, 202): (40, 20), (201, 202): (30, 20)}
PHYSICAL = (86, 87, 88, 89)
EXTRA = (27, 28, 29, 30, 31, 84, 85)
ORIGINAL_STRINGS = ("Hardiness", "Shared original Hardiness description.", "Unrelated text.")


def _tlk(strings: tuple[str, ...]) -> bytes:
    entries, payload = bytearray(), bytearray()
    for text in strings:
        encoded = text.encode("utf-8")
        entries.extend(struct.pack("<H8siiII", 1, b"\0" * 8, 0, 0, len(payload), len(encoded)))
        payload.extend(encoded)
    return struct.pack("<8sHII", b"TLK V1  ", 0, len(strings), 0x12 + len(entries)) + entries + payload


def _strings(path: Path) -> list[str]:
    data = path.read_bytes()
    count, start = struct.unpack_from("<II", data, 0x0A)
    result = []
    for index in range(count):
        offset, length = struct.unpack_from("<II", data, 0x12 + 0x1A * index + 0x12)
        result.append(data[start + offset : start + offset + length].decode("utf-8"))
    return result


def _tree(path: Path) -> dict[str, bytes]:
    return {p.relative_to(path).as_posix().upper(): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def _copy_tail_package(root: Path) -> str:
    package = root / "CBR_SR_HARDINESS"
    shutil.copytree(TAIL, package)
    for relative in ("lib/sr_hardiness.tpa", "languages/english/setup.tra"):
        destination = package / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "chriz-bg-rebalance" / relative, destination)
    return "CBR_SR_HARDINESS/setup-cbr_sr_hardiness.tp2"


def _metadata(effect: SplEffect) -> bytes:
    """All bytes except opcode and selected additive resistance amount."""
    raw = effect.to_bytes()
    return raw[2:4] + raw[8:]


def _spell(*, wish: bool = False, physical: int = 20, extras: bool = True,
           extra_value: int = 20, casting_at_end: bool = False) -> bytes:
    header = bytearray(0x72)
    struct.pack_into("<II", header, 0x08, 0, 0)  # shared name remains unchanged
    struct.pack_into("<H", header, 0x1C, 4)  # innate
    struct.pack_into("<I", header, 0x50, 1)  # shared old description
    header[0x25] = 4
    header[0x27] = 6 if wish else 0  # deliberately different Breach classifications
    header[0x38:0x3A] = b"\x73\x19"
    target = 3 if wish else 1
    abilities = []
    for level, duration in ((1, 6), (20, 60), (40, 120)):
        donor = SplEffect(opcode=86, target=target, parameter1=physical,
                          timing=0, resist_dispel=0, duration=duration)
        effects = [
            SplEffect(opcode=321, target=target, resource="SPCL907", timing=1),
            SplEffect(opcode=321, target=target, resource="SPWISH12", timing=1),
            SplEffect(opcode=321, target=target, resource="SPDWD02", timing=1),
            *(dataclasses.replace(donor, opcode=opcode) for opcode in PHYSICAL),
            SplEffect(opcode=142, target=target, parameter2=89, duration=duration),
        ]
        if extras:
            # SR clones the crushing-resistance donor, changing only opcode/p1.
            effects.extend(dataclasses.replace(donor, opcode=op, parameter1=extra_value) for op in EXTRA)
        effects.extend((
            SplEffect(opcode=328, target=target, parameter2=902, duration=duration),
            # A foreign resistance must survive even a physical-only selection.
            dataclasses.replace(donor, opcode=27, parameter1=13,
                                duration=duration + 7, resource="FOREIGN"),
            SplEffect(opcode=139, target=target, parameter1=2, timing=1),
        ))
        ability = bytearray(0x28)
        ability[0] = 1
        ability[0x12] = 7  # casting speed
        ability[0x16:0x1C] = b"\x31\x32\x33\x34\x35\x36"
        abilities.append(SplAbility(required_level=level, target=5 if wish else 1,
                                    projectile=123 if wish else 1, effects=tuple(effects),
                                    icon="HDICON", raw=bytes(ability)))
    casting = (SplEffect(opcode=146, target=1, timing=1, resource="DWHOOK"),
               SplEffect(opcode=86, target=1, parameter1=7, duration=3, resource="CASTING"))
    result = SplFile(tuple(abilities), casting_effects=casting, header_raw=bytes(header)).to_bytes()
    if casting_at_end:
        # A valid nonzero first-casting index exercises slice relocation, not
        # merely the commonly seen prefix of casting effects.
        raw = bytearray(result)
        effect_offset = struct.unpack_from("<I", raw, 0x6A)[0]
        effect_total = (len(raw) - effect_offset) // 0x30
        raw[effect_offset:] = raw[effect_offset + 2 * 0x30:] + raw[effect_offset:effect_offset + 2 * 0x30]
        struct.pack_into("<H", raw, 0x6E, effect_total - 2)
        for index in range(3):
            first_offset = 0x72 + index * 0x28 + 0x20
            first = struct.unpack_from("<H", raw, first_offset)[0]
            struct.pack_into("<H", raw, first_offset, first - 2)
        result = bytes(raw)
    return result


def _mutate_effects(data: bytes, transform) -> bytes:
    spell = SplFile.from_bytes(data)
    abilities = list(spell.abilities)
    abilities[1] = dataclasses.replace(abilities[1], effects=tuple(transform(list(abilities[1].effects))))
    return dataclasses.replace(spell, abilities=tuple(abilities)).to_bytes()


class SyntheticHardinessGame:
    def __init__(self, root: Path, *, sr_component: int | None = 65, game: str = "bg2ee",
                 normal: bytes | None = None, wish: bytes | None = None,
                 missing: str | None = None, tail: bool = False):
        self.root = root
        root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        self.before = {"SPCL907.SPL": normal or _spell(),
                       "SPWISH12.SPL": wish or _spell(wish=True),
                       "UNRELATE.SPL": _spell(physical=11, extras=False)}
        resources = [("SPELL", "IDS", b"IDS V1.0\n"),
                     ("STATS", "IDS", b"IDS V1.0\n"),
                     ("KIT", "IDS", b"IDS V1.0\n")]
        if game in ("bg2ee", "eet"):
            resources.append(("OH6000", "ARE", b"synthetic BG2EE marker"))
        elif game == "bgee":
            resources.append(("OH1000", "ARE", b"synthetic BGEE marker"))
        if game == "eet":
            # WeiDU 249 src/tppe.ml identifies EET by eet.flag, which also
            # makes GAME_IS bg2ee false even when OH6000.ARE is present.
            (self.override / "EET.FLAG").write_bytes(b"synthetic EET marker")
        # Normal starts BIFF-only; Wish and the unrelated sentinel start loose.
        if missing != "SPCL907":
            resources.append(("SPCL907", "SPL", self.before["SPCL907.SPL"]))
        if missing != "SPWISH12":
            (self.override / "SPWISH12.SPL").write_bytes(self.before["SPWISH12.SPL"])
        (self.override / "UNRELATE.SPL").write_bytes(self.before["UNRELATE.SPL"])
        self.bif = _write_key_and_bif(root, tuple(resources))
        self.tlk = root / "lang/en_us/dialog.tlk"
        self.tlk.parent.mkdir(parents=True)
        self.tlk.write_bytes(_tlk(ORIGINAL_STRINGS))
        (root / "dialog.tlk").write_bytes(_tlk(ORIGINAL_STRINGS))
        if sr_component is not None:
            (root / "weidu.log").write_text(
                f"~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #{sr_component} // Synthetic SR\n", encoding="ascii")
        if tail:
            self.setup = _copy_tail_package(root)
        else:
            shutil.copy2(SETUP, root / SETUP.name)
            shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
            self.setup = SETUP.name
        self.before_override = _tree(self.override)
        self.stable = {str(path.relative_to(root)): path.read_bytes()
                       for path in (root / "chitin.key", self.bif, root / "dialog.tlk")}

    def run(self, *components: int, uninstall: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(WEIDU), self.setup, "--game", str(self.root),
                               "--force-uninstall-list" if uninstall else "--force-install-list",
                               *map(str, components), "--language", "0", "--use-lang", "en_us",
                               "--no-exit-pause", "--quick-log"],
                              cwd=self.root, capture_output=True, text=True, timeout=90, check=False)

    def log(self) -> str:
        path = self.root / "weidu.log"
        return "\n".join(line for line in path.read_text(errors="replace").splitlines()
                         if not line.lstrip().startswith("//")) if path.exists() else ""


class HardinessTestCase(unittest.TestCase):
    def temporary(self) -> Path:
        holder = tempfile.TemporaryDirectory(prefix="cbr-hardiness-")
        self.addCleanup(holder.cleanup)
        return Path(holder.name)

    def make_game(self, **kwargs) -> SyntheticHardinessGame:
        return SyntheticHardinessGame(self.temporary() / "game", **kwargs)

    def assert_stable(self, game: SyntheticHardinessGame) -> None:
        for relative, payload in game.stable.items():
            self.assertEqual(payload, (game.root / relative).read_bytes(), relative)
        self.assertEqual(list(ORIGINAL_STRINGS), _strings(game.tlk)[:len(ORIGINAL_STRINGS)])
        self.assertEqual(game.before["UNRELATE.SPL"], (game.override / "UNRELATE.SPL").read_bytes())

    def assert_spell(self, before: bytes, after: bytes, physical: int, extra: int,
                     *, description_changed: bool = False) -> None:
        old, new = SplFile.from_bytes(before), SplFile.from_bytes(after)
        old_header, new_header = bytearray(old.header_raw), bytearray(new.header_raw)
        # Casting effects may move when per-ability effect counts change.
        old_header[0x6E:0x70] = new_header[0x6E:0x70]
        if description_changed:
            self.assertNotEqual(old.description_strref, new.description_strref)
            old_header[0x50:0x54] = new_header[0x50:0x54]
        self.assertEqual(old_header, new_header, "spell metadata/Breach classification changed")
        self.assertEqual([fx.to_bytes() for fx in old.casting_effects],
                         [fx.to_bytes() for fx in new.casting_effects])
        self.assertEqual(len(old.abilities), len(new.abilities))
        for old_ability, new_ability in zip(old.abilities, new.abilities):
            old_raw, new_raw = bytearray(old_ability.raw), bytearray(new_ability.raw)
            old_raw[0x1E:0x22] = new_raw[0x1E:0x22]
            self.assertEqual(old_raw, new_raw, "casting speed, targeting or level changed")
            donor = next(fx for fx in old_ability.effects if fx.opcode == 86)
            for opcode in PHYSICAL:
                source = [fx for fx in old_ability.effects if fx.opcode == opcode]
                output = [fx for fx in new_ability.effects if fx.opcode == opcode]
                self.assertEqual(1, len(output))
                self.assertEqual(dataclasses.replace(source[0], parameter1=physical).to_bytes(), output[0].to_bytes())
            for opcode in EXTRA:
                output = [fx for fx in new_ability.effects if fx.opcode == opcode and _metadata(fx) == _metadata(donor)]
                self.assertEqual(1 if extra else 0, len(output), f"extra opcode {opcode}")
                if extra:
                    self.assertEqual(dataclasses.replace(donor, opcode=opcode, parameter1=extra).to_bytes(), output[0].to_bytes())
            def foreign(effects):
                return [fx.to_bytes() for fx in effects if fx.opcode not in PHYSICAL
                        and not (fx.opcode in EXTRA and _metadata(fx) == _metadata(donor))]
            self.assertEqual(foreign(old_ability.effects), foreign(new_ability.effects),
                             "stacking, AI markers, icon or unrelated resistance changed")

    def transform(self, payload: bytes, physical: int, extra: int,
                  *, success: bool = True, error: str | None = None) -> tuple[bytes | None, str]:
        folder = self.temporary()
        source, destination = folder / "input.spl", folder / "output.spl"
        source.write_bytes(payload)
        command = [str(WEIDU), str(HARNESS), "--nogame", "--force-install-list", "0",
                   "--no-exit-pause", "--quick-log"]
        for value in (LIBRARY, source, destination, physical, extra):
            command.extend(("--args", str(value)))
        result = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=90, check=False)
        transcript = result.stdout + result.stderr
        if success:
            self.assertEqual(0, result.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertTrue(destination.exists(), transcript)
        else:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", transcript)
            self.assertFalse(destination.exists(), transcript)
            if error is not None:
                self.assertIn(error, transcript)
        self.assertEqual(payload, source.read_bytes())
        return destination.read_bytes() if destination.exists() else None, transcript


class HardinessTransformerTests(HardinessTestCase):
    def test_all_choices_both_targets_all_levels_preserve_other_mechanics(self):
        for physical, extra in CHOICES.values():
            for wish in (False, True):
                with self.subTest(physical=physical, extra=extra, wish=wish):
                    before = _spell(wish=wish)
                    after, _ = self.transform(before, physical, extra)
                    self.assert_spell(before, after, physical, extra)

    def test_complete_absence_of_extra_clones_supports_both_choices(self):
        for physical, extra in CHOICES.values():
            with self.subTest(physical=physical, extra=extra):
                before = _spell(extras=False)
                after, _ = self.transform(before, physical, extra)
                self.assert_spell(before, after, physical, extra)

    def test_old_hotfix_and_arbitrary_additive_values_are_normalized(self):
        for input_value in (40, 30, -17, 999):
            with self.subTest(input_value=input_value):
                before = _spell(physical=input_value, extra_value=-8)
                after, _ = self.transform(before, 30, 20)
                self.assert_spell(before, after, 30, 20)

    def test_unequal_incoming_physical_percentages_are_all_replaced(self):
        before = _mutate_effects(
            _spell(), lambda effects: [dataclasses.replace(fx, parameter1=fx.opcode - 100)
                                      if fx.opcode in PHYSICAL else fx for fx in effects])
        after, _ = self.transform(before, 40, 0)
        self.assert_spell(before, after, 40, 0)

    def test_each_choice_is_exactly_byte_idempotent(self):
        for physical, extra in CHOICES.values():
            with self.subTest(physical=physical, extra=extra):
                first, _ = self.transform(_spell(wish=True), physical, extra)
                second, _ = self.transform(first, physical, extra)
                self.assertEqual(first, second)

    def test_nonzero_casting_effect_slice_is_preserved(self):
        for extra in (0, 20):
            with self.subTest(extra=extra):
                before = _spell(casting_at_end=True)
                self.assertGreater(struct.unpack_from("<H", before, 0x6E)[0], 0)
                after, _ = self.transform(before, 40, extra)
                self.assert_spell(before, after, 40, extra)

    def test_invalid_requested_percentages_fail_closed(self):
        for physical, extra in ((20, 0), (41, 0), (40, 10), (30, -1)):
            with self.subTest(physical=physical, extra=extra):
                self.transform(_spell(), physical, extra, success=False,
                               error="unsupported resistance choice")

    def test_partial_duplicate_or_nonadditive_sr_clones_fail_closed(self):
        def missing(effects):
            return [fx for fx in effects if fx.opcode != 85]
        def duplicate(effects):
            return effects + [next(fx for fx in effects if fx.opcode == 85)]
        def nonadditive(effects):
            return [dataclasses.replace(fx, parameter2=1) if fx.opcode == 85 else fx for fx in effects]
        for mutation, error in ((missing, "incomplete SR resistance clone set"),
                                (duplicate, "ambiguous duplicate SR resistance clones"),
                                (nonadditive, "incomplete SR resistance clone set")):
            with self.subTest(mutation=mutation.__name__):
                self.transform(_mutate_effects(_spell(), mutation), 40, 0, success=False, error=error)

    def test_missing_duplicate_or_incompatible_physical_effects_fail_closed(self):
        def missing(effects):
            return [fx for fx in effects if fx.opcode != 88]
        def duplicate(effects):
            return effects + [next(fx for fx in effects if fx.opcode == 86)]
        def mode(effects):
            return [dataclasses.replace(fx, parameter2=1) if fx.opcode == 87 else fx for fx in effects]
        def delivery(effects):
            return [dataclasses.replace(fx, target=2) if fx.opcode == 89 else fx for fx in effects]
        for mutation, error in ((missing, "expected one direct modifier"),
                                (duplicate, "expected one direct modifier"),
                                (mode, "physical resistance must use additive modifiers"),
                                (delivery, "physical modifiers have inconsistent delivery metadata")):
            with self.subTest(mutation=mutation.__name__):
                self.transform(_mutate_effects(_spell(), mutation), 40, 20, success=False, error=error)

    def test_malformed_effect_partitions_fail_closed(self):
        source = _spell()
        for case in ("signature", "empty", "truncated", "ability_bounds", "effect_bounds",
                     "ability_overlap", "casting_overlap", "casting_bounds"):
            with self.subTest(case=case):
                raw = bytearray(source)
                if case == "signature":
                    raw[:8] = b"SPL V2  "
                elif case == "empty":
                    struct.pack_into("<H", raw, 0x68, 0)
                elif case == "truncated":
                    del raw[-1:]
                elif case == "ability_bounds":
                    struct.pack_into("<H", raw, 0x68, 65535)
                elif case == "effect_bounds":
                    struct.pack_into("<H", raw, 0x72 + 0x20, 65535)
                elif case == "ability_overlap":
                    first = struct.unpack_from("<H", raw, 0x72 + 0x20)[0]
                    struct.pack_into("<H", raw, 0x72 + 0x28 + 0x20, first)
                elif case == "casting_overlap":
                    struct.pack_into("<H", raw, 0x6E, 2)
                elif case == "casting_bounds":
                    struct.pack_into("<H", raw, 0x6E, 65535)
                self.transform(bytes(raw), 40, 0, success=False)


class HardinessInstallerTests(HardinessTestCase):
    def assert_installed(self, game, result, component):
        transcript = result.stdout + result.stderr
        self.assertEqual(0, result.returncode, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        self.assert_stable(game)

    def assert_unchanged(self, game, result, component, *, skipped=False):
        transcript = result.stdout + result.stderr
        self.assertIn("SKIPPING" if skipped else "NOT INSTALLED DUE TO ERRORS", transcript)
        self.assertNotRegex(game.log(), rf"(?m)#0\s+#{component}\b")
        self.assertEqual(game.before_override, _tree(game.override))
        self.assertEqual(_tlk(ORIGINAL_STRINGS), game.tlk.read_bytes())
        self.assert_stable(game)

    def test_public_choices_patch_biff_and_override_and_append_correct_descriptions(self):
        for components, (physical, extra) in CHOICES.items():
            with self.subTest(components=components):
                game = self.make_game()
                result = game.run(*components)
                for component in components:
                    self.assert_installed(game, result, component)
                for name in ("SPCL907.SPL", "SPWISH12.SPL"):
                    output = (game.override / name).read_bytes()
                    self.assert_spell(game.before[name], output, physical, extra, description_changed=True)
                    ref = SplFile.from_bytes(output).description_strref
                    description = _strings(game.tlk)[ref].lower()
                    self.assertIn(f"{physical}%", description)
                    self.assertIn("physical", description)
                    self.assertNotIn("all forms", description)
                    if extra:
                        for word in ("20%", "fire", "cold", "acid", "electricity", "magic damage"):
                            self.assertIn(word, description)
                    else:
                        self.assertNotIn("20%", description)
                self.assertEqual({"SPCL907.SPL", "SPWISH12.SPL", "UNRELATE.SPL"}, set(_tree(game.override)))

    def test_missing_sr_and_main_only_sr_are_noops(self):
        for sr_component in (None, 0):
            for component in (200, 201, 202):
                with self.subTest(sr_component=sr_component, component=component):
                    game = self.make_game(sr_component=sr_component)
                    self.assert_unchanged(game, game.run(component), component, skipped=True)

    def test_non_bg2_game_is_a_noop(self):
        game = self.make_game(game="bgee")
        self.assert_unchanged(game, game.run(200), 200, skipped=True)

    def test_extra_resistance_without_physical_selection_is_a_noop(self):
        game = self.make_game()
        self.assert_unchanged(game, game.run(202), 202, skipped=True)

    def test_eet_markers_are_accepted(self):
        game = self.make_game(game="eet")
        self.assert_installed(game, game.run(200), 200)

    def test_missing_second_spell_leaves_first_and_tlk_untouched(self):
        game = self.make_game(missing="SPWISH12")
        result = game.run(200)
        self.assert_unchanged(game, result, 200,
                              skipped="NOT INSTALLED DUE TO ERRORS" not in result.stdout + result.stderr)

    def test_malformed_second_spell_rolls_back_first_and_tlk(self):
        malformed = _mutate_effects(_spell(wish=True), lambda effects: [fx for fx in effects if fx.opcode != 89])
        game = self.make_game(wish=malformed)
        self.assert_unchanged(game, game.run(200), 200)

    def test_all_four_choices_restore_original_files_on_synthetic_uninstall(self):
        for components in CHOICES:
            with self.subTest(components=components):
                game = self.make_game()
                result = game.run(*components)
                for component in components:
                    self.assert_installed(game, result, component)
                result = game.run(*components, uninstall=True)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(game.before_override, _tree(game.override))
                for component in components:
                    self.assertNotRegex(game.log(), rf"(?m)#0\s+#{component}\b")
                self.assert_stable(game)

    def test_mutually_exclusive_choices_never_remain_installed_together(self):
        game = self.make_game()
        result = game.run(200, 201)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        installed = [component for component in (200, 201) if re.search(rf"(?m)#0\s+#{component}\b", game.log())]
        self.assertEqual(1, len(installed), game.log())
        physical, extra = CHOICES[(installed[0],)]
        self.assert_spell(game.before["SPCL907.SPL"], (game.override / "SPCL907.SPL").read_bytes(),
                          physical, extra, description_changed=True)
        self.assert_stable(game)

    def test_tail_package_exercises_same_four_choices(self):
        self.assertTrue(TAIL.is_dir(), "standalone existing-install patch is missing")
        for components, (physical, extra) in CHOICES.items():
            with self.subTest(components=components):
                game = self.make_game(tail=True)
                result = game.run(*components)
                for component in components:
                    self.assert_installed(game, result, component)
                for name in ("SPCL907.SPL", "SPWISH12.SPL"):
                    self.assert_spell(game.before[name], (game.override / name).read_bytes(), physical, extra,
                                      description_changed=True)

    def test_main_and_tail_installers_reject_cross_family_double_install(self):
        for tail_first in (False, True):
            with self.subTest(tail_first=tail_first):
                game = self.make_game(tail=tail_first)
                self.assert_installed(game, game.run(200), 200)
                before_override, before_tlk, before_log = _tree(game.override), game.tlk.read_bytes(), game.log()
                if tail_first:
                    shutil.copy2(SETUP, game.root / SETUP.name)
                    shutil.copytree(ROOT / "chriz-bg-rebalance", game.root / "chriz-bg-rebalance")
                    game.setup = SETUP.name
                else:
                    game.setup = _copy_tail_package(game.root)
                result = game.run(201, 202)
                self.assertIn("SKIPPING", result.stdout + result.stderr)
                self.assertEqual(before_override, _tree(game.override))
                self.assertEqual(before_tlk, game.tlk.read_bytes())
                self.assertEqual(before_log, game.log())

    def test_uninstalling_only_optional_extra_restores_physical_only_bytes(self):
        game = self.make_game()
        self.assert_installed(game, game.run(201), 201)
        physical_only = _tree(game.override)
        self.assert_installed(game, game.run(202), 202)
        result = game.run(202, uninstall=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(physical_only, _tree(game.override))
        self.assertRegex(game.log(), r"(?m)#0\s+#201\b")
        self.assertNotRegex(game.log(), r"(?m)#0\s+#202\b")
        self.assert_stable(game)

    def test_conflicting_physical_selection_cannot_replace_existing_base_and_extra(self):
        game = self.make_game()
        self.assert_installed(game, game.run(200, 202), 202)
        before_override, before_tlk = _tree(game.override), game.tlk.read_bytes()
        result = game.run(201)
        self.assertIn("another subcomponent", result.stdout + result.stderr)
        self.assertRegex(game.log(), r"(?m)#0\s+#200\b")
        self.assertNotRegex(game.log(), r"(?m)#0\s+#201\b")
        self.assertRegex(game.log(), r"(?m)#0\s+#202\b")
        self.assertEqual(before_override, _tree(game.override))
        self.assertEqual(before_tlk, game.tlk.read_bytes())
        self.assert_stable(game)

    def test_package_builder_ships_canonical_library_and_strings(self):
        output = self.temporary() / "packages"
        result = subprocess.run([sys.executable, str(ROOT / "tools/package_sr_hardiness.py"),
                                 "--output", str(output)],
                                cwd=ROOT, capture_output=True, text=True, timeout=90, check=False)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        archives = sorted(output.glob("*.zip"))
        self.assertEqual(2, len(archives))
        for archive in archives:
            tail = archive.name.startswith("CBR_SR_HARDINESS-")
            package = "CBR_SR_HARDINESS" if tail else "chriz-bg-rebalance"
            with zipfile.ZipFile(archive) as bundle:
                for relative in ("lib/sr_hardiness.tpa", "languages/english/setup.tra"):
                    self.assertEqual((ROOT / "chriz-bg-rebalance" / relative).read_bytes(),
                                     bundle.read(f"{package}/{relative}"))
                installer = "Setup-cbr_sr_hardiness.exe" if tail else "Setup-chriz-bg-rebalance.exe"
                self.assertEqual(WEIDU.read_bytes(), bundle.read(installer))
            expected_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(f"{expected_hash}  {archive.name}",
                             archive.with_suffix(".zip.sha256").read_text().strip())


if __name__ == "__main__":
    unittest.main()
