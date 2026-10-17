"""Donor-variation tests for component 404 (Chaos of Battle tides).

The tide rebuild classifies every record of each OHTMPS2D/OHTMPS2E ability
tier instead of fingerprinting the donor (audit 2026-10-08, item 5): the tide
owns the per-target lottery (stat opcodes and partial probability windows),
the op139 feedback string, and the donor's self-referencing stacking records;
everything else is chrome or an unowned record carried byte-identically in
donor order. These tests mutate the real vanilla/live donor captures
(research/originals) into alternate valid layouts and check

* the semantic outcome named by each test (what is carried, where, and what
  is dropped),
* byte-for-byte agreement of every rebuilt record with an independent Python
  model of the design (``expected_tide``), and
* for the reference donors, byte identity with the output of the code before
  the redesign (``REFERENCE_DIGESTS``).

They reuse the --nogame harness of tests/test_tempus_completion.py; the
verify-only harness exercises cbr_tide_verify_spell's leftover detection.
"""

from __future__ import annotations

import dataclasses
import hashlib
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from tests.ie_formats import SplAbility, SplEffect, SplFile, read_spl
from tests.test_tempus_completion import (
    BULWARK_OPS,
    HOLY_TPA,
    ONSLAUGHT_OPS,
    ROOT,
    TIDE_ALLY,
    TIDE_ENEMY,
    TIDE_STRREFS,
    TIDES_TPA,
    WEIDU,
    TempusCompletionTestCase,
    build_tides_fixture,
)

VERIFY_HARNESS = ROOT / "tests" / "weidu" / "tempus_chaos_tides_verify_harness.tp2"

# SHA-256 of every output file of the tides harness, generated with the
# library as of dd51c72 (origin/main before the classification redesign) on
# the captured vanilla BIF donors and the live EEFP + SCS donors. The
# redesign must reproduce these bytes exactly.
REFERENCE_DIGESTS = {
    "vanilla": {
        "CBRCHT1D.SPL": "d7f95c57f517964a7a2281eef061314c73e2196f83d987871b5287be622c427c",
        "CBRCHT1E.SPL": "05942868e101eee1fab7a04e3ba6b235b16b19f1e39b1889f0f9f1ccbf000ca0",
        "CBRCHT2D.SPL": "4ca95c58ead66b5d50110c50dd7d26656ee2013e89a713d95143cbe16679e7ed",
        "CBRCHT2E.SPL": "7e80fcba1aed7b2bfcd5302605579ab70e45a457475f3e34d9d5a571fe0feeb6",
        "CBRCHT3D.SPL": "9baaa6037a8560627eb44b3e261bda9b640cc2ccbfc979cdab6921f803012f60",
        "CBRCHT3E.SPL": "6637f432814ceea4f0b189bf8cfd7afca5616392d95e96db8861b05eb25a7561",
        "OHTMPS2.SPL": "54d726fc54290180463c7b49321a83c974007703a31d7518e969424f925f181f",
        "OHTMPS2D.SPL": "f4279837b00355006a54cbd2815865f048cc7e25b0617e23d7b3ed0fdfdc03dd",
        "OHTMPS2E.SPL": "c27c0ddef5f8b93085c7f353053e954ec598aef1dea912c672b1608fbb24eccb",
    },
    "live": {
        "CBRCHT1D.SPL": "806c0299d411f8a33b0d3be808e2d21b9c4e4e248cbe4c860a080e09a146c3fa",
        "CBRCHT1E.SPL": "78a452c591546fcd07ea985b4810bfc5a94c1485a5a57ba0c16d804ead8fefbc",
        "CBRCHT2D.SPL": "4848636427e33e005fa93ffa11bd73e7034849d7d585760e7fef13c9df1211a3",
        "CBRCHT2E.SPL": "66cb2e12b4fa70510fde743655e5ae013e9fa27cbad149f64e1f328a4b859a24",
        "CBRCHT3D.SPL": "91d2de636374a3a66f5483d95317f9b6c4026516339e3acf4ea4032fe107f1fa",
        "CBRCHT3E.SPL": "b25ae09ef671771ddf8f1704f1d4444ac2dae972f9dba38076f1343dc6520066",
        "OHTMPS2.SPL": "54d726fc54290180463c7b49321a83c974007703a31d7518e969424f925f181f",
        "OHTMPS2D.SPL": "08a687991ae9bae1a41e67851b0102baf1901d7914d436527d6f867e619ee140",
        "OHTMPS2E.SPL": "651c582081f543e6f7fc9a478e35d52260355dcc0ec660e42e769e9c73e28df6",
    },
}

