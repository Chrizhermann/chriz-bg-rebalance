#!/usr/bin/env python3
"""Add a for-sale item to a store cached inside save-game BALDUR.SAV containers.

Scan mode (default): report, per save, whether the store is cached and whether it
already sells the item. Apply mode (--apply): for saves where the store is cached
without the item, insert a sale entry (end of sale array, header offsets fixed up),
rebuild the SAV, and keep a .bak-<tag> backup of the original.

Usage:
  python patch_sav_store.py <save-root> <store.sto> <itemres> <amount>
                            [--apply] [--tag cbr101] [--exclude <substring>]

--exclude skips save folders whose name contains the substring (e.g. the interval-save
slots a running game session rewrites every few minutes).

SAV V1.0 container: 8-byte sig, then per entry: dword filename length (incl. NUL),
filename, dword uncompressed size, dword compressed size, zlib stream. No count field.
STO V1.0: sale offset @0x34, count @0x38; purchases @0x2C/0x30, drinks @0x4C/0x50,
cures @0x70/0x74. Sale entry (0x1C): resref(8) wear(2) charges1-3(2 each) flags(4)
amount(4) infinite(4).
"""
import os
import struct
import sys
import zlib

SALE_ENTRY = 0x1C


def parse_sav(data):
    assert data[0:8] == b"SAV V1.0", f"bad SAV sig {data[0:8]!r}"
    entries = []
    pos = 8
    while pos < len(data):
        (nlen,) = struct.unpack_from("<I", data, pos)
        pos += 4
        name = data[pos : pos + nlen].split(b"\0")[0].decode("ascii")
        pos += nlen
        usize, csize = struct.unpack_from("<II", data, pos)
        pos += 8
        blob = data[pos : pos + csize]
        pos += csize
        entries.append([name, usize, blob])
    return entries


def build_sav(entries):
    out = [b"SAV V1.0"]
    for name, usize, blob in entries:
        nbytes = name.encode("ascii") + b"\0"
        out.append(struct.pack("<I", len(nbytes)))
        out.append(nbytes)
        out.append(struct.pack("<II", usize, len(blob)))
        out.append(blob)
    return b"".join(out)


def sto_find_item(sto, itemres):
    sale_off, sale_cnt = struct.unpack_from("<II", sto, 0x34)
    for i in range(sale_cnt):
        off = sale_off + SALE_ENTRY * i
        res = sto[off : off + 8].split(b"\0")[0].decode("ascii", "replace")
        if res.upper() == itemres.upper():
            flags, amount, infinite = struct.unpack_from("<III", sto, off + 0x10)
            return {"index": i, "amount": amount, "infinite": infinite}
    return None


def sto_add_item(sto, itemres, amount):
    """Insert sale entry at end of sale array; shift section offsets >= insertion."""
    sale_off, sale_cnt = struct.unpack_from("<II", sto, 0x34)
    ins = sale_off + SALE_ENTRY * sale_cnt
    entry = struct.pack(
        "<8sHHHHIII", itemres.upper().encode("ascii"), 0, 1, 0, 0, 1, amount, 0
    )
    out = bytearray(sto[:ins] + entry + sto[ins:])
    struct.pack_into("<I", out, 0x38, sale_cnt + 1)
    for field in (0x2C, 0x4C, 0x70):  # purchases, drinks, cures offsets
        (off,) = struct.unpack_from("<I", out, field)
        if off >= ins:
            struct.pack_into("<I", out, field, off + SALE_ENTRY)
    return bytes(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply_mode = "--apply" in sys.argv
    tag = "cbr101"
    if "--tag" in sys.argv:
        tag = sys.argv[sys.argv.index("--tag") + 1]
    exclude = sys.argv[sys.argv.index("--exclude") + 1] if "--exclude" in sys.argv else None
    root, store_name, itemres, amount = args[0], args[1], args[2], int(args[3])

    for savedir in sorted(os.listdir(root)):
        if exclude and exclude.lower() in savedir.lower():
            print(f"{savedir}: EXCLUDED")
            continue
        sav_path = os.path.join(root, savedir, "BALDUR.SAV")
        if not os.path.exists(sav_path):
            continue
        data = open(sav_path, "rb").read()
        try:
            entries = parse_sav(data)
        except AssertionError as e:
            print(f"{savedir}: SKIP ({e})")
            continue
        hit = None
        for e in entries:
            if e[0].upper() == store_name.upper():
                hit = e
                break
        if hit is None:
            print(f"{savedir}: store not cached (override version applies)")
            continue
        sto = zlib.decompress(hit[2])
        assert len(sto) == hit[1], f"{savedir}: uncompressed size mismatch"
        found = sto_find_item(sto, itemres)
        if found:
            print(
                f"{savedir}: cached, {itemres} present "
                f"(amount={found['amount']} infinite={found['infinite']})"
            )
            continue
        if not apply_mode:
            print(f"{savedir}: cached, {itemres} MISSING -> would patch")
            continue
        new_sto = sto_add_item(sto, itemres, amount)
        # verify before writing anything
        check = sto_find_item(new_sto, itemres)
        assert check and check["amount"] == amount, "self-check failed"
        assert len(new_sto) == len(sto) + SALE_ENTRY
        hit[1] = len(new_sto)
        hit[2] = zlib.compress(new_sto, 9)
        rebuilt = build_sav(entries)
        parse_sav(rebuilt)  # structural roundtrip check
        bak = sav_path + f".bak-{tag}"
        if not os.path.exists(bak):
            os.replace(sav_path, bak)
        else:
            os.remove(sav_path)
        open(sav_path, "wb").write(rebuilt)
        print(f"{savedir}: PATCHED ({itemres} x{amount} added; backup {os.path.basename(bak)})")


if __name__ == "__main__":
    main()
