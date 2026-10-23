"""Exercise the production WeiDU classifier against bounded SPL delegation graphs.

All fixtures and WeiDU writes stay in disposable directories.  These synthetic
graphs complement the captured installation resources: malformed graph cases
must fail transactionally, while recognized doubling needs no APR bridge.
"""

from __future__ import annotations

import dataclasses
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Callable

from tests.ie_formats import SplAbility, SplEffect, SplFile, make_spl, read_spl, write_spl
from tests.test_tempus_holy_power import (
    APR_CONDITION_RESREFS,
    APR_HELPER_RESREFS,
    HARNESS,
    PHASE_COMPONENT,
    PRODUCTION_TPA,
    WEIDU,
    Fixture,
    HarnessResult,
    _raw_file_tree,
    _rerun_harness,
    build_fixture,
)


CHILD = "FORCHILD"
GRANDCHILD = "FORGRAND"
FEEDBACK = "FORMSG"
MODES = ("auto", "force_double", "force_additive")
FixtureMutation = Callable[[Fixture], None]


def _edge(resource: str = CHILD, **changes: object) -> SplEffect:
    # The CEBG wrapper's observed opcode-146 delivery profile.  Parameter2=1
    # selects instant casting at caster level, so every child header matters.
    return dataclasses.replace(
        SplEffect(
            opcode=146, target=2, power=6, parameter1=0, parameter2=1,
            timing=1, resist_dispel=3, duration=0, resource=resource,
        ),
        **changes,
    )


def _double(opcode: int = 16, **changes: object) -> SplEffect:
    return dataclasses.replace(
        SplEffect(
            opcode=opcode, target=2, power=6, parameter2=1,
            timing=0, resist_dispel=3, duration=90,
        ),
        **changes,
    )


def _marker() -> SplEffect:
    return SplEffect(
        opcode=328, target=2, parameter2=45, timing=0,
        resist_dispel=3, duration=90,
    )


def _spell(*effects: SplEffect, headers: int = 3) -> SplFile:
    return make_spl(tuple(
        SplAbility(
            required_level=level, target=1, projectile=1,
            effects=tuple(
                dataclasses.replace(effect, duration=effect.duration + index * 6)
                if effect.timing == 0 and effect.duration > 0 else effect
                for effect in effects
            ),
        )
        for index, level in enumerate((1, 13, 20)[:headers])
    ))


def _write_delegation(
    fixture: Fixture,
    *,
    opcode: int = 16,
    markers: bool = False,
    edge: SplEffect | None = None,
    child: SplFile | None = None,
) -> None:
    parent_effects = (edge or _edge(),) + ((_marker(),) if markers else ())
    child_effects = (_double(opcode),) + ((_marker(),) if markers else ())
    write_spl(fixture.root / f"{fixture.haste_resref}.SPL", _spell(*parent_effects))
    write_spl(fixture.root / f"{CHILD}.SPL", child or _spell(*child_effects))


