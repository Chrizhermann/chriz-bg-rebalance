# 06 — SR "Revised Warrior HLAs" Hardiness nerf → restore (component 200) + phys-res cap sketch (component 301)

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

## 3. Component 200 spec — `cbr_sr_hardiness` (SR series)

Subcomponents (mutually exclusive), both patching `spcl907.spl` + `spwish12.spl`:

- **200a (default): 40% physical** — vanilla strength, what the live game now runs.
- **200b: 30% physical** — softer middle ground.
- Framing (user, 2026-08-19): 200 is the first of many 2xx SR balances, each
  predicate-gated so it only applies when SR (and the relevant SR subcomponent) is
  installed. No other SR tweaks exist yet anywhere (repo + GitHub issues swept
  2026-08-19; only the SR-wishlist placeholder).
- **OPEN (user decides, deferred 2026-08-19):** keep SR's 20% elemental/magic rider on
  the restored Hardiness (current live-game state) or strip it back to the pure vanilla
  physical-only profile. May become a second option axis (40/30 × rider/no-rider).
- Absolute writes (`parameter1 = 40|30` on op86–89 regardless of current value) ⇒
  idempotent over the live hotfix and over re-runs.
- `REQUIRE_PREDICATE MOD_IS_INSTALLED ~SPELL_REV/SETUP-SPELL_REV.TP2~ ~65~` — no-op
  gracefully when SR's Revised Warrior HLAs isn't present (without #65 Hardiness is
  already 40% and has no elemental rider to preserve).
- SAY UNIDENTIFIED_DESC with corrected text per option, e.g. 40%: *"…gain 40%
  resistance to physical damage and 20% resistance to acid, cold, electricity, fire,
  and magical damage. The ability lasts for 1 round per 2 levels."* (Keep SR's
  duration wording — duration untouched.)
- Tail-install; never uninstall SR.

## 4. Component 301 sketch — physical-resistance cap (cross-cutting)

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

- [x] Live hotfix applied + byte-verified (2026-08-19)
- [ ] Component 200 build (tp2 + strings) — design approved by user request itself
- [ ] Component 301 research (EEex listener + source audit) → design → user sign-off
