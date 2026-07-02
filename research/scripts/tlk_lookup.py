"""Print name + description of SPL/ITM files via dialog.tlk lookup."""
import struct, sys

TLK = sys.argv[1]
with open(TLK, "rb") as f:
    tlk = f.read()
count = struct.unpack_from("<I", tlk, 0x0A)[0]
data_off = struct.unpack_from("<I", tlk, 0x0E)[0]

def strref(n):
    if n in (0xFFFFFFFF, 0) or n >= count:
        return f"<invalid {n}>"
    off, ln = struct.unpack_from("<II", tlk, 0x12 + 26 * n + 0x12)
    return tlk[data_off + off: data_off + off + ln].decode("utf-8", "replace")

for path in sys.argv[2:]:
    with open(path, "rb") as f:
        d = f.read()
    sig = d[0:4]
    name_u, name_i = struct.unpack_from("<II", d, 0x08)
    if sig == b"SPL ":
        desc = struct.unpack_from("<I", d, 0x50)[0]
    else:  # ITM
        desc_u, desc = struct.unpack_from("<II", d, 0x50)
    name = strref(name_i if name_i not in (0xFFFFFFFF,) and name_i < count else name_u)
    print(f"===== {path}")
    print(f"NAME: {name}")
    print(f"DESC: {strref(desc)}")
    print()
