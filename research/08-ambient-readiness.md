# 08 — Enemy "ambient readiness": anti-cheese pre-buffing beyond SCS (candidates 120 / 121)

User question 2026-08-23: with EEex, how hard is it to (1) make SCS casters nearly impossible to
one-click assassinate before they have at least Stoneskin-class buffs up — more buffs when they'd
logically expect the party — without infinite slots and without killing assassination as a
tactic; (2) give fighters / rogues / clerics SOME pre-buffs too.

Provenance: research run `wf_34058b37-a06` (2026-08-22/23) — the SCS pre-buff and EEex-API
readers completed with file:line evidence (raw JSON kept in the session scratchpad as
`research_prebuff.json` / `research_eeex.json`); the detection / buff-duration / prior-art readers
were stopped (token budget) and replaced by the direct checks in §2. The later, explicitly
authorized live capability spike is recorded in `research/10-ambient-readiness-spike.md`.

## 0. Reconciliation and current decision record (updated 2026-08-31)

This file was imported from the uncommitted source-checkout research at
`C:\src\private\chriz-bg-rebalance\research\08-ambient-readiness.md` (22,651 bytes,
modified `2026-08-24T19:44:44Z`). Its numbered sections below preserve the investigation
chronology; their open options and provisional recommendations are historical context. The
approved authority is
`docs/plans/2026-08-27-scs-ambient-readiness-design.md`, followed by its implementation
plan. In particular, the later decision supersedes §9's temporary lean toward a free first
application.

The 2026-08-30 probe's clock conclusion is also superseded. It guessed two EEex globals that
do not exist and silently fell back to `os.clock()`. Its numeric latency values are not
engine-time evidence. Non-clock observations remain usable only where independently checked;
the current EEex v1.2 contract and provenance are in
`research/11-eeex-v1.2-readiness-compatibility.md`.

Current agreed contract:

- **Component 120 comes first** as an SCS/SR compatibility repair. It corrects only proven
  weapon-protection semantics; it does not redesign Moment of Prescience. See
  `research/09-scs-sr-moment-of-prescience.md` for the current binary audit.
- **Component 121 is an interim hybrid bridge, not the long-term AI architecture.** The
  user's separate EEex AI overhaul is expected eventually to own this logic. Both the
  ambient and urgent layers therefore need independent runtime disable/ownership controls.
- **Ambient eligibility starts conservatively at installed self-buffs lasting at least
  2,400 seconds**, filtered by what the caster really has memorized and by reserved
  curation grades / explicit include-exclude data. Cautious neutral and allied casters with
  recognized SCS combat scripts are eligible as well as hostile casters.
- **Resource policy is one real memorized copy per genuine spellbook reset.** The first
  confirmed application debits exactly one slot. Maintenance of that same buff is free only
  after natural expiry and only out of combat with no party member visible. Early removal,
  dispelling, or a suspiciously early loss suppresses free maintenance until a proven reset;
  save/load, elapsed time, and area transition are not resets. SCS's later sight-prebuff pass
  must not double-charge a managed spell.
- **Urgent defense is a fast normal cast, not an instant free effect.** On clear first
  contact, an eligible hostile caster may displace only proven passive work and attempt one
  ordinary, interruptible self-cast using a real slot, aura, and casting time. Candidate
  order is Absolute Immunity, genuine Improved Mantle, Mantle, then PfMW, filtered by actual
  opcode semantics. The attempt is spent when casting starts; a contact episode rearms only
  after one full round without seeing any party member.
- The separately authorized installed EEex spike proved non-clock primitives. Exact-record debit and
  quick-list repair, engine reset notification, cosmetic-free SCS delivery, narrow initial
  SCS reimbursement, current/queued action inspection, normal `SpellRES`, start
  confirmation/interruption, visibility state changes, and Project Image ownership were
  observed. It did not prove elapsed timing, natural-expiry timing, retry timing, or the
  full-round rearm interval. An independent global “dialogue active” boolean remains
  ambiguous and therefore receives no speculative implementation. See the correction in
  `research/10-ambient-readiness-spike.md`.

Current read-only recheck on `2026-08-29` confirms SCS 35.21 component 6030 and 585 installed
common-mage scripts. The authorized 2026-08-30 spike used only a disposable save and
transient remote-console IPC; it installed nothing, saved nothing, and finished with the
game closed and all hashed game inputs unchanged.

