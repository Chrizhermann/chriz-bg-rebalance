"""Python models of the BG2:EE 2.7.3.0 periodic workers, shared by test_cor.py (which checks them
against the pinned executable's own AIUpdates) and decode_cor.py (which replays lab records)."""

from __future__ import annotations

# The four worker classes: CBRTCor family index, vtable and AIUpdate RVAs, the counter step, the
# pulse cap of one update, and the parent opcode.
FAMILIES = {
    "regeneration": {"id": 1, "vtable": 0x598B18, "update": 0x1A5CA0, "step": 1, "cap": 1000, "opcode": 98},
    "poison": {"id": 2, "vtable": 0x598AE8, "update": 0x1A59F0, "step": 2, "cap": 1000, "opcode": 25},
    "disease": {"id": 3, "vtable": 0x598B00, "update": 0x1A4D90, "step": 1, "cap": 1000, "opcode": 78},
    "repeat": {"id": 4, "vtable": 0x598B48, "update": 0x1A47B0, "step": 1, "cap": 100, "opcode": 272},
}
FAMILY_BY_ID = {family["id"]: name for name, family in FAMILIES.items()}
# Poison, disease and the repeated EFF do not update while the game's +0x7978 holds one of these.
WAITING_STATES = (0x1016E, 0x3016E)


def u32(value):
    return value & 0xFFFFFFFF


def s32(value):
    value = u32(value)
    return value - (1 << 32) if value & 0x80000000 else value


def s16(value):
    value &= 0xFFFF
    return value - (1 << 16) if value & 0x8000 else value


def trunc15(value):
    """C's signed division by 15, as the workers' 0x88888889 multiplications compute it."""
    return abs(value) // 15 * (1 if value >= 0 else -1)


def native_seed(world, origin, period):
    """The phase every construct seeds: floor(u32(world - origin) / 15) % movsx(period), unsigned."""
    if period & 0xFFFF == 0:
        return 0
    divisor = u32(s16(period))
    return (u32(world - origin) // 15) % divisor & 0xFFFF


def worker_step(worker, elapsed, family):
    """One unfrozen AIUpdate of a periodic worker in Python, checked against the executable in
    test_cor.py's NativeWorkerTests: the family's counter step, the countdown, one pulse per whole
    15 ticks of elapsed plus one at a counter boundary, then per pulse mode 0 (one unit while
    +0x22 > 0, else the worker ends), 2 (every pulse) or 3 (every `period` pulses; disease's
    resource modes 11 and 12 alike). The repeated EFF keeps its phase past the period and applies
    its count once per call. Returns the units (heals, hits, EFF applications) submitted. Not
    modelled: regeneration stops at full hit points, poison and disease at 0."""
    model = FAMILIES[family]
    old = worker["remaining"]
    counter = u32(worker["counter"] + model["step"])
    remaining = s32(old - elapsed)
    worker["counter"], worker["remaining"] = counter, remaining
    pulses, done = trunc15(s32(elapsed)), False
    if remaining > old:
        worker["remaining"] = remaining = 0
        done = True
    elif remaining <= 0:
        done = True
    if done:
        worker["done"] = 1
        pulses = trunc15(old)
    boundary = s32(counter) == 15 * trunc15(s32(counter))
    if pulses == 0 and not boundary:
        return 0
    if boundary:
        pulses += 1
        worker["counter"] = 0
    if remaining <= 0:
        pulses += trunc15(remaining)
    mode, units = worker["mode"], 0
    for _ in range(min(model["cap"], pulses)):
        if family == "repeat":
            if mode == 0:
                if s16(worker["amount22"]) <= 0:
                    worker["done"] = 1
                    return 0
                units = 1
            elif mode == 2:
                units = s16(worker["amount24"])
            elif mode == 3:
                worker["phase"] = (worker["phase"] + 1) & 0xFFFF
                if s16(worker["phase"]) >= s16(worker["period"]):
                    units = s16(worker["amount24"])
            continue
        if mode == 3 or (family == "disease" and mode in (11, 12)):
            worker["phase"] = (worker["phase"] + 1) & 0xFFFF
            if s16(worker["phase"]) >= s16(worker["period"]):
                worker["phase"] = 0
                units += 1
        elif mode == 2:
            units += 1
        elif mode == 0:
            if s16(worker["amount22"]) <= 0:
                worker["done"] = 1
                break
            units += 1
    return max(units, 0)
