"""Variation tests for the C0PR#C4.SPL grant completion (component 400).

Owned behavior: every ability header whose indexed effect slice carries
Artisan's axe grant (opcode 326 -> C0PR#92 plus opcode 233 proficiency 92)
also carries a longsword gate (326 -> C0PR#90) and longsword/crossbow pips
(233 proficiency 90/103), cloned from that header's own axe records and
inserted at the end of that header's slice. Every pre-existing record stays
byte-identical; only positions move. Casting-feature storage position, extra
headers, extra visual/marker records, and record order are not assumed.
"""

from __future__ import annotations

import dataclasses
import struct
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import SplEffect, read_spl
from tests.test_tempus_completion import (
    LS_PERM_STAT,
    TempusCompletionTestCase,
    _axe_gate,
    _pip,
    build_training_fixture,
)
from tests.test_tempus_completion_installer import CompletionGame
from tests.test_tempus_holy_power import _raw_file_tree

SPL_HEADER_SIZE = 0x72
ABILITY_SIZE = 0x28
EFFECT_SIZE = 0x30
GRANT = "C0PR#C4.SPL"


# ---------------------------------------------------------------------------
# Raw SPL layout builder (arbitrary slice placement)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Header:
    level: int
    first: int
    count: int


def build_spl(
    effects: list[SplEffect],
    headers: list[Header],
    casting: tuple[int, int] = (0, 0),
) -> bytes:
    header = bytearray(SPL_HEADER_SIZE)
    header[:8] = b"SPL V1  "
    ability_offset = SPL_HEADER_SIZE
    effect_offset = ability_offset + ABILITY_SIZE * len(headers)
    struct.pack_into("<IHIHH", header, 0x64, ability_offset, len(headers), effect_offset, *casting)
    abilities = bytearray()
    for entry in headers:
        raw = bytearray(ABILITY_SIZE)
        raw[0x0C] = 1
        struct.pack_into("<H", raw, 0x10, entry.level)
        raw[0x1C] = 1
        struct.pack_into("<HH", raw, 0x1E, entry.count, entry.first)
        struct.pack_into("<H", raw, 0x26, 1)
        abilities.extend(raw)
    return bytes(header) + bytes(abilities) + b"".join(effect.to_bytes() for effect in effects)


def slices(raw: bytes) -> tuple[list[bytes], list[list[bytes]]]:
    """(casting records, per-header records) as raw 0x30-byte blobs; asserts an exact partition."""
    ability_offset, ability_count, effect_offset, casting_first, casting_count = struct.unpack_from(
        "<IHIHH", raw, 0x64
    )
    total = (len(raw) - effect_offset) // EFFECT_SIZE
    assert (len(raw) - effect_offset) % EFFECT_SIZE == 0
    references = [0] * total
    records = [raw[effect_offset + i * EFFECT_SIZE : effect_offset + (i + 1) * EFFECT_SIZE] for i in range(total)]
    for index in range(casting_first, casting_first + casting_count):
        references[index] += 1
    headers = []
    for header in range(ability_count):
        count, first = struct.unpack_from("<HH", raw, ability_offset + header * ABILITY_SIZE + 0x1E)
        for index in range(first, first + count):
            references[index] += 1
        headers.append(records[first : first + count])
    assert references == [1] * total, f"effect table is not an exact partition: {references}"
    return records[casting_first : casting_first + casting_count], headers


def gate90_from(gate: SplEffect) -> bytes:
    data = bytearray(gate.to_bytes())
    data[0x14:0x1C] = b"C0PR#90\0"
    return bytes(data)


def pip_from(pip: SplEffect, proficiency: int) -> bytes:
    data = bytearray(pip.to_bytes())
    struct.pack_into("<i", data, 0x08, proficiency)
    return bytes(data)


def completion(gate: SplEffect, pip: SplEffect) -> list[bytes]:
    return [gate90_from(gate), pip_from(pip, 90), pip_from(pip, 103)]


def _visual(resource: str = "SPFLESHS") -> SplEffect:
    return SplEffect(opcode=215, target=1, parameter2=1, timing=1, duration=2, resource=resource)


def _marker() -> SplEffect:
    return SplEffect(opcode=206, target=1, parameter1=-1, timing=9, resource="C0PR#C4")


def _sound() -> SplEffect:
    return SplEffect(opcode=174, target=1, timing=1, resource="EFF_M01")