### 0.1 Session-scoped Task 6 probe (corrected 2026-08-31)

`research/scripts/ambient_readiness_probe.lua` is the reviewable, non-persistent probe for
the remaining capability gate. Merely loading it defines `_G.CBR_RDY_PROBE`; registration is
an explicit `CBR_RDY_PROBE.install()` call. Its process-lifetime listeners are append-only
but root-guarded, and `CBR_RDY_PROBE.teardown()` makes them inert. The probe keeps timestamps
and observations only in memory and exposes them through `dump()`; it has no file, resource,
save, or installer write path.

The checked-in probe now capability-selects one verified listener/clock pair before
activation: v1.2 deferred + `GetCurrentTime()` first, or legacy synchronous + direct
`m_gameTime` only when deferred is absent. The 2026-08-30 execution used the older
`os.clock()` fallback; its numerical timestamps remain invalid even though the current file
no longer contains that fallback.

The only mutating helpers are explicit controlled experiments:

- `debit_once(sprite, resref)` changes one available memorized bit only after validation,
  records an in-memory restoration token, rebuilds quick lists, and rolls back immediately
  if the expected one-slot delta is not observed;
- `restore_debit(token)` restores that exact record and confirms availability; and
- `queue_normal_cast(sprite, resref)` queues an ordinary self `SpellRES`, leaving slot,
  aura, casting time, visuals, and interruption to the engine.

`teardown()` attempts every outstanding restoration before becoming inert. A controlled
slot experiment must still use a disposable actor/save and may not be repeated on that actor
unless restoration is independently confirmed or the save is reloaded. No production API
choice is considered proven merely because the probe parses or because an action was queued;
Task 6 must separately observe the started action and resulting engine state.

### 0.2 Corrected Task 6 capability decision (2026-08-31)

The spike observed `See([PC])`, later SCS preparation, and a later cosmetic-free delivery in
that order, but its `os.clock()` timestamps cannot measure the gaps. The exact 0.570 s,
0.938 s, and 0.871 s claims are withdrawn. A current-version live pass must use the EEex
world timer before component 121 receives timing acceptance.

The non-clock production paths remain fixed to the observed installed contracts:

- mutate exactly one available mage/priest memorized record and rebuild quick lists with a
  real `CAbilityId` and change amount `-1` / `+1`;
- treat `EEex_Sprite_AddQuickListCountsResetListener` as the only charge-reset signal;
- identify `m_curAction`, `m_queuedActions`, action `m_specificID`, and CString resrefs via
  `m_string1.m_pchData:get()`; unknown current/queued representation skips;
- queue urgent defense as normal action 31 `SpellRES`, and spend the contact attempt on an
  exact started-action callback even when the spell is interrupted before the engine
  debits its slot;
- identify a Project Image clone by opcode 237, parameter 2 equal to 2, and `m_sourceId`
  pointing to its engine-disabled owner; both clone and locked owner skip; and
- reimburse only the exact initial generic SCS delivery-181 / adjacent RemoveSpell-147
  sequence for the ledger-paid spell, after confirming its numeric `m_specificID`, delivery
  effect, and availability delta. Free `_PRECAST`, renewal, combat, non-adjacent, and unknown
  shapes never reimburse.

`Infinity_GetInCutsceneMode()` is a proven cutscene predicate. The available
`GetInControlOfDialog()` observation is not a dialogue-active predicate (it was true during
ordinary play), so the runtime does not reinterpret it. Dialogue/tactical actions remain
outside the passive allowlist and uncertainty remains a no-action result.

### 0.3 Current EEex v1.2 implementation result (2026-08-31)

Components 120 and 121 are implemented on `codex/ambient-readiness-121`; neither has been
installed into the active playthrough game. A disposable v0.11 laboratory installation of
121 produced no readiness effects because production required the nonexistent
`EEex_GameState_GetTime` global and correctly retired itself before mutation. Component
121 now targets EEex v1.2.0. Its public WeiDU transaction requires BG2:EE/EET, SCS Smarter
Mages 6030, `M___EEex.lua`, final loose `SPELL.IDS`, and SCS's final
`instant_prebuff_spells.2da`; it does not hardcode EEex component numbers. The stamped
profile records the v1.2 deferred listener and raw 15-Hz engine-time unit, while the runtime
rechecks every required entry point and fails closed before gameplay mutation if world time
or another required capability is unavailable.