TIDE_FILES = TIDE_ALLY + TIDE_ENEMY
STAT_OPS = frozenset({0, 18, 22, 33, 34, 35, 36, 37, 54, 285, 286})
TIDE_STATS = {1: ONSLAUGHT_OPS, 2: BULWARK_OPS, 3: (22,)}


# ---------------------------------------------------------------------------
# Raw-preserving SPL serialization (ie_formats.SplFile.to_bytes normalizes
# resref case, which would hide the byte identity these tests assert)
# ---------------------------------------------------------------------------


def _fx_bytes(effect: SplEffect) -> bytes:
    """Original bytes for an untouched record, re-serialized after a change."""
    if len(effect.raw) == 0x30 and SplEffect.from_bytes(effect.raw) == effect:
        return effect.raw
    return effect.to_bytes()


def spl_bytes(spell: SplFile) -> bytes:
    header = bytearray(spell.header_raw)
    ability_offset = 0x72
    effect_offset = ability_offset + len(spell.abilities) * 0x28
    struct.pack_into("<I", header, 0x64, ability_offset)
    struct.pack_into("<H", header, 0x68, len(spell.abilities))
    struct.pack_into("<I", header, 0x6A, effect_offset)
    struct.pack_into("<H", header, 0x6E, 0)
    struct.pack_into("<H", header, 0x70, len(spell.casting_effects))
    abilities = []
    effects = list(spell.casting_effects)
    for ability in spell.abilities:
        raw = bytearray(ability.raw)
        struct.pack_into("<H", raw, 0x10, ability.required_level)
        struct.pack_into("<H", raw, 0x1E, len(ability.effects))
        struct.pack_into("<H", raw, 0x20, len(effects))
        abilities.append(bytes(raw))
        effects.extend(ability.effects)
    return bytes(header) + b"".join(abilities) + b"".join(_fx_bytes(e) for e in effects)


def with_raw_resource(effect: SplEffect, resource: bytes) -> SplEffect:
    """Effect whose raw resref bytes are exactly ``resource`` (case kept)."""
    raw = bytearray(_fx_bytes(effect))
    raw[0x14:0x1C] = resource.ljust(8, b"\0")
    return SplEffect.from_bytes(bytes(raw))


def map_tiers(
    spell: SplFile, change: Callable[[int, tuple[SplEffect, ...]], tuple[SplEffect, ...]]
) -> SplFile:
    abilities = tuple(
        dataclasses.replace(ability, effects=change(index, ability.effects))
        for index, ability in enumerate(spell.abilities)
    )
    return dataclasses.replace(spell, abilities=abilities)


def insert_after(effects: tuple[SplEffect, ...], opcode: int, new: SplEffect, occurrence: int = 1):
    seen = 0
    for index, effect in enumerate(effects):
        if effect.opcode == opcode:
            seen += 1
            if seen == occurrence:
                return effects[: index + 1] + (new,) + effects[index + 1 :]
    raise AssertionError(f"opcode {opcode} occurrence {occurrence} not found")


def without(effects: tuple[SplEffect, ...], *opcodes: int) -> tuple[SplEffect, ...]:
    return tuple(effect for effect in effects if effect.opcode not in opcodes)


Mutation = Callable[[SplFile], SplFile]


def build_variant(
    root: Path, *, shape: str = "vanilla", ally: Mutation | None = None,
    enemy: Mutation | None = None,
) -> None:
    build_tides_fixture(root, shape=shape)
    for name, mutate in (("OHTMPS2D", ally), ("OHTMPS2E", enemy)):
        if mutate is not None:
            path = root / f"{name}.SPL"
            path.write_bytes(spl_bytes(mutate(read_spl(path))))


