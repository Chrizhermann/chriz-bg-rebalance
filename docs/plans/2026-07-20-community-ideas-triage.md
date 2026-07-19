# Community ideas triage — Discord backlog 2026-07-12 → 2026-07-20

**Status:** triaged 2026-07-20 against the live install's WeiDU.log (read-only). Nothing
green-lit for implementation yet; per-idea verdicts and proposed component slots below.
Each green-lit item still gets its own `research/NN-*.md` (binary evidence) and, where
non-trivial, a `docs/plans/*-design.md` approved by the user — this document replaces neither.

**Source:** Discord suggestions channel, 2026-07-12 → 2026-07-20
(ChrizFader = the user; IAIWE, Jester, Reeca, GachiBalor, Archibald = community).

## Verdict summary

| # | Idea (proposer) | User stance | Verdict | Slot | Effort |
|---|---|---|---|---|---|
| 1 | Unidentified potions all look the same (ChrizFader) | own idea, high | Research first — engine has no per-state icon; EEex hook framework | 310 | M–L |
| 2 | Magic + cursed weapons look mundane until identified (IAIWE, Jester) | implicit positive | Same framework as #1; extra Randomiser #570 interaction | 311 | M–L |
| 3 | Weapon base damage à la NWN2/Forgotten Armament (IAIWE) | cautious yes, **dice only** | Design session, then table-driven dynamic patch | 320 | M |
| 4 | Granular cleric/druid weapon loosening, deity-appropriate (IAIWE + ChrizFader) | agreed, own direction | Continuation of Tempus 400-machinery for other kits | 410+ | M |
| 5 | Dragons stronger on high difficulties (ChrizFader + thread) | own idea, **flagship** | Full research + design; layered over SCS #6540 | 110 | L |
| 6 | Monks use quarterstaves (IAIWE) | **low priority** | Parked | — | S |
| 7 | Rasaad-quest monk headband, crit immunity (IAIWE) | **low priority** | Parked | — | S–M |
| 8 | Kensai may use bracers, not gloves (IAIWE) | liked, minor | Parked-near; revisit in a 4xx batch | 4xx | S |
| 9 | Weak companions need tweaks (ChrizFader) | own idea, vague | Out of scope here → NPC-fix layer (chriz-bg-modpack side); needs its own audit | — | L |

Effort: S small / M medium / L large. Slots are **proposals**, not allocations —
102 stays earmarked for the SCS orphan audit (`bonus_spell_scrolls`).

## Install ground truth that shapes everything

Read from `WeiDU.log` (455 entries) on 2026-07-20. The user's standing rule is to check
compatibility per component against **SCS, SR, Item Randomiser, cdtweaks** — for this batch
the surprise is that Randomiser and cdtweaks are *central*, not rarely relevant, and
**Artisan's Kitpack is a fifth axis** nobody listed:

- **cdtweaks #1142** "Gems and Potions Require Identification → Just potions" — the
  unidentified-potion *mechanic* is already live; the leak is purely visual (icons/names).
  Idea 1 builds directly on it. **#2192** (limited storekeeper identification, hybrid) makes
  the identification economy real, raising the value of ideas 1–2.
- **cdtweaks #170** "Unique Icons [Lava]" + **#110** "Icon Improvements" — actively make
  item icons *more* distinct. Exactly opposed to ideas 1–2 for the unidentified state,
  exactly aligned for the identified state. Any disguise component must sit after these and
  must only mask the *unidentified* presentation, or it destroys value the user opted into.
- **Item Randomiser #570** "Randomise the appearance of cursed items" — already reshuffles
  cursed-item looks (Jester's sub-ask). Idea 2 overlaps: same ITM appearance fields. Must
  read what #570 actually rewrites before touching cursed items; possibly skip cursed items
  when #570 is present, or deliberately supersede it.
- **Item Randomiser #1100** (mode 1, script-based shuffling) — moves item *instances*, never
  item definitions ⇒ ITM-definition patches stay compatible. Synergy: randomised loot with
  no visual tell is the point of ideas 1–2 for randomiser users.
- **SCS #6540** "Smarter dragons" (+ #6830 Smarter Abazigal, #8180 Improved Abazigal's Lair,
  Ascension #1000 Tougher Abazigal) — dragons already have caster-grade AI. Idea 5 is a
  *layer on top*, not a rewrite; and Abazigal is the one mandatory dragon, already double-
  toughened — he needs a fairness carve-out.
- **SCS #8040** ties level-dependent groupings to the difficulty slider — precedent that
  difficulty-runtime coupling is the house style here. **chriz-sod-remix #250** ("Morentherene —
  a real dragon on Hard and Insane") is our own working reference implementation of a
  difficulty-gated dragon buff.
- **cdtweaks #3010** Maximum HP for all creatures — dragon HP is already maxed; further HP
  scaling must be % on top, not re-rolls.
- **IWDification #190** "Increase Spear Damage" + cdtweaks **#2020/2030/2035** (two-handed
  bastard swords/katanas/axes) — prior touches on weapon dice and wield-style; idea 3 must
  detect and reconcile (spears may already sit at the target value; two-handed variants have
  their own ability headers to patch).
