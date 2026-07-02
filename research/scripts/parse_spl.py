"""Dump SPL v1 ability headers + feature blocks, focused on save fields."""
import struct, sys

def dump(path):
    with open(path, "rb") as f:
        data = f.read()
    sig, ver = data[0:4], data[4:8]
    name_strref = struct.unpack_from("<I", data, 0x08)[0]
    ext_off = struct.unpack_from("<I", data, 0x64)[0]
    ext_cnt = struct.unpack_from("<H", data, 0x68)[0]
    fx_off  = struct.unpack_from("<I", data, 0x6A)[0]
    cast_idx = struct.unpack_from("<H", data, 0x6E)[0]
    cast_cnt = struct.unpack_from("<H", data, 0x70)[0]
    print(f"{path}: sig={sig} ver={ver} name_strref={name_strref} abilities={ext_cnt} "
          f"ext_off={ext_off:#x} fx_off={fx_off:#x} cast_idx={cast_idx} cast_cnt={cast_cnt}")
    for a in range(ext_cnt):
        ao = ext_off + a * 40
        target = data[ao + 0x0C]
        minlvl = struct.unpack_from("<H", data, ao + 0x10)[0]
        nfx    = struct.unpack_from("<H", data, ao + 0x1E)[0]
        first  = struct.unpack_from("<H", data, ao + 0x20)[0]
        proj   = struct.unpack_from("<H", data, ao + 0x26)[0]
        print(f"  ability[{a}] minlvl={minlvl} target={target} proj={proj} nfx={nfx} firstFx={first}")
        for e in range(nfx):
            eo = fx_off + (first + e) * 48
            opcode = struct.unpack_from("<H", data, eo)[0]
            tgt    = data[eo + 2]
            power  = data[eo + 3]
            p1, p2 = struct.unpack_from("<II", data, eo + 4)
            timing = data[eo + 0x0C]
            resist = data[eo + 0x0D]
            dur    = struct.unpack_from("<I", data, eo + 0x0E)[0]
            res    = data[eo + 0x14:eo + 0x1C].rstrip(b"\x00").decode("ascii", "replace")
            dice_n, dice_s = struct.unpack_from("<II", data, eo + 0x1C)
            savetype, savebonus, special = struct.unpack_from("<III", data, eo + 0x24)
            extra = ""
            if opcode == 12:
                extra = (f"  <-- DAMAGE dice={dice_n}d{dice_s} dmgtype={p2>>16:#x} "
                         f"savetype={savetype:#x} savebonus={savebonus} special={special:#x}"
                         f"{' SAVE_FOR_HALF' if special & 0x100 else ''}"
                         f"{' NO_SAVE_TYPE!' if savetype & 0x1F == 0 else ''}"
                         f"{' bypassMI' if savetype & 0x1000000 else ' NO_bypassMI'}")
            print(f"    fx[{e}] op={opcode} tgt={tgt} pow={power} p1={p1} p2={p2:#x} "
                  f"timing={timing} res='{res}' save={savetype:#x}/{savebonus} spec={special:#x}{extra}")

for p in sys.argv[1:]:
    dump(p)