# Records other mods plausibly add to a tier. Distinctive values in rarely
# used fields make byte identity observable.
SOUND = SplEffect(opcode=174, target=2, power=1, timing=1, resource="CAS_M07", special=0x5A5A)
STATE_MARKER = SplEffect(
    opcode=328, target=2, power=1, parameter1=0, parameter2=160, timing=0, duration=60,
    resist_dispel=3, dice_number=7,
)
THIRD_VISUAL = SplEffect(
    opcode=215, target=2, power=1, parameter2=1, timing=0, duration=3, resist_dispel=3,
    resource="SPMAGMIS",
)
FOREIGN_RESET = SplEffect(opcode=321, target=2, power=1, timing=1, resist_dispel=3, resource="SPPR101")
OTHER_SIDE_RESET = SplEffect(opcode=321, target=2, power=1, timing=1, resource="OHTMPS2E")
FOREIGN_PROTECTION = SplEffect(
    opcode=206, target=2, power=1, timing=0, duration=60, parameter1=-1, resource="SPWI101"
)


# ---------------------------------------------------------------------------
# Independent model of the design
# ---------------------------------------------------------------------------


def band(level: int) -> int:
    for index, threshold in enumerate((7, 13, 19, 25)):
        if level < threshold:
            return index
    return 4


def magnitude(tide: int, level: int) -> int:
    b = band(level)
    if tide == 3:
        return 2 if b >= 3 else 1
    return 4 if b >= 4 else 3 if b >= 2 else 2


def classify(effect: SplEffect, donor: str) -> str:
    if effect.opcode == 139:
        return "feedback"
    if effect.opcode in STAT_OPS:
        return "lottery"
    if effect.probability1 < 100 or effect.probability2 > 0:
        return "lottery"
    own = effect.opcode in (321, 206, 318, 324) and effect.resource.upper() == donor
    if own:
        return "reset" if effect.opcode == 321 else "control"
    if effect.opcode == 215:
        return "visual"
    if effect.opcode in (142, 9):
        return "status"
    return "carried"


def _template(effects: tuple[SplEffect, ...]) -> tuple[int, int] | None:
    for effect in effects:
        if effect.opcode == 54:
            return effect.power, effect.resist_dispel
    return None


def expected_tide(
    donor_spell: SplFile, donor: str, tide: int, sign: int, resets: tuple[str, ...]
) -> tuple[list[bytes], list[list[bytes]]]:
    templates = [_template(ability.effects) for ability in donor_spell.abilities]
    fallback = next(t for t in templates if t is not None)
    tiers = []
    for ability, own_template in zip(donor_spell.abilities, templates):
        power, resist = own_template or fallback
        reset = next((e for e in ability.effects if classify(e, donor) == "reset"), None)
        records = []
        for name in resets:
            if reset is not None:
                raw = bytearray(_fx_bytes(reset))
                raw[0x14:0x1C] = name.encode("ascii").ljust(8, b"\0")
                records.append(bytes(raw))
            else:
                records.append(
                    SplEffect(
                        opcode=321, target=2, power=power, timing=1, resist_dispel=resist,
                        resource=name,
                    ).to_bytes()
                )
        for effect in ability.effects:
            kind = classify(effect, donor)
            if kind in ("visual", "carried"):
                records.append(_fx_bytes(effect))
            elif kind == "status":
                raw = bytearray(_fx_bytes(effect))
                struct.pack_into("<I", raw, 0x0E, 30)
                records.append(bytes(raw))
        signed = magnitude(tide, ability.required_level) * sign
        for opcode in TIDE_STATS[tide]:
            records.append(
                SplEffect(
                    opcode=opcode, target=2, power=power, parameter1=signed, timing=0,
                    resist_dispel=resist, duration=30,
                ).to_bytes()
            )
        tiers.append(records)
    return [_fx_bytes(e) for e in donor_spell.casting_effects], tiers