- **Artisan's Kitpack** Kensai Overhaul (#1004) and Monk Revisions (#10001, + Ninja/Sacred
  Fist) — ideas 6–8 do not target vanilla kensai/monks on this install; AK also runs its own
  opcode-319/SPLPROT permission system for weapons. Nothing kensai/monk-shaped is a
  "one usability bit" change here.
- **Spell Revisions** is spells-only — no interaction with the item-facing ideas. **Item
  Revisions is NOT installed**, which simplifies ideas 2–3 substantially.
- **EEex v0.11.0-alpha with LuaJIT** is live (plus Bubb's Spell Menu Extended v5.1) — EEex
  solutions are available, but must be verified against the *0.11.0-alpha* API surface
  (v1.0.0 docs don't apply; see bg-modding gotchas).

---

## 1+2. Unidentified-item disguise (potions identical; magic/cursed weapons look mundane)

**Ask.** Unidentified potions should be visually indistinguishable; unidentified magic
(and cursed) weapons should look like their mundane base type. Identification reveals the
true look.

**The hard fact:** the ITM format has a single inventory icon (0x3A), ground icon (0x44)
and description icon (0x58) plus one avatar-animation code (0x22) — none of them vary with
the item instance's IDENTIFIED flag. (To be re-verified against IESDP + live ITM dumps in
the research doc, but this is settled format knowledge.) Consequences:

- **No static WeiDU patch can show different icons before/after identification.** Any
  approach that just rewrites icon fields changes the identified look too — which #170
  Unique Icons proves the user doesn't want.
- The unidentified *name/description* side is already handled by the engine (generic
  strrefs at 0x08/0x50); a cheap audit that no mod-added potion/weapon leaks its identity
  through its unidentified name rides along for free.

**Approaches (framework serves both components):**

- **A. EEex icon-resolution hook (recommended research target).** Hook where the engine
  resolves an item's icon/avatar for rendering; when the instance lacks the IDENTIFIED
  flag, serve a substitute from an install-time-generated 2DA (potion → one generic potion
  icon; weapon → icon of its mundane base item, resolved by item category/animation at
  install time). One framework, two components: 310 (potions), 311 (weapons incl. cursed).
  Feasibility unknowns: does EEex 0.11.0-alpha expose a usable hook point (eeex-ui render
  hooks? sprite/item getters?), and which surfaces it covers (inventory grid, ground pile,
  store/container UI, paperdoll, description screen). This is the research question.
- **B. UI.MENU-side substitution (partial fallback).** EE 2.6 renders inventory/store
  screens via UI.MENU + lua; if slot rendering exposes the icon + identified state to lua,
  a menu-side swap could cover the main screens without engine hooks. Likely misses ground
  piles/paperdoll. Must coexist with Bubb's Spell Menu Extended and EEex UI modules.
- **C. Permanent same-look (rejected).** Give all potions one icon forever — destroys the
  identified-state UX and fights cdtweaks #170. Only acceptable for *cursed* items (which
  Randomiser #570 already handles its own way).

**Compatibility:** SCS/SR none. Randomiser #570 (cursed appearance) — read before touching
cursed items. cdtweaks #170/#110 — install after (we are tail anyway); mask unidentified
state only. Mod-added items covered by patching dynamically per itemtype (9 = potions) /
weapon categories, never by resref lists. EEex approach gates on
`FILE_EXISTS ~override/M___EEex.lua~` + LuaJIT (per gotchas, never on EEex component numbers).

**Verdict:** research doc `research/04-unidentified-item-disguise.md` first — enumerate the
EEex 0.11.0-alpha hook surface, dump how Randomiser #570 and cdtweaks #170 rewrite
appearance fields, then a design doc. Components 310/311. This is the one the user hoped
was "easy" — it is not; it's the most technically novel item in the batch.

## 3. Weapon base damage rework (NWN2 / Forgotten Armament style)

**Ask.** IAIWE: adopt Forgotten Armament's "NWN2 weapon damage" values ("ridiculous that a
War Hammer should do 1d4+1"). User constraint (Discord, 7/13): **damage dice only** — no
crit-rate or other item-level power creep; wary of upsetting item balance.

**Shape.** Table-driven dynamic patch: for every ITM of the melee/ranged weapon categories,
match (proficiency byte 0x31, current base dice per ability header) against a
vanilla→target mapping; rewrite dice only when the current value equals the known vanilla
value (conservative whitelist — mod-added or already-modified weapons with nonstandard dice
are left alone, or get a reasoned mapping in the table). Reference values from FA's
component (e.g. war hammer 1d4+1 → 1d8; pull the full table during design). Description
text updated by regex against the damage line (English TLK on this install).

**Why the balance risk is smaller than it looks:** enemies wield the same ITMs — the change
is largely symmetric for melee-vs-melee, shifting mostly the melee-vs-caster axis. Worth
saying in the design doc with numbers per weapon.

**Compatibility:** IWDification #190 already raised spear dice — reconcile (skip spears or
map from their modified value). cdtweaks #2020/2030/2035 add two-handed ability variants —
patch all ability headers, not header[0]. Randomiser: none (instances move, definitions
patched). SCS: none directly (its CREs get the same buffed weapons). SR: none. IR absent.
Idempotency: value-gated writes (only rewrite known-source dice) make re-runs safe.