GATE = _axe_gate()
PIP = _pip(92)
GATE90 = SplEffect(opcode=326, target=1, power=0, timing=0, resource="C0PR#90")


class WeaponTrainingVariantTests(TempusCompletionTestCase):
    def run_grant(self, raw: bytes, *, expect_success: bool = True, rerun: bool = True):
        def build(root: Path) -> None:
            build_training_fixture(root)
            (root / GRANT).write_bytes(raw)

        return self.run_component(
            "training",
            build,
            extra_args=(str(LS_PERM_STAT),),
            expect_success=expect_success,
            rerun_on_output=rerun and expect_success,
        )

    def assert_completed(self, raw: bytes, additions: dict[int, list[bytes]]) -> bytes:
        """Every original record stays byte-identical in its own slice; only `additions` follow it."""
        run = self.run_grant(raw)
        after = (run.output / GRANT).read_bytes()
        casting_before, headers_before = slices(raw)
        casting_after, headers_after = slices(after)
        self.assertEqual(casting_before, casting_after, "casting features must stay byte-identical")
        self.assertEqual(len(headers_before), len(headers_after))
        self.assertEqual(raw[:0x64], after[:0x64], "SPL header fields outside the tables changed")
        for index, (before, current) in enumerate(zip(headers_before, headers_after)):
            self.assertEqual(before, current[: len(before)], f"header {index} lost or changed a record")
            self.assertEqual(additions.get(index, []), current[len(before):], f"header {index} additions")
        spell_before = read_spl(run.fixture / GRANT)
        spell_after = read_spl(run.output / GRANT)
        for before, current in zip(spell_before.abilities, spell_after.abilities):
            self.assertEqual(before.raw[:0x1E], current.raw[:0x1E])
            self.assertEqual(before.raw[0x22:], current.raw[0x22:])
        return after

    # -- storage layouts -----------------------------------------------------

    def test_casting_first_layout(self) -> None:
        raw = build_spl([_sound(), _visual(), GATE, PIP], [Header(1, 2, 2)], casting=(0, 2))
        self.assert_completed(raw, {0: completion(GATE, PIP)})

    def test_casting_features_stored_after_the_abilities(self) -> None:
        raw = build_spl([GATE, PIP, _sound(), _visual()], [Header(1, 0, 2)], casting=(2, 2))
        after = self.assert_completed(raw, {0: completion(GATE, PIP)})
        self.assertEqual((5, 2), struct.unpack_from("<HH", after, 0x6E), "casting slice must shift")

    def test_extra_visual_and_marker_records_in_the_grant_slice(self) -> None:
        effects = [_visual(), GATE, _marker(), PIP, _visual("SPROTECT")]
        raw = build_spl(effects, [Header(1, 0, 5)])
        self.assert_completed(raw, {0: completion(GATE, PIP)})

    def test_pip_before_gate(self) -> None:
        raw = build_spl([PIP, GATE], [Header(1, 0, 2)])
        self.assert_completed(raw, {0: completion(GATE, PIP)})

    # -- several headers ----------------------------------------------------

    def test_two_level_headers_both_carry_and_clone_their_own_templates(self) -> None:
        gate_b = dataclasses.replace(GATE, power=3, parameter2=7)
        pip_b = dataclasses.replace(PIP, parameter1=2, probability1=90)
        effects = [GATE, PIP, _sound(), _marker(), pip_b, gate_b]
        raw = build_spl(effects, [Header(1, 0, 2), Header(10, 3, 3)], casting=(2, 1))
        after = self.assert_completed(raw, {0: completion(GATE, PIP), 1: completion(gate_b, pip_b)})
        self.assertEqual((5, 1), struct.unpack_from("<HH", after, 0x6E))

    def test_header_without_the_axe_pair_stays_unchanged(self) -> None:
        other_pip = _pip(95)
        effects = [GATE, PIP, other_pip, _visual(), GATE]
        # Header 1 has only an axe gate (no pip), header 2 only an unrelated pip.
        raw = build_spl(effects, [Header(1, 0, 2), Header(5, 2, 2), Header(9, 4, 1)])
        self.assert_completed(raw, {0: completion(GATE, PIP)})

    def test_carrying_header_after_a_non_carrying_one(self) -> None:
        effects = [_visual(), GATE, PIP]
        raw = build_spl(effects, [Header(1, 0, 1), Header(2, 1, 2)])
        self.assert_completed(raw, {1: completion(GATE, PIP)})

    # -- existing grant records ---------------------------------------------

    def test_already_complete_nonstandard_layout_is_byte_identical(self) -> None:
        effects = [
            _sound(),
            _pip(103), GATE, _visual(), _pip(90), PIP, GATE90,
            GATE, PIP, GATE90, _pip(90), _pip(103),
        ]
        raw = build_spl(effects, [Header(1, 1, 6), Header(12, 7, 5)], casting=(0, 1))
        run = self.run_grant(raw)
        self.assertEqual(raw, (run.output / GRANT).read_bytes())

    def test_partially_present_grants_are_kept_and_never_duplicated(self) -> None:
        effects = [GATE, PIP, _pip(90), _pip(90), _pip(103)]
        raw = build_spl(effects, [Header(1, 0, 5)])
        self.assert_completed(raw, {0: [gate90_from(GATE)]})

    def test_identical_duplicate_axe_templates_are_accepted(self) -> None:
        raw = build_spl([GATE, PIP, GATE, PIP], [Header(1, 0, 4)])
        self.assert_completed(raw, {0: completion(GATE, PIP)})

    def test_differing_duplicates_are_irrelevant_when_nothing_must_be_cloned(self) -> None:
        effects = [GATE, dataclasses.replace(GATE, power=2), PIP, dataclasses.replace(PIP, parameter1=3),
                   GATE90, _pip(90), _pip(103)]
        raw = build_spl(effects, [Header(1, 0, 7)])
        run = self.run_grant(raw)
        self.assertEqual(raw, (run.output / GRANT).read_bytes())

    # -- honest failures -----------------------------------------------------

    def test_differing_duplicate_axe_gates_fail_as_ambiguous(self) -> None:
        effects = [GATE, PIP, dataclasses.replace(GATE, power=2)]
        raw = build_spl([_sound(), *effects], [Header(1, 1, 3)], casting=(0, 1))
        run = self.run_grant(raw, expect_success=False)
        self.assertIn("C0PR#C4.SPL ability header 0 (level 1) has several axe permission gates", run.transcript)

    def test_differing_duplicate_axe_pips_fail_as_ambiguous(self) -> None:
        effects = [GATE, PIP, GATE90, dataclasses.replace(PIP, timing=0)]
        raw = build_spl(effects, [Header(3, 0, 4)])
        run = self.run_grant(raw, expect_success=False)
        self.assertIn("C0PR#C4.SPL ability header 0 (level 3) has several axe pips", run.transcript)

    def test_axe_pair_split_across_headers_has_no_carrier(self) -> None:
        raw = build_spl([GATE, PIP], [Header(1, 0, 1), Header(2, 1, 1)])
        run = self.run_grant(raw, expect_success=False)
        self.assertIn("no ability header carries Artisan's axe permission gate", run.transcript)

    def test_overlapping_slices_are_still_rejected(self) -> None:
        raw = build_spl([GATE, PIP], [Header(1, 0, 2), Header(2, 1, 1)])
        run = self.run_grant(raw, expect_success=False)
        self.assertIn("exact nonoverlapping partition", run.transcript)


