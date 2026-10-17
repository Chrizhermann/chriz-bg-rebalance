"""Compatibility variants for component 301 (Emotion, Courage / Emotion, Hope).

Audit 2026-10-08 item 2: component 301 must validate only what its rebuild
and installer depend on, rebuild every ability header, and describe each
spell from its actual header.  These tests exercise valid alternate layouts
(casting time, range, school, several level headers, reordered records) on
both layers: the hermetic transformer harness and the public installer on a
synthetic BG2:EE game.  They also pin the canonical description text and the
remaining, deliberately kept rejections.
"""

from __future__ import annotations

import re
import struct
import tempfile
import unittest
from pathlib import Path

from tests import test_emotion_hope_courage_installer as installer_tests
from tests.ie_formats import SPL_ABILITY_SIZE, SplEffect, SplFile, read_spl
from tests.test_emotion_hope_courage import (
    COURAGE,
    COURAGE_CHROME,
    COURAGE_FOREIGN_MARKER,
    COURAGE_MECHANICS,
    COURAGE_STATE,
    EXTRA_FOREIGN_MARKER,
    FEAR,
    HOPE,
    HOPE_CHROME,
    HOPE_FOREIGN_MARKER,
    HOPE_MECHANICS,
    HOPE_STATE,
    HOPELESSNESS,
    HORROR,
    INNATE_HORROR,
    PRODUCTION_TPA,
    ROOT,
    SECOND_HEADER_PROJECTILE_DELTA,
    SECOND_HEADER_REQUIRED_LEVEL,
    SYMBOL,
    HarnessResult,
    _assert_exact_partition_coverage,
    _cleanse,
    _marker,
    _masked,
    _raw_tree,
    _transition,
    apply_beneficial_variant,
    build_fixture,
)
from tests.test_emotion_hope_courage_installer import (
    COURAGE_RESREF,
    COURAGE_SYMBOL,
    FEAR_RESREF,
    HOPE_RESREF,
    HOPE_SYMBOL,
    HORROR_RESREF,
    SYMBOL_HOPELESS_RESREF,
    GameOptions,
    _raw_tree as _override_tree,
    _tlk_string,
    _tlk_strings,
    spell_resref,
)


TRA = ROOT / "chriz-bg-rebalance" / "languages" / "english" / "setup.tra"

# The exact description text component 301 installed before descriptions
# were generated from the spell header.  Canonical spells must keep it byte
# for byte so existing installations reuse the same TLK strings.
CANONICAL_COURAGE_DESCRIPTION = (
    "Emotion, Courage\n(Enchantment/Charm)\n\nLevel: 4\nRange: 50 ft.\n"
    "Duration: 300 seconds (50 rounds)\nCasting Time: 4\n"
    "Area of Effect: 7-foot radius\nSaving Throw: None\n\n"
    "This spell fills allies in the area with steadfast courage. For the duration, "
    "affected creatures gain +1 to THAC0, +3 to damage, and +5 Hit Points. It also "
    "ends fear and morale failure, including effects caused by Emotion, Fear, Horror, "
    "and Innate Horror.\n\n"
    "A creature can be affected by only one of Emotion, Courage and Emotion, Hope at "
    "a time. Applying either spell removes the other."
)
CANONICAL_HOPE_DESCRIPTION = (
    "Emotion, Hope\n(Enchantment/Charm)\n\nLevel: 4\nRange: 50 ft.\n"
    "Duration: 300 seconds (50 rounds)\nCasting Time: 4\n"
    "Area of Effect: 7-foot radius\nSaving Throw: None\n\n"
    "This spell inspires allies in the area with supernatural hope. For the duration, "
    "affected creatures gain +2 morale, +2 to THAC0, +2 to damage, and +2 to all "
    "saving throws. It also ends effects caused by Emotion, Hopelessness and Symbol, "
    "Hopelessness.\n\n"
    "A creature can be affected by only one of Emotion, Courage and Emotion, Hope at "
    "a time. Applying either spell removes the other."
)

