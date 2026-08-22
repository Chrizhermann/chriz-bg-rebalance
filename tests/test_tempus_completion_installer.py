"""End-to-end installer tests for components 400/404/405/406/407 on a
synthetic game.

Each test builds a minimal KEY V1/BIFF V1/TLK game (OH6000.ARE marker makes
GAME_IS ~bg2ee~ true), installs a component through the real
setup-chriz-bg-rebalance.tp2 — exercising the REQUIRE_PREDICATEs, the
IDS_OF_SYMBOL stats/kit resolution, the school-byte discovery sweep, and the
RESOLVE_STR_REF TLK growth — and asserts the override delta and the
byte-exact uninstall restore. The 406→407 swap test rehearses the live
migration command (one run: --force-uninstall-list 406 --force-install-list
407) including the subcomponent exclusivity of the two variants.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.ie_formats import SplAbility, make_spl, read_2da, read_eff_v2, read_spl
from tests.test_tempus_completion import (
    EEEX_KIT_ID,
    MARKER_SYMBOL,
    PLANNED_STATE,
    ORIGINALS,
    ROOT,
    TOLL_SPELLS,
    build_specapr_fixture,
    build_toll_fixture,
    build_training_fixture,
)
from tests.test_tempus_holy_power import SETUP_TP2, WEIDU, _raw_file_tree
from tests.test_tempus_holy_power_installer import (
    ONE_EMPTY_STRING_TLK,
    _write_key_and_bif,
)

ANNOUNCE_TEXTS = (
    "Tide of Battle: Onslaught!",
    "Tide of Battle: Bulwark!",
    "Tide of Battle: Fortune!",
)


def _school_spl(school: int) -> bytes:
    data = bytearray(make_spl([]).to_bytes())
    data[0x25] = school
    return bytes(data)


def _artisan_permission_spl() -> bytes:
    return make_spl([]).to_bytes()


def _read_tlk_strings(path: Path) -> list[str]:
    data = path.read_bytes()
    if data[:8] != b"TLK V1  ":
        raise AssertionError(f"not a TLK V1 file: {path}")
    count = struct.unpack_from("<I", data, 0x0A)[0]
    strings_offset = struct.unpack_from("<I", data, 0x0E)[0]
    strings = []
    for index in range(count):
        entry = 0x12 + index * 26
        offset, length = struct.unpack_from("<II", data, entry + 18)
        strings.append(data[strings_offset + offset : strings_offset + offset + length].decode("utf-8"))
    return strings


class CompletionGame:
    """Synthetic game tailored to the 400/404/405/406/407 prerequisites."""

    def __init__(
        self,
        temporary: tempfile.TemporaryDirectory[str],
        *,
        training_shape: str = "pristine",
        with_artisan_permissions: bool = True,
        override_schools: tuple[tuple[str, int], ...] = (
            ("SPPR104", 3),
            ("SPPR205", 3),
            ("SPPR317", 2),
        ),
        biff_schools: tuple[tuple[str, int], ...] = (("SPPR150", 3),),
    ):
        self.temporary = temporary
        self.root = Path(temporary.name) / "game"
        self.root.mkdir()
        self.override = self.root / "override"
        self.override.mkdir()

        shutil.copy2(SETUP_TP2, self.root / SETUP_TP2.name)
        shutil.copytree(ROOT / "chriz-bg-rebalance", self.root / "chriz-bg-rebalance")

        staging = Path(temporary.name) / "staging"
        weapprof_shape = "hotfixed" if training_shape == "hotfixed" else "pristine"
        build_training_fixture(
            staging / "training", grant_shape=training_shape, weapprof_shape=weapprof_shape
        )
        build_toll_fixture(staging / "toll")
        build_specapr_fixture(staging / "specapr")
        for name in ("WEAPPROF.2DA", "C0PR#C4.SPL", "SPLPROT.2DA"):
            shutil.copy2(staging / "training" / name, self.override / name)
        shutil.copy2(staging / "toll" / "OHTEMPUS.2DA", self.override / "OHTEMPUS.2DA")
        shutil.copy2(staging / "specapr" / "CLSWPBON.2DA", self.override / "CLSWPBON.2DA")
        shutil.copy2(ORIGINALS / "OHTMPS2D.spl.orig", self.override / "OHTMPS2D.SPL")
        shutil.copy2(ORIGINALS / "OHTMPS2E.spl.orig", self.override / "OHTMPS2E.SPL")
        (self.override / "STATS.IDS").write_text(
            "IDS V1.0\n90 PROFICIENCYLONGSWORD\n92 PROFICIENCYAXE\n"
            "103 PROFICIENCYCROSSBOW\n204 C0_PROFICIENCYLONGSWORD\n",
            encoding="ascii",
            newline="\n",
        )
        # Component 407 prerequisites: the EEex marker (existence-checked
        # only) and a KIT.IDS defining OHTEMPUS at the live install's value.
        (self.override / "M___EEex.lua").write_text(
            "-- synthetic EEex marker for installer tests\n", encoding="ascii"
        )
        (self.override / "KIT.IDS").write_text(
            f"IDS V1.0\n0x{int(EEEX_KIT_ID):04x} OHTEMPUS\n",
            encoding="ascii",
            newline="\n",
        )
        # Component 408 prerequisites: KITLIST with the OHTEMPUS row (HELP
        # points at TLK entry 0 — the synthetic TLK's single empty string)
        # and an OHTMPS1 shaped like the 401 rework (per-tier abilities).
        (self.override / "KITLIST.2DA").write_text(
            "2DA V1.0\n0\n"
            "ROWNAME\tLOWER\tMIXED\tHELP\tABILITIES\tPROFICIENCY\tUNUSABLE\tCLASS\tKITIDS\n"
            "0\tTRUECLASS\t0\t0\t0\t****\t0\t0x00000000\t0\t0x00004000\n"
            f"41\tOHTEMPUS\t0\t0\t0\tOHTEMPUS\t62\t0x00004000\t3\t0x{int(EEEX_KIT_ID):08x}\n",
            encoding="ascii",
            newline="\n",
        )
        ohtmps1 = bytearray(
            make_spl(
                [
                    SplAbility(required_level=level, target=1, projectile=1, effects=())
                    for level in (1, 7, 13, 19, 25)
                ]
            ).to_bytes()
        )
        struct.pack_into("<i", ohtmps1, 0x50, 0)
        (self.override / "OHTMPS1.SPL").write_bytes(bytes(ohtmps1))
        if with_artisan_permissions:
            for name in ("C0PR#90", "C0PR#92", "C0PR#103"):
                (self.override / f"{name}.SPL").write_bytes(_artisan_permission_spl())
        for resref, school in override_schools:
            (self.override / f"{resref}.SPL").write_bytes(_school_spl(school))

        biff_resources = [
            ("OH6000", "ARE", b"synthetic BG2EE marker"),
            ("OHTMPS2", "SPL", (ORIGINALS / "OHTMPS2.spl.orig").read_bytes()),
            # The sibling Holy Power components' REQUIRE_PREDICATEs evaluate
            # IDS_OF_SYMBOL during tp2 processing; ship the IDS files so that
            # evaluation is quiet instead of spamming get_ids_map errors.
            ("SPELL", "IDS", b"IDS V1.0\n1388 CLERIC_HOLY_POWER\n2788 WIZARD_IMPROVED_HASTE\n"),
            ("SPLSTATE", "IDS", b"IDS V1.0\n9 HOLY_POWER\n"),
        ]
        for resref, school in biff_schools:
            biff_resources.append((resref, "SPL", _school_spl(school)))
        self.bif_path = _write_key_and_bif(self.root, tuple(biff_resources))

        self.lang_tlk = self.root / "lang/en_US/dialog.tlk"
        self.lang_tlk.parent.mkdir(parents=True)
        self.lang_tlk.write_bytes(ONE_EMPTY_STRING_TLK)
        self.root_tlk = self.root / "dialog.tlk"
        self.root_tlk.write_bytes(ONE_EMPTY_STRING_TLK)

        self.pre_override = _raw_file_tree(self.override)

    @property
    def setup_tp2(self) -> Path:
        return self.root / SETUP_TP2.name

    def run_raw(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                str(WEIDU),
                str(self.setup_tp2),
                "--game",
                str(self.root),
                *args,
                "--language",
                "0",
                "--use-lang",
                "en_US",
                "--no-exit-pause",
                "--quick-log",
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

    def run(self, operation: str, component: int) -> subprocess.CompletedProcess[str]:
        return self.run_raw(operation, str(component))

    def transcript(self, process: subprocess.CompletedProcess[str]) -> str:
        return f"{process.stdout}\n{process.stderr}".strip()


class TempusCompletionInstallerTests(unittest.TestCase):
    def _game(self, **kwargs) -> CompletionGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-completion-game-")
        self.addCleanup(temporary.cleanup)
        return CompletionGame(temporary, **kwargs)

    def _install(self, game: CompletionGame, component: int) -> None:
        process = game.run("--force-install-list", component)
        transcript = game.transcript(process)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)

    def _uninstall_restores_override(self, game: CompletionGame, component: int) -> None:
        process = game.run("--force-uninstall-list", component)
        transcript = game.transcript(process)
        self.assertNotIn("NOT UNINSTALLED", transcript, transcript)
        self.assertEqual(
            game.pre_override,
            _raw_file_tree(game.override),
            "uninstall must restore the override byte-exactly",
        )

    def test_component_400_fresh_install_transforms_then_uninstalls(self) -> None:
        game = self._game()
        self._install(game, 400)

        table = read_2da(game.override / "WEAPPROF.2DA")
        for name in ("LONGSWORD", "AXE", "CROSSBOW", "2HANDED", "SLING", "HALBERD"):
            self.assertEqual(table.cell(name, "OHTEMPUS"), "2", name)
        self.assertEqual(table.cell("BLUNT_BG1", "OHTEMPUS"), "1")
        self.assertEqual(table.cell("BASTARDSWORD", "OHTEMPUS"), "0")

        grant = read_spl(game.override / "C0PR#C4.SPL")
        self.assertEqual(len(grant.abilities[0].effects), 5)

        new_files = {name.upper() for name in _raw_file_tree(game.override)} - {
            name.upper() for name in game.pre_override
        }
        self.assertEqual(
            new_files, {"CBRTMG2.SPL", "CBRTMG2L.SPL", "CBRTMG2X.SPL"}
        )
        migration = read_spl(game.override / "CBRTMG2.spl")
        self.assertEqual(
            [effect.opcode for effect in migration.abilities[0].effects], [326, 326, 326]
        )

        splprot_text = (game.override / "SPLPROT.2DA").read_text(encoding="ascii")
        for label in ("CBR_TEMPUS_C0LS_LE0", "CBR_TEMPUS_PROFLS_LE0", "CBR_TEMPUS_PROFXB_LE0"):
            self.assertIn(label, splprot_text)

        self.assertEqual(
            _read_tlk_strings(game.lang_tlk), [""], "component 400 must stay TLK-neutral"
        )
        self._uninstall_restores_override(game, 400)

    def test_component_400_is_byte_stable_over_hotfixed_state(self) -> None:
        game = self._game(training_shape="hotfixed")
        self._install(game, 400)
        for name in ("WEAPPROF.2DA", "C0PR#C4.SPL"):
            self.assertEqual(
                game.pre_override[name.upper()],
                (game.override / name).read_bytes(),
                f"{name} must stay byte-identical over the hotfixed state",
            )

    def test_component_400_fails_without_artisan_permissions(self) -> None:
        game = self._game(with_artisan_permissions=False)
        process = game.run("--force-install-list", 400)
        transcript = game.transcript(process)
        # A failing REQUIRE_PREDICATE reports the component as SKIPPING (it is
        # never attempted), not as a failed install.
        self.assertIn("SKIPPING", transcript, transcript)
        self.assertIn("Artisan's Kitpack proficiency permission spells", transcript)
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))

    def test_component_404_installs_tides_and_grows_tlk_by_three(self) -> None:
        game = self._game()
        self._install(game, 404)

        strings = _read_tlk_strings(game.lang_tlk)
        self.assertEqual(strings, ["", *ANNOUNCE_TEXTS], "exactly three appended strings")

        new_files = {name.upper() for name in _raw_file_tree(game.override)} - {
            name.upper() for name in game.pre_override
        }
        self.assertEqual(
            new_files,
            {
                "OHTMPS2.SPL",
                "CBRCHT1D.SPL",
                "CBRCHT1E.SPL",
                "CBRCHT2D.SPL",
                "CBRCHT2E.SPL",
                "CBRCHT3D.SPL",
                "CBRCHT3E.SPL",
            },
        )
        dispatcher = read_spl(game.override / "OHTMPS2.SPL")
        announces = [
            effect for effect in dispatcher.abilities[0].effects if effect.opcode == 139
        ]
        self.assertEqual([effect.parameter1 for effect in announces], [1, 2, 3])

        self._uninstall_restores_override(game, 404)
        self.assertEqual(
            _read_tlk_strings(game.lang_tlk),
            ["", *ANNOUNCE_TEXTS],
            "WeiDU keeps appended TLK strings on uninstall (documented residue)",
        )

    def test_component_405_discovery_spans_override_and_bif(self) -> None:
        game = self._game()
        self._install(game, 405)

        toll = read_spl(game.override / "CBRTMDV.spl")
        effects = toll.abilities[0].effects
        removed = {effect.resource for effect in effects if effect.opcode == 172}
        self.assertEqual(
            removed,
            {"SPPR104", "SPPR205", "SPPR150"},
            "school-3 spells from both override and BIF, school-2 excluded",
        )
        pulses = [effect for effect in effects if effect.opcode == 272]
        self.assertEqual(len(pulses), 3)
        eff_targets = set()
        for index in range(3):
            eff = read_eff_v2(game.override / f"CBRTMD{index}.eff")
            self.assertEqual(eff.opcode, 172)
            eff_targets.add(eff.resource)
        self.assertEqual(eff_targets, removed)

        table = read_2da(game.override / "OHTEMPUS.2DA")
        self.assertEqual(table.cell("CBR_DIVTOLL", "50"), "AP_CBRTMDV")

        self.assertEqual(
            _read_tlk_strings(game.lang_tlk), [""], "component 405 must stay TLK-neutral"
        )
        self._uninstall_restores_override(game, 405)

    def test_component_405_fails_without_divination_spells(self) -> None:
        game = self._game(
            override_schools=(("SPPR104", 2), ("SPPR205", 6)), biff_schools=()
        )
        process = game.run("--force-install-list", 405)
        transcript = game.transcript(process)
        self.assertIn("NOT INSTALLED", transcript, transcript)
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))

    def test_component_407_ships_stamped_listener_then_uninstalls(self) -> None:
        game = self._game()
        self._install(game, 407)

        new_files = {name.upper() for name in _raw_file_tree(game.override)} - {
            name.upper() for name in game.pre_override
        }
        self.assertEqual(new_files, {"M_CBRAPR.LUA", "SPLSTATE.IDS"})
        shipped = (game.override / "M_CBRAPR.lua").read_text(encoding="ascii")
        self.assertIn(f"local CBR_APR_TEMPUS_KIT = {EEEX_KIT_ID}", shipped)
        self.assertIn(f"local CBR_APR_MARKER_STATE = {PLANNED_STATE}", shipped)
        self.assertNotIn("CBR_TEMPUS_KIT_ID", shipped)
        self.assertNotIn("CBR_TEMPUS_SPEC_APR_STATE", shipped)
        ids_text = (game.override / "SPLSTATE.IDS").read_text(encoding="ascii")
        self.assertIn(f"{PLANNED_STATE} {MARKER_SYMBOL}", ids_text)
        self.assertIn("9 HOLY_POWER", ids_text, "materialized from the BIF, rows preserved")
        self.assertEqual(
            _read_tlk_strings(game.lang_tlk), [""], "component 407 must stay TLK-neutral"
        )
        self._uninstall_restores_override(game, 407)

    def test_component_409_reships_the_listener_over_407_then_uninstalls_back(self) -> None:
        """The live-install path: 407 (v0.1.0 listener) is mid-stack and must
        never be reinstalled; 409 re-ships the fixed listener as a tail
        component over the existing file and its uninstall hands the old
        bytes back."""
        game = self._game()
        self._install(game, 407)
        fresh = (game.override / "M_CBRAPR.lua").read_bytes()
        ids_after_407 = (game.override / "SPLSTATE.IDS").read_bytes()
        stale = b"-- stale v0.1.0 listener (relative write, no marker)\n"
        (game.override / "M_CBRAPR.lua").write_bytes(stale)
        tree_before_409 = _raw_file_tree(game.override)

        self._install(game, 409)
        self.assertEqual((game.override / "M_CBRAPR.lua").read_bytes(), fresh)
        self.assertEqual(
            (game.override / "SPLSTATE.IDS").read_bytes(), ids_after_407,
            "the marker row already exists — 409 must not append a second one",
        )
        weidu_log = (game.root / "WeiDU.log").read_text(encoding="ascii", errors="replace")
        installed = [line for line in weidu_log.splitlines() if line.startswith("~")]
        self.assertEqual(len(installed), 2, weidu_log)
        self.assertIn("#407", installed[0])
        self.assertIn("#409", installed[1])
        self.assertEqual(
            _read_tlk_strings(game.lang_tlk), [""], "component 409 must stay TLK-neutral"
        )

        process = game.run("--force-uninstall-list", 409)
        self.assertNotIn("NOT UNINSTALLED", game.transcript(process))
        self.assertEqual(
            _raw_file_tree(game.override), tree_before_409,
            "uninstalling 409 must restore the pre-409 override byte-exactly",
        )

    def test_component_409_requires_the_407_listener(self) -> None:
        game = self._game()
        process = game.run("--force-install-list", 409)
        transcript = game.transcript(process)
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertIn("install the EEex specialization APR component (407) first", transcript)
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))

    def test_spec_apr_swap_406_to_407_in_one_run(self) -> None:
        """Rehearses the live migration: one WeiDU run uninstalls the
        CLSWPBON variant and installs the EEex variant."""
        game = self._game()
        clswpbon_pre = (game.override / "CLSWPBON.2DA").read_bytes()

        self._install(game, 406)
        self.assertNotEqual(
            (game.override / "CLSWPBON.2DA").read_bytes(), clswpbon_pre,
            "406 must actually change the table before the swap is meaningful",
        )

        process = game.run_raw(
            "--force-uninstall-list", "406", "--force-install-list", "407"
        )
        transcript = game.transcript(process)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript, transcript)
        self.assertEqual(
            (game.override / "CLSWPBON.2DA").read_bytes(), clswpbon_pre,
            "uninstalling 406 must restore CLSWPBON.2DA byte-exactly",
        )
        shipped = (game.override / "M_CBRAPR.lua").read_text(encoding="ascii")
        self.assertIn(f"local CBR_APR_TEMPUS_KIT = {EEEX_KIT_ID}", shipped)

        weidu_log = (game.root / "WeiDU.log").read_text(encoding="ascii", errors="replace")
        installed = [line for line in weidu_log.splitlines() if line.startswith("~")]
        self.assertEqual(len(installed), 1, weidu_log)
        self.assertIn("#407", installed[0])

    def test_component_408_chain_updates_texts_then_uninstalls(self) -> None:
        """408 on top of its four sibling artifacts: three appended TLK
        strings, three repoints, and an uninstall that restores the
        pre-408 override exactly (the appended strings legitimately stay)."""
        game = self._game()
        for component in (400, 404, 405, 407):
            self._install(game, component)
        pre_408 = _raw_file_tree(game.override)
        tlk_pre = _read_tlk_strings(game.lang_tlk)

        self._install(game, 408)
        strings = _read_tlk_strings(game.lang_tlk)
        self.assertEqual(len(strings), len(tlk_pre) + 3, "exactly three appended strings")
        kit_ref, hp_ref, cob_ref = len(tlk_pre), len(tlk_pre) + 1, len(tlk_pre) + 2
        self.assertIn("PRIEST OF TEMPUS", strings[kit_ref])
        self.assertIn("extra half attack per round", strings[kit_ref])
        self.assertIn("Tempus grants no future sight", strings[kit_ref])
        self.assertIn("A battle prayer to the Foehammer", strings[hp_ref])
        self.assertIn("tide of battle", strings[cob_ref])

        kitlist_rows = {
            tokens[1]: tokens
            for tokens in (
                line.split()
                for line in (game.override / "KITLIST.2DA")
                .read_text(encoding="ascii")
                .splitlines()
            )
            if len(tokens) == 10
        }
        self.assertEqual(kitlist_rows["OHTEMPUS"][4], str(kit_ref))
        self.assertEqual(kitlist_rows["TRUECLASS"][4], "0", "foreign rows untouched")
        for name, ref in (("OHTMPS1.SPL", hp_ref), ("OHTMPS2.SPL", cob_ref)):
            data = (game.override / name).read_bytes()
            self.assertEqual(struct.unpack_from("<i", data, 0x50)[0], ref, name)

        process = game.run("--force-uninstall-list", 408)
        transcript = game.transcript(process)
        self.assertNotIn("NOT UNINSTALLED", transcript, transcript)
        self.assertEqual(
            pre_408,
            _raw_file_tree(game.override),
            "uninstalling 408 must restore the pre-408 override byte-exactly",
        )
        self.assertEqual(
            len(_read_tlk_strings(game.lang_tlk)),
            len(tlk_pre) + 3,
            "appended TLK strings remain on uninstall (documented residue)",
        )

    def test_component_408_skips_without_sibling_artifacts(self) -> None:
        game = self._game()
        process = game.run("--force-install-list", 408)
        transcript = game.transcript(process)
        self.assertIn("SKIPPING", transcript, transcript)
        self.assertIn("weapon training component (400)", transcript)
        self.assertEqual(game.pre_override, _raw_file_tree(game.override))


if __name__ == "__main__":
    unittest.main()
