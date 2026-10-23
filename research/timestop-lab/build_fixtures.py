"""Build synthetic SPL V1 resources for the disposable Time Stop and Time Clocks labs.

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
The lab must measure actual native timing; these are not live-test results.

The Time Clocks lab (CBR_LAB_VARIANT=timeclocks) stages three more, CLOCK_FIXTURES: native Slow
(op40), Spell Revisions' Haste (SR 4.19 SPWI305: movement rate, half an attack and the Haste icon,
no op16) and a disease (op78 type 0 takes parameter 1 HP each second; here 2 HP for 8 seconds),
a periodic effect besides regeneration and poison. Until session n3 (2026-10-23) the disease had
parameter 1 = 0 and 20 seconds, which deals no damage, so sessions n1 and n2 could not see its
pulses (the type switch of CGameEffectDisease::ApplyEffect at 0x1401B1818, jump table 0x1401B1B28).

For its area cases it also stages AREA_FIXTURES: 5 crushing damage once (op12, timing 1), cast
on the instant projectile; a contingency that casts Magic Missile at whoever hits its bearer
(op232: parameter 1 = 1 LastHitter, parameter 2 = 0 HitBy, as the stock Fire Shield (Red)
BALSHLD.SPL and Studded Leather of Thorns LEAT23.ITM use it); +20 to-hit (op54), so the
caster's single round of attacks lands; a Time Stop of 15 seconds (op231, 30 encoded), long
enough for the caster to act during it; and -20 to saves vs. death (op33, a penalty as the
stock Doom SPPR113 gives -2), so a target cannot save against the stock Stinking Cloud (save
vs. death at +2).
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path
import stat
import struct
import sys

# Reuse the repository's tested SPL encoder without writing import caches.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))
from ie_formats import SplAbility, SplEffect, SplFile, make_spl  # noqa: E402


# resref, opcode, parameter1, parameter2, encoded duration in seconds.
FIXTURES = (
    ("CBRTBUF", 0, -2, 0, 6),
    ("CBRTREG", 98, 2, 3, 12),
    ("CBRTHST", 16, 0, 0, 20),
    ("CBRTIHS", 16, 0, 1, 20),
    ("CBRTSTP", 231, 0, 0, 12),
)

# resref, encoded duration in seconds, effects as (opcode, parameter1, parameter2).
CLOCK_FIXTURES = (
    ("CBRTSLW", 20, ((40, 0, 0),)),
    ("CBRTSRH", 20, ((176, 6, 0), (1, 6, 0), (142, 0, 38))),
    ("CBRTDIS", 8, ((78, 2, 0),)),
)

# resref, encoded duration in seconds, effects as (opcode, parameter1, parameter2, timing, resource).
AREA_FIXTURES = (
    ("CBRTDMG", 0, ((12, 5, 0, 1, ""),)),
    ("CBRTCON", 120, ((232, 1, 0, 0, "SPWI112"),)),
    ("CBRTHIT", 120, ((54, 20, 0, 0, ""),)),
    ("CBRTSTL", 30, ((231, 0, 0, 0, ""),)),
    ("CBRTSAV", 120, ((33, -20, 0, 0, ""),)),
)


def fixture_bytes() -> dict[str, bytes]:
    """Return complete resources; no files or native effects are touched."""
    result = {}
    specifications = [(resref, duration, ((opcode, parameter1, parameter2, 0, ""),))
                      for resref, opcode, parameter1, parameter2, duration in FIXTURES]
    clocks = [(resref, duration, tuple((*effect, 0, "") for effect in effects))
              for resref, duration, effects in CLOCK_FIXTURES]
    for resref, duration, effects in (*specifications, *clocks, *AREA_FIXTURES):
        effects = tuple(SplEffect(
            opcode=opcode,
            target=2,  # The single projectile target, not an area or caster list.
            parameter1=parameter1,
            parameter2=parameter2,
            timing=timing,
            duration=duration,
            resist_dispel=2,  # Explicitly ignore MR; no dispel confound in baseline.
            resource=resource,
        ) for opcode, parameter1, parameter2, timing, resource in effects)
        ability_raw = bytearray(0x28)
        ability_raw[0] = 1  # Standard spell form.
        struct.pack_into("<H", ability_raw, 0x02, 2)  # Spell ability location.
        ability_raw[0x0D] = 1  # One target.
        struct.pack_into("<H", ability_raw, 0x0E, 30)  # Range.
        ability = SplAbility(
            required_level=1,
            target=1,  # Living actor.
            projectile=1,  # Native instant projectile, no area resource.
            effects=effects,
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
    """Write only the named files, exclusively, after a full collision check."""
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