class WeaponTrainingVariantInstallerTests(unittest.TestCase):
    def test_component_400_completes_a_casting_first_two_header_grant_and_uninstalls(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-wt-variant-game-")
        self.addCleanup(temporary.cleanup)
        game = CompletionGame(temporary)
        raw = build_spl(
            [_sound(), _visual(), GATE, PIP, _marker(), PIP, GATE],
            [Header(1, 2, 2), Header(10, 4, 3)],
            casting=(0, 2),
        )
        (game.override / GRANT).write_bytes(raw)
        game.pre_override = _raw_file_tree(game.override)

        install = game.run("--force-install-list", 400)
        self.assertIn("SUCCESSFULLY INSTALLED", game.transcript(install), game.transcript(install))
        after = (game.override / GRANT).read_bytes()
        casting_before, headers_before = slices(raw)
        casting_after, headers_after = slices(after)
        self.assertEqual(casting_before, casting_after)
        for before, current in zip(headers_before, headers_after):
            self.assertEqual(before, current[: len(before)])
            self.assertEqual(completion(GATE, PIP), current[len(before):])

        uninstall = game.run("--force-uninstall-list", 400)
        self.assertNotIn("NOT UNINSTALLED", game.transcript(uninstall), game.transcript(uninstall))
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))


if __name__ == "__main__":
    unittest.main()
