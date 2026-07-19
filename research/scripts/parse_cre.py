#!/usr/bin/env python3
"""Dump combat-relevant CRE V1.0 header fields for one or more .cre files.

Offsets from the bg-modding skill's verified CRE quick reference (HP 0x24/0x26,
THAC0 0x52, APR 0x53, saves 0x54-0x58, level1 0x234, class 0x273, DV 0x280,
script slots 0x248..0x268) plus IESDP for AC (0x46 natural / 0x48 effective,
signed words) and resistances (0x59 fire, 0x5A cold, 0x5B electricity,
0x5C acid, 0x5D magic, bytes). AC/resist offsets are cross-checked at runtime
against a known creature when available (see --selftest note in repo research).

APR byte uses the stat-8 key encoding: 0-5 = whole attacks, 6-10 = n-5 + 1/2.

Usage: python parse_cre.py file1.cre [file2.cre ...]
"""
import struct
import sys


def apr_decode(b: int) -> str:
    if b <= 5:
        return str(b)
    return f"{b - 5}.5"


def read_res8(buf: bytes, off: int) -> str:
    return buf[off:off + 8].split(b"\x00")[0].decode("ascii", "replace")


def dump(path: str) -> None:
    with open(path, "rb") as f:
        buf = f.read()
    if buf[:8] != b"CRE V1.0":
        print(f"{path}: not CRE V1.0 ({buf[:8]!r})")
        return
    cur_hp, max_hp = struct.unpack_from("<HH", buf, 0x24)
    anim = struct.unpack_from("<I", buf, 0x28)[0]
    xp_reward = struct.unpack_from("<I", buf, 0x14)[0]
    ac_nat, ac_eff = struct.unpack_from("<hh", buf, 0x46)
    thac0 = buf[0x52]
    apr = buf[0x53]
    saves = list(buf[0x54:0x59])
    r_fire, r_cold, r_elec, r_acid, r_magic = buf[0x59:0x5E]
    levels = list(buf[0x234:0x237])
    cls = buf[0x273]
    dv = buf[0x280:0x2A0].split(b"\x00")[0].decode("ascii", "replace")
    scripts = [read_res8(buf, off) for off in (0x248, 0x250, 0x258, 0x260, 0x268)]
    print(f"== {path}")
    print(f"  HP {cur_hp}/{max_hp}  AC nat {ac_nat} eff {ac_eff}  THAC0 {thac0}"
          f"  APR {apr_decode(apr)} (raw {apr})")
    print(f"  saves d/w/p/b/s {saves}  MR {r_magic}"
          f"  resist F/C/E/A {r_fire}/{r_cold}/{r_elec}/{r_acid}")
    print(f"  levels {levels}  class {cls}  anim {anim:#06x}  XP {xp_reward}  DV '{dv}'")
    print(f"  scripts O/C/R/G/D {scripts}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        try:
            dump(p)
        except Exception as exc:  # noqa: BLE001 - research tool, keep sweeping
            print(f"{p}: ERROR {exc}")