**Verdict:** solid 3xx candidate (320), medium effort, needs a short design session to fix
the table (which weapons move, which stay) before any code.

## 4. Deity-appropriate weapons for more cleric kits (Tempus continuation)

**Ask.** IAIWE wanted looser weapon/armor rules for cleric/druid × fighter multi/duals;
user's stated direction is finer-grained: *deity-appropriate* weapons per kit ("clerics of
Tempus should be able to use axes and swords" — shipped as components 400/407/408).

**Already served on this install:** cdtweaks **#2420** (cleric multi/dual equipment
loosening) and **#2430** (druid multi/dual loosening) are installed — IAIWE's literal
multi/dual ask is done. What remains is the single-class kit layer, where Tweaks Anthology
only offers all-or-nothing (user's criticism, 7/13).

**Shape.** Generalize the proven Tempus machinery (WEAPPROF column patch by header name,
AK `C0PR#`-style permission grants where AK's EEex proficiency system is present, starter
pips, description updates, joined-NPC migration helper) into per-kit packages driven by a
deity→weapons table. Candidate kits on this install: Priest of Talos / Helm / Lathander,
SoD-imported kits (e.g. Tyr), Yeslick's Alaghor of Clangeddin (mod kit, war-priest of a
battle god), possibly AK's cleric-adjacent kits. Deity weapon choices need the user (lore
pass: favored weapons per FR canon vs. game balance).

**Compatibility:** must layer over AK's permission system exactly as 400 does; cdtweaks
#2420/#2430 orthogonal (different class shapes); SCS/SR/Randomiser none. Each kit its own
subcomponent, `REQUIRE_PREDICATE` on the kit's presence.

**Verdict:** natural 4xx continuation (410+), machinery is hot, medium effort. Needs a
short design session for the deity/weapon table.

## 5. Dragons stronger on high difficulties — flagship