The install-time compiler resolves each candidate dynamically, validates both memorized and
cosmetic-free delivery SPL semantics, and classifies urgent candidates by reachable genuine
opcode 120. Current SR Moment of Prescience is therefore emitted as a false Improved Mantle
candidate and skipped at runtime; a future restored Improved Mantle is automatically enabled.
The Project Image owner-lock source is likewise resolved from the final `SPELL.IDS` and
stamped into the runtime rather than assuming the currently observed `SPWI703` slot.
The public component publishes only `override/M_CBRRDY.lua` through WeiDU's backup-aware
transaction and changes no SPL or BCS file.

Hermetic coverage now includes absent SCS/EEex-autoload/mapping prerequisites, current
SCS/SR, future genuine Improved Mantle, optional ambient omissions, malformed mapping
rollback, deterministic reinstall, exact synthetic uninstall restoration, and stamped Lua
syntax/token checks. The fake-EEex suite covers exact ambient debit/reset/maintenance and SCS
reimbursement, normal urgent casting and interruption, passive-only queue displacement,
Project Image exclusion, bounded retry, contact rearm, hot reload, ownership flags, marshal
shape, recycled engine-object IDs, incomplete effect-list fail-closed behavior, and
independent fault fuses. The v1.2 path is source- and simulation-verified; live v1.2
deployment and gameplay acceptance remain a separate user-approval checkpoint. The
source/simulator-verified older-EEex capability fallback is implemented, but its corrected
live test remains a later, separately approved stage after v1.2 acceptance.

## 1. How SCS 35.21 pre-buffs in this install (verified)

- **Mechanism** (`stratagems/caster_shared/caster_definitions.ssl:470-513`): each prep block =
  `HaveSpell(X)` + `Global("instantprep","LOCALS",0)` + sighting trigger →
  `ReallyForceSpellRES("%X_PREBUFF%",Myself)` + `RemoveSpell(X)` + `Continue()`. Pre-buffs are
  **instant** (no casting time/aura), **consume one memorized slot**, and land at **full
  duration** — the `dwsw###/dwsp###` clones only drop cosmetic opcodes 139/174/141/215/50
  (`sfo/filetype/lib_spl.tpa:753-830`; binary: `dwsw408` op218 dur 2400 = `spwi408`). Mapping:
  `weidu_external/data/stratagems/instant_prebuff_spells.2da`.
- **Free exceptions:** `*_PRECAST` entries (Stoneskin for SR's mage/thief list, Ironskins for
  SR druids) fire without `HaveSpell`/`RemoveSpell` (`mage/ssl/prep/very_long.ssl:11-49`).
- **Tiers** = four prep files by duration class, all `Continue()` in one script pass
  (`mage/ssl/main/magesetup.ssl:53-56`, `priest/ssl/main/priestsetup.ssl:14-17`):
  very_long (Armor, Stoneskin, Mind Blank, Non-Detection + out-of-sight summons) → long
  (Shield, PfNM, Prot. Elements/Dispelling Screen, Spirit/Ghost Armor, elemental protections)
  → medium (Spell Shield, Spell Turning/Deflection, Energy Blades) → short (Mirror Image,
  Improved Invisibility/Mislead, Globe/Minor Globe, SI:*, Fire Shields, Spell Trap, Haste…).
  PfMW/Mantle/Absolute Immunity are never pre-buffed; they are the **first real cast** after
  sighting, 6 s timer (`mage/ssl/prep/first_round_buff.ssl`).
- **Tier gating is in-game, not install-time:** `DMWW_mage_prep_difficulty` /
  `DMWW_priest_prep_difficulty` (1 none … 5 everything; 0 = follow engine `Difficulty()`),
  `lib/data/difficulty_controls.2da:6,9`, `ssl/difficulty.slb`. `stratagems.ini` has no prep
  keys (only `Conceal_Prebuff_Spell_Names=0`, `potion_version=6`). Quirk: `CorePlusPrep`
  (gates the long tier) reads the general mage/priest difficulty var, not the prep var
  (`difficulty.slb:176-189`).
