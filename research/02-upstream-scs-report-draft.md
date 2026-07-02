# PARKED — upstream bug report for Gibberlings3/SwordCoastStratagems (will not be filed)

> Status: **PARKED per user decision 2026-07-03** — the SCS author does not react to GitHub
> reports; effort goes into our own repos instead. Kept for reference/documentation of the
> root cause. The fix ships as component 100 of this mod.

---

**Title:** Telekinetic Storm: save-for-half flag set but no save type — spell never rolls its
promised save (and misses bypass-MI)

**Body:**

In `stratagems/newspell/extra_arcane_spells.tpa`, `DEFINE_ACTION_FUNCTION telekinetic_storm`,
the damage effect is missing its save type:

```
m.ab_fx.add{s_opcode=12 s_power=8 s_parameter2b=64 s_target=2 s_timing=1
            s_dicenumber=p_level=1?16:p_level s_dicesize=6 s_save_for_half=1 s_dispel_resist=1}
```

`s_save_for_half=1` is present, but `s_save_vs_spell=1` is not — so the installed spell's
op12 effects have an empty save-type field. The engine only rolls a save against set
save-type bits, so **no save is ever rolled and the spell always deals full damage
(1d6/level, 16d6–20d6)**, contradicting its description ("Saving Throw: 1/2", "a saving
throw for half damage").

It's also missing `s_bypass_mirror_image=1`, which EE sets on AoE damage spells (cf. vanilla
ADHW) and which the other new arcane spells in the same file do set.

Sibling spells show the intended pattern, e.g. Stormbolts in the same file:

```
m.ab_fx.add{s_opcode=12 s_target=2 s_timing=1 s_power=9 s_parameter2b=4
            s_dicenumber=p_level=1?18:p_level s_dicesize=8 s_save_vs_spell=1
            s_save_for_half=1 s_bypass_mirror_image=1 s_dispel_resist=1}
```

**Suggested fix:** add `s_save_vs_spell=1 s_bypass_mirror_image=1` to the damage line in
`telekinetic_storm`.

Verified against a v35.21 install (all 5 scaled ability headers: savetype dword = 0x0,
special = 0x100) and against current master source. First surfaced by Reeca, Epicfurylol and
Anterwaare on Discord (Nov 2025), who fixed it manually in NearInfinity; this report adds the
source-level cause.

Thanks for SCS — it's the backbone of every install I run.