# BG2:EE's English school spellings for SPL header 0x25 values 1-8.
SCHOOL_NAMES = {
    1: "Abjuration",
    2: "Conjuration/Summoning",
    3: "Divination",
    4: "Enchantment/Charm",
    5: "Illusion/Phantasm",
    6: "Evocation",
    7: "Necromancy",
    8: "Alteration",
}
PRESENTATION_OPCODES = {61, 141, 142, 174, 215}

ERR_BENEFICIAL_TARGET = "CBR_EM_ERR_BENEFICIAL_TARGET"
ERR_BENEFICIAL_NO_ABILITY = "CBR_EM_ERR_BENEFICIAL_NO_ABILITY"
ERR_BENEFICIAL_PARTITION = "CBR_EM_ERR_BENEFICIAL_PARTITION"

# Non-text header bytes and non-partition ability bytes are preserved.
HEADER_TEXT_FIELDS = ((0x08, 0x10), (0x50, 0x54))
ABILITY_PARTITION_FIELDS = ((0x1E, 0x22),)


def expected_description(
    canonical: str,
    *,
    school: int = 4,
    level: int = 4,
    range_: int = 50,
    casting_time: int = 4,
) -> str:
    """Independent oracle for the generated description text."""
    text = canonical
    replacements = (
        ("(Enchantment/Charm)\n", f"({SCHOOL_NAMES[school]})\n" if school in SCHOOL_NAMES else ""),
        ("\nLevel: 4\n", f"\nLevel: {level}\n"),
        ("\nRange: 50 ft.\n", f"\nRange: {range_} ft.\n"),
        ("\nCasting Time: 4\n", f"\nCasting Time: {casting_time}\n"),
    )
    for old, new in replacements:
        if text.count(old) != 1:
            raise AssertionError((old, text))
        text = text.replace(old, new)
    return text


def expected_slice(
    donor: tuple[SplEffect, ...],
    *,
    courage: bool,
    own: str,
    other: str,
    cleanses: tuple[str, ...],
    state: int | None,
) -> tuple[SplEffect, ...]:
    """Independent oracle for one rebuilt recipient header (provider spell)."""
    effects = [_transition(own), _transition(other)]
    effects.extend(_cleanse(resource) for resource in cleanses)
    effects.extend(effect for effect in donor if effect.opcode in PRESENTATION_OPCODES)
    effects.extend(COURAGE_MECHANICS if courage else HOPE_MECHANICS)
    if state is not None:
        effects.append(_marker(state))
    effects.extend(
        effect
        for effect in donor
        if effect.opcode == 328 and (state is None or effect.parameter2 != state)
    )
    return tuple(effects)


def _canonical(effects: tuple[SplEffect, ...]) -> tuple[tuple[object, ...], ...]:
    return tuple(effect.canonical() for effect in effects)


def _owned_semantics(effects: tuple[SplEffect, ...]) -> tuple[tuple[object, ...], ...]:
    """Owned records of a rebuilt header: everything except presentation and
    foreign (non-owned) markers."""
    return tuple(
        effect.canonical()
        for effect in effects
        if effect.opcode not in PRESENTATION_OPCODES
        and not (effect.opcode == 328 and effect.parameter2 not in {
            COURAGE_STATE, HOPE_STATE, 211, 213,
        })
    )


