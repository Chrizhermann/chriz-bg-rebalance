"""Changed inputs must produce the decided Tempus output, without warnings."""

import dataclasses
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tests import test_tempus_holy_power as hp
from tests.ie_formats import SplAbility, SplEffect, make_spl, read_ids, read_spl, read_2da, write_spl


class HolyPowerOverwriteTests(unittest.TestCase):
    def base(self, mode="auto"):
        run = hp._run_harness("additive", mode)
        self.addCleanup(run.temporary.cleanup)
        self.success(run)
        return run

    def changed(self, first, mutate):
        run = hp._rerun_harness(first, fixture_mutator=mutate)
        self.addCleanup(run.temporary.cleanup)
        self.success(run)
        return run

    def success(self, run):
        self.assertEqual(0, run.process.returncode, run.transcript)
        self.assertTrue(run.succeeded, run.transcript)
        self.assertNotIn("WITH WARNINGS", run.transcript)
        if (run.output / "OHTMPS1.SPL").exists():
            hp.assert_defined_holy(self, run.output)
            hp._assert_strength_helper_graph(run.output, run.fixture.divine_resref)

    def stable(self, run):
        again = self.changed(run, lambda root: None)
        self.assertEqual(hp._raw_file_tree(run.output), hp._raw_file_tree(again.output))

    def test_holy_missing_extra_and_hand_edited_effects_and_other_text(self):
        first = self.base()
        expected = (first.output / "OHTMPS1.SPL").read_bytes()
        for shape in ("empty", "extra", "one_header", "truncated"):
            with self.subTest(shape=shape):
                def mutate(root):
                    path = root / "OHTMPS1.SPL"
                    spell = read_spl(path)
                    if shape == "truncated":
                        path.write_bytes(b"SPL V1  ")
                        return
                    if shape == "empty":
                        abilities = ()
                    else:
                        changed = dataclasses.replace(spell.abilities[0], required_level=90,
                            effects=(SplEffect(opcode=54, parameter1=99), SplEffect(opcode=18, parameter1=999)))
                        abilities = (changed,) if shape == "one_header" else (changed, *spell.abilities[::-1])
                    header = bytearray(spell.header_raw)
                    # The description component owns text; arbitrary translated references survive here.
                    for offset, value in ((8, 123456), (12, 777777), (0x50, 666666), (0x54, 888888)):
                        struct.pack_into("<I", header, offset, value)
                    write_spl(path, dataclasses.replace(spell, abilities=abilities, header_raw=bytes(header),
                        casting_effects=(SplEffect(opcode=18, parameter1=1000),)))
                run = self.changed(first, mutate)
                actual = bytearray((run.output / "OHTMPS1.SPL").read_bytes())
                for offset in (8, 12, 0x50, 0x54):
                    if shape != "truncated":
                        self.assertEqual((run.fixture.root / "OHTMPS1.SPL").read_bytes()[offset:offset+4], actual[offset:offset+4])
                    actual[offset:offset+4] = expected[offset:offset+4]
                self.assertEqual(expected, actual)
                self.stable(run)

    def test_all_private_helper_bytes_are_replaced_and_other_extensions_survive(self):
        first = self.base()
        owned = {p.name: p.read_bytes() for p in first.output.iterdir()
                 if p.stem.upper() in hp.RESERVED_PRIVATE_RESREFS and p.suffix.upper() in (".SPL", ".EFF")}
        def mutate(root):
            for name in owned:
                (root / name).write_bytes(b"foreign helper contents")
            for resref in hp.RESERVED_PRIVATE_RESREFS:
                (root / f"{resref}.ITM").write_bytes(b"unrelated item extension")
        run = self.changed(first, mutate)
        for name, payload in owned.items():
            self.assertEqual(payload, (run.output / name).read_bytes(), name)
        for resref in hp.RESERVED_PRIVATE_RESREFS:
            self.assertEqual(b"unrelated item extension", (run.output / f"{resref}.ITM").read_bytes())
        self.stable(run)

    def test_splprot_named_columns_missing_cells_and_changed_owned_values(self):
        first = self.base()
        for shape in ("reordered", "missing_columns", "missing_table"):
            with self.subTest(shape=shape):
                def mutate(root):
                    path = root / "SPLPROT.2DA"
                    if shape == "missing_table":
                        path.unlink()
                    elif shape == "missing_columns":
                        path.write_text("2DA V1.0\n0\nVALUE FOREIGN\nCBR_TEMPUS_STR_LT 999 keep\nFOREIGN 27 retained\n")
                    else:
                        path.write_text("2DA V1.0\n0\nRELATION FOREIGN VALUE STAT\nCBR_TEMPUS_STR_LT 9 keep 99 99\nFOREIGN 7 retained 11 22\n")
                run = self.changed(first, mutate)
                table = read_2da(run.output / "SPLPROT.2DA")
                self.assertEqual(["36", "-1", "2"], [table.cell("CBR_TEMPUS_STR_LT", c) for c in ("STAT", "VALUE", "RELATION")])
                if shape != "missing_table":
                    self.assertEqual("retained", table.cell("FOREIGN", "FOREIGN"))
                    self.assertEqual("keep", table.cell("CBR_TEMPUS_STR_LT", "FOREIGN"))
                self.stable(run)

    def test_absent_and_unreadable_targets_only_cost_their_own_resource(self):
        first = self.base()
        for name in ("OHTMPS1.SPL", f"{first.fixture.haste_resref}.SPL", f"{first.fixture.divine_resref}.SPL"):
            for absent in (False, True):
                with self.subTest(name=name, absent=absent):
                    def mutate(root):
                        if absent:
                            (root / name).unlink()
                        else:
                            (root / name).write_bytes(b"unreadable")
                        (root / "CBRST18.SPL").write_bytes(b"also needs repair")
                    run = self.changed(first, mutate)
                    self.assertEqual((first.output / "CBRST18.SPL").read_bytes(), (run.output / "CBRST18.SPL").read_bytes())
                    if absent:
                        self.assertFalse((run.output / name).exists())
                    elif name != "OHTMPS1.SPL":
                        self.assertEqual(b"unreadable", (run.output / name).read_bytes())
                    self.stable(run)

    def test_empty_foreign_spell_headers_receive_owned_behavior(self):
        first = self.base("force_additive")
        for shape in ("no_abilities", "no_effects", "unused_offsets", "bad_signature"):
            with self.subTest(shape=shape):
                def mutate(root):
                    spell = make_spl(()) if shape != "no_effects" else make_spl((SplAbility(1, 1, 0, ()),))
                    raw = bytearray(spell.to_bytes())
                    if shape == "unused_offsets":
                        struct.pack_into("<I", raw, 0x64, 0)
                        struct.pack_into("<I", raw, 0x6a, 0)
                        struct.pack_into("<H", raw, 0x6e, 65535)
                    elif shape == "bad_signature":
                        raw[:8] = b"changed!"
                    for resref in (first.fixture.haste_resref, first.fixture.divine_resref):
                        (root / f"{resref}.SPL").write_bytes(raw)
                run = self.changed(first, mutate)
                ih = read_spl(run.output / f"{first.fixture.haste_resref}.SPL")
                divine = read_spl(run.output / f"{first.fixture.divine_resref}.SPL")
                self.assertEqual([328, 326, 326, 326], [e.opcode for e in ih.abilities[0].effects])
                self.assertEqual(["OHTMPS1", "CBRST18", "CBRST19", "CBRST20", "CBRST21"], [e.resource for e in divine.abilities[0].effects])
                self.stable(run)

    def test_deep_mixed_resource_chain_and_cycle_terminate_without_depth_cutoff(self):
        first = self.base()
        def mutate(root):
            for i in range(80):
                name = first.fixture.haste_resref if i == 0 else f"CH{i:06}"
                next_name = f"CH{i+1:06}" if i < 79 else first.fixture.haste_resref
                effects = (SplEffect(opcode=146, resource=next_name),)
                if i == 79:
                    effects += (SplEffect(opcode=1, parameter1=7),)
                write_spl(root / f"{name}.SPL", make_spl((SplAbility(1, 1, 0, effects),)))
        run = self.changed(first, mutate)
        state = read_ids(run.output / "SPLSTATE.IDS").value("CBR_TEMPUS_IH")
        parent = read_spl(run.output / f"{first.fixture.haste_resref}.SPL")
        self.assertTrue(any(e.opcode == 328 and e.parameter2 == state for e in parent.abilities[0].effects))
        for i in range(1, 80):
            name = f"CH{i:06}.SPL"
            self.assertEqual((run.fixture.root / name).read_bytes(), (run.output / name).read_bytes())
        self.stable(run)

    def test_visited_resource_names_are_compared_literally(self):
        first = self.base()
        def mutate(root):
            write_spl(root / f"{first.fixture.haste_resref}.SPL", make_spl((
                SplAbility(1, 1, 0, (SplEffect(opcode=146, resource="SPWI..."),)),)))
            write_spl(root / "SPWI....SPL", make_spl((
                SplAbility(1, 1, 0, (SplEffect(opcode=1, parameter1=1),)),)))
        run = self.changed(first, mutate)
        spell = read_spl(run.output / f"{first.fixture.haste_resref}.SPL")
        self.assertEqual([328, 326, 326, 326, 146], [e.opcode for e in spell.abilities[0].effects])
        self.stable(run)

    def test_key_only_private_resources_are_overridden_and_restored_on_uninstall(self):
        from tests import test_tempus_holy_power_installer as public
        holder = tempfile.TemporaryDirectory(prefix="cbr-holy-key-overwrite-")
        self.addCleanup(holder.cleanup)
        game = public.SyntheticGame(holder, "additive")
        resources = [("OH6000", "ARE", b"synthetic BG2EE marker")]
        for name in ("OHTMPS1.SPL", "SPELL.IDS", f"{public.HASTE_RESREF}.SPL", "SPLSTATE.IDS"):
            stem, extension = name.rsplit(".", 1)
            resources.append((stem, extension, (game.fixture_root / name).read_bytes()))
        resources.extend((name, extension, b"foreign indexed helper") for name, extension in (
            ("CBRST18", "SPL"), ("CBRSE18", "EFF"), ("CBRAPR1", "SPL"),
            ("CBRAPC1", "EFF"), ("CBRST18", "ITM"), ("CBRSE18", "SPL")))
        with patch.dict(public.RESOURCE_TYPE, {"EFF": 1016, "ITM": 1005}):
            game.bif_path = public._write_key_and_bif(game.root, tuple(resources))
        game.stable_hashes["key"] = public._sha256(game.root / "chitin.key")
        game.stable_hashes["bif"] = public._sha256(game.bif_path)
        result = game.run_install(401)
        self.assertEqual(0, result.returncode, game.transcript(result))
        self.assertNotIn("WITH WARNINGS", game.transcript(result))
        hp.assert_defined_holy(self, game.override)
        hp._assert_strength_helper_graph(game.override, game.fixture.divine_resref)
        self.assertFalse((game.override / "CBRST18.ITM").exists())
        self.assertFalse((game.override / "CBRSE18.SPL").exists())
        game.assert_stable_inputs(self)
        removed = game.run_uninstall(401)
        self.assertEqual(0, removed.returncode, game.transcript(removed))
        self.assertEqual(game.pre_override, hp._raw_file_tree(game.override))
        game.assert_stable_inputs(self)

    def test_effect_tables_before_abilities_and_padding_are_serialized(self):
        first = self.base()
        def mutate(root):
            for resref in (first.fixture.haste_resref, first.fixture.divine_resref):
                path = root / f"{resref}.SPL"
                raw = path.read_bytes()
                ability_offset = struct.unpack_from("<I", raw, 0x64)[0]
                count = struct.unpack_from("<H", raw, 0x68)[0]
                effect_offset = struct.unpack_from("<I", raw, 0x6a)[0]
                effects = raw[effect_offset:]
                header = bytearray(raw[:0x72])
                struct.pack_into("<I", header, 0x64, 0x72 + len(effects) + 17)
                struct.pack_into("<I", header, 0x6a, 0x72)
                path.write_bytes(header + effects + b"padding is unused" + raw[ability_offset:ability_offset + count * 0x28])
        run = self.changed(first, mutate)
        for resref in (first.fixture.haste_resref, first.fixture.divine_resref):
            self.assertEqual((first.output / f"{resref}.SPL").read_bytes(), (run.output / f"{resref}.SPL").read_bytes())
        self.stable(run)

    def test_old_owned_casting_effects_are_replaced_with_ability_behavior(self):
        first = self.base()
        sentinel = SplEffect(opcode=139, parameter1=345678, target=1)
        def mutate(root):
            state = read_ids(root / "SPLSTATE.IDS").value("CBR_TEMPUS_IH")
            for resref, old in (
                (first.fixture.haste_resref, (SplEffect(opcode=328, parameter2=state), SplEffect(opcode=146, resource="CBRAPR1"))),
                (first.fixture.divine_resref, (SplEffect(opcode=321, resource="OHTMPS1"), SplEffect(opcode=321, resource="CBRST18"))),
            ):
                path = root / f"{resref}.SPL"
                spell = read_spl(path)
                write_spl(path, dataclasses.replace(spell, casting_effects=(*old, sentinel)))
        run = self.changed(first, mutate)
        for resref in (first.fixture.haste_resref, first.fixture.divine_resref):
            spell = read_spl(run.output / f"{resref}.SPL")
            self.assertEqual((sentinel,), spell.casting_effects)
            expected = read_spl(first.output / f"{resref}.SPL")
            self.assertEqual(expected.abilities, spell.abilities)
        self.stable(run)

    def test_exhaustion_omits_only_bridge_and_disables_stale_helpers(self):
        first = self.base()
        for free in (0, 3):
            with self.subTest(free=free):
                def mutate(root):
                    states = "IDS V1.0\n" + "".join(f"{i} FOREIGN_{i}\n" for i in range(256-free))
                    # Keep aliases from the previous installation; none may be reused.
                    states += "".join(f"{i} {sym}\n" for i,sym in zip(range(240,244), hp.PRIVATE_STATE_SYMBOLS))
                    (root / "SPLSTATE.IDS").write_text(states)
                run = self.changed(first, mutate)
                self.assertEqual((run.fixture.root / "SPLSTATE.IDS").read_bytes(), (run.output / "SPLSTATE.IDS").read_bytes())
                hp.assert_defined_holy(self, run.output)
                for name in ("OHTMPS1.SPL", f"{run.fixture.haste_resref}.SPL"):
                    for ability in read_spl(run.output / name).abilities:
                        self.assertFalse(any(e.resource.startswith(("CBRAPR", "CBRAPC")) or (e.opcode == 328 and (name != "OHTMPS1.SPL" or e.parameter2 not in (9, 68))) for e in ability.effects))
                for key in ("6", "1", "7"):
                    self.assertEqual([321], [e.opcode for e in read_spl(run.output / f"CBRAPR{key}.spl").abilities[0].effects])
                    self.assertEqual(321, hp.read_eff_v2(run.output / f"CBRAPC{key}.eff").opcode)
                self.assertEqual(1, run.transcript.count("insufficient unused SPLSTATE slots"))
                self.stable(run)

    def test_shared_foreign_state_is_never_reused_for_the_bridge(self):
        first = self.base()
        def mutate(root):
            text = "IDS V1.0\n" + "".join(f"{240+i} {sym}\n{240+i} FOREIGN_{i}\n" for i,sym in enumerate(hp.PRIVATE_STATE_SYMBOLS))
            (root / "SPLSTATE.IDS").write_text(text)
        run = self.changed(first, mutate)
        ids = read_ids(run.output / "SPLSTATE.IDS")
        self.assertTrue(all(ids.value(sym) not in range(240,244) for sym in hp.PRIVATE_STATE_SYMBOLS))
        self.assertEqual(4, len({ids.value(sym) for sym in hp.PRIVATE_STATE_SYMBOLS}))
        self.stable(run)

    def test_shared_state_writer_handles_exhaustion_and_absent_table(self):
        for planned, exists in ((-1, True), (-1, False), (247, False)):
            with self.subTest(planned=planned, exists=exists), tempfile.TemporaryDirectory(prefix="cbr-state-writer-") as temporary:
                root = Path(temporary)
                ids = root / "SPLSTATE.IDS"
                original = "IDS V1.0\n" + "".join(f"{i} FOREIGN_{i}\n" for i in range(256))
                if exists:
                    ids.write_text(original, encoding="ascii", newline="\n")
                plan = "0 - 1" if planned < 0 else str(planned)
                harness = root / "harness.tp2"
                harness.write_text("\n".join([
                    "BACKUP ~backup~", "AUTHOR ~test~", "BEGIN ~state writer~ DESIGNATED 0",
                    f"INCLUDE ~{hp.PRODUCTION_TPA.as_posix()}~",
                    f"LAF cbr_find_or_allocate_splstate INT_VAR planned_value = ({plan})",
                    f"  STR_VAR resource_path = ~{ids.as_posix()}~ symbol = ~CBR_TEST_MARKER~",
                    "  RET state_value appended END",
                    "PRINT ~WRITER_RESULT %state_value% %appended%~",
                ]) + "\n", encoding="ascii")
                process = subprocess.run([str(hp.WEIDU), str(harness), "--nogame", "--force-install-list", "0",
                    "--no-exit-pause", "--quick-log"], cwd=root, capture_output=True, text=True, timeout=90)
                transcript = process.stdout + process.stderr
                self.assertEqual(0, process.returncode, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                self.assertNotIn("WITH WARNINGS", transcript)
                self.assertIn(f"WRITER_RESULT {planned} {int(planned >= 0)}", transcript)
                self.assertEqual(int(planned < 0), transcript.count("no unused SPLSTATE slot for CBR_TEST_MARKER"))
                if planned >= 0:
                    self.assertEqual("IDS V1.0\n247 CBR_TEST_MARKER\n", ids.read_text(encoding="ascii"))
                elif exists:
                    self.assertEqual(original.encode("ascii"), ids.read_bytes())
                else:
                    self.assertFalse(ids.exists())

    def test_duplicate_owned_splprot_columns_are_all_written(self):
        first = self.base()
        def mutate(root):
            (root / "SPLPROT.2DA").write_text("2DA V1.0\n0\nSTAT VALUE RELATION STAT VALUE RELATION FOREIGN\nCBR_TEMPUS_STR_LT 99 98 97 96 95 94 keep\nFOREIGN 1 2 3 4 5 6 stay\n")
        run = self.changed(first, mutate)
        table = read_2da(run.output / "SPLPROT.2DA")
        row = next(cells for name,cells in table.rows if name == "CBR_TEMPUS_STR_LT")
        self.assertEqual(("36","-1","2","36","-1","2","keep"), row)
        foreign = next(cells for name,cells in table.rows if name == "FOREIGN")
        self.assertEqual(("1","2","3","4","5","6","stay"), foreign)
        self.stable(run)


if __name__ == "__main__":
    unittest.main()
