"""Tests for the read-only SCS common-mage semantic audit."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from research.scripts import audit_scs_weapon_semantics


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "research" / "scripts" / "audit_scs_weapon_semantics.py"
SPELL_ID = 2808


FIRST_ROUND = """\
// compiled token 2808
IF
  !GlobalTimerNotExpired("castspell","LOCALS")
  HaveSpell(WIZARD_MOMENT_OF_PRESCIENCE)
  CheckStatLT(Myself,60,SPELLFAILUREMAGE)
  Global("instantprep","LOCALS",0)
  See(NearestEnemyOf(Myself))
THEN
  RESPONSE #100
    SetGlobalTimer("castspell","LOCALS",ONE_ROUND)
    Spell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)
    SetGlobal("instantprep","LOCALS",1)
    SetGlobalTimer("redefend","LOCALS",7)
END
"""

RENEWAL = """\
IF
  !GlobalTimerNotExpired("castspell","LOCALS")
  HaveSpell(WIZARD_MOMENT_OF_PRESCIENCE)
  CheckStatLT(Myself,60,SPELLFAILUREMAGE)
  !CheckStatGT(Myself,0,WIZARD_PROTECTION_FROM_MAGIC_WEAPONS)
  !CheckSpellState(Myself,TIME_STOP)
  !StateCheck(Myself,STATE_INVISIBLE)
  See(NearestEnemyOf(Myself))
  !GlobalTimerNotExpired("justdonepmw","LOCALS")
  Global("instantprep","LOCALS",1)
THEN
  RESPONSE #100
    SetGlobalTimer("castspell","LOCALS",ONE_ROUND)
    Spell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)
    SetGlobalTimer("redefend","LOCALS",7)
    SetGlobalTimer("justdonepmw","LOCALS",7)
END
"""

CHAIN_CONTINGENCY = """\
IF
  Global("ChainContingencyFired","LOCALS",0)
  Allegiance(Myself,ENEMY)
  OR(7)
    Detect(NearestEnemyOf(Myself))
    Range(Player1,20)
    Range(Player2,20)
    Range(Player3,20)
    Range(Player4,20)
    Range(Player5,20)
    Range(Player6,20)
  !StateCheck(Myself,STATE_REALLY_DEAD)
  OR(4)
    INI("DMWW_mage_prep_difficulty",0)
    INI("DMWW_mage_prep_difficulty",1)
    INI("DMWW_mage_prep_difficulty",2)
    INI("DMWW_mage_prep_difficulty",3)
  OR(2)
    !INI("DMWW_mage_prep_difficulty",0)
    DifficultyLT(HARD)
  OR(4)
    INI("DMWW_mage_prep_difficulty",0)
    INI("DMWW_mage_prep_difficulty",1)
    INI("DMWW_mage_prep_difficulty",2)
    Global("created_out_of_sight","LOCALS",1)
  OR(3)
    !INI("DMWW_mage_prep_difficulty",0)
    DifficultyLT(NORMAL)
    Global("created_out_of_sight","LOCALS",1)
  !GlobalGT("Chapter","GLOBAL",19)
THEN
  RESPONSE #100
    SetGlobal("ChainContingencyFired","LOCALS",1)
    ReallyForceSpellRES("dw#cc23",Myself)
    ReallyForceSpell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)
    Continue()
END
"""

UNKNOWN = """\
IF
  HaveSpell(WIZARD_MOMENT_OF_PRESCIENCE)
  Global("cbr_sentinel","LOCALS",0)
THEN
  RESPONSE #100
    DisplayStringHead(Myself,12345)
END
"""

NEAR_MATCH = FIRST_ROUND.replace(
    "    Spell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)\n",
    "    Spell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)\n"
    "    SetGlobal(\"cbr_extra\",\"LOCALS\",1)\n",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fake_weidu(root: Path) -> Path:
    """Create a process-level WeiDU stand-in with the positional decompile contract."""
    implementation = root / "fake_weidu.py"
    implementation.write_text(
        """\
import json
import os
import sys
from pathlib import Path

sources = [Path(value) for value in sys.argv[1:] if value.lower().endswith('.bcs')]
if len(sources) != 1:
    print('expected exactly one BCS input', file=sys.stderr)
    raise SystemExit(2)
source = sources[0]
log = Path(os.environ['CBR_FAKE_WEIDU_LOG'])
with log.open('a', encoding='utf-8', newline='\\n') as handle:
    handle.write(json.dumps({'cwd': str(Path.cwd()), 'source': str(source)}) + '\\n')
