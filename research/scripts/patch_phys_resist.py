"""Set physical-resistance (op 86/87/88/89) parameter1 in SPL feature blocks.

Usage: patch_phys_resist.py <file.spl> <old> <new>

Walks every 48-byte feature block from the header's feature-block offset
(0x6A) to EOF and rewrites parameter1 for blocks with opcode in
{86 slashing, 87 crushing, 88 piercing, 89 missile} whose current
parameter1 == <old>. Only the four param1 dwords per ability change;
nothing else in the file is touched. Used for the 2026-08-19 live
Hardiness hotfix (research/06) and reusable to verify component 200.
"""
import struct
import sys

PHYS = {86: "slashing", 87: "crushing", 88: "piercing", 89: "missile"}


def patch(path, old, new):
    with open(path, "rb") as f:
        data = bytearray(f.read())
    assert data[0:8] == b"SPL V1  ", f"{path}: not SPL V1"
    fx_off = struct.unpack_from("<I", data, 0x6A)[0]
    tail = len(data) - fx_off
    assert tail % 48 == 0, f"{path}: feature-block region not a multiple of 48"
    hits = 0
    for i in range(tail // 48):
        eo = fx_off + i * 48
        op = struct.unpack_from("<H", data, eo)[0]
        p1 = struct.unpack_from("<I", data, eo + 4)[0]
        if op in PHYS and p1 == old:
            struct.pack_into("<I", data, eo + 4, new)
            timing = data[eo + 0x0C]
            print(f"  fx#{i} op={op} ({PHYS[op]}) timing={timing}: {old} -> {new}")
            hits += 1
    with open(path, "wb") as f:
        f.write(data)
    print(f"{path}: patched {hits} effects")
    return hits


if __name__ == "__main__":
    patch(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
