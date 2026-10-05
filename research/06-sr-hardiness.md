# 06 — SR Hardiness resistance choices (components 200–202)

## Current decision — 2026-10-06

This section supersedes the old hotfix's retained extra resistances and the old
200a/200b sketch below. The user requested the **vanilla resistance profile** as
our recommendation: **40% physical only**, optional **30% physical only**, with
SR's seven **20% nonphysical damage-resistance effects as a separate option**.
Duration, stacking, casting, dispel flags and existing Breach classifications stay
unchanged. There is no authorization to modify a live game or publish this work.

Implementation lives on `codex/sr-hardiness-adjustment`, based on current local
`origin/main` at `c3f3cc2c084cd25619506ed1fb865af1251a570c` (v0.7.1), with new
version `v0.8.0-dev` (unpublished). The prior root checkout was behind this source.

| Component | Stable label | Behavior |
| --- | --- | --- |
| 200 | `cbr_sr_hardiness_40` | 40% physical only; recommended |
| 201 | `cbr_sr_hardiness_30` | 30% physical only; same mutually exclusive subgroup |
| 202 | `cbr_sr_hardiness_extra_resistance` | Optional 20% extras; requires 200 or 201 |

Both native resources `SPCL907` and `SPWISH12` are patched in every level header.
All components require SR's Revised Warrior HLAs (#65) and BG2:EE/EET. This is a
balance choice rather than an upstream bug fix. The full mod and separate
existing-install TP2 use the same library and block overlapping Hardiness installs.

### Source audit and corrections to the old handover

The current SR fork and official v4.21 source retain the v4.19 resistance patch:
component 65 writes physical opcodes 86–89 to 20 and clones opcode 86 into
27/28/29/30/31/84/85. **Opcode 86 is crushing**, not slashing as the historical
note called it. Opcode 31 is magic *damage* resistance, not Magic Resistance
(opcode 166). No poison resistance (opcode 173) is added; SR's "all forms of
damage" description overstates coverage.

SR's main component additionally clears normal Hardiness's secondary type to 0
(`kreso_extra.tph`), making it unbreachable. It does not do so for Wish Hardiness.
A read-only comparison of the old SR backups and captured post-SR spells confirms
normal secondary type 7 -> 0 and Wish remaining 7. The extra choice does not alter
this asymmetry. AI detection metadata is not an additional protection effect.

The examined old files have 15 ability headers at levels 1, 4, 6, ..., 30, durations
6, 12, 18, ..., 90 seconds, casting speed 0, resistance dispel flags 2, and intact
op321 cross-removal effects. All remain unchanged by the new transformation.
These are archived-file and source observations, not validation of the current
stream installation or a live-engine test.

### Implementation contract

