# Tempus kit completion — components 400 / 404 / 405 (lean build)

Scope approved 2026-07-16: finish the Cleric of Tempus rework with three independent
components, then one combined live install for Branwen (separate, explicitly approved
checkpoint — see the live addendum at the end). Process is lean: this one design pass,
implementation on the existing test harness, focused tests for new surfaces only, one
review at the end.

Component numbering (family 400-499, class and kit revisions):

- `400` — Cleric of Tempus: weapon training (formalizes the 2026-07-14 live hotfix)
- `401/402/403` — Holy Power rework (already shipped; subcomponent family)
- `404` — Cleric of Tempus: Chaos of Battle — announced tides
- `405` — Cleric of Tempus: Divination toll (kit downside)

## Verified evidence (live install, 2026-07-16)

- `OHTMPS2.SPL` (Chaos of Battle, vanilla BG2:EE 2.5+, `data/Patch25.bif`, KEY entry
  33415, no override copy; sha256 96a34912…) is a pure dispatcher: 1 self ability,
  2× op146 (p2=1, timing=1) casting `OHTMPS2D` (ally area, projectile 162) and
  `OHTMPS2E` (enemy area, projectile 171). CLAB grants `GA_OHTMPS2` at levels
  1/11/21/31/41 (Branwen 13 → 2 charges).
- `OHTMPS2D/E` (vanilla, override copies exist): 5 abilities at minlvl 1/7/13/19/25,
  magnitude = tier (1..5), duration 60 s, all timing=0. Effects: op321 self-reset,
  2× op215 visual (`PRAYERG`/`PRAYERB`), op139 per-target string
  (103226/103227), op142 icon (0xC0 ally / 0x21 enemy, 60 s), op9 color pulse, then
  stat effects partitioned by probability windows over ONE d100 per application per
  target: op0 AC [0-25], op54 THAC0 [26-50], op18 max HP ±5N [51-65], op22 Luck
  [66-75], op33..37 single save type each [76-80]/[81-85]/[86-90]/[91-95]/[96-100].
  This confirms the engine rolls once per effect-list application and tests each
  effect's [prob2..prob1] window against that single roll — the mechanism 404 uses
  for coherent tide selection.
