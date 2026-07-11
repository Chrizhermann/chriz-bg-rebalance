#!/usr/bin/env python3
"""Dump an Infinity Engine STO V1.0 file: header, purchased categories, items for sale.

Usage: python parse_sto.py <file.sto> [...]

Sale-item struct (0x1C bytes): resref(8) wear(2) charge1(2) charge2(2) charge3(2)
flags(4: 1=identified 2=unstealable 4=stolen 8=undroppable) amount(4) infinite(4).
"""
import struct
import sys


def dump(path: str) -> None:
    with open(path, "rb") as f:
        data = f.read()
    sig, ver = data[0:4], data[4:8]
    print(f"== {path} ({len(data)} bytes) sig={sig!r} ver={ver!r}")
    if sig != b"STOR":
        print("   not a STO file, skipping")
        return
    stype = struct.unpack_from("<I", data, 0x08)[0]
    name = struct.unpack_from("<I", data, 0x0C)[0]
    buy_off, buy_cnt = struct.unpack_from("<II", data, 0x2C)
    sale_off, sale_cnt = struct.unpack_from("<II", data, 0x34)
    print(f"   type={stype} name_strref={name}")
    print(f"   purchases: off=0x{buy_off:x} cnt={buy_cnt}  sale: off=0x{sale_off:x} cnt={sale_cnt}")
    for i in range(buy_cnt):
        (cat,) = struct.unpack_from("<I", data, buy_off + 4 * i)
        print(f"   buys category {cat}")
    for i in range(sale_cnt):
        off = sale_off + 0x1C * i
        resref = data[off : off + 8].split(b"\0")[0].decode("ascii", "replace")
        wear, c1, c2, c3 = struct.unpack_from("<HHHH", data, off + 8)
        flags, amount, infinite = struct.unpack_from("<III", data, off + 0x10)
        print(
            f"   [{i:3}] {resref:<8} charges={c1}/{c2}/{c3} flags=0x{flags:x} "
            f"amount={amount} infinite={infinite}"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for p in sys.argv[1:]:
        dump(p)