`chriz-bg-rebalance/lib/sr_hardiness.tpa` validates the SPL V1 tables and disjoint
casting/ability slices. Each ability must contain exactly one additive modifier
for each physical damage type. The selected 40/30 is written absolutely; old
values (including the prior hotfix's 40) are not compatibility fingerprints.

SR clones are recognized by matching the opcode-86 donor's bytes except opcode
and resistance amount. A complete seven-effect set is removed for 200/201;
202 restores a missing set by cloning that donor or normalizes an existing set
to 20. Foreign effects with different delivery metadata are retained. Partial,
duplicate or malformed layouts abort. The effect table preserves original group
order and retained effect ordering, including casting-first and casting-last files.
No header field except effect counts/indexes and the description reference is
changed. All non-owned effects remain byte-identical.

The wrapper transforms both spells transactionally before adding descriptions,
so malformed Wish input cannot leave an unused TLK string after rollback. SAY
assigns the new description to each resource; original shared strings are untouched.
The English duration wording remains one round per two levels, as in SR.

### Delivery and collection boundary

- Full TP2: `setup-chriz-bg-rebalance.tp2`, IDs 200/201/202.
- Existing stack: `live-patch/CBR_SR_HARDINESS/setup-cbr_sr_hardiness.tp2`, same
  IDs and separate backup identity. Build with `python tools/package_sr_hardiness.py`.
- Install one Hardiness family after SR #65 and final changes to these spells;
  never reinstall SR or another existing mid-stack component to apply this change.
- Active buffs in saves are not rewritten. Apply with the game closed, then let
  old buffs expire and cast again.
- The collection remains on v0.7.1 until its own integration is completed.
  See `docs/handovers/2026-10-06-sr-hardiness-collection.md` for the exact source,
  feature, dependency, preset and test changes. Recommend 200; 201 and 202 off.

## Historical evidence — 2026-08-19

User request 2026-08-19: with Spell Revisions installed, Hardiness grants only 20%
physical resistance; restore it to "30 or 40%, like the original — I want both options",
and apply 40% to the live game immediately (explicit sign-off given in-session).

## 1. Diagnosis

**Source of the nerf: Spell Revisions v4.19, component #65 "Revised Warrior HLAs"**
(`~SPELL_REV/SETUP-SPELL_REV.TP2~ #0 #65`, WeiDU.log line 115), implemented in
`spell_rev/lib/kreso_hla.tph`:

- `spcl907.spl` (Hardiness, lines 22–36): `ALTER_SPELL_EFFECT` sets opcodes
  86/87/88/89 (slashing/crushing/piercing/missile) `parameter1 = 20`, then
  `CLONE_EFFECT`s the op86 donor into opcodes 27/28/29/30/31/84/85
  (acid/cold/electricity/fire/magic-damage/magical-fire/magical-cold) at 20%.
  Net design: vanilla "40% physical" becomes "20% everything".
- `spwish12.spl` (Wish-granted party Hardiness, lines 39–52): identical treatment.
- Same component also touches `spcl900`/`spcl901` (Whirlwinds: deletes the op1 APR
  effect, re-times icon/sound to 12s) — out of scope here; candidate material for the
  SR wishlist session.

### Evidence chain for the installed `SPCL907.spl`

| Stage | File | Size | op86–89 p1 |
|---|---|---|---|
| pre-SR (backup) | `weidu_external/backup/spell_rev/65/spcl907.spl` | 10,074 | **40** (15 abilities × 13 fx) |
| post-SR #65 (cdtweaks backup) | `weidu_external/cdtweaks/backup/2010/SPCL907.SPL` | 15,114 | 20 + 7 elemental clones @20 |
| post cdtweaks #2010 (icon split adds 2× op142/ability) | — | 16,554 | 20 |
| SCS #2000 (backed up, wrote identical content) | `weidu_external/backup/stratagems/2000/SPCL907.spl` | 16,554 | 20 |
| **override before hotfix** | `research/originals/SPCL907.spl.orig` | 16,554 | 20 |
| **override after hotfix (2026-08-19)** | `override/SPCL907.spl` | 16,554 | **40** |

`SPWISH12.spl`: 15 abilities × 4 physical ops (tgt=3 pow=9) at 20 → 40; pristine copy
`research/originals/SPWISH12.spl.orig` (15,834 bytes).

Structure facts (dump: `research/scripts/parse_spl.py`):

- 15 ability headers (minlvl 1, 4, …) = level-scaled duration; scaling predates SR and
  was not touched.
- No casting features, no op146 sub-spell delivery — all effects live on the parent SPL.
- Anti-stacking verified **bidirectional** (2026-08-19, user challenged it): all three
  spells carry the same op321 (Remove Effects by Resource) triple — `SPCL907` removes
  {SPDWD02, SPWISH12, self}; `SPDWD02` removes {SPWISH12, SPCL907, self} — present in
  the **pre-AK vanilla backup** (`weidu_external/backup/ArtisansKitpack/1007/SPDWD02.SPL`,
  1 ability, flat 50% physical) *and* in the live AK-overhauled version; `SPWISH12`
  removes {SPDWD02, SPCL907, self}. Latest cast wins; they never sum. The two extra AK
  stance effects referencing 'SPCL907' (op184 No Collision Detection, op235 Wing Buffet
  — NI-source-verified names) ignore their resource field — cloning leftovers, **not**
  Hardiness locks. Relevant to comp 301.
- Name strref 63953; description (SR text) reads: *"…gain 20% resistance to all forms
  of damage. The ability lasts for 1 round per 2 levels."*

## 2. Live hotfix record (2026-08-19, user-approved in-session)

- Game was not running (process check). Direct override edit per CLAUDE.md hotfix rule.
- Tool: `research/scripts/patch_phys_resist.py <spl> 20 40` — rewrites parameter1 only
  for feature blocks with opcode ∈ {86,87,88,89} and p1==20.
- `override/SPCL907.spl`: 60 effects patched (15 abilities × 4). `cmp -l` vs pristine:
  exactly 60 bytes differ, every one `0x14 → 0x28`.
- `override/SPWISH12.spl`: same — 60 effects, 60 bytes, `0x14 → 0x28`.
- SR's elemental/magic riders (op 27/28/29/30/31/84/85) deliberately left at 20 — a
  strict improvement over both vanilla (no elemental) and SR (20 physical); removing
  them was not requested and would restructure the file.
- Applies on next cast (SPL override edits are runtime-loaded; verified gotcha). An
  already-running Hardiness buff keeps 20% until it expires and is recast.
- **Known cosmetic gap:** in-game description still says 20%; fixed by comp 200's
  STRING_SET, not worth a mid-playthrough dialog.tlk rewrite.

## 3. Superseded installer sketch

The old 200a/200b design retained SR's 20% extra resistances by default. It never
became an installer component. The current 200/201/202 contract above supersedes
that choice and resolves the previously open extra-resistance question.

## 4. Historical physical-resistance-cap sketch — deferred, no component ID

**Historical design only:** 301 now belongs to Emotion Courage/Hope exclusivity.
The following cap sketch is not implemented here and must be renumbered if pursued.

User intent: the problem is not Hardiness 40 + Defender of Easthaven 20; it is Dwarven
Defender-style kits trivially reaching ~100% physical. Don't nerf the abilities — make
the last stretch hard-stop: **cap at 90% (default) or 80% (option)**, exempting things
that legitimately should be immune (golems immune to all but crushing, etc.).

Design direction (to be researched before build):

- **Mechanism:** EEex `EEex_Opcode_AddListsResolvedListener` clamping the four physical
  resistance derived stats after each effect-list re-evaluation — same stat-clamp
  technique family as `research/05-eeex-apr-cap.md`. Record screen then shows the
  capped value (honest UI). Requires EEex (present: InfinityLoader install).
- **Exemption rule (proposed):** apply the cap to **party members only**. All the
  degenerate stacking lives player-side; enemy designed immunities (golems, statues,
  incorporeals) stay untouched — most are opcode 120 protection anyway, which a
  resistance cap never affects. Optional stretch variant for NPCs: exempt any creature
  whose pre-buff base already ≥ cap.
- **301c — soft knee (planned third subcomponent, user-endorsed 2026-08-19):** points
  above 60% count half, then the hard cap. Ship 301a (cap 90) / 301b (cap 80) first;
  301c is the same listener with a transform instead of a clamp. The record screen must
  show the post-transform value (honest UI).
- **Reference build (verified in this install; AK "Dwarven Defender Overhaul" #1007):**
  kit passives +20% physical by L20 (4× `AP_SPDWD01`, +5% each, timing-9 permanent) +
  Defensive Stance 20/35/**50% ALL damage** by L18 (+6 AC/saves) + Defender of
  Easthaven +20% = **90% physical while stanced** before any other gear — achieved
  *without* Hardiness, so the vanilla exclusivity never constrains it. Plus Fortitude
  (heal 1 HP per damage instance) and Unyielding (L20: 10% full damage negate).
  Cap 90 leaves this build as-is; cap 80 actually trims it — the 80-vs-90 option is
  exactly this build's knob.
- **Stacking-source audit needed** (install-specific): Hardiness 40 (mutually
  exclusive with Defensive Stance/Wish per §1), Defender of Easthaven, Armor of Faith,
  rage effects, Roranach's Horn, potions, **our own AKCB_BERSERKER low-HP
  resistances**, Dwarven Defender kit if present. Enumerate what a party can actually
  stack before fixing the default cap value.
- Ship after 200; live-game deployment needs its own sign-off.

## 5. Status

- Historical hotfix: applied and byte-verified in the August session only.
- New 200/201/202 and standalone tail installer: implemented in v0.8.0-dev.
- Automated checks: 24 focused tests pass with WeiDU 24900 on synthetic games,
  covering all four combinations, both resources, malformed-input rollback,
  prerequisites, exclusivity, descriptions, preservation, idempotence and exact
  synthetic uninstall. The package builder's payloads/checksums are verified.
- Archived-resource checks: both August post-SR captures pass all four resistance
  profiles and byte-exact repeat application, preserving all 15 level headers and
  unrelated effects. Only disposable copies were transformed.
- The broader unrelated-component suite was not rerun for this isolated addition.
- Current live game, saves and collection manifests: untouched.
- Publication and live acceptance: pending; not authorized in this task.
- Physical-resistance-cap project: deferred and outside this change.
