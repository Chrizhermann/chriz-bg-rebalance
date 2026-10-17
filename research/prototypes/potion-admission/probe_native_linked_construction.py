"""Read-only linked SPL construction/header metadata probe, BG2EE 2.7.3.

Actual CSpell/CResSpell selection, DecodeEffect, opcode constructors, base
constructor and resref helpers execute against synthetic resource bytes. Native
FireSpell executes through selection/construction/duration scaling; dispatch is
omitted to isolate construction. No game, native DLL or installed hook executes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

import probe_native_admission as admission
import probe_native_linked_cast as lineage

BASE = 0x140000000
DATA = 0x710000000
RESOURCE = lineage.HEAP + 0x74000
SPELL = lineage.HEAP + 0x74100


def require(value, message):
    if not value:
        raise AssertionError(message)


def raw_effect(opcode=90, *, target=1, power=7, p1=13, p2=0, timing=0,
               resistance=3, duration=61, dice_count=2, dice_size=3,
               save_type=1, save_bonus=5, special=17, resource=b"Abc\0junk"):
    raw = bytearray(0x30)
    struct.pack_into("<HBBIIH", raw, 0, opcode, target, power, p1, p2, timing | resistance << 8)
    struct.pack_into("<IBB8sIIIII", raw, 0xE, duration, 81, 7, resource, dice_count,
                     dice_size, save_type, save_bonus & 0xFFFFFFFF, special)
    return raw


class Machine(lineage.Machine):
    def __init__(self, image, unicorn, registers, *, records=None, headers=None,
                 globals_count=0, level=12, school=4, secondary=9, source_flags=0x12345678,
                 caster_type=1, kit=0, duration_scale=100, actor_is_sprite=True,
                 header_offset=0x100, effect_offset=0x300, global_first=0):
        super().__init__(image, unicorn, registers, base=BASE, duration_scale=duration_scale)
        self.u.mem_map(DATA, 0x20000)
        self.constructed, self.decoded, self.metadata = [], [], []
        self.level, self.actor_is_sprite = level, actor_is_sprite
        self.stop_at, self.branch_calls = None, []
        self.records = records if records is not None else [raw_effect()]
        self.headers = headers if headers is not None else [(1, 0, len(self.records))]
        self.fx_address = DATA + effect_offset
        self.header_address = DATA + header_offset
        self.u.mem_write(DATA, b"SPL V1  ")
        self.put(DATA+0x18, "I", source_flags)
        self.put(DATA+0x1C, "H", caster_type)
        self.put(DATA+0x25, "B", school)
        self.put(DATA+0x27, "B", secondary)
        self.put(DATA+0x64, "IHIHH", header_offset, len(self.headers), effect_offset,
                 global_first, globals_count)
        for index, (minimum, first, count) in enumerate(self.headers):
            pointer = self.header_address + index*0x28
            self.put(pointer+0x10, "H", minimum)
            self.put(pointer+0x1E, "HH", count, first)
            self.put(pointer+0x26, "H", 1)
        for index, raw in enumerate(self.records):
            self.u.mem_write(self.fx_address+index*0x30, bytes(raw))
        self.put(RESOURCE+0x51, "B", 1)
        self.put(SPELL, "Q", RESOURCE)
        self.u.mem_write(SPELL+8, b"POTN36\0\0")
        self.put(admission.ACTOR+0x79E, "H", kit)
        for offset in (0x11A6, 0x11A8, 0x11E2, 0x1E4E, 0x1E50, 0x1E8A):
            self.put(admission.ACTOR+offset, "h", duration_scale)
        # Execute the actual parser that establishes header/effect base pointers.
        self.run(0x114D30, RESOURCE, DATA)
        require(self.reg_read("AL") == 1, "synthetic SPL parse failed")

    def snapshot(self, pointer):
        fields = {
            "opcode": (0x10, "I"), "target": (0x14, "I"), "power": (0x18, "I"),
            "p1": (0x1C, "I"), "p2": (0x20, "I"), "timing": (0x24, "I"),
            "duration": (0x28, "I"), "probability_high": (0x2C, "H"),
            "probability_low": (0x2E, "H"), "dice_count": (0x38, "I"),
            "dice_size": (0x3C, "I"), "save_type": (0x40, "I"),
            "save_bonus": (0x44, "i"), "special": (0x48, "I"), "school": (0x4C, "I"),
            "min_level": (0x54, "I"), "max_level": (0x58, "I"),
            "resistance_flags": (0x5C, "I"), "time_applied": (0x6C, "I"),
            "source_type": (0x90, "I"), "source_flags": (0x9C, "I"),
            "caster_level": (0xC8, "i"), "first_call": (0xCC, "I"),
            "secondary": (0xD0, "I"), "source_id": (0x110, "I"),
            "original_duration": (0x11C, "I"), "target_id": (0x150, "I"),
        }
        result = {name: self.get(pointer+offset, fmt) for name, (offset, fmt) in fields.items()}
        result["resource_hex"] = self.read(pointer+0x30, 8).hex()
        result["source_resource_hex"] = self.read(pointer+0x94, 8).hex()
        return result

    def on_code(self, uc, address, size, opaque):
        rva = address - BASE
        if self.stop_at == rva:
            self.reg_write("RIP", admission.RETURN)
            return
        if rva in (0x24EE30, 0x24ED80, 0x24EDD0, 0x24F010):
            if rva == 0x24EE30:
                self.constructed.append((self.reg_read("EDX"), self.reg_read("R8D")))
            return  # Execute native implementations, not the lineage probe doubles.
        if rva == 0x1DE3D0:
            self.decoded.append((self.reg_read("RCX")-self.fx_address)//0x30)
            return
        if rva in (0x3F6D50, 0x40D580):
            self.ret(self.reg_read("RCX"))  # resource Demand / sound member construction
            return
        if rva == 0x4FAB70:
            pointer, value, length = self.reg_read("RCX"), self.reg_read("RDX") & 0xFF, self.reg_read("R8")
            self.u.mem_write(pointer, bytes([value])*length)
            self.ret(pointer)
            return
        if rva == 0x164F90:
            pointer = self.reg_read("RCX")
            self.put(pointer, "Q", RESOURCE)
            self.put(pointer+8, "Q", self.reg_read("RDX"))
            self.ret(pointer)
            return
        if rva == 0x39CC30:
            self.events["GetCasterLevel_true" if self.reg_read("R8D") else "GetCasterLevel_false"] += 1
            self.ret(self.level & 0xFFFF)
            return
        if address == admission.FAKE_CALLS+0x100:
            self.ret(self.get(BASE+0x59971F, "B") if self.actor_is_sprite else 0)
            return
        if rva == lineage.CHILD_READY:
            pointer = self.reg_read("RBX")
            row = self.snapshot(pointer)
            row["ability"] = self.get(self.reg_read("RSP")+0x50, "I")
            row["ordinal"] = self.reg_read("EDI")
            self.metadata.append(row)
            # Construction only: do not apply any child, including adverse/global
            # controls. Native ordinal iteration still executes from16B331.
            self.reg_write("RIP", BASE+0x16B331)
            return
        if rva in (0x387930, 0x388060):
            self.branch_calls.append(rva)
            self.ret(0)
            return
        super().on_code(uc, address, size, opaque)

    def ability_effect(self, ability=0, ordinal=0, actor=admission.ACTOR):
        self.run(0x24EE30, SPELL, ability, ordinal, actor)
        pointer = self.reg_read("RAX")
        return None if pointer == 0 else self.snapshot(pointer)

    def cast(self):
        self.run(lineage.FIRE_SPELL, admission.ACTOR, lineage.STRING, admission.ACTOR,
                 0, 0xFFFFFFFF, 0, 1, 1)
        return self.metadata

    def cast_global_branch(self, flag):
        # Execute the actual tail predicates in two bounded segments. The first
        # skips projectile launch/feedback; the second stops before AI triggers.
        self.put(admission.STACK+0x4000+0xF8, "I", flag)
        self.put(admission.STACK+0x5FF8+0x58, "H", self.level)
        for start, stop in ((0x16B45C, 0x16B513), (0x16B544, 0x16B56E)):
            self.stop_at = stop
            self.reg_write("RBP", admission.STACK+0x4000)
            self.reg_write("R14", admission.ACTOR)
            self.reg_write("R15", SPELL)
            self.reg_write("R12", 0)
            self.run(start)
        self.stop_at = None
        return self.branch_calls


def run_probes(image, unicorn, registers):
    cases = []
    for opcode, uses_dice in ((0, False), (1, False), (10, False), (18, True),
                              (19, False), (54, False), (90, False), (92, False),
                              (142, False), (146, False), (206, False)):
        m = Machine(image, unicorn, registers, records=[raw_effect(opcode)], kit=0x200)
        row = m.ability_effect()
        require(row["opcode"] == opcode and row["target"] == 1 and row["power"] == 7, "raw identity")
        require(row["source_type"] == 1 and row["source_resource_hex"] == b"POTN36\0\0".hex(), "SPL source")
        require(row["school"] == 4 and row["secondary"] == 9 and row["source_flags"] == 0x12345678,
                "SPL header metadata")
        require(row["caster_level"] == 12 and row["save_bonus"] == 3, "specialist/caster level")
        require(row["resistance_flags"] == 3 and row["timing"] == 0 and row["duration"] == 61,
                "timing/resistance split")
        require(row["resource_hex"] == b"ABC\0\0\0\0\0".hex(), "resource normalization")
        require((row["dice_count"], row["dice_size"], row["min_level"], row["max_level"]) ==
                ((2, 3, 0, 0) if uses_dice else (0, 0, 3, 2)), "dice/level constructor mapping")
        require(row["time_applied"] == 1000 and row["original_duration"] == 61 and row["first_call"] == 1,
                "native construction defaults")
        cases.append({"case": "native_opcode_constructor", "opcode": opcode, "metadata": row})
    for school, kit, expected in ((0, 0x200, 5), (4, 0, 5), (4, 0x100, 5), (4, 0x200, 3), (9, 0x4000, 3)):
        m = Machine(image, unicorn, registers, school=school, kit=kit)
        require(m.ability_effect()["save_bonus"] == expected, "specialist selection")
        cases.append({"case": "specialist", "school": school, "kit": kit, "save_bonus": expected})
    for target in range(10):
        m = Machine(image, unicorn, registers, records=[raw_effect(target=target)], level=0xFFFF)
        row = m.ability_effect()
        require(row["target"] == target and row["caster_level"] == -1, "target copy / signed caster level")
    cases.append({"case": "targets_0_through_9_unchanged_and_level_sign_extension"})
    for actor, sprite, expected in ((0, True, 0), (admission.ACTOR, False, 1)):
        m = Machine(image, unicorn, registers, actor_is_sprite=sprite)
        require(m.ability_effect(actor=actor)["caster_level"] == expected, "non-sprite/null caster level")
    cases.append({"case": "null_and_non_sprite_caster"})
    for resistance in (0, 1, 2, 3, 4, 128, 255):
        m = Machine(image, unicorn, registers, records=[raw_effect(resistance=resistance)])
        row = m.ability_effect()
        require(row["resistance_flags"] == (resistance & 3) and
                row["timing"] == ((resistance << 8) & ~0x300), "native packed timing mapping")
    cases.append({"case": "V1_packed_timing_resistance_word_mapping"})
    m = Machine(image, unicorn, registers)
    m.u.mem_write(SPELL+8, b"mixed\0\0\0")
    require(m.ability_effect()["source_resource_hex"] == b"mixed\0\0\0".hex(),
            "CSpell source resref should copy exactly, unlike effect-resource normalization")
    cases.append({"case": "source_resref_copies_existing_CSpell_bytes"})
    for opcode in (18, 90):
        m = Machine(image, unicorn, registers, records=[raw_effect(opcode, dice_size=0xFFFFFFFF)])
        row = m.ability_effect()
        require(m.get(m.fx_address+0x20, "I") == 0, "native raw -1 normalization missing")
        require(row["dice_size"] == row["min_level"] == 0, "normalized runtime field")
    cases.append({"case": "DecodeEffect_raw_dword20_minus1_to_zero"})
    # Headers deliberately use reordered/noncontiguous effect regions and an
    # unrelated global record. Native selection uses the qualifying prefix.
    records = [raw_effect(p1=i+100) for i in range(10)]
    headers = [(1, 7, 2), (5, 3, 1), (10, 5, 2)]
    for level, indices, ability in ((0, [7, 8], 0), (4, [7, 8], 0), (5, [3], 1),
                                     (9, [3], 1), (10, [5, 6], 2), (30, [5, 6], 2)):
        m = Machine(image, unicorn, registers, records=records, headers=headers,
                    globals_count=2, global_first=9, level=level, header_offset=0x240, effect_offset=0x900)
        rows = m.cast()
        require(m.decoded == indices, "header-first-index or global leakage")
        require([(r["ability"], r["ordinal"]) for r in rows] == [(ability, i) for i in range(len(indices))],
                "ability/global ordinal mapping")
        require([r["p1"] for r in rows] == [100+i for i in indices], "record ordering changed")
        cases.append({"case": "multiple_headers", "caster_level": level, "selected": ability, "indices": indices})
    for headers, expected in (([(1, 7, 1), (10, 3, 1), (5, 5, 1)], [7]),
                              ([(1, 7, 1), (5, 3, 1), (5, 5, 1)], [5]),
                              ([(20, 7, 1), (1, 3, 1)], []), ([], [])):
        m = Machine(image, unicorn, registers, records=records, headers=headers, level=5)
        m.cast()
        require(m.decoded == expected, "native ordered-prefix selection changed")
        cases.append({"case": "header_order_or_no_matching_header", "headers": headers, "indices": expected})
    for caster_type in (0, 1, 2, 4, 5):
        for scale in (0, 50, 100, 150, -1):
            m = Machine(image, unicorn, registers, caster_type=caster_type, duration_scale=scale)
            row = m.cast()[0]
            expected = ((61*scale) & 0xFFFFFFFF)//100 if caster_type in (1, 2, 5) and scale != 100 else 61
            require(row["duration"] == expected and row["original_duration"] == 61, "duration formula")
            cases.append({"case": "native_duration_scale", "spell_type": caster_type, "percent": scale,
                          "duration": expected})
    for timing in (1, 9, 10, 4096):
        m = Machine(image, unicorn, registers, records=[raw_effect(timing=timing)], duration_scale=150)
        row = m.cast()[0]
        require(row["duration"] == 91 and row["timing"] == timing, "scaling has no timing-mode guard")
    cases.append({"case": "duration_scaling_applies_without_timing_mode_filter"})
    m = Machine(image, unicorn, registers, duration_scale=50)
    m.put(admission.ACTOR+0x4EA4, "I", 0)
    m.put(admission.ACTOR+0x1E4E, "h", 200)
    require(m.cast()[0]["duration"] == 122, "inactive-derived-stat multiplier selection")
    cases.append({"case": "alternate_derived_stat_set_duration_multiplier"})
    for mode, offset in ((0, 0x11A6), (1, 0x11A8), (2, 0x11E2)):
        m = Machine(image, unicorn, registers)
        m.put(admission.EFFECT+0x1C, "II", 65536+150, mode)
        m.run(0x1B3120, admission.EFFECT, admission.ACTOR)
        require(m.get(admission.ACTOR+offset, "H") == 150, "op99 low-word field write")
    cases.append({"case": "op99_native_mage_priest_bard_low16_fields"})
    # Global helper itself is real and addresses the beginning of the effect
    # array. The main-header global-first value is ignored by these native APIs.
    m = Machine(image, unicorn, registers, records=records, headers=headers,
                globals_count=2, global_first=9)
    for ordinal in (0, 1):
        m.run(0x24F060, SPELL, ordinal)
        row = m.snapshot(m.reg_read("RAX"))
        require(row["p1"] == 100+ordinal and row["source_type"] == 0 and row["caster_level"] == 0,
                "global helper metadata/indexing differs")
    require(m.decoded == [0, 1], "global indexing changed")
    cases.append({"case": "global_constructor_separate_metadata_and_zero_based_indices"})
    for flag, expected in ((1, []), (0, [0x387930, 0x388060])):
        m = Machine(image, unicorn, registers)
        require(m.cast_global_branch(flag) == expected, "mode1 casting/global flag branch")
        cases.append({"case": "native_tail_global_gate", "arg8": flag, "calls": [hex(x) for x in expected]})
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--python-libs", type=Path)
    args = parser.parse_args()
    if args.python_libs:
        sys.path.insert(0, str(args.python_libs))
    import pefile
    import unicorn
    from unicorn import x86_const
    data = args.exe.read_bytes()
    require(hashlib.sha256(data).hexdigest() == lineage.SHA256, "unsupported executable")
    cases = run_probes(pefile.PE(data=data).get_memory_mapped_image(), unicorn, x86_const)
    print(json.dumps({"sha256": lineage.SHA256, "cases": cases,
                      "services": [
                          "Synthetic CResSpell object/file bytes; Demand returns that already-parsed resource.",
                          "CSpell wrapper constructor uses that resource; CString bridge is the lineage probe service.",
                          "GetCasterLevel returns controlled native short; class/kit/2DA/wild-mage arithmetic not emulated.",
                          "Sound member constructor and allocation are doubles; memset has equivalent byte semantics.",
                          "Child dispatch/application omitted; native selection, DecodeEffect and constructors execute.",
                          "FireSpell's remaining tail omitted; global gates execute separately with casting services recording calls.",
                      ]}, indent=2))


if __name__ == "__main__":
    main()