class EmotionVariantTransformerTests(unittest.TestCase):
    """Hermetic file-backed transformation with valid alternate layouts."""

    def run_harness(
        self,
        *,
        courage_variant: tuple[str, ...] = (),
        hope_variant: tuple[str, ...] = (),
    ) -> tuple[HarnessResult, Path]:
        holder = tempfile.TemporaryDirectory(prefix="cbr-emotion-variant-")
        self.addCleanup(holder.cleanup)
        fixture = Path(holder.name) / "fixture"
        build_fixture(fixture)
        for resref, variant in ((COURAGE, courage_variant), (HOPE, hope_variant)):
            if variant:
                path = fixture / f"{resref}.SPL"
                path.write_bytes(apply_beneficial_variant(path.read_bytes(), variant))
        result = HarnessResult(fixture)
        self.addCleanup(result.cleanup)
        self.assertTrue(PRODUCTION_TPA.is_file())
        return result, fixture

    def assert_rebuilt_per_header(self, result: HarnessResult, fixture: Path) -> None:
        for resref, courage, own, other, cleanses, state in (
            (COURAGE, True, COURAGE, HOPE, (FEAR, HORROR, INNATE_HORROR), COURAGE_STATE),
            (HOPE, False, HOPE, COURAGE, (HOPELESSNESS, SYMBOL), HOPE_STATE),
        ):
            before_raw = (fixture / f"{resref}.SPL").read_bytes()
            after_raw = (result.output / f"{resref}.SPL").read_bytes()
            _assert_exact_partition_coverage(self, after_raw, SPL_ABILITY_SIZE)
            before = SplFile.from_bytes(before_raw)
            after = SplFile.from_bytes(after_raw)
            self.assertEqual(
                _masked(before.header_raw, *HEADER_TEXT_FIELDS),
                _masked(after.header_raw, *HEADER_TEXT_FIELDS),
                f"{resref} non-text header bytes",
            )
            self.assertEqual(
                [effect.to_bytes() for effect in before.casting_effects],
                [effect.to_bytes() for effect in after.casting_effects],
                f"{resref} casting-feature prefix",
            )
            self.assertEqual(len(before.abilities), len(after.abilities))
            for index, (old, new) in enumerate(zip(before.abilities, after.abilities, strict=True)):
                self.assertEqual(
                    _masked(old.raw, *ABILITY_PARTITION_FIELDS),
                    _masked(new.raw, *ABILITY_PARTITION_FIELDS),
                    f"{resref} header {index} non-effect fields",
                )
                expected = expected_slice(
                    old.effects,
                    courage=courage,
                    own=own,
                    other=other,
                    cleanses=cleanses,
                    state=state,
                )
                self.assertEqual(
                    _canonical(expected), _canonical(new.effects), f"{resref} header {index}"
                )
                # Retained presentation and foreign markers are byte-exact.
                self.assertEqual(
                    [effect.to_bytes() for effect in old.effects if effect.opcode in PRESENTATION_OPCODES],
                    [effect.to_bytes() for effect in new.effects if effect.opcode in PRESENTATION_OPCODES],
                    f"{resref} header {index} presentation bytes",
                )

    def test_single_field_variants_keep_their_field_and_the_canonical_mechanics(self) -> None:
        canonical, _fixture = self.run_harness()
        self.assertTrue(canonical.succeeded, canonical.transcript)
        canonical_tree = _raw_tree(canonical.output)
        for variant in ("casting_time_3", "range_60", "school_8"):
            with self.subTest(variant=variant):
                result, fixture = self.run_harness(
                    courage_variant=(variant,), hope_variant=(variant,)
                )
                self.assertTrue(result.succeeded, result.transcript)
                self.assertNotIn("CBR_EM_ERR", result.transcript)
                self.assert_rebuilt_per_header(result, fixture)
                tree = _raw_tree(result.output)
                self.assertEqual(set(canonical_tree), set(tree))
                for name, payload in tree.items():
                    if name in {f"{COURAGE}.SPL", f"{HOPE}.SPL"}:
                        # Identical owned rebuild; only the varied field differs.
                        self.assertEqual(
                            apply_beneficial_variant(canonical_tree[name], (variant,)),
                            payload,
                            f"{name} differs from the canonical rebuild beyond {variant}",
                        )
                        self.assertNotEqual(canonical_tree[name], payload)
                    else:
                        self.assertEqual(canonical_tree[name], payload, name)
                spell = read_spl(result.output / f"{HOPE}.SPL")
                ability_raw = spell.abilities[0].raw
                field = {
                    "casting_time_3": (struct.unpack_from("<H", ability_raw, 0x12)[0], 3),
                    "range_60": (struct.unpack_from("<H", ability_raw, 0x0E)[0], 60),
                    "school_8": (spell.header_raw[0x25], 8),
                }[variant]
                self.assertEqual(field[1], field[0])

    def test_every_level_header_is_rebuilt_with_its_own_presentation(self) -> None:
        result, fixture = self.run_harness(
            courage_variant=("two_headers",), hope_variant=("two_headers",)
        )
        self.assertTrue(result.succeeded, result.transcript)
        self.assert_rebuilt_per_header(result, fixture)
        for resref, foreign in ((COURAGE, COURAGE_FOREIGN_MARKER), (HOPE, HOPE_FOREIGN_MARKER)):
            spell = read_spl(result.output / f"{resref}.SPL")
            self.assertEqual(2, len(spell.abilities))
            first, second = spell.abilities
            self.assertEqual(_owned_semantics(first.effects), _owned_semantics(second.effects))
            self.assertEqual(SECOND_HEADER_REQUIRED_LEVEL, second.required_level)
            self.assertEqual(first.projectile + SECOND_HEADER_PROJECTILE_DELTA, second.projectile)
            self.assertEqual(0x5A, second.raw[0x01])
            self.assertEqual(3, struct.unpack_from("<H", second.raw, 0x22)[0])
            # The second header keeps its own presentation, not a copy of the first.
            self.assertNotEqual(
                [e.to_bytes() for e in first.effects if e.opcode in PRESENTATION_OPCODES],
                [e.to_bytes() for e in second.effects if e.opcode in PRESENTATION_OPCODES],
            )
            self.assertEqual(
                [foreign.parameter2],
                [e.parameter2 for e in first.effects if e.opcode == 328 and e.duration != 300],
            )
            self.assertEqual(
                [foreign.parameter2 + 100],
                [e.parameter2 for e in second.effects if e.opcode == 328 and e.duration != 300],
            )

    def test_reordered_presentation_and_foreign_markers_keep_donor_order(self) -> None:
        result, fixture = self.run_harness(
            courage_variant=("reordered",), hope_variant=("reordered",)
        )
        self.assertTrue(result.succeeded, result.transcript)
        self.assert_rebuilt_per_header(result, fixture)
        for resref, chrome, foreign in (
            (COURAGE, COURAGE_CHROME, COURAGE_FOREIGN_MARKER),
            (HOPE, HOPE_CHROME, HOPE_FOREIGN_MARKER),
        ):
            effects = read_spl(result.output / f"{resref}.SPL").abilities[0].effects
            self.assertEqual(
                _canonical(tuple(reversed(chrome))),
                _canonical(tuple(e for e in effects if e.opcode in PRESENTATION_OPCODES)),
            )
            self.assertEqual(
                [EXTRA_FOREIGN_MARKER.canonical(), foreign.canonical()],
                [
                    e.canonical()
                    for e in effects
                    if e.opcode == 328 and e.parameter2 not in {COURAGE_STATE, HOPE_STATE}
                ],
            )

    def test_combined_variants_repeat_application_is_byte_exact(self) -> None:
        combined = ("two_headers", "reordered", "casting_time_3", "range_60", "school_8")
        first, fixture = self.run_harness(courage_variant=combined, hope_variant=combined)
        self.assertTrue(first.succeeded, first.transcript)
        self.assert_rebuilt_per_header(first, fixture)
        second = HarnessResult(first.output)
        self.addCleanup(second.cleanup)
        self.assertTrue(second.succeeded, second.transcript)
        self.assertEqual(_raw_tree(first.output), _raw_tree(second.output))

    def assert_rejected(self, result: HarnessResult, token: str, *details: str) -> None:
        self.assertFalse(result.succeeded, "unsupported beneficial layout was accepted")
        self.assertIn("NOT INSTALLED DUE TO ERRORS", result.transcript)
        self.assertIn(token, result.transcript)
        self.assertNotIn(ERR_BENEFICIAL_PARTITION, result.transcript)
        for detail in details:
            self.assertIn(detail, result.transcript)
        self.assertFalse((result.output / "CBR_TEST.OK").exists())
        self.assertEqual({}, _raw_tree(result.output), "failed preflight did not roll back")

    def test_changed_target_type_is_a_controlled_failure_with_its_own_message(self) -> None:
        for courage_variant, hope_variant, resref, header in (
            (("target_1",), (), COURAGE, 0),
            ((), ("second_target_1",), HOPE, 1),
        ):
            with self.subTest(resref=resref, header=header):
                result, _fixture = self.run_harness(
                    courage_variant=courage_variant, hope_variant=hope_variant
                )
                self.assert_rejected(
                    result,
                    ERR_BENEFICIAL_TARGET,
                    f"{resref}.SPL ability header {header} has target type 1",
                    "point-targeted area delivery (target type 4)",
                )

    def test_beneficial_spell_without_ability_header_fails_clearly(self) -> None:
        result, _fixture = self.run_harness(hope_variant=("no_abilities",))
        self.assert_rejected(
            result, ERR_BENEFICIAL_NO_ABILITY, f"{HOPE}.SPL has no ability header"
        )


