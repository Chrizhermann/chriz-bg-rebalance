"""Sweep override for op12 damage effects with Save-for-half flag but no save type.

Scans SPL and ITM feature-block tables. Reports:
  BUG:  special bit8 (save-for-half) set, savetype save bits (0-4) all clear
  INFO: op12 with a save bit set but save-for-half clear (full-negate save) -- not a bug, context only
"""
import struct, sys, os, glob

SAVE_BITS = 0x1F  # spell/breath/death/wand/poly

def scan(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    if len(data) < 0x72:
        return []
    sig = data[0:4]
    if sig not in (b"SPL ", b"ITM "):
        return []
    fx_off = struct.unpack_from("<I", data, 0x6A)[0]
    if fx_off == 0 or fx_off >= len(data):
        return []
    n = (len(data) - fx_off) // 48
    hits = []
    for i in range(n):
        eo = fx_off + i * 48
        opcode = struct.unpack_from("<H", data, eo)[0]
        if opcode != 12:
            continue
        savetype, savebonus, special = struct.unpack_from("<III", data, eo + 0x24)
        dice_n, dice_s = struct.unpack_from("<II", data, eo + 0x1C)
        p1, p2 = struct.unpack_from("<II", data, eo + 4)
        if (special & 0x100) and (savetype & SAVE_BITS) == 0:
            hits.append(f"{os.path.basename(path)} fx#{i}: {dice_n}d{dice_s}+{p1} dmgtype={p2>>16:#x} "
                        f"savetype={savetype:#x} special={special:#x} SAVE_FOR_HALF_NO_SAVETYPE")
    return hits

root = sys.argv[1]
total = 0
files = glob.glob(os.path.join(root, "*.spl")) + glob.glob(os.path.join(root, "*.SPL")) \
      + glob.glob(os.path.join(root, "*.itm")) + glob.glob(os.path.join(root, "*.ITM"))
seen = set()
for p in files:
    k = p.lower()
    if k in seen:
        continue
    seen.add(k)
    for h in scan(p):
        print(h)
        total += 1
print(f"-- scanned {len(seen)} files, {total} buggy effects")
