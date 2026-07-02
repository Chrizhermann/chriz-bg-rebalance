# Research 01 — SCS Telekinetic Storm never rolls its save

**Date:** 2026-07-02 · **Status:** verified, hotfixed live, component 100 shipped ·
**Upstream:** still broken on SCS master as of this date (see `02-upstream-scs-report-draft.md`)

## Symptom

Telekinetic Storm (SCS "extra arcane spells", level 8 wizard, 1d6/level magic damage, AoE)
always deals **full damage**. Its description says "Saving Throw: 1/2" and "a saving throw for
half damage". Reported on Discord (Reeca/Epicfurylol/Anterwaare, Nov 2025) with a NearInfinity
manual-fix recipe; verified independently here at the binary level.

## Root cause chain

1. **Source:** `stratagems/newspell/extra_arcane_spells.tpa`, `DEFINE_ACTION_FUNCTION
   telekinetic_storm`, damage line:

   ```
   m.ab_fx.add{s_opcode=12 s_power=8 s_parameter2b=64 s_target=2 s_timing=1
               s_dicenumber=p_level=1?16:p_level s_dicesize=6 s_save_for_half=1 s_dispel_resist=1}
   ```

   `s_save_for_half=1` is present, but `s_save_vs_spell=1` and `s_bypass_mirror_image=1` are
   **missing**. Sibling spells in the same file have all three — e.g. Stormbolts:

   ```
   ... s_dicenumber=p_level=1?18:p_level s_dicesize=8 s_save_vs_spell=1 s_save_for_half=1
       s_bypass_mirror_image=1 s_dispel_resist=1
   ```

2. **Installed binary** (this install: spell.ids `2820 WIZARD_TELEKINETIC_STORM` → `SPWI820.spl`,
   5 scaled ability headers, min caster level 1/17/18/19/20): every op12 effect had
   `savetype=0x00000000`, `special=0x00000100` (bit 8 = save-for-half).

3. **Engine semantics:** the engine rolls a saving throw only against the save-type bits
   (dword at effect+0x24; bits 0–4 = spell/breath/death/wand/polymorph). With **zero bits set,
   no save is rolled** and the save-for-half flag (op12 special bit 8) is inert → full damage,
   every time. Bit 24 of the same dword is the EE "bypass mirror image" flag, which vanilla EE
   sets on all AoE damage spells (cf. ADHW); it was missing too, so the storm popped mirror
   images instead of damaging their owner.

## Fix

For each op12 effect with special bit 8 set, in every ability header:
`savetype |= 0x1000001` (bit 0 save-vs-spell + bit 24 bypass-MI). Result verified:
`savetype=0x1000001`, save-for-half semantics now live, 10 bytes changed total.

- **Hotfix:** applied directly to `override/SPWI820.spl` 2026-07-02 (user-approved).
  Pristine original: `research/originals/SPWI820.spl.orig`. Takes effect on next game start.
- **Durable:** component 100 (`setup-chriz-bg-rebalance.tp2`) — dynamic resref resolution via
  spell.ids, idempotent over the hotfix.

## Install-wide sweep (same bug class)

`research/scripts/sweep_savehalf.py` scanned all 12,291 SPL/ITM in `override/` for
op12 effects with save-for-half set but no save-type bits. **9 effects in 5 files, 3 unique
resources:**

| Resource | What | Detail |
|---|---|---|
| `SPWI820.spl` | SCS Telekinetic Storm | fixed (above) |
| `c0ausw05.itm` (+ CDTweaks 2030 clones `c!kt37.itm`, `cdkt37.itm`) | Aura "Spirit Blade, Empty-Of-All +5" | desc promises "(Save vs. Death for half)" on the 10%-max-HP drain hit; never rolled. Fix = savetype bit 2 (0x4). Parked → Aura patch repo issue. |
| `c0ayuki.SPL` | Aura Shirayuri (yuki-onna) breath | 10d10 magic-cold, save-for-half + bypass-MI set, no save bits; bug present in Aura's shipped source. Convention fix = save vs. breath (bit 1, 0x2). Desc strref also mismatched (shows a fire-breath text). Parked → Aura patch repo issue. |

Counter-example proving Aura's author knows the pattern: Sunshooter "Blazing Shot" arrows
(`c0aubob1–3.itm`) correctly pair save-for-half with savetype 0x4 (death).

## Reusable tooling

- `scripts/parse_spl.py` — dump SPL ability headers + feature blocks (save fields annotated).
- `scripts/sweep_savehalf.py` — install-wide audit for the bug class.
- `scripts/tlk_lookup.py` — resolve name/description strrefs via dialog.tlk.

Empirical layout notes (IESDP-divergent, verified): SPL ability nFx @ +0x1e, firstFxIdx @
+0x20; effect savetype @ +0x24, save bonus @ +0x28, special @ +0x2c.