class EmotionVariantInstallerTests(unittest.TestCase):
    """The public installer on synthetic games with valid alternate layouts."""

    # Borrow the public-installer assertions.  The TestCase class itself is
    # not imported into this module, so unittest does not rerun its tests.
    make_game = installer_tests.EmotionHopeCourageInstallerTests.make_game
    assert_spell_ids_contract = installer_tests.EmotionHopeCourageInstallerTests.assert_spell_ids_contract
    assert_failed_atomically = installer_tests.EmotionHopeCourageInstallerTests.assert_failed_atomically
    assert_adverse_outputs = installer_tests.EmotionHopeCourageInstallerTests.assert_adverse_outputs
    assert_matches_transformer_oracle = installer_tests.EmotionHopeCourageInstallerTests.assert_matches_transformer_oracle
    target_scrolls = installer_tests.EmotionHopeCourageInstallerTests.target_scrolls
    assert_publication_delta = installer_tests.EmotionHopeCourageInstallerTests.assert_publication_delta

    def install(self, options: GameOptions, *, warnings: bool = False):
        game = self.make_game(options)
        process = game.run_install()
        transcript = game.transcript(process)
        if warnings:
            # WeiDU exits with status 3 after an install that warned.
            self.assertEqual(3, process.returncode, transcript)
            self.assertIn("INSTALLED WITH WARNINGS", transcript)
        else:
            self.assertEqual(0, process.returncode, transcript)
            self.assertIn("SUCCESSFULLY INSTALLED", transcript)
            self.assertNotIn("INSTALLED WITH WARNINGS", transcript)
        self.assertRegex(game.active_log(), r"(?m)#0\s+#301\b")
        game.assert_engine_inputs_stable(self)
        self.assert_spell_ids_contract(game)
        return game, transcript

    def descriptions(self, game) -> dict[str, str]:
        ids = game.effective_ids()
        found = {}
        for symbol in (COURAGE_SYMBOL, HOPE_SYMBOL):
            resref = spell_resref(ids.value(symbol), symbol)
            header = read_spl(game.override / f"{resref}.SPL").header_raw
            found[symbol] = _tlk_string(game.lang_tlk, struct.unpack_from("<i", header, 0x50)[0])
        return found

    def assert_provider_variant_semantics(self, game) -> None:
        """Both spells are installed providers here; check every header."""
        options = game.options
        cleanses = {
            COURAGE_RESREF: tuple(
                resref
                for resref in (FEAR_RESREF, HORROR_RESREF, game.innate_horror_resref)
                if resref != options.missing_adverse
            ),
            HOPE_RESREF: tuple(
                resref
                for resref in (game.hopelessness_resref, SYMBOL_HOPELESS_RESREF)
                if resref != options.missing_adverse
            ),
        }
        for resref, courage, other, state in (
            (COURAGE_RESREF, True, HOPE_RESREF, 211),
            (HOPE_RESREF, False, COURAGE_RESREF, 213),
        ):
            before = SplFile.from_bytes(game.original_bytes(resref, "SPL"))
            after = read_spl(game.override / f"{resref}.SPL")
            self.assertEqual(
                _masked(before.header_raw, *HEADER_TEXT_FIELDS),
                _masked(after.header_raw, *HEADER_TEXT_FIELDS),
                f"{resref} non-text header bytes",
            )
            self.assertEqual(len(before.abilities), len(after.abilities))
            for index, (old, new) in enumerate(zip(before.abilities, after.abilities, strict=True)):
                self.assertEqual(
                    _masked(old.raw, *ABILITY_PARTITION_FIELDS),
                    _masked(new.raw, *ABILITY_PARTITION_FIELDS),
                    f"{resref} header {index} non-effect fields",
                )
                self.assertEqual(
                    _canonical(
                        expected_slice(
                            old.effects,
                            courage=courage,
                            own=resref,
                            other=other,
                            cleanses=cleanses[resref],
                            state=state,
                        )
                    ),
                    _canonical(new.effects),
                    f"{resref} header {index}",
                )
            if len(after.abilities) > 1:
                owned = {_owned_semantics(ability.effects) for ability in after.abilities}
                self.assertEqual(1, len(owned), f"{resref} headers differ in owned semantics")
        self.assert_adverse_outputs(game, COURAGE_RESREF, HOPE_RESREF)
        self.assert_matches_transformer_oracle(game, COURAGE_RESREF, HOPE_RESREF)
        scrolls = self.target_scrolls(game, {COURAGE_RESREF, HOPE_RESREF})
        self.assert_publication_delta(game, {COURAGE_RESREF, HOPE_RESREF}, scrolls)

    def test_canonical_descriptions_keep_the_previous_exact_text(self) -> None:
        for symbols in ("both", "neither"):
            with self.subTest(symbols=symbols):
                game, _transcript = self.install(GameOptions(symbols=symbols, markers="present"))
                self.assertEqual(
                    {
                        COURAGE_SYMBOL: CANONICAL_COURAGE_DESCRIPTION,
                        HOPE_SYMBOL: CANONICAL_HOPE_DESCRIPTION,
                    },
                    self.descriptions(game),
                )
                strings = _tlk_strings(game.lang_tlk)
                self.assertEqual(
                    ["", "Emotion, Courage", CANONICAL_COURAGE_DESCRIPTION,
                     "Emotion, Hope", CANONICAL_HOPE_DESCRIPTION],
                    strings[:5],
                )
                self.assertFalse(any("%cbr_em_desc" in value for value in strings))

    def test_casting_time_range_and_school_variants_install_with_true_descriptions(self) -> None:
        canonical, _ = self.install(GameOptions(symbols="both", markers="present"))
        canonical_tree = _override_tree(canonical.override)
        cases = (
            (
                GameOptions(symbols="both", hope_variant=("casting_time_3",)),
                CANONICAL_COURAGE_DESCRIPTION,
                expected_description(CANONICAL_HOPE_DESCRIPTION, casting_time=3),
            ),
            (
                GameOptions(symbols="both", courage_variant=("range_60",)),
                expected_description(CANONICAL_COURAGE_DESCRIPTION, range_=60),
                CANONICAL_HOPE_DESCRIPTION,
            ),
            (
                GameOptions(
                    symbols="both", courage_variant=("school_8",), hope_variant=("school_8",)
                ),
                expected_description(CANONICAL_COURAGE_DESCRIPTION, school=8),
                expected_description(CANONICAL_HOPE_DESCRIPTION, school=8),
            ),
        )
        for options, courage_text, hope_text in cases:
            with self.subTest(courage=options.courage_variant, hope=options.hope_variant):
                game, _transcript = self.install(options)
                self.assert_provider_variant_semantics(game)
                self.assertEqual(
                    {COURAGE_SYMBOL: courage_text, HOPE_SYMBOL: hope_text},
                    self.descriptions(game),
                )
                # Same owned rebuild as the canonical install; only the varied
                # header field (and the description strref) may differ.
                for resref, variant in (
                    (COURAGE_RESREF, options.courage_variant),
                    (HOPE_RESREF, options.hope_variant),
                ):
                    name = f"{resref}.SPL"
                    expected = canonical_tree[name]
                    if variant:
                        expected = apply_beneficial_variant(expected, variant)
                    self.assertEqual(
                        _masked(expected, (0x50, 0x54)),
                        _masked(_override_tree(game.override)[name], (0x50, 0x54)),
                        name,
                    )

    def test_two_level_headers_install_with_identical_owned_semantics(self) -> None:
        game, _transcript = self.install(
            GameOptions(
                symbols="both",
                courage_variant=("two_headers",),
                hope_variant=("two_headers", "reordered"),
            )
        )
        self.assert_provider_variant_semantics(game)
        for resref in (COURAGE_RESREF, HOPE_RESREF):
            spell = read_spl(game.override / f"{resref}.SPL")
            self.assertEqual(2, len(spell.abilities))
            self.assertEqual(SECOND_HEADER_REQUIRED_LEVEL, spell.abilities[1].required_level)
        self.assertEqual(
            {
                COURAGE_SYMBOL: CANONICAL_COURAGE_DESCRIPTION,
                HOPE_SYMBOL: CANONICAL_HOPE_DESCRIPTION,
            },
            self.descriptions(game),
        )

    def test_disagreeing_headers_describe_the_first_header_and_warn(self) -> None:
        game, transcript = self.install(
            GameOptions(symbols="both", hope_variant=("two_headers_disagree",)),
            warnings=True,
        )
        self.assert_provider_variant_semantics(game)
        second = read_spl(game.override / f"{HOPE_RESREF}.SPL").abilities[1]
        self.assertEqual(
            (70, 2),
            (
                struct.unpack_from("<H", second.raw, 0x0E)[0],
                struct.unpack_from("<H", second.raw, 0x12)[0],
            ),
        )
        self.assertEqual(CANONICAL_HOPE_DESCRIPTION, self.descriptions(game)[HOPE_SYMBOL])
        self.assertRegex(
            transcript,
            rf"WARNING: the ability headers of {HOPE_RESREF}\.SPL do not share one range "
            r"and casting time; its installed description states the first header's "
            r"range 50 and casting time 4\.",
        )

    def test_unknown_school_omits_the_school_line_and_warns(self) -> None:
        game, transcript = self.install(
            GameOptions(symbols="both", courage_variant=("school_11",)), warnings=True
        )
        self.assert_provider_variant_semantics(game)
        self.assertEqual(
            {
                COURAGE_SYMBOL: expected_description(CANONICAL_COURAGE_DESCRIPTION, school=11),
                HOPE_SYMBOL: CANONICAL_HOPE_DESCRIPTION,
            },
            self.descriptions(game),
        )
        self.assertTrue(self.descriptions(game)[COURAGE_SYMBOL].startswith("Emotion, Courage\n\nLevel: 4\n"))
        self.assertRegex(
            transcript,
            rf"WARNING: {COURAGE_RESREF}\.SPL has spell school 11, which is not one of the "
            r"eight standard BG2:EE schools; its installed description omits the school line\.",
        )

    def test_changed_target_type_fails_atomically_with_a_clear_message(self) -> None:
        for options, resref, header in (
            (GameOptions(symbols="both", courage_variant=("target_1",)), COURAGE_RESREF, 0),
            (GameOptions(symbols="both", hope_variant=("second_target_1",)), HOPE_RESREF, 1),
        ):
            with self.subTest(resref=resref):
                game = self.make_game(options)
                process = game.run_install()
                self.assert_failed_atomically(game, process)
                transcript = game.transcript(process)
                self.assertIn(ERR_BENEFICIAL_TARGET, transcript)
                self.assertRegex(
                    transcript,
                    rf"(?i){resref}\.SPL ability header {header} has target type 1",
                )
                self.assertNotIn(ERR_BENEFICIAL_PARTITION, transcript)

    def test_late_failure_after_variant_descriptions_leaves_files_and_tlk_untouched(self) -> None:
        # Hope is a valid multi-header variant whose description is generated
        # after allocation; the newly allocated Courage then hits a conflicting
        # STATDESC row before any string is resolved.
        variant = ("two_headers", "casting_time_3", "range_60", "school_8", "reordered")
        game = self.make_game(
            GameOptions(
                symbols="hope_only",
                hope_variant=variant,
                statdesc_layout="courage_d_collision",
            )
        )
        process = game.run_install()
        self.assert_failed_atomically(game, process)
        self.assertRegex(game.transcript(process), r"(?i)status BAM.*conflicting STATDESC")

    def test_variant_force_reinstall_is_byte_stable_and_uninstall_restores(self) -> None:
        game, _transcript = self.install(
            GameOptions(
                symbols="both",
                courage_variant=("two_headers", "range_60"),
                hope_variant=("casting_time_3", "school_8", "reordered"),
            )
        )
        first_override = _override_tree(game.override)
        first_tlk = game.lang_tlk.read_bytes()
        self.assertEqual(
            {
                COURAGE_SYMBOL: expected_description(CANONICAL_COURAGE_DESCRIPTION, range_=60),
                HOPE_SYMBOL: expected_description(
                    CANONICAL_HOPE_DESCRIPTION, school=8, casting_time=3
                ),
            },
            self.descriptions(game),
        )
        second = game.run_reinstall()
        self.assertEqual(0, second.returncode, game.transcript(second))
        self.assertIn("SUCCESSFULLY INSTALLED", game.transcript(second))
        self.assertEqual(first_override, _override_tree(game.override))
        self.assertEqual(first_tlk, game.lang_tlk.read_bytes())
        uninstall = game.run_uninstall()
        self.assertEqual(0, uninstall.returncode, game.transcript(uninstall))
        self.assertNotRegex(game.active_log(), r"(?m)#0\s+#301\b")
        self.assertEqual(game.pre_override, _override_tree(game.override))
        self.assertEqual(first_tlk, game.lang_tlk.read_bytes())
        game.assert_engine_inputs_stable(self)


class EmotionDescriptionSourceTests(unittest.TestCase):
    def test_translation_uses_header_placeholders_and_standard_school_names(self) -> None:
        tra = TRA.read_text(encoding="utf-8")
        for ref in (3012, 3014):
            body = re.search(rf"(?ms)^@{ref}\s*=\s*~(?P<body>[^~]*)~", tra)
            self.assertIsNotNone(body, ref)
            text = body.group("body")  # type: ignore[union-attr]
            for placeholder in (
                "%cbr_em_desc_school_line%",
                "Level: %cbr_em_desc_level%",
                "Range: %cbr_em_desc_range% ft.",
                "Casting Time: %cbr_em_desc_casting_time%",
            ):
                self.assertEqual(1, text.count(placeholder), (ref, placeholder))
            self.assertNotIn("(Enchantment/Charm)", text)
            self.assertIn("Area of Effect: 7-foot radius", text)
        for school, name in SCHOOL_NAMES.items():
            self.assertRegex(tra, rf"(?m)^@{3030 + school}\s*=\s*~{re.escape(name)}~")


if __name__ == "__main__":
    unittest.main()
