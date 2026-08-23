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


## Addendum 2026-07-17 — Component 406: specialization APR (`cbr_cleric_tempus_spec_apr`)

User feedback after live play: the kit feels underwhelming because 2 pips never
yield the warrior half-attack. Root fact (verified on the live install):
`CLSWPBON.2DA` supports **per-kit rows** — `OHTEMPUS  GETS_PROF_APR 0` — and
Artisan's Kitpack already grants the flag to non-warrior kits (C0_NINJA,
C0_BRAWLER, C0TBM), so the per-kit path is engine-supported. Component 406
flips exactly that one cell (append a cleric-shaped `OHTEMPUS 1 0 3` row when
missing), read-compare-guarded for byte-idempotence, two-pass verified, hard
FAIL on any unrecognized shape. Engine reads CLSWPBON at attack-resolution
time per wielded weapon — correct spec-APR semantics with zero save surgery;
needs only a game restart. Harness component 3 + 5 pytest cases
(flip/done/append/no-column/garbage).

Design rationale: fixes the kit's PASSIVE baseline (1.5 APR with a
specialized weapon) instead of further inflating the Holy Power burst;
Fighter/Cleric duals remain ahead, as intended.

**v2 (same day):** live testing disproved the kit-row path — with the OHTEMPUS row
at 1 in the loaded table, an equipped 2-pip flail, and pips confirmed via stat 100,
Branwen's APR stat (8) still read exactly 1 while a Berserker-16 control read 3.5
(encoding 9). The engine consults the CLASS row only; CLSWPBON kit rows (incl. all
of Artisan's) are decorative for this mechanic. v2 flips CLERIC as well (row must
exist; kit row kept at 1 as future-proof data). Scope: a KITLIST(CLASS=3)×WEAPPROF
scan of the reference install found OHTEMPUS to be the ONLY pure-cleric kit with
any weapon cap >= 2 — no other pure cleric can ever reach specialization, so the
class flip is de-facto kit-scoped. Follow-up (fresh installs): informational
install-time scan listing other >=2-cap cleric kits.

## Addendum 2026-07-20 — Component 407: EEex spec-APR variant (`cbr_cleric_tempus_spec_apr_eeex`)

Live play on 406 v2 gave 2.5 APR with a 2-pip flail — the CLERIC-row flip
grants the FULL warrior WSPATCK progression (fighter-grade), stronger than the
kit advertises. The research sweep (consolidated in the bg-modding skill,
`ie-apr-proficiency.md`) found no data-only spec-cap knob anywhere:
GETS_PROF_APR is a boolean class-row gate into the whole table, SPLPROT has no
equipment sensor, op183 is category- (not proficiency-) granular. User chose
Option A (2026-07-20): an EEex derived-stats listener.

Mechanism: `override/M_CBRAPR.lua` registers
`EEex_Opcode_AddListsResolvedListener`; every rebuild of a sprite's derived
stats (equip, weapon switch, level-up, load — all funnel through
`CGameSprite::ProcessEffectList`, which reloads `CDerivedStats` first) re-runs
the hook, so the +1/2 write is self-healing, save-clean, and vanishes with the
file. Listener gates, in order: kit stat 152 == OHTEMPUS id; selected-weapon
slot from `m_equipment.m_selectedWeapon` (conjured weapons in fist slot 10
COUNT on purpose — Spiritual Hammer is kit flavor; bare fists drop out at the
proficiency-range check); ITM-header `proficiencyType` in 89..115 excluding
styles 111-114; pips (stat == prof id) >= 2. Then
`stats.m_nNumberOfAttacks = encode(decode(n) + 0.5)` with a hard clamp at 5.
pcall-wrapped; self-disables after 10 body errors; guarded against loading
without EEex (M_*.lua auto-load is a vanilla feature).

