"""Build the synthetic SPL V1 resources for the disposable Time Stop lab.

Usage: python -B research/timestop-lab/build_fixtures.py ABSOLUTE_OUTPUT_DIRECTORY

The selected output directory's parent must exist. Existing fixture names are
never overwritten, including case-insensitive collisions. No game is inspected,
installed, launched, or changed unless its directory is explicitly selected as
the output by the caller. These are diagnostic resources, not a fix.

Native semantics checked against IESDP on 2026-09-26:
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op231
  Time Stop runs for half its encoded duration: 12 seconds requests 6 seconds.
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op98
  Regeneration type 3 with amount 2 restores one HP every two seconds.
Checked on 2026-10-25:
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op16
  Every Haste type sets STATE_HASTED; type 2 (weak) gives no attack bonus.
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op40
  Slow takes no parameters and cancels Haste.
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op310
  A nonzero stat value makes the target immune to Time Stop.
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op321
  Type 0 removes the named resource's effects of every timing mode.
https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op208 and #op175
  A minimum of 1 HP and a hold on any creature (EA.IDS ANYONE) keep a target
  alive and helpless, so every weapon swing at it hits.
Spell Revisions 4.19 rc5 builds its Haste (SPWI305) from movement rate (op176)
and attacks per round (op1) without op16; CBRTSRH has that shape.
The lab must measure actual native timing; these are not live-test results.
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
import stat
import struct
import sys
from typing import NamedTuple

# Reuse the repository's tested SPL encoder without writing import caches.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from ie_formats import SplAbility, SplEffect, SplFile, make_spl  # noqa: E402


class Effect(NamedTuple):
    opcode: int
    parameter1: int = 0
    parameter2: int = 0
    duration: int = 0  # Seconds.
    timing: int = 0  # 0: limited duration, 1: instant/permanent.
    resource: str = ""


# Five single-effect fixtures from the first captures; their bytes must not change.
FIXTURES = {
    "CBRTBUF": (Effect(0, -2, 0, 6),),
    "CBRTREG": (Effect(98, 2, 3, 12),),
    "CBRTHST": (Effect(16, 0, 0, 20),),
    "CBRTIHS": (Effect(16, 0, 1, 20),),
    "CBRTSTP": (Effect(231, 0, 0, 12),),
    "CBRTWHS": (Effect(16, 0, 2, 20),),  # Weak Haste.
    "CBRTSRH": (Effect(176, 6, 0, 20), Effect(1, 6, 0, 20), Effect(142, 0, 38, 20)),  # SR-shaped Haste.
    "CBRTSLW": (Effect(40, 0, 0, 20),),
    "CBRTTSI": (Effect(310, 0, 1, 40),),  # Time Stop immunity.
    "CBRTRMB": (Effect(321, 0, 0, 0, 1, "CBRTBUF"),),
    "CBRTRMR": (Effect(321, 0, 0, 0, 1, "CBRTREG"),),
    "CBRTDUM": (Effect(208, 1, 0, 900), Effect(175, 0, 2, 900)),  # Weapon-hit dummy.
}


def fixture_bytes() -> dict[str, bytes]:
    """Return complete resources; no files or native effects are touched."""
    result = {}
    for resref, effects in FIXTURES.items():
        encoded = tuple(
            SplEffect(
                opcode=effect.opcode,
                target=2,  # The single projectile target, not an area or caster list.
                parameter1=effect.parameter1,
                parameter2=effect.parameter2,
                timing=effect.timing,
                duration=effect.duration,
                resist_dispel=2,  # Explicitly ignore MR; no dispel confound in baseline.
                resource=effect.resource,
            )
            for effect in effects
        )
        ability_raw = bytearray(0x28)
        ability_raw[0] = 1  # Standard spell form.
        struct.pack_into("<H", ability_raw, 0x02, 2)  # Spell ability location.
        ability_raw[0x0D] = 1  # One target.
        struct.pack_into("<H", ability_raw, 0x0E, 30)  # Range.
        ability = SplAbility(
            required_level=1,
            target=1,  # Living actor.
            projectile=1,  # Native instant projectile, no area resource.
            effects=encoded,
            raw=bytes(ability_raw),
        )
        spell = make_spl((ability,))
        header = bytearray(spell.header_raw)
        for offset in (0x08, 0x0C, 0x50, 0x54):
            struct.pack_into("<i", header, offset, -1)  # No TLK dependency.
        struct.pack_into("<H", header, 0x1C, 1)  # Wizard; never learned by fixture.
        struct.pack_into("<H", header, 0x22, 0xFFFF)  # No casting graphics.
        struct.pack_into("<I", header, 0x34, 1)  # Spell level 1.
        payload = dataclasses.replace(spell, header_raw=bytes(header)).to_bytes()
        SplFile.from_bytes(payload)  # Reject structural encoder errors before I/O.
        result[f"{resref}.SPL"] = payload
    return result


def _reject_linked_path(path: Path) -> None:
    for candidate in (*reversed(path.parents), path):
        try:
            metadata = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) or (
            getattr(metadata, "st_file_attributes", 0)
            & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise ValueError(f"linked/reparse output path rejected: {candidate}")


def build_fixtures(output_directory: Path | str) -> tuple[Path, ...]:
    """Write only the named fixture files, exclusively, after a full collision check."""
    output = Path(output_directory)
    if not output.is_absolute() or ".." in output.parts:
        raise ValueError("output directory must be an absolute path without '..'")
    _reject_linked_path(output)
    if not output.parent.is_dir():
        raise ValueError("output directory's parent must already exist")
    if output.exists() and not output.is_dir():
        raise ValueError("output destination is not a directory")
    resources = fixture_bytes()
    existing = {entry.name.casefold() for entry in output.iterdir()} if output.exists() else set()
    collisions = [name for name in resources if name.casefold() in existing]
    if collisions:
        raise FileExistsError("fixture output already exists: " + ", ".join(collisions))
    output.mkdir(exist_ok=True)
    written = []
    for name, payload in resources.items():
        path = output / name
        with path.open("xb") as handle:
            handle.write(payload)
        written.append(path)
    return tuple(written)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    try:
        for path in build_fixtures(args.output_directory):
            print(path)
    except (OSError, ValueError) as error:
        parser.exit(1, f"CBR_FIXTURE_ERROR: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