(Path.cwd() / (source.stem + '.baf')).write_bytes(source.read_bytes())
""",
        encoding="utf-8",
        newline="\n",
    )
    wrapper = root / "fake_weidu.cmd"
    wrapper.write_text(
        f'@echo off\r\n"{sys.executable}" "%~dp0fake_weidu.py" %*\r\n',
        encoding="ascii",
        newline="",
    )
    return wrapper


class AuditScsWeaponSemanticsTests(unittest.TestCase):
    def _make_tree(self, root: Path) -> tuple[Path, Path, Path]:
        game = root / "game"
        override = game / "override"
        override.mkdir(parents=True)

        (override / "dw#mg10.bcs").write_text(
            FIRST_ROUND
            + "\n"
            + RENEWAL
            + "\n"
            + CHAIN_CONTINGENCY
            + "\n"
            + UNKNOWN
            + "\n"
            + NEAR_MATCH,
            encoding="ascii",
            newline="\n",
        )
        (override / "DW#MG11.BCS").write_text(FIRST_ROUND, encoding="ascii", newline="\n")
        (override / "dw#mg12.bcs").write_text(
            FIRST_ROUND.replace("2808", "2707"), encoding="ascii", newline="\n"
        )
        (override / "dw#mgx.bcs").write_text(FIRST_ROUND, encoding="ascii", newline="\n")
        (override / "bheye.bcs").write_text(FIRST_ROUND, encoding="ascii", newline="\n")

        fake_log = root / "fake-weidu.jsonl"
        fake_weidu = _write_fake_weidu(root)
        return game, override, fake_weidu

    def test_audit_is_scoped_deterministic_and_leaves_sources_unchanged(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-audit-test-") as temporary:
            root = Path(temporary)
            game, override, fake_weidu = self._make_tree(root)
            fake_log = root / "fake-weidu.jsonl"
            snapshots = {
                path.name: (path.read_bytes(), _sha256(path))
                for path in override.iterdir()
                if path.is_file()
            }

            old_log = os.environ.get("CBR_FAKE_WEIDU_LOG")
            os.environ["CBR_FAKE_WEIDU_LOG"] = str(fake_log)
            try:
                first_output = root / "report-one.json"
                first_report = audit_scs_weapon_semantics.audit_scripts(
                    game_root=game,
                    override_dir=override,
                    weidu_path=fake_weidu,
                    spell_id=SPELL_ID,
                    output_path=first_output,
                )
                first_json = first_output.read_bytes()
                first_summary = first_output.with_suffix(".txt").read_bytes()

                second_output = root / "report-two.json"
                second_report = audit_scs_weapon_semantics.audit_scripts(
                    game_root=game,
                    override_dir=override,
                    weidu_path=fake_weidu,
                    spell_id=SPELL_ID,
                    output_path=second_output,
                )
            finally:
                if old_log is None:
                    os.environ.pop("CBR_FAKE_WEIDU_LOG", None)
                else:
                    os.environ["CBR_FAKE_WEIDU_LOG"] = old_log

            self.assertEqual(first_report, second_report)
            self.assertEqual(first_json, second_output.read_bytes())
            self.assertEqual(first_summary, second_output.with_suffix(".txt").read_bytes())
            self.assertEqual(
                first_report["totals"],
                {
                    "common_mage_scripts": 3,
                    "prefilter_candidates": 2,
                    "decompiled": 2,
                    "first_round": 2,
                    "renewal": 1,
                    "chain_contingency": 1,
                    "unknown_blocks": 2,
                },
            )
            self.assertEqual([entry["name"] for entry in first_report["scripts"]], ["dw#mg10.bcs", "DW#MG11.BCS"])
            self.assertEqual(first_report["scripts"][0]["contexts"], {
                "chain_contingency": [2],
                "first_round": [0],
                "renewal": [1],
                "unknown": [3, 4],
            })

            for name, (before_bytes, before_hash) in snapshots.items():
                path = override / name
                self.assertEqual(path.read_bytes(), before_bytes)
                self.assertEqual(_sha256(path), before_hash)
            self.assertFalse(any(override.glob("*.baf")))

            calls = [json.loads(line) for line in fake_log.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(calls), 4)
            for call in calls:
                cwd = Path(call["cwd"])
                self.assertNotEqual(cwd.resolve(), override.resolve())
                self.assertFalse(cwd.exists(), "TemporaryDirectory must clean decompile output")
                self.assertIn(Path(call["source"]).name.casefold(), {"dw#mg10.bcs", "dw#mg11.bcs"})

    def test_output_inside_game_is_rejected_before_decompile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cbr-audit-safety-") as temporary:
            root = Path(temporary)
            game, override, fake_weidu = self._make_tree(root)
            forbidden = game / "audit.json"

            with self.assertRaisesRegex(audit_scs_weapon_semantics.AuditError, "inside game"):
                audit_scs_weapon_semantics.audit_scripts(
                    game_root=game,
                    override_dir=override,
                    weidu_path=fake_weidu,
                    spell_id=SPELL_ID,
                    output_path=forbidden,
                )

            self.assertFalse(forbidden.exists())
            self.assertFalse((root / "fake-weidu.jsonl").exists())

    def test_every_installed_structural_family_is_classified_exactly(self) -> None:
        from tests.test_scs_weapon_semantics import _chain_family, _first_round_family

        for variable in (
            "DMWW_mage_difficulty",
            "DMWW_ascension_difficulty",
            "DMWW_beholder_difficulty",
        ):
            self.assertEqual(
                audit_scs_weapon_semantics._classify_block(
                    _first_round_family("difficulty", variable)
                ),
                "first_round",
            )
        self.assertEqual(
            audit_scs_weapon_semantics._classify_block(
                _first_round_family("chapter_range")
            ),
            "first_round",
        )
        for kind, helper, variable in (
            ("prep_low", "dw#cc25", "DMWW_mage_difficulty"),
            ("prep_high", "dw#cc15", "DMWW_mage_difficulty"),
            ("difficulty", "dw#cc0", "DMWW_mage_difficulty"),
            ("difficulty", "dw#cc19", "DMWW_beholder_difficulty"),
        ):
            self.assertEqual(
                audit_scs_weapon_semantics._classify_block(
                    _chain_family(kind, helper, variable)
                ),
                "chain_contingency",
            )
        self.assertEqual(
            audit_scs_weapon_semantics._classify_block(NEAR_MATCH), "unknown"
        )

    def test_cli_requires_explicit_inputs(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        for option in ("--game", "--override", "--weidu", "--spell-id", "--output"):
            self.assertIn(option, completed.stderr)


if __name__ == "__main__":
    unittest.main()
