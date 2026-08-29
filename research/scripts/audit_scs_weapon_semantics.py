"""Read-only semantic audit for SCS common-mage weapon-defense blocks.

The installed BCS files are treated as immutable inputs.  Each candidate is
decompiled in its own temporary directory and classified from the resulting
BAF text; only the requested report files are written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable


COMMON_MAGE_RE = re.compile(r"^dw#mg[0-9]+\.bcs$", re.IGNORECASE)
SPELL_ALIASES = (
    "WIZARD_MOMENT_OF_PRESCIENCE",
    "WIZARD_IMPROVED_MANTLE",
)


class AuditError(RuntimeError):
    """Raised when the audit cannot proceed without violating its contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _validate_inputs(
    game_root: Path,
    override_dir: Path,
    weidu_path: Path,
    spell_id: int,
    output_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    game_root = game_root.resolve()
    override_dir = override_dir.resolve()
    weidu_path = weidu_path.resolve()
    output_path = output_path.resolve()
    summary_path = output_path.with_suffix(".txt")

    if not game_root.is_dir():
        raise AuditError(f"game root is not a directory: {game_root}")
    if not override_dir.is_dir():
        raise AuditError(f"override directory is not a directory: {override_dir}")
    if not weidu_path.is_file():
        raise AuditError(f"WeiDU executable does not exist: {weidu_path}")
    if spell_id <= 0:
        raise AuditError("spell ID must be a positive integer")
    if not output_path.parent.is_dir():
        raise AuditError(f"output directory does not exist: {output_path.parent}")
    if _is_within(output_path, game_root) or _is_within(summary_path, game_root):
        raise AuditError("report output must not be inside game directory")
    if output_path.exists() or summary_path.exists():
        raise AuditError("report output already exists")

    return game_root, override_dir, weidu_path, output_path, summary_path


def _split_blocks(source: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] | None = None
    for line in source.splitlines():
        marker = line.strip().upper()
        if current is None:
            if marker == "IF":
                current = [line]
            continue
        current.append(line)
        if marker == "END":
            blocks.append("\n".join(current))
            current = None
    return blocks


def _contains_alias(block: str) -> bool:
    upper = block.upper()
    return any(alias in upper for alias in SPELL_ALIASES)


def _has(pattern: str, block: str) -> bool:
    return re.search(pattern, block, flags=re.IGNORECASE | re.MULTILINE) is not None


def _classify_block(block: str) -> str:
    alias = r"(?:WIZARD_MOMENT_OF_PRESCIENCE|WIZARD_IMPROVED_MANTLE)"

    is_chain = all(
        (
            _has(r'Global\(\s*"ChainContingencyFired"\s*,\s*"LOCALS"\s*,\s*0\s*\)', block),
            _has(r'SetGlobal\(\s*"ChainContingencyFired"\s*,\s*"LOCALS"\s*,\s*1\s*\)', block),
            _has(r'ReallyForceSpellRES\(\s*"dw#cc[^"\r\n]*"\s*,\s*Myself\s*\)', block),
            _has(rf'ReallyForceSpell\(\s*Myself\s*,\s*{alias}\s*\)', block),
            _has(r'Continue\(\s*\)', block),
        )
    )
    if is_chain:
        return "chain_contingency"

    is_renewal = all(
        (
            _has(rf'HaveSpell\(\s*{alias}\s*\)', block),
            _has(r'Global\(\s*"instantprep"\s*,\s*"LOCALS"\s*,\s*1\s*\)', block),
            _has(
                r'!CheckStatGT\(\s*Myself\s*,\s*0\s*,\s*'
                r'WIZARD_PROTECTION_FROM_MAGIC_WEAPONS\s*\)',
                block,
            ),
            _has(rf'Spell\(\s*Myself\s*,\s*{alias}\s*\)', block),
            _has(r'SetGlobalTimer\(\s*"justdonepmw"\s*,\s*"LOCALS"\s*,\s*7\s*\)', block),
        )
    ) and not _has(r"ReallyForceSpell", block)
    if is_renewal:
        return "renewal"

    is_first_round = all(
        (
            _has(rf'HaveSpell\(\s*{alias}\s*\)', block),
            _has(r'Global\(\s*"instantprep"\s*,\s*"LOCALS"\s*,\s*0\s*\)', block),
            _has(rf'Spell\(\s*Myself\s*,\s*{alias}\s*\)', block),
            _has(r'SetGlobal\(\s*"instantprep"\s*,\s*"LOCALS"\s*,\s*1\s*\)', block),
        )
    ) and not _has(r"ReallyForceSpell", block)
    if is_first_round:
        return "first_round"

    return "unknown"


def _find_decompiled_baf(directory: Path, source: Path) -> Path:
    expected = f"{source.stem}.baf".casefold()
    matches = [path for path in directory.iterdir() if path.name.casefold() == expected]
    if len(matches) != 1:
        raise AuditError(
            f"WeiDU did not produce exactly one {source.stem}.baf for {source.name}"
        )
    return matches[0]


def _decompile(game_root: Path, weidu_path: Path, source: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="cbr-scs-audit-") as temporary:
        scratch = Path(temporary)
        completed = subprocess.run(
            [
                str(weidu_path),
                "--game",
                str(game_root),
                str(source),
                "--no-exit-pause",
            ],
            cwd=scratch,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout).strip()
            raise AuditError(
                f"WeiDU failed to decompile {source.name} (exit {completed.returncode}): "
                f"{details}"
            )
        return _find_decompiled_baf(scratch, source).read_text(
            encoding="utf-8", errors="replace"
        )


def _summary_lines(report: dict[str, object]) -> Iterable[str]:
    totals = report["totals"]
    assert isinstance(totals, dict)
    yield f"SCS common-mage semantic audit (spell ID {report['spell_id']})"
    yield ""
    for name in (
        "common_mage_scripts",
        "prefilter_candidates",
        "decompiled",
        "first_round",
        "renewal",
        "chain_contingency",
        "unknown_blocks",
    ):
        yield f"{name}: {totals[name]}"
    yield ""
    yield "Scripts:"
    scripts = report["scripts"]
    assert isinstance(scripts, list)
    for entry in scripts:
        assert isinstance(entry, dict)
        contexts = entry["contexts"]
        assert isinstance(contexts, dict)
        rendered = ", ".join(
            f"{name}={contexts[name]}"
            for name in ("first_round", "renewal", "chain_contingency", "unknown")
        )
        yield f"- {entry['name']}: {rendered}"


def audit_scripts(
    *,
    game_root: Path,
    override_dir: Path,
    weidu_path: Path,
    spell_id: int,
    output_path: Path,
) -> dict[str, object]:
    """Audit installed SCS common-mage scripts without writing to the game."""
    game_root, override_dir, weidu_path, output_path, summary_path = _validate_inputs(
        Path(game_root),
        Path(override_dir),
        Path(weidu_path),
        int(spell_id),
        Path(output_path),
    )

    common_scripts = sorted(
        (
            path
            for path in override_dir.iterdir()
            if path.is_file() and COMMON_MAGE_RE.fullmatch(path.name)
        ),
        key=lambda path: path.name.casefold(),
    )
    token = str(spell_id).encode("ascii")
    candidates = [path for path in common_scripts if token in path.read_bytes()]

    entries: list[dict[str, object]] = []
    totals = {
        "common_mage_scripts": len(common_scripts),
        "prefilter_candidates": len(candidates),
        "decompiled": 0,
        "first_round": 0,
        "renewal": 0,
        "chain_contingency": 0,
        "unknown_blocks": 0,
    }
    for source in candidates:
        baf = _decompile(game_root, weidu_path, source)
        totals["decompiled"] += 1
        contexts = {
            "chain_contingency": [],
            "first_round": [],
            "renewal": [],
            "unknown": [],
        }
        relevant_index = 0
        for block in _split_blocks(baf):
            if not _contains_alias(block):
                continue
            classification = _classify_block(block)
            contexts[classification].append(relevant_index)
            relevant_index += 1
            if classification == "unknown":
                totals["unknown_blocks"] += 1
            else:
                totals[classification] += 1
        entries.append(
            {
                "name": source.name,
                "sha256": _sha256(source),
                "contexts": contexts,
            }
        )

    report: dict[str, object] = {
        "schema": 1,
        "spell_id": spell_id,
        "totals": totals,
        "scripts": entries,
    }
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary_path.write_text(
        "\n".join(_summary_lines(report)) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path, help="read-only game root")
    parser.add_argument("--override", required=True, type=Path, help="read-only override")
    parser.add_argument("--weidu", required=True, type=Path, help="WeiDU executable")
    parser.add_argument("--spell-id", required=True, type=int, help="numeric spell.ids ID")
    parser.add_argument("--output", required=True, type=Path, help="JSON report outside game")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = audit_scripts(
            game_root=args.game,
            override_dir=args.override,
            weidu_path=args.weidu,
            spell_id=args.spell_id,
            output_path=args.output,
        )
    except (AuditError, OSError, ValueError) as error:
        print(f"audit failed: {error}", file=sys.stderr)
        return 1
    print("\n".join(_summary_lines(report)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