def _digests(root: Path) -> dict[str, str]:
    return {
        path.name.upper(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file() and path.name.upper() != "CBR_TEST.OK"
    }


def tide_digests(root: Path) -> dict[str, str]:
    return {name: digest for name, digest in _digests(root).items() if name.startswith("CBRCHT")}


def reference_tides(shape: str) -> dict[str, str]:
    return {
        name: digest for name, digest in REFERENCE_DIGESTS[shape].items()
        if name.startswith("CBRCHT")
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class ChaosTidesVariantTestCase(TempusCompletionTestCase):
    def build(self, **variant) -> "object":
        rerun = variant.pop("rerun_on_output", False)
        expect_success = variant.pop("expect_success", True)
        return self.run_component(
            "tides",
            lambda root: build_variant(root, **variant),
            extra_args=TIDE_STRREFS,
            expect_success=expect_success,
            rerun_on_output=rerun,
        )

    def assert_matches_model(self, run) -> None:
        """Every tide spell equals the model built from the fixture donors."""
        for donor, names, sign in (("OHTMPS2D", TIDE_ALLY, 1), ("OHTMPS2E", TIDE_ENEMY, -1)):
            donor_spell = read_spl(run.fixture / f"{donor}.SPL")
            self.assertEqual(
                (run.fixture / f"{donor}.SPL").read_bytes(),
                (run.output / f"{donor}.SPL").read_bytes(),
                f"{donor} is a read-only input",
            )
            for tide, name in enumerate(names, start=1):
                spell = read_spl(run.output / f"{name}.SPL")
                casting, tiers = expected_tide(donor_spell, donor, tide, sign, names)
                self.assertEqual([e.raw for e in spell.casting_effects], casting, f"{name} casting")
                self.assertEqual(len(spell.abilities), len(donor_spell.abilities), name)
                for index, (ability, donor_ability, records) in enumerate(
                    zip(spell.abilities, donor_spell.abilities, tiers)
                ):
                    self.assertEqual(ability.raw[:0x1E], donor_ability.raw[:0x1E], f"{name} header {index}")
                    self.assertEqual(ability.raw[0x22:], donor_ability.raw[0x22:], f"{name} header {index}")
                    self.assertEqual(
                        [e.raw for e in ability.effects], records, f"{name} tier {index} records"
                    )

    def tier_opcodes(self, run, name: str, tier: int) -> list[int]:
        return [e.opcode for e in read_spl(run.output / f"{name}.SPL").abilities[tier].effects]


class ReferenceDonorTests(ChaosTidesVariantTestCase):
    def test_reference_donors_reproduce_pre_redesign_bytes_and_rerun(self) -> None:
        for shape in ("vanilla", "live"):
            with self.subTest(shape=shape):
                run = self.build(shape=shape, rerun_on_output=True)
                self.assertEqual(_digests(run.output), REFERENCE_DIGESTS[shape])
                self.assert_matches_model(run)
                self.assertIn(
                    "cbr 404: ally donor OHTMPS2D: 5 tiers, 0 unowned records carried, "
                    "0 tiers with synthesized resets.",
                    run.transcript,
                )


class CarriedRecordTests(ChaosTidesVariantTestCase):
    def test_third_visual_is_carried_in_place(self) -> None:
        def add_visual(spell: SplFile) -> SplFile:
            return map_tiers(spell, lambda _i, fx: insert_after(fx, 9, THIRD_VISUAL))

        run = self.build(ally=add_visual, enemy=add_visual, rerun_on_output=True)
        self.assert_matches_model(run)
        for name in TIDE_FILES:
            spell = read_spl(run.output / f"{name}.SPL")
            for ability in spell.abilities:
                kept = [e.opcode for e in ability.effects[3:] if e.opcode in (215, 142, 9)]
                self.assertEqual(kept, [215, 142, 9, 215, 215], f"{name} chrome order")
                self.assertIn(THIRD_VISUAL.to_bytes(), [e.raw for e in ability.effects])

    def test_full_window_sound_and_state_marker_are_carried_in_place(self) -> None:
        def add_markers(spell: SplFile) -> SplFile:
            # Sound right after the first visual, state marker after the
            # whole lottery (the end of the tier).
            return map_tiers(
                spell, lambda _i, fx: insert_after(fx, 215, SOUND) + (STATE_MARKER,)
            )

        run = self.build(shape="live", ally=add_markers, enemy=add_markers)
        self.assert_matches_model(run)
        for name in TIDE_FILES:
            for tier, ability in enumerate(read_spl(run.output / f"{name}.SPL").abilities):
                kept = [e.opcode for e in ability.effects[3:] if e.opcode in (215, 142, 9, 174, 328)]
                expected = [215, 174, 142, 9, 328] if tier == 0 else [215, 174, 142, 9, 215, 328]
                self.assertEqual(kept, expected, f"{name} tier {tier} donor order")
                raws = [e.raw for e in ability.effects]
                self.assertIn(SOUND.to_bytes(), raws)
                self.assertIn(STATE_MARKER.to_bytes(), raws)
        self.assertIn("ally donor OHTMPS2D: 5 tiers, 10 unowned records carried", run.transcript)

    def test_foreign_resets_and_protections_are_carried(self) -> None:
        def add_foreign(spell: SplFile) -> SplFile:
            return map_tiers(
                spell,
                lambda _i, fx: fx[:1] + (FOREIGN_RESET, OTHER_SIDE_RESET) + fx[1:]
                + (FOREIGN_PROTECTION,),
            )

        run = self.build(ally=add_foreign)
        self.assert_matches_model(run)
        for name in TIDE_ALLY:
            for ability in read_spl(run.output / f"{name}.SPL").abilities:
                effects = ability.effects
                self.assertEqual([e.resource for e in effects[:3]], list(TIDE_ALLY))
                self.assertEqual(
                    [_fx_bytes(e) for e in effects[3:5]],
                    [FOREIGN_RESET.to_bytes(), OTHER_SIDE_RESET.to_bytes()],
                    "foreign op321 records keep their donor position after the trio",
                )
                self.assertIn(FOREIGN_PROTECTION.to_bytes(), [e.raw for e in effects])


class OwnedRecordTests(ChaosTidesVariantTestCase):
    def test_reset_not_at_record_zero_is_recognized(self) -> None:
        def move_reset(spell: SplFile) -> SplFile:
            def change(_i, fx):
                reset, rest = fx[0], fx[1:]
                self.assertEqual(reset.opcode, 321)
                return rest[:4] + (reset,) + rest[4:]

            return map_tiers(spell, change)

        for shape in ("vanilla", "live"):
            with self.subTest(shape=shape):
                run = self.build(shape=shape, ally=move_reset, enemy=move_reset)
                self.assertEqual(
                    tide_digests(run.output),
                    reference_tides(shape),
                    "a reordered reset rebuilds to the reference tides",
                )
                self.assert_matches_model(run)

    def test_scs_self_protections_are_dropped(self) -> None:
        def add_self_protection(donor: str) -> Mutation:
            protect = SplEffect(opcode=318, target=2, power=1, timing=0, duration=60, resist_dispel=3)
            immune = SplEffect(opcode=324, target=2, power=1, timing=0, duration=60, resist_dispel=3)
            records = (
                with_raw_resource(protect, donor.encode("ascii")),
                with_raw_resource(immune, donor.lower().encode("ascii")),
            )
            return lambda spell: map_tiers(spell, lambda _i, fx: fx + records)

        run = self.build(
            shape="live", ally=add_self_protection("OHTMPS2D"), enemy=add_self_protection("OHTMPS2E")
        )
        self.assertEqual(tide_digests(run.output), reference_tides("live"))
        self.assert_matches_model(run)

    def test_partial_window_foreign_outcomes_are_dropped(self) -> None:
        damage = SplEffect(opcode=12, target=2, power=1, parameter2=0x10000, duration=0,
                           probability1=10, probability2=0, dice_number=1, dice_size=6)
        rare_sound = SplEffect(opcode=174, target=2, power=1, timing=1, probability1=100,
                               probability2=90, resource="CAS_M07")

        def add_outcomes(spell: SplFile) -> SplFile:
            return map_tiers(spell, lambda _i, fx: insert_after(fx, 142, damage) + (rare_sound,))

        run = self.build(ally=add_outcomes, enemy=add_outcomes)
        self.assertEqual(tide_digests(run.output), reference_tides("vanilla"))
        self.assert_matches_model(run)


class TierShapeTests(ChaosTidesVariantTestCase):
    LEVELS = (1, 5, 9, 15, 21, 31)

    def test_sixth_header_and_different_minimum_levels(self) -> None:
        def six_tiers(spell: SplFile) -> SplFile:
            abilities = spell.abilities + (spell.abilities[-1],)
            return dataclasses.replace(
                spell,
                abilities=tuple(
                    dataclasses.replace(ability, required_level=level)
                    for ability, level in zip(abilities, self.LEVELS)
                ),
            )

        run = self.build(shape="live", ally=six_tiers, enemy=six_tiers, rerun_on_output=True)
        self.assert_matches_model(run)
        bands = [band(level) for level in self.LEVELS]
        self.assertEqual(bands, [0, 0, 1, 2, 3, 4])
        for tide, (ally, enemy) in enumerate(zip(TIDE_ALLY, TIDE_ENEMY), start=1):
            for name, sign in ((ally, 1), (enemy, -1)):
                spell = read_spl(run.output / f"{name}.SPL")
                self.assertEqual([a.required_level for a in spell.abilities], list(self.LEVELS))
                for level, ability in zip(self.LEVELS, spell.abilities):
                    stats = [e for e in ability.effects if e.opcode in STAT_OPS]
                    self.assertEqual(sorted(e.opcode for e in stats), sorted(TIDE_STATS[tide]))
                    want = {1: (2, 2, 2, 3, 3, 4), 2: (2, 2, 2, 3, 3, 4), 3: (1, 1, 1, 1, 2, 2)}[tide]
                    for effect in stats:
                        self.assertEqual(
                            effect.parameter1, want[self.LEVELS.index(level)] * sign,
                            f"{name} level {level}",
                        )
        self.assertIn("ally donor OHTMPS2D: 6 tiers", run.transcript)

    def test_tier_without_icon_and_pulse_still_builds(self) -> None:
        def strip(spell: SplFile) -> SplFile:
            return map_tiers(spell, lambda i, fx: without(fx, 142, 9) if i == 2 else fx)

        run = self.build(ally=strip, enemy=strip)
        self.assert_matches_model(run)
        for name in TIDE_FILES:
            spell = read_spl(run.output / f"{name}.SPL")
            for tier, ability in enumerate(spell.abilities):
                chrome = [e.opcode for e in ability.effects if e.opcode in (142, 9)]
                self.assertEqual(chrome, [] if tier == 2 else [142, 9], f"{name} tier {tier}")

    def test_tier_without_own_reset_gets_synthesized_trio(self) -> None:
        def drop_reset(spell: SplFile) -> SplFile:
            return map_tiers(spell, lambda i, fx: without(fx, 321) if i == 3 else fx)

        run = self.build(enemy=drop_reset)
        self.assert_matches_model(run)
        for name in TIDE_ENEMY:
            trio = read_spl(run.output / f"{name}.SPL").abilities[3].effects[:3]
            for effect, resref in zip(trio, TIDE_ENEMY):
                self.assertEqual(
                    effect.canonical(),
                    (321, 2, 1, 0, 0, 1, 3, 0, 100, 0, resref, 0, 0, 0, 0, 0),
                    "synthesized reset: target 2, power/resist from the tier's op54, timing 1",
                )
        self.assertIn("enemy donor OHTMPS2E: 5 tiers, 0 unowned records carried, 1 tiers with synthesized resets.", run.transcript)

    def test_tier_without_thac0_uses_the_donor_template(self) -> None:
        def reshape(spell: SplFile) -> SplFile:
            def change(index, fx):
                if index == 0:
                    return without(fx, 54)
                if index == 1:
                    return tuple(
                        dataclasses.replace(e, power=7, resist_dispel=2) if e.opcode == 54 else e
                        for e in fx
                    )
                return fx

            return map_tiers(spell, change)

        run = self.build(ally=reshape)
        self.assert_matches_model(run)
        spell = read_spl(run.output / "CBRCHT1D.SPL")
        for tier, ability in enumerate(spell.abilities):
            fields = {(e.power, e.resist_dispel) for e in ability.effects if e.opcode in ONSLAUGHT_OPS}
            self.assertEqual(fields, {(7, 2)} if tier in (0, 1) else {(1, 3)}, f"tier {tier}")


class RejectionTests(ChaosTidesVariantTestCase):
    def test_donor_without_any_thac0_template_fails(self) -> None:
        run = self.build(
            ally=lambda spell: map_tiers(spell, lambda _i, fx: without(fx, 54)),
            expect_success=False,
        )
        self.assertIn("OHTMPS2D.SPL carries no opcode 54 (THAC0) record in any tier", run.transcript)
        self.assertFalse(list(run.output.glob("CBRCHT*")), "preflight fails before any tide exists")

    def test_protection_against_a_tide_spell_fails(self) -> None:
        guard = SplEffect(opcode=206, target=2, power=1, duration=60, resource="CBRCHT2D")
        run = self.build(
            ally=lambda spell: map_tiers(spell, lambda i, fx: fx + (guard,) if i == 1 else fx),
            expect_success=False,
        )
        self.assertIn(
            "OHTMPS2D.SPL tier 1 record 15: opcode 206 protects against the tide spell CBRCHT2D",
            run.transcript,
        )

    def test_donor_without_ability_headers_fails(self) -> None:
        run = self.build(
            enemy=lambda spell: dataclasses.replace(spell, abilities=()), expect_success=False
        )
        self.assertIn("OHTMPS2E.SPL has no ability header", run.transcript)

    def test_out_of_bounds_tier_slice_fails(self) -> None:
        def build(root: Path) -> None:
            build_tides_fixture(root)
            data = bytearray((root / "OHTMPS2D.SPL").read_bytes())
            struct.pack_into("<H", data, 0x72 + 2 * 0x28 + 0x1E, 400)
            (root / "OHTMPS2D.SPL").write_bytes(bytes(data))

        run = self.run_component("tides", build, extra_args=TIDE_STRREFS, expect_success=False)
        self.assertIn("OHTMPS2D.SPL: header 2 opcode slice is out of bounds", run.transcript)


class VerifyHarnessRun:
    def __init__(self, spell: bytes, args: tuple[str, ...]):
        self.temporary = tempfile.TemporaryDirectory(prefix="cbr-tide-verify-")
        base = Path(self.temporary.name)
        source = base / "input" / "TIDE.SPL"
        source.parent.mkdir()
        source.write_bytes(spell)
        self.output = base / "output"
        self.output.mkdir()
        run_dir = base / "weidu-run"
        run_dir.mkdir()
        command = [
            str(WEIDU), str(VERIFY_HARNESS), "--nogame", "--force-install-list", "0",
            "--args", str(HOLY_TPA), "--args", str(TIDES_TPA),
            "--args", str(source), "--args", str(self.output),
        ]
        for value in args:
            command.extend(["--args", value])
        command.extend(["--no-exit-pause", "--quick-log"])
        self.process = subprocess.run(
            command, cwd=run_dir, capture_output=True, text=True, timeout=60, check=False
        )
        self.transcript = f"{self.process.stdout}\n{self.process.stderr}"
        self.succeeded = (
            (self.output / "CBR_TEST.OK").exists() and "SUCCESSFULLY INSTALLED" in self.transcript
        )
        self.temporary.cleanup()


class VerifierTests(ChaosTidesVariantTestCase):
    """cbr_tide_verify_spell accepts carried records and rejects leftovers."""

    ARGS = ("1", "1", "OHTMPS2D", *TIDE_ALLY)

    def _built_onslaught_ally(self) -> SplFile:
        run = self.build()
        return read_spl(run.output / "CBRCHT1D.SPL")

    def _verify(self, spell: SplFile, tier: int, change) -> VerifyHarnessRun:
        mutated = map_tiers(spell, lambda i, fx: change(fx) if i == tier else fx)
        return VerifyHarnessRun(spl_bytes(mutated), self.ARGS)

    def test_verifier_accepts_carried_records(self) -> None:
        spell = self._built_onslaught_ally()
        sibling_reset = SplEffect(opcode=321, target=2, power=1, timing=1, resource="CBRCHT2D")
        accepted = self._verify(
            spell, 0, lambda fx: fx[:3] + (SOUND, STATE_MARKER, FOREIGN_RESET, sibling_reset) + fx[3:]
        )
        self.assertTrue(accepted.succeeded, accepted.transcript)

    def test_verifier_rejects_leftovers(self) -> None:
        spell = self._built_onslaught_ally()
        tail = lambda record: (lambda fx: fx + (record,))  # noqa: E731

        def replace_first(opcode: int, **fields):
            def change(fx):
                index = next(i for i, e in enumerate(fx) if e.opcode == opcode)
                return fx[:index] + (dataclasses.replace(fx[index], **fields),) + fx[index + 1 :]

            return change

        onslaught_54 = next(e for e in spell.abilities[4].effects if e.opcode == 54)
        cases = {
            "partial probability window": (
                0, tail(dataclasses.replace(SOUND, probability1=50, probability2=0))
            ),
            "leftover per-target op139": (0, tail(SplEffect(opcode=139, target=2, parameter1=103226, timing=1))),
            "leftover self-stacking control": (
                2, tail(SplEffect(opcode=318, target=2, duration=60, resource="OHTMPS2D"))
            ),
            "protects against the tide spell CBRCHT3D": (
                1, tail(SplEffect(opcode=206, target=2, duration=60, resource="CBRCHT3D"))
            ),
            "opcode 18 is not part of tide 1's stat set": (
                3, tail(SplEffect(opcode=18, target=2, parameter1=5, duration=30))
            ),
            "tide stat opcode 54 appears more than once": (4, tail(onslaught_54)),
            "opcode 285 magnitude": (4, replace_first(285, parameter1=3)),
            "stat opcode 286 has duration 60": (4, replace_first(286, duration=60)),
            "reset 1 removes CBRCHT9D instead of CBRCHT2D": (
                0, lambda fx: fx[:1] + (dataclasses.replace(fx[1], resource="CBRCHT9D"),) + fx[2:]
            ),
            "chrome opcode 142 runs 60 s": (2, replace_first(142, duration=60)),
            "stats 2/3": (3, lambda fx: without(fx, 286)),
        }
        for message, (tier, change) in cases.items():
            with self.subTest(message=message):
                rejected = self._verify(spell, tier, change)
                self.assertFalse(rejected.succeeded)
                self.assertIn("NOT INSTALLED DUE TO ERRORS", rejected.transcript)
                self.assertIn(message, rejected.transcript)

    def test_verifier_checks_signed_enemy_magnitudes(self) -> None:
        run = self.build()
        spell = read_spl(run.output / "CBRCHT1E.SPL")
        args = ("1", "-1", "OHTMPS2E", *TIDE_ENEMY)
        accepted = VerifyHarnessRun(spl_bytes(spell), args)
        self.assertTrue(accepted.succeeded, accepted.transcript)

        def weaken(fx):
            return tuple(
                dataclasses.replace(e, parameter1=-3) if e.opcode == 54 else e for e in fx
            )

        mutated = map_tiers(spell, lambda i, fx: weaken(fx) if i == 4 else fx)
        rejected = VerifyHarnessRun(spl_bytes(mutated), args)
        self.assertFalse(rejected.succeeded)
        self.assertIn("tier 4: opcode 54 magnitude -3 != -4", rejected.transcript)


if __name__ == "__main__":
    unittest.main()
