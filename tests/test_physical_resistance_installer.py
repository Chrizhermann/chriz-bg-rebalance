"""Real WeiDU tests on disposable games, never on an installed playthrough.

Only component 310 is public. The proposed 95% variant is not an installer
feature: native physical-resistance clamping still needs separate work.
No test uninstalls or reinstalls an existing WeiDU entry.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_tempus_holy_power_installer import ONE_EMPTY_STRING_TLK, _write_key_and_bif


ROOT = Path(__file__).resolve().parents[1]
WEIDU = ROOT / "weidu.exe"
TP2 = "setup-chriz-bg-rebalance.tp2"
SYMBOL = "CBR_PHYSICAL_SOFTCAP"


def tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix().upper(): path.read_bytes()
        for path in root.rglob("*") if path.is_file()
    }


class ResistanceGame:
    def __init__(
        self, root: Path, *, states: str | None = "IDS V1.0\n0 NORMAL\n",
        eeex: bool = True, override_states: bool = False, bg2ee: bool = True,
    ) -> None:
        self.root = root
        self.root.mkdir()
        self.override = root / "override"
        self.override.mkdir()
        shutil.copy2(ROOT / TP2, root / TP2)
        shutil.copytree(ROOT / "chriz-bg-rebalance", root / "chriz-bg-rebalance")
        resources = [
            ("OH6000" if bg2ee else "AR0000", "ARE", b"synthetic game marker"),
            ("SPELL", "IDS", b"IDS V1.0\n1 EMPTY_SPELL\n"),
            ("STATS", "IDS", b"IDS V1.0\n1 MAXHITPOINTS\n"),
            ("KIT", "IDS", b"IDS V1.0\n0 TRUECLASS\n"),
            ("PROJECTL", "IDS", b"IDS V1.0\n1 NONE\n"),
        ]
        if states is not None:
            if override_states:
                (self.override / "SPLSTATE.IDS").write_text(states, encoding="ascii", newline="\n")
            else:
                resources.append(("SPLSTATE", "IDS", states.encode("ascii")))
        bif = _write_key_and_bif(root, tuple(resources))
        root_tlk = root / "dialog.tlk"
        game_tlk = root / "lang/en_us/dialog.tlk"
        game_tlk.parent.mkdir(parents=True)
        for path in (root_tlk, game_tlk):
            path.write_bytes(ONE_EMPTY_STRING_TLK)
        if eeex:
            (self.override / "M___EEex.lua").write_text("-- fixture bootstrap\n", encoding="ascii")
        (self.override / "SENTINEL.CRE").write_bytes(b"unrelated creature: must not change")
        (self.override / "SENTINEL.SPL").write_bytes(b"unrelated spell: must not change")
        self.before = tree(self.override)
        self.stable = {
            path: hashlib.sha256(path.read_bytes()).digest()
            for path in (root / "chitin.key", bif, root_tlk, game_tlk)
        }

    def install(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(WEIDU), TP2, "--game", str(self.root), "--force-install-list", "310",
             "--language", "0", "--use-lang", "en_US", "--no-exit-pause", "--quick-log"],
            cwd=self.root, capture_output=True, text=True, timeout=90, check=False,
        )

    def active_log(self) -> str:
        path = self.root / "WeiDU.log"
        if not path.exists():
            return ""
        return "\n".join(
            line for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if not line.lstrip().startswith("//")
        )

    def marker_rows(self) -> list[tuple[int, str]]:
        source = (self.override / "SPLSTATE.IDS").read_text(encoding="ascii")
        return [
            (int(value, 0), symbol.upper())
            for value, symbol in re.findall(r"(?m)^\s*(0x[\da-fA-F]+|\d+)\s+(\w+)", source)
            if symbol.upper() == SYMBOL
        ]


class PhysicalResistanceInstallerTests(unittest.TestCase):
    def game(self, **kwargs: object) -> ResistanceGame:
        temporary = tempfile.TemporaryDirectory(prefix="cbr-resistance-installer-")
        self.addCleanup(temporary.cleanup)
        return ResistanceGame(Path(temporary.name) / "game", **kwargs)

    def assert_stable(self, game: ResistanceGame) -> None:
        for path, digest in game.stable.items():
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), digest, str(path))

    def assert_success(self, game: ResistanceGame, expected_state: int) -> None:
        process = game.install()
        transcript = process.stdout + "\n" + process.stderr
        self.assertEqual(process.returncode, 0, transcript)
        self.assertIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertRegex(game.active_log(), r"(?m)#0\s+#310\b")
        self.assert_stable(game)
        after = tree(game.override)
        self.assertEqual(set(after), set(game.before) | {"SPLSTATE.IDS", "M_CBRRES.LUA"})
        for name, payload in game.before.items():
            if name != "SPLSTATE.IDS":
                self.assertEqual(after[name], payload, name)
        self.assertEqual(game.marker_rows(), [(expected_state, SYMBOL)])
        template = (ROOT / "chriz-bg-rebalance/lua/M_CBRRES.lua").read_text(encoding="ascii")
        expected = template.replace("%CBR_RES_CAP%", "90").replace("%CBR_RES_STATE%", str(expected_state))
        actual = (game.override / "M_CBRRES.lua").read_text(encoding="ascii")
        self.assertEqual(actual, expected)

    def assert_rejected(self, game: ResistanceGame, text: str) -> None:
        process = game.install()
        transcript = process.stdout + "\n" + process.stderr
        self.assertNotIn("SUCCESSFULLY INSTALLED", transcript)
        self.assertNotRegex(game.active_log(), r"(?m)#0\s+#310\b")
        self.assertIn(text.lower(), transcript.lower(), transcript)
        self.assertEqual(tree(game.override), game.before)
        self.assert_stable(game)

    def test_installs_only_runtime_and_private_marker(self) -> None:
        self.assert_success(self.game(), 255)

    def test_existing_override_state_table_is_preserved_except_new_row(self) -> None:
        states = "IDS V1.0\n0 NORMAL\n248 OTHER_STATE\n"
        game = self.game(states=states, override_states=True)
        self.assert_success(game, 255)
        self.assertTrue((game.override / "SPLSTATE.IDS").read_text(encoding="ascii").startswith(states))

    def test_occupied_preferred_state_uses_another_free_value(self) -> None:
        states = "IDS V1.0\n0 NORMAL\n255 OTHER_MOD\n254 ANOTHER_MOD\n"
        self.assert_success(self.game(states=states), 253)

    def test_existing_unique_private_marker_is_reused_without_duplicate_row(self) -> None:
        states = f"IDS V1.0\n0 NORMAL\n231 {SYMBOL}\n"
        game = self.game(states=states, override_states=True)
        self.assert_success(game, 231)
        self.assertEqual((game.override / "SPLSTATE.IDS").read_bytes(), game.before["SPLSTATE.IDS"])

    def test_production_helper_is_byte_stable_without_reinstalling_an_entry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-resistance-repeat-") as temporary:
            root = Path(temporary)
            resources = root / "resources"
            resources.mkdir()
            (resources / "SPLSTATE.IDS").write_text("IDS V1.0\n0 NORMAL\n", encoding="ascii")
            snapshots = []
            for run in (1, 2):
                # Each harness has its own fresh log/backup directory. Only its
                # resource input is shared; no existing entry gets reinstalled.
                work = root / f"run{run}"
                work.mkdir()
                library = ROOT / "chriz-bg-rebalance/lib"
                source = ["BACKUP ~backup~", "AUTHOR ~test~", "BEGIN ~helper idempotence~ DESIGNATED 0"]
                for name in ("tempus_holy_power.tpa", "tempus_spec_apr_eeex.tpa", "physical_resistance.tpa"):
                    source.append(f"INCLUDE ~{(library / name).as_posix()}~")
                source.extend([
                    "LAF cbr_apply_physical_resistance",
                    "  INT_VAR cap = 90",
                    f"  STR_VAR resource_dir = ~{resources.as_posix()}~",
                    f"    template_file = ~{(ROOT / 'chriz-bg-rebalance/lua/M_CBRRES.lua').as_posix()}~",
                    "END",
                ])
                harness = work / "harness.tp2"
                harness.write_text("\n".join(source) + "\n", encoding="ascii")
                process = subprocess.run(
                    [str(WEIDU), str(harness), "--nogame", "--force-install-list", "0",
                     "--no-exit-pause", "--quick-log"],
                    cwd=work, capture_output=True, text=True, timeout=90, check=False,
                )
                transcript = process.stdout + "\n" + process.stderr
                self.assertEqual(process.returncode, 0, transcript)
                self.assertIn("SUCCESSFULLY INSTALLED", transcript)
                self.assertNotIn("SUCCESSFULLY REMOVED", transcript)
                snapshots.append(tree(resources))
            self.assertEqual(snapshots[0], snapshots[1])
            self.assertEqual(set(snapshots[1]), {"SPLSTATE.IDS", "M_CBRRES.LUA"})

    def test_missing_eeex_rejects_before_writes(self) -> None:
        self.assert_rejected(self.game(eeex=False), "EEex")

    def test_unsupported_game_rejects_before_writes(self) -> None:
        self.assert_rejected(self.game(bg2ee=False), "BG2")

    def test_missing_spell_state_table_rejects_before_writes(self) -> None:
        self.assert_rejected(self.game(states=None), "SPLSTATE")

    def test_shared_private_marker_value_rejects_and_rolls_back(self) -> None:
        states = f"IDS V1.0\n0 NORMAL\n230 {SYMBOL}\n230 OTHER_MOD\n"
        self.assert_rejected(self.game(states=states), "collision")

    def test_duplicate_private_symbol_rejects_and_rolls_back(self) -> None:
        states = f"IDS V1.0\n0 NORMAL\n230 {SYMBOL}\n231 {SYMBOL}\n"
        self.assert_rejected(self.game(states=states), "collision")

    def test_out_of_range_private_marker_rejects_and_rolls_back(self) -> None:
        states = f"IDS V1.0\n0 NORMAL\n256 {SYMBOL}\n"
        self.assert_rejected(self.game(states=states), "collision")

    def test_exhausted_spell_state_space_rejects_and_rolls_back(self) -> None:
        states = "IDS V1.0\n" + "".join(f"{i} OTHER_{i}\n" for i in range(256))
        self.assert_rejected(self.game(states=states), "exhausted")

    def test_optional_ninety_five_is_not_published_as_an_installer_choice(self) -> None:
        self.assertNotRegex((ROOT / TP2).read_text(encoding="utf-8"), r"\bDESIGNATED\s+311\b")


if __name__ == "__main__":
    unittest.main()