- **This install:** newest save (Kool Koveras auto-save, 3484 globals) has **no DMWW prep
  globals** → default 0; `Baldur.lua` `Difficulty Level = 5` → SCS resolves to its top tier.
  **The user already plays with maximum SCS pre-buffing.**
- **Sighting triggers — the actual gap:** only `SpellPrecastLong` (very_long mage tier) uses
  `Detect(NearestEnemyOf(Myself)) OR Range(Player1..6,20)` ("so that they're in place even if
  you sneak up", `caster_definitions.ssl:489`). Every other tier, **all priest prep**, potions
  and fighter HLAs require `See(NearestEnemyOf(Myself))` — a stealthed/invisible opener beats
  them. Mages with `Detect([PC]) && !See([PC])` cast Oracle/Detect Invisibility at Core+
  (`mage/ssl/generalblocks/findhidden.ssl`, 5-min timer). Neutral casters never pre-buff
  (`DMWWNeutralPrebuff` is never set); on turning hostile they buff instantly on the first
  script pass that sees the party.
- **"Expecting the party"** is only the LOCAL `created_out_of_sight` (caster not in `See()` of
  the party on its first script pass, `mage/ssl/generalblocks/gohostile.ssl:14-24`) — there is
  no per-creature "alert" concept beyond that.
- **Non-casters** (`genai/ssl/initial.ssl:58-137`, `potionuse.ssl`): thieves/assassins/stalkers
  get silent invisibility `dw#silin` at creation and re-hide when no PC is `Detect()`ed;
  fighters get **nothing at spawn** — potions (speed, giant strength, defence, heroism, healing)
  only on `See()` at Core+, 6 s each. Potion allocation is install-time per CRE
  (`potion/potion_shared.tph`), undroppable clones for 6/8 of them.

## 2. What can be "always up" under Spell Revisions (installed SPL dumps, 2026-08-23)

| Spell | Duration | Notes |
|---|---|---|
| Stoneskin `spwi408` / Ironskins `sppr506` | **2400 s = 8 game hours** | 3 → 8 skins (L1…L16+); each skin absorbs one weapon hit → **absorbs a backstab** |
| Mirror Image `spwi212` | 300 s = 1 hour | SR made it long |
| Spell Shield `spwi519` | 300 s | |
| Armor of Faith `sppr111`, Barkskin `sppr202`, Prot. from Evil `sppr107` | 300 s | priest ambient set |
| Minor Globe `spwi406` | 120 s | borderline |
| PfNM `spwi311` | 60 s | short |
| PfMW `spwi611` | 24 s | never ambient (by design) |

Ambient-eligible ⇒ the "expect trouble" package is Stoneskin/Ironskins + MI + Spell Shield
(arcane), AoF + Barkskin + Ironskins (divine) — all slot-consuming, so no infinite-slot problem.

## 3. Historical EEex v0.11.0-alpha hook inventory

- **Spawn:** `EEex_Sprite_AddLoadedListener(fn(sprite))` — from the `CGameSprite::Unmarshal`
  hook (`EEex_Sprite.lua:8-10, 1562-1577`; `EEex_Sprite_Patch.lua:213-219`): area load, save
  load, transitions, clones; name/EA/area may be **unsettled at fire time** → act on the first
  `ListsResolved` pass. No construct/destruct Lua listener.
- **Instant, slot-free, cast-time-free effects with any source resref:**
  `EEex_GameObject_ApplyEffect(sprite,{effectID=…,res=…,m_sourceRes=…,sourceID=…})`
  (`EEex_GameObject.lua:257-323`). `ReallyForceSpellRES` via the instant action path is
  unreliable (skill doc: silent no-op) — queue it, or use ApplyEffect (op146 with p2=1 for a
  silent self-cast: speculative, untested).
- **No damage/attacked listener.** The op12 hooks exist but are dead unless `CONCENTR.2DA
  CHECK_MODE=EEex-LuaFunction=…` (this install: 0) and enabling them hijacks concentration
  checks. Substitutes: `EEex_Sprite_AddBlockWeaponHitListener(fn(ctx))` — fires in
  `CGameSprite::Swing` after weapon immunities, ctx `{attackingSprite,targetSprite,weapon,
  weaponAbility}`, **return true blocks the hit like op120** (`EEex_Sprite.lua:992-1056`,
  `EEex_Mix_Patch.lua:15-135`); `EEex_Action_AddSpriteStartedActionListener` (any sprite
  starts Attack/Spell); `EEex_AIBase_AddScriptingObjectUpdatedListener` (ATTACKER/HITTER/
  SEEN… updates; values not visible in Lua). No projectile-hit hook.
- **Queries:** EA `sprite.m_typeAI.m_EnemyAlly`; state bits via `getActiveStats()
  .m_generalState` (INVISIBLE 0x10, IMPROVEDINVISIBILITY 0x400000, MIRRORIMAGE 0x40000000);
  `EEex_Sprite_GetSpellState` (STONESKIN 18); modal 3 = stealth; BCS semantics from Lua via
  `EEex_Trigger_EvalConditionalStringAsAIBase('See([PC])', sprite)` / `Detect`, objects via
  `EEex_Object_EvalStringAsAIBase`; in-range via `forAllOfTypeStringInRange('[PC]',448,…)`
  (**never pass CGameObjectType ints — hard crash**).
- **Periodic:** old `EEex_Opcode_AddListsResolvedListener` fires synchronously for each
  resolved effect-list occurrence and can repeat around one sprite AI pass; v1.2's
  `EEex_Opcode_AddDeferredListsResolvedListener` coalesces that to at most once per sprite AI
  tick. Stats are rebuilt only every 15th fast-path pass or on `m_newEffect` (`research/07`),
  so keep callback work O(1), elapsed logic on raw game time, and mutations idempotent.
- **Slot economy:** memorized lists are bound (`m_memorizedSpellsMage/Priest`, records with
  `m_flags` bit0 = available; `CheckQuickLists`). Decrement from Lua = clear bit0 +
  `CheckQuickLists(id,-1,0,0)` — **probable, untested on v0.11**. Alternative: queue
  `SpellRES` (normal cast, honest slot) / `SpellNoDecRES`.
- **Persistence:** `EEex_Sprite_SetLocalInt` → LOCALS (readable by SCS BCS, saved);
  `EEex_Sprite_AddMarshalHandlers` + `EEex_GetUDAux` (no booleans on v0.11). Never persist
  EEex opcodes 400-409 on creatures (load-time CTD precedent); no effect-list surgery
  (CDTweaks #260 save-poisoning precedent).
- **BCS↔Lua:** trigger `0x410E EEex_LuaTrigger`, action `472 EEex_LuaAction`, op402;
  Lua can set LOCALS SCS scripts read, and evaluate SCS's own triggers.
- Landmines: listener registries append-only (guard re-registration); Lua errors propagate
  into engine code; loaded-listener fields unsettled; instant-path RES actions unreliable.

## 4. Where the cheese actually lives (gap analysis)

1. Stealth/invisible opener vs **See()-gated tiers**: at tier 5 a *seen* mage gets MI, Spell
   Shield, Stoneskin… instantly; an *unseen* opener only meets the Detect/Range-20 tier
   (Stoneskin, Armor, Non-Detection). If Stoneskin is memorized, the backstab is absorbed by
   a skin and the mage wakes up fully buffed — the one-click kill already fails. Victims:
   casters **without Stoneskin memorized** (low level, spell-list variance) and the Range-20
   race (script pass ≈ 1 s; an opener from outside 20 units with a ranged/charge attack).
2. **Priests:** no Detect path at all; Ironskins free only for SR druids; AoF/Barkskin are
   short-tier. A stealth opener on a cleric meets nothing.
3. **Fighters/rogues:** nothing at spawn; potions need See().
4. **Post-dialogue hostility:** fine for casters once the first hostile preparation pass
   runs, but the probe did not validly measure that scheduling window.

## 5. Options

**A — SCS-native re-gating (no EEex; candidate 120 `cbr_scs_ready_vs_stealth`)**
Tail component patching the compiled SCS scripts in `override` (regex over the BCS, the same
technique planned for 111): (a) give the *long* tier and priests the Detect/Range-20 OR-block
that very_long already has; (b) promote Ironskins/Armor of Faith/Barkskin to that path;
(c) optionally let "expecting" non-casters drink one defence/speed potion at creation
instead of on See(). Plus the zero-cost lever the user already has: the in-game SCS prep
widget (tier 5 is already effective here). Effort: small-medium; no live-game CTD risk;
idempotent; reversible. Fun: assassination still kills anything unskinned and still strips a
skin; it stops being an I-Win vs. every caster.

**B — EEex readiness layer (candidate 121 `cbr_eeex_ambient_readiness`)**
`M_*.lua`: loaded-listener → first ListsResolved pass → classify hostile sprites (class,
level, "expects trouble" heuristic) → apply an ambient package via `EEex_GameObject_ApplyEffect`
with the real spell as `m_sourceRes` (so SR/SCS op321 anti-stacking still works), decrement
the memorized slot (bit0 + CheckQuickLists) or, if that proves unreliable, queue a normal
`SpellRES`; stamp a LOCAL so it runs once per creature and SCS scripts can see it.
Extensions: **alert escalation** (`Detect([PC]) && !See([PC])` evaluated from Lua every N
passes → apply the medium tier early = "they heard you"); **reflex skin** via
`AddBlockWeaponHitListener`: on a weapon hit against an unbuffed caster that has Stoneskin
memorized, block that one hit (as op120 would) and apply Stoneskin minus one skin — exactly
"the skin absorbed the backstab", gated to designated casters or a level-based chance so
assassination stays viable against the rest. Non-casters: spawn-time "battle-ready"
package (equivalent of their own allocated potions, consuming the potion item). Effort:
large — Lua + fake-EEex test harness (409's exists) + WeiDU + live validation on the only
SCS+SR install; unknowns in §6 must be live-probed first.

**C — Hybrid (recommended):** ship A first (it removes most of the cheese and teaches what
"feels" right), then B only for the pieces A cannot do: non-caster readiness, alert
escalation, reflex skin.

## 6. Open questions / live probes needed before B

- Definition of "expecting trouble" (named/unique creatures? level ≥ N? area class? SCS
  script class?) — user lever.
- Does the Unmarshal-based loaded listener fire for spawn-point/`CreateCreature`/op67
  summons with `m_pArea` set? Does `BlockWeaponHit` fire on misses too?
- Does clearing memorized bit0 + `CheckQuickLists(-1)` reproduce engine bookkeeping on v0.11?
- `ApplyEffect` op146 p2=1 as silent self-cast: children get the SPL as `m_sourceRes`?
- Difficulty mapping: `Baldur.lua` level 5 ↔ `Difficulty(HARDEST)` in `ssl/difficulty.slb`
  (inferred from the 1..5 order, not checked).
- Detection/prior-art pillars not researched (stopped): engine stealth-detection roll
  cadence; community precedent for spawn-time buffs (Improved Anvil / Tactics).

## 7. User clarification (2026-08-23) → revised recommendation

- **The real pain is latency + the honest-player wait.** Attacking before an enemy's
  pre-buffs land feels like an engine exploit, so the user waits; they want buffs already
  up (or a ≤1 s reaction), for whoever is in the fight. Scope narrowed: mages (and any caster
  with hour-plus buffs) should logically walk around buffed, more so when expecting company;
  fighters/clerics without long buffs need no ambient prep; "had no idea" scenarios are fine.
- **Where the wait actually comes from** (§1): SCS's batch is instant once its script pass
  runs with `See()` true. Latency = script-pass cadence (sub-second to ~1 s; **unmeasured**)
  + one extra pass for the hostility transition when a non-hostile creature is attacked
  (`gohostile.ssl`) + PfMW / Mantle / Absolute Immunity being real 6-s casts by design
  (`first_round_buff.ssl`) + zero coverage for stealth openers. "After the round tick" is
  the sum of these, not a per-round gate.
- **Revised plan — 121 "ambient at load" is primary and simpler than alert-escalation:**
  on sprite load (Unmarshal → first `ListsResolved` pass, fields settled) a hostile caster
  (+ option: neutral casters that carry an SCS combat script) gets its long-duration package
  applied instantly, consuming slots — reuse SCS's own `_PREBUFF` clones from
  `instant_prebuff_spells.2da` (SR-aware, cosmetic-free, same source resrefs SCS's
  anti-stacking expects); stamp a LOCAL so it runs once and SCS scripts can see it. Package =
  the ambient-eligible set of §2 (Stoneskin/Ironskins, Mirror Image, Spell Shield, Armor,
  Non-Detection; Armor of Faith, Barkskin, PfE, + Chaotic Commands/Death Ward if ≥ 1 h under
  SR). Slot decrement: queued `RemoveSpell(SPELL)` exactly like SCS (probe: queued removal
  reliability — gotchas record queued `RemoveSpellRES` failing for innates) or memorized
  bit0 flip + `CheckQuickLists`. Zero latency, no `See()`/`Detect()` dependency, no polling.
- **Optional reaction sub-feature** (only if measured): per-pass check that a hostile caster
  within Range 20 / `Detect` of the party without its short tier gets it immediately.
  Cheap first step: a ~20-line EEex probe logging load → first See → buff timestamps to
  measure the real latency in the user's game before building anything.
- **120 (script re-gating) demoted to optional** — ambient-at-load makes the sighting gate
  moot for long buffs.
- **Open (user):** neutral/blue casters that carry an SCS combat script — ambient too, or only
  red-circle hostiles? (Recommendation: yes if they have an SCS mage/priest script; "had no
  idea" = casters with no combat script at all.)
- **Delegation plan (user rule 2026-08-23):** Lua module + fake-EEex harness → implementer
  (Opus); independent design/code review → Codex (`gpt-5.6-sol`); mechanical sweeps → Sonnet;
  engine-cadence probes / hook semantics → session model or Sol.

## 8. Corrections + design constraints from the user (2026-08-23, second pass)

- **Latency is real and unverified by me:** the user sees SCS's batch land 1–3 s after
  engagement, never more than a round. The sources only prove the *action* is instant;
  *when the script pass runs* was never measured. Plausible engine causes: per-creature
  script cycle; a creature committed to an action (move/attack/cast) does not re-evaluate
  its script until the action ends; neutral casters spend a pass on `gohostile`. §7's
  "instant once seen" was wrong as a description of play. **First deliverable of 121 must
  be the timing probe** (via the EEex remote console, `@file` mode, user sign-off): log
  ticks between first PC action against a hostile caster / first `See` and the prep block
  firing, for a few casters and a fighter (potions).
- **Reaction must not depend on the script pass.** Design: an *engagement detector* in Lua —
  `EEex_Action_AddSpriteStartedActionListener` (PC starts Attack/Spell targeting the
  creature), `EEex_Sprite_AddBlockWeaponHitListener` (hit), `AddScriptingObjectUpdatedListener`
  (SEEN/ATTACKER) — that reacts within one AI tick. Two candidate reactions, to probe: (a)
  clear the creature's *idle* action (NoAction/RandomWalk/MoveToPoint/Wander only — never
  dialogue/cutscene) so SCS's own script runs its prep batch on the very next pass, keeping
  SCS's spell selection; (b) apply the short-tier `_PREBUFF` clones the creature has
  memorized directly from Lua (duplicates SCS logic — fallback only). Class-agnostic: the
  same detector advances fighters' potion pass.
- **Waiting exploit (user):** slot-consuming ambient buffs with durations invite "wait it
  out": 1-hour buffs (MI, Spell Shield, AoF, Barkskin) = **5 real minutes**, Stoneskin 8 h =
  40 real minutes, and leaving the area to rest passes 8 h at once. A one-shot ambient
  package would leave casters *weaker* than without the mod (buff gone, slot gone).
  ⇒ Ambient readiness must be a **maintained invariant**, not a one-shot: on load and on a
  cheap out-of-combat check (every ~N passes; `EEex_Sprite_GetSpellState` STONESKIN etc.),
  re-apply expired ambient buffs **only while not in combat** (`inafight` LOCAL = 0, no
  `See([PC])`); never refresh mid-fight (SCS's renewals stay real casts). Fiction: eight
  hours passing for the player passed for the mage too.
- **Slot policy options for the ambient package:** (a) fully free baseline like SCS's own
  `*_PRECAST` exception — waiting changes nothing, slight buff to casters; (b) consume the
  memorized slot once on first application, refresh free — SCS parity in the first fight;
  (c) consume on every refresh — rejected (waiting exploit). Recommendation: (b), with (a)
  as a subcomponent option.
- Open questions to the user: slot policy (a/b); neutral SCS-scripted casters included?;
  is interrupting *idle* actions of hostile creatures on engagement acceptable (vs the pure
  Lua fallback)?

## 9. User directions (2026-08-23, third pass) + curation baseline

- **Slot policy:** leaning **free** ("a little unfair, but not really that bad"); the user wants
  to sit with it before implementation — immersion of fairness matters. Design note to
  verify: SCS's own on-sight batch has no "already active" check in `SpellPrecast` (triggers
  seen: DoNotPrebuff, SSLBoolean, HaveSpell, instantprep, See) — if so, SCS re-applies and
  **spends the slot at fight start anyway**, so a free walking-around copy still costs the
  real slot in the first fight (natural parity; op321 self-remove just refreshes duration).
- **Broader, curated set — and more casters, but not all:** "not all mages would know and not
  all are wise enough". Curation levers: (1) the ambient list below × what the creature
  actually has memorized (SCS's per-creature allocation already encodes "knows it");
  (2) a caution grade per creature (level band / kit / named-boss / explicit overrides)
  deciding how much of its memorized long set it walks around with; (3) explicit
  include/exclude list. This is the base layer for deep SCS rebalancing — plan it as such.
- **Cautious neutral and allied casters get it too**, curated (user).

**Installed durations of the SCS `_PREBUFF` clones (SR v4.19; L1 / L10 / L20; 300 s = 1 game
hour = 5 real minutes):**

| Tier | Spells |
|---|---|
| ≥ 8 h (2400 s+) | Stoneskin, Ironskins, Mage Armor, Non-Detection (2400); Impervious Sanctity of Mind (2880); Mind Blank (7200) |
| ~1 turn/level, 420→1200 s | Prot. from Fire / Cold / Acid / Electricity (wizard + priest fire), Death Ward, Chaotic Commands, Free Action; Prot. from Magic Energy 720→1200 |
| 2 h (600 s) | Ghost Armor, Spirit Armor; Prot. from the Elements 420→600 |
| 1 h (300 s) | Shield, Mirror Image, Spell Shield, Minor/normal/Greater Spell Deflection (SR names), Dispelling Screen, Armor of Faith, Barkskin, Energy Blades |
| short (≤ 240 s) — never ambient | PfNM 60, Minor Globe / Globe 120, Physical Mirror 120, Improved Chaos Shield 120, Regeneration 180, Magic Resistance 108–240, DUHM 60, Divine Power 42–120, Globe of Blades 60 |

Maintenance cost follows directly: 8-h buffs need a refresh only after rest/long travel;
1-turn/level buffs every 7–20 real minutes; 1-h buffs every 5 real minutes — all cheap for
an out-of-combat check, all exploitable without one.

## 10. Decision direction + spike plan (2026-08-23)

- User leans **(b) direct Lua reaction** as the long-run product: never touches the action
  queue → cannot disturb scripted interactions or in-progress actions; works mid-action. (a)
  stays a cheap experiment. Decide after an in-game spike on 1–2 representative creatures.
- **Spike = zero-footprint, session-scoped Lua** injected through the installed EEex remote
  console (`M_EEexRC.lua`, `@file` mode reads the script from disk) on a **throwaway copy of
  a save** — nothing installed, restart = clean; only the console's transient IPC files touch
  `override/` (needs the user's explicit sign-off; game not otherwise written to).
- Measure (ticks via the per-tick ListsResolved pass): (1) **baseline** — first PC attack /
  first `See` → SCS's own prep batch lands (STONESKIN spell state / MIRRORIMAGE state bit
  flips); (2) **(b)** — engagement detector → `EEex_GameObject_ApplyEffect` op146 of the SCS
  `_PREBUFF` clone (p2=1) → state flips same tick? children carry the clone as `m_sourceRes`?
  skins/images correct? SCS's later pass re-casts or skips (HaveSpell)? slot decrement via
  bit0 + `CheckQuickLists(-1)` reflected in the memorized list?; (3) **(a)** — clear idle
  action → ticks until SCS's pass fires (only if cheap and safe).
- Safety rules (gotchas): only send primitives already proven or type-checked against the
  installed EEex source; a console timeout right after a new engine call = crash, not "wrong
  screen"; never on the live save.
- Deliverable: `research/09-ambient-spike.md` (measured numbers + decision), probe Lua kept in
  `research/scripts/` — no residue in the game directory.
- Candidate creatures: one hostile-at-spawn idling SCS caster; one dialogue-turned-hostile
  caster (user to pick).
