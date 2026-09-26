"""Public-documentation contract for Emotion, Courage / Emotion, Hope (301)."""

from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SCOPE = ROOT / "docs" / "00-project-scope.md"
RESEARCH = ROOT / "research" / "11-emotion-hope-courage.md"
TRA = ROOT / "chriz-bg-rebalance" / "languages" / "english" / "setup.tra"
ASSET_DIR = ROOT / "chriz-bg-rebalance" / "resources" / "emotion_iwdee"


class EmotionHopeCourageDocsTests(unittest.TestCase):
    def test_readme_documents_component_behavior_compatibility_and_provenance(self) -> None:
        readme = README.read_text(encoding="utf-8")
        lower = readme.lower()
        normalized = re.sub(r"\s+", " ", lower)

        self.assertRegex(readme, r"(?m)^\|\s*301\s*\|.*Emotion, Courage.*Emotion, Hope")
        self.assertRegex(readme, r"(?m)^### Component 301 .*Emotion, Courage.*Emotion, Hope")
        for phrase in (
            "deliberately overwrites",
            "install it after IWDification, SCS, Spell Revisions",
            "A spell mod installed later can overwrite component 301 again",
            "last beneficial Emotion applied wins",
            "recasting the same spell refreshes it",
            "Courage grants +1 THAC0, +3 damage, and +5 Hit Points",
            "Hope grants +2 morale, +2 THAC0, +2 damage, and +2 to all saving throws",
            "allocates the missing spell dynamically in a normal level-four wizard slot",
            "private CBR learn-scroll",
            "mirrors their store entries",
            "donor scrolls remain guarded requirements",
            "a missing or ambiguous donor aborts the WeiDU transaction",
            "An existing spell with no discoverable learn-scroll is left without one",
            "does not add fixed area, creature, save, or spellbook edits",
            "original blue IWDEE A/B/C icons",
            "IWDEE's allies-only Emotion projectile",
            "point targeting, range 50, opcode 148 at caster level 10",
            "distribution anchors only",
            "final manual status-list retest remains",
            "original CBR code and English text",
        ):
            self.assertIn(phrase.lower(), normalized)

        for credit in ("IWDification", "Sword Coast Stratagems (SCS)"):
            self.assertIn(credit, readme)
        self.assertIn("research/11-emotion-hope-courage.md", readme)
        self.assertRegex(
            readme,
            r"(?m)^.*--force-install-list\s+(?:\d+\s+)*301\s+--language\b",
        )

    def test_scope_and_research_report_the_current_boundary(self) -> None:
        scope = SCOPE.read_text(encoding="utf-8")
        part3 = scope.split("## Part 3", 1)[1].split("## Part 4", 1)[0]
        self.assertIn("301 — Emotion, Courage / Emotion, Hope", part3)
        self.assertIn("candidate 300", part3)
        self.assertRegex(part3, r"\b310/311\b")
        self.assertRegex(part3, r"\b320\b")

        research = RESEARCH.read_text(encoding="utf-8")
        self.assertRegex(
            research,
            r"(?s)^# Research 11.*?\*\*Date:\*\* 2026-08-30 .*?\*\*Status:\*\* "
            r"delivery and mutual exclusion live-verified; status-list\s+correction\s+"
            r"automated-verified, manual retest pending",
        )
        self.assertIn(
            "The production installation at `C:\\Games\\Baldur's Gate II Enhanced Edition modded` "
            "and its\nactive saves remained read-only.",
            research,
        )
        self.assertRegex(
            research,
            r"final manual status-list retest remains\s+pending",
        )
        handover = (ROOT / "docs" / "handover.md").read_text(encoding="utf-8")
        self.assertIn("The earlier controlled result did not validate delivery", handover)
        self.assertRegex(
            handover,
            r"production\s+game and active playthrough stayed read-only",
        )
        for document in (scope, handover):
            self.assertRegex(
                document,
                r"(?is)(?:Emotion, Hopelessness.{0,100}unconditional|"
                r"unconditional.{0,100}Emotion, Hopelessness)",
            )
            for phrase in ("Fear", "Symbol", "save/MR"):
                self.assertIn(phrase, document)

    def test_translation_comment_and_shipped_asset_boundary_are_current(self) -> None:
        tra = TRA.read_text(encoding="utf-8")
        self.assertNotRegex(tra, r"(?i)component 404[^\n]*only TLK additions|only TLK additions[^\n]*this mod")
        self.assertRegex(tra, r"(?i)game-facing strings.*components? 301.*404")

        binary_suffixes = {
            ".SPL", ".ITM", ".STO", ".BAM", ".VVC", ".PRO", ".WAV", ".EFF"
        }
        shipped_binaries = [
            path
            for path in (ROOT / "chriz-bg-rebalance").rglob("*")
            if path.is_file() and path.suffix.upper() in binary_suffixes
        ]
        expected_names = {
            "#ARE_M21.WAV", "#EFF_E03.WAV", "#GENENCH.VVC", "ENCHANX.BAM",
            "IDPRO407.PRO", "SPWI427A.BAM", "SPWI427B.BAM", "SPWI427C.BAM",
            "SPWI427D.BAM", "SPWI429A.BAM", "SPWI429B.BAM", "SPWI429C.BAM",
            "SPWI429D.BAM",
        }
        self.assertEqual(expected_names, {path.name for path in shipped_binaries})
        self.assertTrue(all(path.parent == ASSET_DIR for path in shipped_binaries))
        provenance = (ASSET_DIR / "README.md").read_text(encoding="utf-8")
        normalized = re.sub(r"\s+", " ", provenance)
        self.assertIn("extracted with WeiDU from the user's pristine IWDEE installation", normalized)
        self.assertIn("No IWDification or SCS binary was copied", normalized)
        for path in shipped_binaries:
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            self.assertIn(f"`{path.name}` | `{digest}`", provenance)


if __name__ == "__main__":
    unittest.main()
