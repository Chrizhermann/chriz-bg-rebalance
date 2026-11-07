#!/usr/bin/env python3
"""Write decided stock to a store cached inside save-game BALDUR.SAV containers.

Scan mode (default): report, per save, whether the store is cached and whether it
already sells the item. Apply mode (--apply): write one owned sale entry, replacing
any previous stock for that item, rebuild the SAV, and keep a .bak-<tag> backup
of the original. Other sale entries and compressed resources are preserved.

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
import argparse
import os
import struct
import tempfile
import zlib
from pathlib import Path

SALE_ENTRY = 0x1C


def parse_sav(data):
    if data[:8] != b"SAV V1.0":
        raise ValueError("unreadable SAV header")
    entries = []
    pos = 8
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError("truncated SAV filename length")
        (nlen,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if nlen == 0 or pos + nlen + 8 > len(data):
            raise ValueError("truncated SAV entry header")
        name = data[pos : pos + nlen].split(b"\0")[0].decode("ascii", "surrogateescape")
        pos += nlen
        usize, csize = struct.unpack_from("<II", data, pos)
        pos += 8
        if csize > len(data) - pos:
            raise ValueError("truncated SAV compressed resource")
        blob = data[pos : pos + csize]
        pos += csize
        entries.append([name, usize, blob])
    return entries


def build_sav(entries):
    out = [b"SAV V1.0"]
    for name, usize, blob in entries:
        nbytes = name.encode("ascii", "surrogateescape") + b"\0"
        out.append(struct.pack("<I", len(nbytes)))
        out.append(nbytes)
        out.append(struct.pack("<II", usize, len(blob)))
        out.append(blob)
    return b"".join(out)


def sale_layout(sto):
    if len(sto) < 0x78:
        raise ValueError("truncated store header")
    sale_off, sale_cnt = struct.unpack_from("<II", sto, 0x34)
    if sale_cnt == 0 and sale_off == 0:
        sale_off = len(sto)
    if sale_off < 0x78 or sale_off + SALE_ENTRY * sale_cnt > len(sto):
        raise ValueError("unreadable store sale array")
    return sale_off, sale_cnt


def item_name(entry):
    return entry[:8].split(b"\0")[0].decode("ascii", "surrogateescape").upper()


def sto_find_item(sto, itemres):
    sale_off, sale_cnt = sale_layout(sto)
    for i in range(sale_cnt):
        off = sale_off + SALE_ENTRY * i
        if item_name(sto[off : off + SALE_ENTRY]) == itemres.upper():
            flags, amount, infinite = struct.unpack_from("<III", sto, off + 0x10)
            return {"index": i, "amount": amount, "infinite": infinite}
    return None


def sto_add_item(sto, itemres, amount):
    """Write one owned sale entry, with offsets adjusted when the array grows/shrinks."""
    sale_off, sale_cnt = sale_layout(sto)
    sale_end = sale_off + SALE_ENTRY * sale_cnt
    entry = struct.pack(
        "<8sHHHHIII", itemres.upper().encode("ascii"), 0, 1, 0, 0, 1, amount, 0
    )
    rows = []
    written = False
    for off in range(sale_off, sale_end, SALE_ENTRY):
        old = sto[off : off + SALE_ENTRY]
        if item_name(old) == itemres.upper():
            if not written:
                rows.append(entry)
                written = True
        else:
            rows.append(old)
    if not written:
        rows.append(entry)
    delta = (len(rows) - sale_cnt) * SALE_ENTRY
    out = bytearray(sto[:sale_off] + b"".join(rows) + sto[sale_end:])
    struct.pack_into("<II", out, 0x34, sale_off, len(rows))
    for field in (0x2C, 0x4C, 0x70):  # purchases, drinks, cures offsets
        (off,) = struct.unpack_from("<I", out, field)
        if off >= sale_end:
            struct.pack_into("<I", out, field, off + delta)
    return bytes(out)


def replace_save(path, original, rebuilt, tag):
    """Keep the first backup; publish only a completely written replacement."""
    backup = path.with_name(path.name + f".bak-{tag}")
    try:
        with backup.open("xb") as stream:
            stream.write(original)
    except FileExistsError:
        pass
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".cbr-stock-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(rebuilt)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return backup.name


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("store_name")
    parser.add_argument("itemres")
    parser.add_argument("amount", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--tag", default="cbr101")
    parser.add_argument("--exclude")
    args = parser.parse_args(argv)
    if not (args.itemres.isascii() and 1 <= len(args.itemres) <= 8):
        parser.error("itemres must contain 1 to 8 ASCII characters")
    if not 0 <= args.amount <= 0xFFFFFFFF:
        parser.error("amount must fit an unsigned 32-bit stock field")
    if not args.tag or any(c in args.tag for c in '/\\:\0'):
        parser.error("tag must be a filename suffix")

    for savedir in sorted(os.listdir(args.root)):
        if args.exclude and args.exclude.lower() in savedir.lower():
            print(f"{savedir}: EXCLUDED")
            continue
        sav_path = args.root / savedir / "BALDUR.SAV"
        if not sav_path.is_file():
            continue
        try:
            data = sav_path.read_bytes()
            entries = parse_sav(data)
        except (OSError, ValueError) as e:
            print(f"{savedir}: cannot read this save ({e})")
            continue
        hits = [e for e in entries if e[0].upper() == args.store_name.upper()]
        if not hits:
            print(f"{savedir}: store not cached (override version applies)")
            continue
        patched = False
        for hit in hits:
            try:
                sto = zlib.decompress(hit[2])
                found = sto_find_item(sto, args.itemres)
                if not args.apply:
                    detail = "missing" if not found else f"amount={found['amount']} infinite={found['infinite']}"
                    print(f"{savedir}: cached, {args.itemres} {detail}; would write x{args.amount}")
                    continue
                new_sto = sto_add_item(sto, args.itemres, args.amount)
            except (ValueError, zlib.error) as e:
                print(f"{savedir}: cannot read cached {hit[0]} ({e})")
                continue
            # The actual decompressed payload is authoritative, including its size.
            hit[1] = len(new_sto)
            hit[2] = zlib.compress(new_sto, 9)
            patched = True
        if patched:
            try:
                backup = replace_save(sav_path, data, build_sav(entries), args.tag)
                print(f"{savedir}: PATCHED ({args.itemres} x{args.amount}; backup {backup})")
            except OSError as e:
                print(f"{savedir}: could not write this save ({e})")


if __name__ == "__main__":
    main()