- `C0PR#C4.SPL` (Artisan's Kitpack + 2026-07-14 live hotfix, override): 5 effects —
  op326 row0→`C0PR#92` / op233 p1=1 p2=92 t=9 (axe, AK original), op326
  row0→`C0PR#90` / op233 p1=1 p2=90 t=9 (longsword, hotfix), op233 p1=1 p2=103 t=9
  (crossbow pip, ungated — permission comes from shared `C0PR#CL`).
- Live `WEAPPROF.2DA` OHTEMPUS column (post-hotfix target state): LONGSWORD, AXE,
  WARHAMMER, CLUB, FLAILMORNINGSTAR, MACE, QUARTERSTAFF, CROSSBOW, SLING and all four
  styles = 2; BLUNT_BG1/SPIKED_BG1/MISSILE_BG1 = 1 (untouched legacy composites);
  everything else 0.
- Proficiency stats (live STATS.IDS): 90 PROFICIENCYLONGSWORD, 92 PROFICIENCYAXE,
  103 PROFICIENCYCROSSBOW; AK custom permission stats 204/206/217
  (C0_PROFICIENCY{LONGSWORD,AXE,CROSSBOW}), set to 1 via op401 t=9 by `C0PR#XX.SPL`.
- Priest-school scan (`research/scripts/scan_priest_schools.py`, 222 effective
  SPPR1xx-7xx, 221 override copies): school byte 0x25 == 3 (Diviner) exactly matches
  the Divination spells by name on this install: SPPR104 Detect Alignment, SPPR205
  Find Traps, SPPR209 Know Opponent (IWDification), SPPR415 Farsight, SPPR505 True
  Seeing.
- `EEex.dll` exists in the game root (presence marker for the 405 Lua listener);
  `override/M_CBMprs.lua` (bug #21 backfill) is the proven load-listener precedent.

## Component 400 — weapon training (`cbr_cleric_tempus_weapon_training`)

Formalizes the approved 2026-07-14 design (`2026-07-14-tempus-weapon-training-design.md`)
so a fresh install gets the same result and the live install becomes WeiDU-tracked.
Idempotent over the live hotfix: installing on the current game must leave
`WEAPPROF.2DA` and `C0PR#C4.SPL` byte-identical.

**WEAPPROF.2DA.** Resolve `CLERIC` and `OHTEMPUS` columns by header name (data index =
header index + 1). Validated row classification: styles = {2HANDED, SWORDANDSHIELD,
SINGLEWEAPON, 2WEAPON}; excluded = rows matching `_BG1$` or `^EXTRA` (explicit
compatibility decision: BG1 composite rows stay at their installed values; BG2EE/EET
individual rows are authoritative); weapons = all other rows. Transform: weapons with
installed CLERIC > 0 or OHTEMPUS > 0 → OHTEMPUS = 2; LONGSWORD/AXE/CROSSBOW → 2;
styles → 2. No other cell changes.

**C0PR#C4.SPL.** Preflight: resources `C0PR#90/#92/#103` exist; spell contains the AK
axe pair (op326 res=C0PR#92 + op233 p2=92). Ensure-present (append only what is
missing, cloning the byte layout of the existing axe pair / pip): op326 row0
res=`C0PR#90`, op233 p1=1 p2=90 t=9, op233 p1=1 p2=103 t=9. Live file already has all
three → byte-identical.

**Migration helper `CBRTMG2`** (new resref; the dead 07-14 `CBRTMG*` attempt
`CBRTMIG` is not reused — its op326 gates never fired, suspected untrained-prof stat
reading −1 instead of 0). Gates use relation `<=` which is correct under both
hypotheses. Structure — `CBRTMG2.SPL`, 3 gated effects, all self-target:

| gate (SPLPROT append, semantic reuse first) | on match casts |
|---|---|
| `CBR_TEMPUS_C0LS_LE0` = `204 0 0` (no AK longsword permission) | `C0PR#90` (AK's own permission spell) |
| `CBR_TEMPUS_PROFLS_LE0` = `90 0 0` (no longsword pips) | `CBRTMG2L` = op233 p1=1 p2=90 t=9 |
| `CBR_TEMPUS_PROFXB_LE0` = `103 0 0` (no crossbow pips) | `CBRTMG2X` = op233 p1=1 p2=103 t=9 |

Axe is deliberately absent (Branwen already has permission + 1 pip; fresh characters
get it from AK). All gates make the helper idempotent — recasting is harmless.
Console: `C:Eval('ReallyForceSpellRES("CBRTMG2","O#Bran")')` — the object must be her
QUOTED death variable, and this install's Branwen (Kulyok's BG2 mod) is `O#Bran`, not
"Branwen" (verified from save 443's GAM, CRE+0x280). Unquoted names are OBJECT.IDS
special-case lookups ("Special Case: Not found" error); a quoted-but-wrong DV is a
SILENT no-op — which is the likely true cause of the 2026-07-14 CBRTMIG "miss".

TLK-neutral. New resources: CBRTMG2/CBRTMG2L/CBRTMG2X.SPL; ≤3 SPLPROT appends.

## Component 404 — Chaos of Battle tides (`cbr_cleric_tempus_chaos_tides`)

Rework: one coherent, announced, party-wide tide per cast instead of a per-target
stat lottery. Same resref (`OHTMPS2`) so Branwen's existing innate charges keep
working; grant cadence (1/11/21/31/41) unchanged; header name strref 103224 untouched.

**Dispatcher `OHTMPS2`** (COPY_EXISTING from BIF → override): rebuild ability-0
effects as 9 entries in 3 window groups over the single self-application roll
(windows [0..33] / [34..66] / [67..100] ≈ 34/33/34 %):

- op139 announce (new TLK strref), timing=1
- op146 p2=1 timing=1 → `CBRCHT{n}D` (ally spell)
- op146 p2=1 timing=1 → `CBRCHT{n}E` (enemy spell)

**Tide spells** (6 CREATEd SPLs, cloned from the vanilla D/E chassis: same
projectiles 162/171, 5 abilities at minlvl 1/7/13/19/25, visuals op215
PRAYERG/PRAYERB ×2, op142 icon 0xC0/0x21, op9 color pulse; the vanilla per-target
op139 is dropped — announcement is dispatcher-level only). Every tide spell opens
with 3× op321 (its own side's three resrefs: D spells remove CBRCHT1D/2D/3D, E
spells CBRCHT1E/2E/3E) — a new tide replaces any active tide, no stacking. Stat
effects at 100 % probability, duration 30 s (5 rounds), timing=0:

| Tide | Ally spell (D) | Enemy spell (E) | Magnitude N by tier (L1/7/13/19/25) |
|---|---|---|---|
| Onslaught | op54 THAC0 +N, op285 melee dmg +N, op286 missile dmg +N | same ops, −N | 2/2/3/3/4 |
| Bulwark | op0 AC +N (p2=0 as vanilla), op33..37 each +N | same ops, −N | 2/2/3/3/4 |
| Fortune | op22 Luck +N | op22 Luck −N | 1/1/1/2/2 |

**TLK**: exactly 3 appended strings (announce lines, e.g. "Tide of Battle:
Onslaught!"), TRA-driven, resolved at install into op139 param1. This is a
deliberate difference from 401's TLK-neutral bar; dialog.tlk grows append-only by 3
entries and nothing else. Enemy debuffs keep vanilla's no-save, resistable-flags
semantics (clone the vanilla effect fields).

New resources: CBRCHT1D/1E/2D/2E/3D/3E.SPL; OHTMPS2.SPL materialized to override.

## Component 405 — Divination toll (`cbr_cleric_tempus_divination_toll`)

The kit's downside: Clerics of Tempus lose access to Divination priest spells
("Tempus favors those who read the battle, not the future"). No global edits — other
clerics unaffected.

**Discovery at install**: iterate effective `SPPR[1-7][0-9][0-9].SPL`, school byte
0x25 == 3 → removal list (on this install: the 5 spells above; recorded into the
generated resources, never hardcoded).

**`CBRTMDV.SPL`** (CREATE): fully engine-native, no EEex dependency —

1. op321 self-reset (resource `CBRTMDV`, timing=1): re-application replaces any
   prior instance, so the every-column CLAB grant never stacks duplicates.
2. one op172 (remove spell, timing=1) per discovered resref — instant strip at
   apply time.
3. one op272 (apply EFF on condition, timing=9 permanent, param1=1 param2=3 —
   the verified 401 heartbeat) per discovered resref, each firing
   `CBRTMD<i>.EFF` (EFF V2, op172 for that spell). The pulse strips a
   Divination spell within ~1 second of it ever appearing (level-up auto-learn
   ordering becomes irrelevant).

**`OHTEMPUS.2DA`**: append row `CBR_DIVTOLL` with `AP_CBRTMDV` in every level column
(1..50) — both a level-up strip and a self-replacing refresh of the pulse set.

Live migration for the already-leveled Branwen: one console cast at the install
checkpoint — `C:Eval('ReallyForceSpellRES("CBRTMDV","O#Bran")')` (quoted DV; see
component 400 note) — after which the
permanent pulses keep her book clean forever (uninstalling 405 leaves saved pulse
effects pointing at deleted EFFs; the engine treats a missing EFF resource as a
no-op, same residue class as any CLAB-applied mod effect).

TLK-neutral (helper SPL unnamed). Kit-description text updates for 404/405 are
deferred polish — recorded here, not smuggled in.

## Test plan (lean, existing harness)

Fixture principle: live-shaped captures over hand-built (SPLPROT lesson). OHTMPS2/D/E
fixtures = the real vanilla bytes from `research/originals/`. Focused tests only for
new surfaces:

- 400: pristine-AK fixtures (WEAPPROF column pre-hotfix, C0PR#C4 with only the axe
  pair) → transform assertions; live-shaped fixtures → byte-identity; second run
  byte-idempotent; CBRTMG2* created; SPLPROT appends with semantic-reuse (reuse-hit
  and append cases); preflight hard-fails (missing C0PR#90 etc.) before writes.
- 404: dispatcher rebuilt with exact windows/strrefs; 6 tide spells with tier
  magnitudes and op321 reset sets; TLK grows by exactly 3 strings (installer test);
  uninstall restores byte-exactly (OHTMPS2 override copy removed, CBRCHT* removed).
- 405: fake game with mixed-school SPPR samples → CBRTMDV op172/op272 lists match
  school-3 set exactly; CBRTMD<i>.EFF per discovered spell; CLAB row appended
  across all columns and only that row changed.
- Wrapper/installer: components 400/404/405 in the tp2 as independent components;
  `--parse-check` clean; full suite green.

## Live-install addendum (combined checkpoint — requires explicit user approval)

Extends `2026-07-16-tempus-holy-power-live-checklist.md`: install 400, one of
401-403 (per checklist), 404, 405 in one tail run; game closed; rollback bundle
first. Additional acceptance items:

- dialog.tlk: byte-identical EXCEPT exactly 3 appended strings from 404 (record
  before/after entry count and tail bytes).
- Branwen: casts Chaos of Battle → exactly one announce line, coherent party-wide
  tide, recast replaces tide; magnitudes tier-3 (N=3 / Luck 1).
- 405: after the one-shot `CBRTMDV` console cast, Branwen's book has no Detect
  Alignment/Find Traps/Know Opponent/Farsight/True Seeing; verify memorized
  instances are also gone (or clear after rest); other clerics (e.g. Viconia)
  keep them.
- 400: CBRTMG2 console cast grants LS permission + LS/xbow pips once; recast
  changes nothing; optional manual cleanup of the dead `CBRTMIG.SPL` override
  orphan (user sign-off).

## Review outcome (2026-07-16) and tracked follow-ups

Single review pass: **APPROVED WITH NITS** (95/95 tests, parse-checks clean, byte-surgery and
spec conformance verified against the captured live fixtures). Finding 4 (CBRCHT2E magnitude
assertion) was applied immediately. The rest are hardening for FRESH installs — none affects
the authorized live run, where the manual reserved-resref sweep and recognized live shapes
cover them:

1. (Minor) 404 preflight should recognize the dispatcher shape verify-only before the tide
   spells are created — today a foreign dispatcher fails only at rebuild time (WeiDU rollback
   contains it; proven by test).
2. (Minor) The three libs CREATE/COPY their reserved resources without an ownership preflight;
   mirror 401's absent-or-recognized-own-shape-else-FAIL pattern before public/fresh use.
3. (Nit) Fixture-mode `FILE_EXISTS → skip MOVE` guards keep a stale destination; fail-on-foreign
   (finding 2) subsumes this.
4. (Nit, DONE) CBRCHT2E covered in the vanilla-donor magnitude matrix.
5. (Nit) Add an install→uninstall→reinstall TLK test pinning WeiDU's identical-string reuse
   (the "+3 exactly" acceptance across reinstalls).