class TempusHasteDelegationTests(unittest.TestCase):
    def run_case(
        self,
        mutate: FixtureMutation | None = None,
        *,
        mode: str = "auto",
        variant: str = "doubling",
        phase: str = "full",
        alternate_ids: bool = False,
    ) -> HarnessResult:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-tempus-delegation-")
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        fixture = build_fixture(
            base / "fixture", variant,
            divine_id=1388 if alternate_ids else 1499,
            haste_id=2788 if alternate_ids else 2699,
        )
        if mutate is not None:
            mutate(fixture)
        before_source = _raw_file_tree(fixture.root)
        run_dir = base / "weidu-run"
        run_dir.mkdir()
        output = base / "output"
        output.mkdir()
        # Include both an unrelated file and an overwritten resource.  A failed
        # COPY-based harness must restore their exact bytes, not merely empty
        # a freshly created output directory.
        (output / "ROLLBACK.KEEP").write_bytes(b"foreign output must survive\r\n")
        (output / f"{fixture.haste_resref}.SPL").write_bytes(b"previous resource bytes")
        before_output = _raw_file_tree(output)
        command = [
            str(WEIDU), str(HARNESS), "--nogame", "--force-install-list",
            PHASE_COMPONENT[phase], "--args", str(PRODUCTION_TPA),
            "--args", str(fixture.root), "--args", str(output),
            "--args", mode, "--args", fixture.divine_resref,
            "--args", fixture.haste_resref, "--no-exit-pause", "--quick-log",
        ]
        process = subprocess.run(
            command, cwd=run_dir, capture_output=True, text=True,
            timeout=45, check=False,
        )
        result = HarnessResult(
            temporary=temporary, fixture=fixture, output=output, run_dir=run_dir,
            mode=mode, variant=variant, process=process,
            source_snapshot=before_source,
        )
        self.assertEqual(before_source, _raw_file_tree(fixture.root), result.transcript)
        if not result.succeeded:
            self.assertIn("NOT INSTALLED DUE TO ERRORS", result.transcript)
            self.assertEqual(before_output, _raw_file_tree(output), result.transcript)
        return result

    def assert_accepted(self, result: HarnessResult) -> None:
        self.assertTrue(result.succeeded, result.transcript)

    def assert_rejected(self, result: HarnessResult) -> None:
        self.assertFalse(result.succeeded, "unsafe delegation was accepted")
        self.assertIn(result.fixture.haste_resref, result.transcript.upper())
        self.assertRegex(result.transcript, r"(?i)CBR.*(?:HASTE|SPL V1|DELEGAT)")

    def test_direct_semantics_with_and_without_scs_markers(self) -> None:
        for variant, forced, additive in (
            ("additive", "force_additive", True),
            ("doubling", "force_double", False),
            ("doubling317", "force_double", False),
        ):
            for markers in (False, True):
                for mode in ("auto", forced):
                    with self.subTest(variant=variant, markers=markers, mode=mode):
                        def mutate(fixture: Fixture) -> None:
                            donor = (SplEffect(
                                opcode=1, target=2, power=6, parameter1=1,
                                timing=0, resist_dispel=3, duration=90,
                            ) if additive else _double(317 if variant == "doubling317" else 16))
                            write_spl(
                                fixture.root / f"{fixture.haste_resref}.SPL",
                                _spell(donor, *((_marker(),) if markers else ())),
                            )
                        self.assert_accepted(self.run_case(mutate, variant=variant, mode=mode))

    def test_direct_force_mode_mismatches_restore_previous_output(self) -> None:
        for variant, mode in (("additive", "force_double"), ("doubling", "force_additive")):
            with self.subTest(variant=variant, mode=mode):
                self.assert_rejected(self.run_case(variant=variant, mode=mode))

    def test_single_hop_doubling_preserves_sources_and_has_no_apr_bridge(self) -> None:
        for opcode in (16, 317):
            for markers in (False, True):
                for mode in ("auto", "force_double"):
                    with self.subTest(opcode=opcode, markers=markers, mode=mode):
                        result = self.run_case(
                            lambda fixture: _write_delegation(fixture, opcode=opcode, markers=markers),
                            mode=mode, alternate_ids=True,
                        )
                        self.assert_accepted(result)
                        for resref in (result.fixture.haste_resref, CHILD):
                            self.assertEqual(
                                (result.fixture.root / f"{resref}.SPL").read_bytes(),
                                (result.output / f"{resref}.SPL").read_bytes(),
                            )
                        output_names = {name.upper() for name in _raw_file_tree(result.output)}
                        self.assertTrue(output_names.isdisjoint(
                            {f"{name}.SPL" for name in APR_HELPER_RESREFS}
                            | {f"{name}.EFF" for name in APR_CONDITION_RESREFS}
                        ))

    def test_delegated_doubling_is_byte_identical_on_second_application(self) -> None:
        first = self.run_case(_write_delegation)
        self.assert_accepted(first)
        second = _rerun_harness(first)
        self.addCleanup(second.temporary.cleanup)
        self.assert_accepted(second)
        self.assertEqual(_raw_file_tree(first.output), _raw_file_tree(second.output))
        self.assertEqual(second.source_snapshot, _raw_file_tree(second.fixture.root))

    def test_forced_additive_cannot_override_delegated_doubling(self) -> None:
        self.assert_rejected(self.run_case(_write_delegation, mode="force_additive"))

    def test_unsafe_opcode146_delivery_is_rejected(self) -> None:
        alterations = (
            {"probability1": 50}, {"probability2": 1}, {"timing": 3},
            {"timing": 0, "duration": 90}, {"duration": 1},
            {"parameter1": 10}, {"parameter2": 0}, {"target": 1},
            {"resist_dispel": 1},
            {"save_type": 1}, {"save_bonus": -1}, {"dice_number": 1},
            {"dice_size": 1}, {"special": 1},
            {"resource": ""}, {"resource": "../BAD"},
            {"resource": "BAD/REF"}, {"resource": "BAD\\REF"}, {"resource": "BAD:REF"},
        )
        for fields in alterations:
            with self.subTest(fields=fields):
                def mutate(fixture: Fixture) -> None:
                    _write_delegation(fixture, edge=dataclasses.replace(_edge(), **fields))
                self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_missing_conditional_multiple_and_mixed_edges_are_rejected(self) -> None:
        for shape in ("missing", "conditional", "duplicate", "two_children", "mixed_double", "mixed_additive"):
            with self.subTest(shape=shape):
                def mutate(fixture: Fixture) -> None:
                    _write_delegation(fixture)
                    effects = [_edge()]
                    if shape == "missing":
                        (fixture.root / f"{CHILD}.SPL").unlink()
                    elif shape == "conditional":
                        effects = [dataclasses.replace(_edge(), opcode=326)]
                    elif shape == "duplicate":
                        effects.append(_edge())
                    elif shape == "two_children":
                        effects.append(_edge(GRANDCHILD))
                        write_spl(fixture.root / f"{GRANDCHILD}.SPL", _spell(_double()))
                    elif shape == "mixed_double":
                        effects.append(_double())
                    elif shape == "mixed_additive":
                        effects.append(dataclasses.replace(_double(), opcode=1, parameter1=1, parameter2=0))
                    write_spl(fixture.root / f"{fixture.haste_resref}.SPL", _spell(*effects))
                self.assert_rejected(self.run_case(mutate))

    def test_nested_and_cyclic_delegation_are_rejected(self) -> None:
        for shape in ("parent_self", "child_self", "child_parent", "nested", "double_and_nested"):
            with self.subTest(shape=shape):
                def mutate(fixture: Fixture) -> None:
                    _write_delegation(fixture)
                    if shape == "parent_self":
                        write_spl(fixture.root / f"{fixture.haste_resref}.SPL", _spell(_edge(fixture.haste_resref)))
                        return
                    resource = {"child_self": CHILD, "child_parent": fixture.haste_resref}.get(shape, GRANDCHILD)
                    effects = (_edge(resource),) + ((_double(),) if shape == "double_and_nested" else ())
                    write_spl(fixture.root / f"{CHILD}.SPL", _spell(*effects))
                    write_spl(fixture.root / f"{GRANDCHILD}.SPL", _spell(_double()))
                self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_direct_and_delegated_parent_headers_cannot_mix(self) -> None:
        def mutate(fixture: Fixture) -> None:
            _write_delegation(fixture)
            path = fixture.root / f"{fixture.haste_resref}.SPL"
            parent = read_spl(path)
            headers = list(parent.abilities)
            headers[1] = dataclasses.replace(headers[1], effects=(_double(),))
            write_spl(path, dataclasses.replace(parent, abilities=tuple(headers)))
        self.assert_rejected(self.run_case(mutate))

    def test_delegated_additive_requires_an_implemented_bridge_and_is_rejected(self) -> None:
        additive = dataclasses.replace(_double(), opcode=1, parameter1=1, parameter2=0)
        for mode in MODES:
            with self.subTest(mode=mode):
                self.assert_rejected(self.run_case(
                    lambda fixture: _write_delegation(fixture, child=_spell(additive)), mode=mode,
                ))

    def test_every_child_header_must_have_consistent_deterministic_doubling(self) -> None:
        defects = {
            "missing": (),
            "duplicate": (_double(), _double()),
            "normal_haste": (_double(parameter2=0),),
            "additive": (dataclasses.replace(_double(), opcode=1, parameter1=1, parameter2=0),),
            "mixed": (_double(), dataclasses.replace(_double(), opcode=1, parameter1=1, parameter2=0)),
            "probability": (_double(probability1=50),),
            "probability_floor": (_double(probability2=1),),
            "permanent": (_double(timing=1, duration=0),),
            "zero_duration": (_double(duration=0),),
        }
        for header_index in (0, 1, 2):
            for defect, effects in defects.items():
                with self.subTest(header=header_index, defect=defect):
                    def mutate(fixture: Fixture) -> None:
                        child = _spell(_double())
                        headers = list(child.abilities)
                        headers[header_index] = dataclasses.replace(headers[header_index], effects=effects)
                        _write_delegation(fixture, child=dataclasses.replace(child, abilities=tuple(headers)))
                    self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_delegated_doubling_delivery_metadata_is_not_a_validation_bypass(self) -> None:
        for fields in (
            {"target": 1}, {"parameter1": 1}, {"timing": 3},
            {"resist_dispel": 1}, {"resource": "FOREIGN"},
            {"dice_number": 1}, {"dice_size": 1}, {"save_type": 1},
            {"save_bonus": -1}, {"special": 1},
        ):
            with self.subTest(fields=fields):
                self.assert_rejected(self.run_case(
                    lambda fixture: _write_delegation(fixture, child=_spell(_double(**fields))),
                    phase="classify",
                ))

    def test_every_child_header_requires_supported_target_and_projectile(self) -> None:
        for header_index in (0, 1, 2):
            for fields in ({"target": 2}, {"projectile": 47}):
                with self.subTest(header=header_index, fields=fields):
                    def mutate(fixture: Fixture) -> None:
                        child = _spell(_double())
                        headers = list(child.abilities)
                        headers[header_index] = dataclasses.replace(headers[header_index], **fields)
                        _write_delegation(fixture, child=dataclasses.replace(child, abilities=tuple(headers)))
                    self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_unknown_and_indirect_auxiliary_opcodes_are_rejected(self) -> None:
        for owner in ("parent", "child"):
            for opcode in (999, 258, 260, 340, 402):
                with self.subTest(owner=owner, opcode=opcode):
                    def mutate(fixture: Fixture) -> None:
                        _write_delegation(fixture)
                        resource = fixture.haste_resref if owner == "parent" else CHILD
                        path = fixture.root / f"{resource}.SPL"
                        spell = read_spl(path)
                        write_spl(path, dataclasses.replace(spell, abilities=tuple(
                            dataclasses.replace(
                                header, effects=header.effects + (SplEffect(opcode=opcode, target=2),),
                            )
                            for header in spell.abilities
                        )))
                    self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_scs_conditional_message_leaf_is_safe_and_preserved(self) -> None:
        for owner in ("parent", "child"):
            with self.subTest(owner=owner):
                def mutate(fixture: Fixture) -> None:
                    _write_delegation(fixture)
                    condition = SplEffect(
                        opcode=326, target=2, parameter1=65536, parameter2=138,
                        timing=1, resource=FEEDBACK,
                    )
                    write_spl(fixture.root / f"{FEEDBACK}.SPL", _spell(SplEffect(opcode=139)))
                    resource = fixture.haste_resref if owner == "parent" else CHILD
                    path = fixture.root / f"{resource}.SPL"
                    spell = read_spl(path)
                    write_spl(path, dataclasses.replace(spell, abilities=tuple(
                        dataclasses.replace(header, effects=header.effects + (condition,))
                        for header in spell.abilities
                    )))
                result = self.run_case(mutate)
                self.assert_accepted(result)
                self.assertEqual(
                    (result.fixture.root / f"{FEEDBACK}.SPL").read_bytes(),
                    (result.output / f"{FEEDBACK}.SPL").read_bytes(),
                )

    def test_conditional_auxiliary_cannot_hide_apr_or_delegation(self) -> None:
        for defect in ("missing", "malformed", "empty", "apr", "nested", "conditional", "later_header", "casting"):
            with self.subTest(defect=defect):
                def mutate(fixture: Fixture) -> None:
                    condition = SplEffect(
                        opcode=326, target=2, parameter1=65536, parameter2=138,
                        timing=1, resource=FEEDBACK,
                    )
                    _write_delegation(fixture, child=_spell(_double(), condition))
                    path = fixture.root / f"{FEEDBACK}.SPL"
                    if defect == "missing":
                        return
                    if defect == "malformed":
                        path.write_bytes(b"not a spell")
                        return
                    leaf = _spell(SplEffect(opcode=139))
                    if defect == "empty":
                        leaf = make_spl(())
                    elif defect == "apr":
                        leaf = _spell(_double())
                    elif defect == "nested":
                        leaf = _spell(_edge(CHILD))
                    elif defect == "conditional":
                        leaf = _spell(dataclasses.replace(condition, resource=FEEDBACK))
                    elif defect == "later_header":
                        headers = list(leaf.abilities)
                        headers[2] = dataclasses.replace(headers[2], effects=(_double(),))
                        leaf = dataclasses.replace(leaf, abilities=tuple(headers))
                    elif defect == "casting":
                        leaf = dataclasses.replace(leaf, casting_effects=(_double(),))
                    write_spl(path, leaf)
                self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_delegated_graph_casting_effects_cannot_add_hidden_haste(self) -> None:
        for owner in ("parent", "child"):
            for effect in (_double(), _edge(), SplEffect(opcode=177, resource=GRANDCHILD)):
                with self.subTest(owner=owner, opcode=effect.opcode):
                    def mutate(fixture: Fixture) -> None:
                        _write_delegation(fixture)
                        resource = fixture.haste_resref if owner == "parent" else CHILD
                        path = fixture.root / f"{resource}.SPL"
                        write_spl(path, dataclasses.replace(read_spl(path), casting_effects=(effect,)))
                    self.assert_rejected(self.run_case(mutate, phase="classify"))

    def test_malformed_child_resources_fail_before_publication(self) -> None:
        import struct

        for defect in ("truncated", "signature", "no_headers", "partial_record", "slice", "overlap", "orphan", "duplicate_levels"):
            with self.subTest(defect=defect):
                def mutate(fixture: Fixture) -> None:
                    _write_delegation(fixture)
                    path = fixture.root / f"{CHILD}.SPL"
                    raw = bytearray(path.read_bytes())
                    if defect == "truncated":
                        raw = raw[:20]
                    elif defect == "signature":
                        raw[:8] = b"SPL V2  "
                    elif defect == "no_headers":
                        raw = bytearray(make_spl(()).to_bytes())
                    elif defect == "partial_record":
                        raw = raw[:-1]
                    elif defect == "slice":
                        struct.pack_into("<H", raw, 0x72 + 2 * 0x28 + 0x20, 0xFFFF)
                    elif defect == "overlap":
                        struct.pack_into("<H", raw, 0x72 + 0x28 + 0x20, 0)
                    elif defect == "orphan":
                        raw.extend(_double().to_bytes())
                    elif defect == "duplicate_levels":
                        struct.pack_into("<H", raw, 0x72 + 0x28 + 0x10, 1)
                    path.write_bytes(raw)
                self.assert_rejected(self.run_case(mutate))


if __name__ == "__main__":
    unittest.main()