**Ask (user's own, plus thread):** dragons feel too weak; buff them on high difficulties.
Thread constraints the user endorsed or set:

- **No spammable wing buffet** — "very unfun" (user), "one of the most toxic mechanics"
  (Archibald). Do not add knockdown loops; investigate whether SCS's existing buffet
  cadence itself needs calming as part of this component.
- **Vorpal chance acceptable** (Reeca proposed; user "doesn't hate it") — a small
  per-melee-hit chance to kill outright, behind a save vs. death at a bonus, respecting
  death ward/immunities. Difficulty-gated.
- **Debuff presence/aura** (IAIWE: −50 resistances / −4 saves): direction accepted, the
  magnitude needs taming — design decides numbers, likely scaled by difficulty and save-able
  per pulse.
- **Innate spellcasting** (IAIWE): SCS #6540 already delivers full casting — this becomes
  tuning/extending, not adding.
- **Escorts/adds** (GachiBalor: "one threat is easy to manage no matter how beefed") —
  encounter-level work overlapping SCS's lair components; optional subcomponent, later.
- **Optionality license** (IAIWE/Reeca): every dragon except Abazigal is skippable, so the
  top tier can be genuinely wild ("FF7 Weapons" energy) — but **Abazigal keeps a fairness
  carve-out** (already Ascension-#1000 + SCS-#6830 toughened).
- **Drops unchanged** for now (IAIWE concedes Carsomyr can stay on Firkraag; revisiting
  drop placement explicitly deferred).
- User meta-constraint (7/13): "we don't want a grind fest — more fun, more replayable."
  Translation: fewer flat HP-sponge buffs, more decision-forcing mechanics.

**Mechanism sketch (to be verified in research):** enumerate dragon CREs dynamically
(dragon class/animation IDs, not resref lists) across SoA/ToB incl. Watcher's Keep;
difficulty gating at *runtime* so one install serves all difficulties — the pattern our own
chriz-sod-remix #250 already ships (Morentherene, Hard+Insane). Buff delivery via a
difficulty-gated applied package (e.g. % max-HP boost — safe on top of cdtweaks #3010 max
HP — plus the aura and vorpal riders) and/or a prepended override script, layered to never
touch SCS's #6540 AI scripts themselves. Open research questions: how SCS reads the slider
at runtime (align semantics, incl. Legacy of Bhaal), opcode-level difficulty conditioning
options, per-dragon tiering (Firkraag vs. Thaxll'ssillyia vs. ToB set), and what SCS
already does per difficulty so we buff the delta, not the base.

**Compatibility:** SCS #6540/#6830/#8180 (layer, don't replace), Ascension #1000, cdtweaks
#3010 (HP already maxed), #2312 (casters already save-penalized — factor into aura math),
SR (dragon spell kits come partly from SR-shaped lists via SCS), Randomiser (drops move —
irrelevant while drops stay untouched). SoD dragons stay in chriz-sod-rebalance.

**Verdict:** the flagship. 1xx slot (proposed **110**), research doc
`research/05-dragons.md` (inventory + SCS-layer analysis) then a full design session.
Largest item in the batch and the best fit for "building upon/rebalancing SCS."

## Parked

- **6. Monk quarterstaves** — user: monks are low priority. Also technically weak value
  (monk fists outscale staves; GachiBalor made the same point), and AK Monk Revisions owns
  monk balance on this install. Revisit only as part of a deliberate monk pass.
- **7. Rasaad headband (crit immunity for monks)** — same monk-priority parking. It's also
  *content* (quest reward placement), which sits at the edge of this repo's scope.
- **8. Kensai bracers (not gloves)** — small and liked ("gives a small edge mid-BG1" —
  IAIWE runs it), but on this install kensai = AK Kensai Overhaul, and "bracers vs.
  gauntlets" needs a real classifier (both are itemtype 12; split by AC-setting opcode or
  resref family). Fine rider for a future 4xx equipment batch; not worth its own session.
- **9. Weak companions** — real, but this repo is SCS/SR/cross-cutting balance; the
  companion layer already lives in the tail fix-mod family (NPC kit/class changes, per-NPC
  fixes) from the chriz-bg-modpack side. Needs its own audit session ("who is still weak
  after the existing fixes, and on what axis") — route there.

## Proposed working order

1. **Dragons (110)** — research + design. Flagship, user's own itch, squarely "building
   upon SCS."
2. **Unidentified-item disguise (310/311)** — EEex feasibility research; it decides whether
   the user's favorite QoL idea is buildable as imagined.
3. **Deity weapons continuation (410+)** — cheap wins on hot machinery once the user picks
   kits/weapons.
4. **Weapon damage (320)** — after the table design session.
5. Orphan audit continuation (102 `bonus_spell_scrolls`) stays queued independently
   (`docs/handover.md` work queue).

## Open questions for the user

1. Priority/green-light across the four active tracks (asked in-session 2026-07-20).
2. Dragons: which levers are in for v1 — % HP/stats, aura (numbers?), vorpal (chance/save?),
   SCS-buffet calming — and does Abazigal get the full treatment or a lighter tier?
3. Weapon damage: adopt FA/NWN2 values wholesale or a curated subset (warhammer/morningstar/
   flail obviously; touch d8 swords at all?)?
4. Deity weapons: which kits first, and what per-deity weapon lists?