Packaging: 406 and 407 are SUBCOMPONENTs of one group (@1406) — mutually
exclusive by construction. 407 predicates: `GAME_IS bg2ee eet`,
`OHTEMPUS.2DA`, `M___EEex.lua`, `IDS_OF_SYMBOL(kit OHTEMPUS) > 0`. The kit id
is stamped into the Lua at install time via REPLACE_TEXTUALLY of
`%CBR_TEMPUS_KIT_ID%` (kit ids are per-install ADD_KIT allocations — never
hardcode). Numbers: 1.5 APR baseline with a specialized weapon, 2.5 during
Holy Power tier-1 (vs 406's 2.5/3.5).

Verification: harness DESIGNATED 4; pytest — stamp+byte-idempotence, shipped
listener compiles under EET's Lua 5.3 AND bows out cleanly without EEex
globals, no-placeholder/missing-template/kit_id<=0 controlled-RED; installer
suite — fresh 407 install/uninstall byte-restore, plus a one-run
`--force-uninstall-list 406 --force-install-list 407` swap rehearsal
(CLSWPBON.2DA byte-exact revert + WeiDU.log ends with exactly one #407 line).
Full suite 108 green.

OPEN at ship time — the one unverified primitive: Lua *write* acceptance on
`m_nNumberOfAttacks` (reads verified live; bindings may reject or chain the
setter). Decisive live check after the swap: Branwen, flail at 2 pips, no
Holy Power → APR stat 8 must read 7 (= 1.5). Fallback if the write does not
take: Lua-managed op1 (type 0, key 6) effect with op321/sourceRes dedup.

## Addendum 2026-07-20 — Component 408: updated descriptions (`cbr_cleric_tempus_descriptions`)

Resolves the "kit-description text updates are deferred polish" item: after
400/401/404/405/407 the player-facing text was stale (kit description still
SoD's, Holy Power showing the SHARED vanilla spell text, Chaos of Battle
describing the per-target stat lottery).

Mechanism — append + repoint, never edit in place: three new TLK strings
(RESOLVE_STR_REF, append-stable across reinstalls via WeiDU's
identical-string reuse), then repoint the three consumers: KITLIST.2DA
OHTEMPUS HELP cell (header-located, SET_2DA_ENTRY read-compare-guarded),
OHTMPS1.SPL header 0x50, OHTMPS2.SPL header 0x50. In-place editing is off
the table because OHTMPS1's live desc strref (6088) is shared with the
standard priest spell Holy Power — a STRING_SET there would rewrite every
priest's spell description. Kit names (LOWER/MIXED) and both spell names
stay untouched; 0x54 identified-desc dwords stay untouched.

Text contents (verified against implementation, not memory): weapon caps
from the live WEAPPROF target state (Axes/Clubs/Crossbows/Flails/Long
Swords/Maces/Quarterstaffs/Slings/War Hammers + all styles at 2); +1/2
attack with a 2-slot wielded weapon (407); Holy Power table from the
approved 401 design (STR floors 18/00→19/20/21 at L13/19/25, fighter
THAC0, +1 temp HP/level cap 30, +1/2 / +1 / +1 1/2 attacks at L7/13/25,
3/4/5 rounds, five uses, Divine Power exclusion; Casting Time 1 read from
the installed SPL); Chaos of Battle tides (three named tides, ally bonus =
enemy penalty, 5 rounds, magnitude 2/3/4 at L1/13/25, Fortune 1→2 at L19,
recast replaces); Divination toll disadvantage.

Gating: sibling artifacts as predicates (CBRTMG2/CBRCHT1D/CBRTMDV SPLs +
M_CBRAPR.lua). The 401 family has no unique artifact in auto/doubling mode;
its presence is assumed and documented, not enforced. Uninstall restores
KITLIST/SPLs from backup; the three appended strings remain (same accepted
residue class as 404's announce lines).

Verification: harness DESIGNATED 5; nogame — repoint matrix + byte-
idempotence + already-repointed byte-identity + missing-row/dup-row/
no-HELP-column/bad-SPL-signature/nonpositive-strref controlled-RED;
installer — full-chain 400→404→405→407→408 (TLK +3 exactly, repoints land,
408-only uninstall restores the pre-408 override byte-exactly, appended
strings persist) + predicate-skip without siblings. Full suite 117 green.

## Addendum 2026-08-22 — 407 listener runaway + Component 409 (`cbr_cleric_tempus_spec_apr_eeex_refresh`)

**Live verdict on 407 v0.1.0: broken.** In play, Branwen's attacks-per-round climbed
1.5 → 2 → … → 5 and snapped back to 1.5, cycling rapidly whenever the game was unpaused.

**Root cause (engine, not plumbing) — `research/07-spec-apr-listener-runaway.md`:** the
2026-07-20 premise "`EEex_Opcode_AddListsResolvedListener` fires after every derived-stats
rebuild" is false. Disassembly of `CGameSprite::ProcessEffectList` (Baldur.exe 2.6.6.0,
RVA 0x3AB390; hook sites from `InfinityLoader.db`) shows the hook fires once per *pass*
(every AI tick per sprite), while `CDerivedStats::Reload` + effect-list re-application run
only when `m_id % 15 == m_PAICallCounter % 15` (per-sprite AI-call counter) or `m_newEffect` is set; every other pass takes a fast
path straight into the same hook with the unrebuilt `m_derivedStats`. A relative
`+½` write therefore accumulates until the next real rebuild. The Lua stat write itself
works — the runaway is the proof.

**Fix (listener, v0.2.0):** make the write idempotent per rebuild with a marker that lives
in the same struct as the bump: a private spell state `CBR_TEMPUS_SPEC_APR` (SPLSTATE.IDS,
planned value 242, allocated install-time like 401's bridge states) set in
`stats.m_spellStates` (`Array<unsigned int,8>`; word `id/32`, mask `1<<(id%32)` — the
engine's own `SetSpellState` packing) after the bump. `Reload` clears every spell state,
so "bit clear ⇔ this pass rebuilt the stats". Gate order: kit stat 152 → marker → selected
slot → ITM prof → pips ≥ 2 → set marker → bump. The marker is written *before* the bump so a
missing `:set` binding can never re-enable the runaway (pcall fuse retires the listener
after 10 errors). Read/write `sprite.m_derivedStats` directly (the struct `Reload`
targets; identical to `getActiveStats()` at hook time because `m_bAllowEffectListCall` is
already 1 there). Weapon swaps that do not dirty the effect list are picked up within one
rebuild (≤ 15 ticks); swap-in on a fast pass lands immediately. Still save-clean, still
zero residue on removal. Rejected: per-sprite "last written value" cache (ambiguous when
the fresh engine value equals the previous bumped value — exactly Holy Power tier-1);
Lua-managed op1 effect (persists in saves, needs refresh/removal bookkeeping inside the
hook); forcing `m_newEffect` every tick.

**Packaging:** the 407 template now carries two placeholders (`%CBR_TEMPUS_KIT_ID%`,
`%CBR_TEMPUS_SPEC_APR_STATE%`); `tempus_spec_apr_eeex.tpa` gains
`cbr_plan_tempus_spec_apr_state` (reuse the symbol's value, else highest free value ≤
planned; duplicate symbol / shared value = hard failure) and
`cbr_allocate_tempus_spec_apr_state` (wraps 401's `cbr_find_or_allocate_splstate`,
`CLEAR_IDS_MAP` after). The tp2 shares one macro between **407** (fresh install; now also
materializes `SPLSTATE.IDS` into override) and the new tail component **409**, which
re-ships `override/M_CBRAPR.lua` over a live install — the live 407 is mid-stack under 408
and is never reinstalled. 409 predicates: the 407 artifact (`M_CBRAPR.lua`) first, then
407's own. Its uninstall hands the previous listener back (WeiDU backup); on a fresh
install it is a byte-identical no-op. Mod `VERSION` bumped to v0.2.0.

**Verification:** new `tests/lua/cbrapr_sim.lua` + `tests/test_cbrapr_listener.py` drive the
stamped listener through the real cadence with a fake EEex surface under EET's Lua 5.3
(13 cases: +½ exactly once per rebuild across 200 fast passes, Holy Power baseline
1.5 → 2.0, marker lifecycle, every gate, weapon swaps on the fast path, key-encoding
arithmetic incl. the 5 ceiling, inert on a missing array/setter). These were written first
and reproduced the live bug against v0.1.0 (APR pinned at key 5, swap-in → key 7).
Hermetic harness: both placeholders stamped, SPLSTATE row appended once, byte-idempotent
re-run, symbol reuse (200), occupied 242 → 241, duplicate symbol → NOT INSTALLED, stale
template (kit placeholder only) → NOT INSTALLED. Installer: 407 fresh (+`SPLSTATE.IDS`)
with byte-exact uninstall; 407 → tamper → 409 re-ships exactly the fresh bytes without a
second IDS row, WeiDU.log #407 then #409, uninstall of 409 restores the tampered file;
409 without 407 → predicate skip. Parse-checks clean. Live deployment: tail-install 409
with the game closed, then restart the game (`M_*.lua` load at process start).

**Knowledge captured:** bg-modding KB `eeex-sprites.md` § ListsResolved,
`ie-apr-proficiency.md` (f), `gotchas.md` § API Corrections — the per-pass cadence, the
field map, the SPLSTATE-bit idempotence pattern, and the `InfinityLoader.db` → PE
exception table → capstone re-derivation recipe.
