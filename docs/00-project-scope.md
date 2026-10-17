# 00 — Project Scope & Plan

## Goal

Principled, well-credited balance adjustments on top of **SCS** and **Spell Revisions** for a
heavily-modded BG2:EE + EET install: SCS is "already doing a great job overall" (few
adjustments + fixes), SR has many great changes "but not all of them" (cherry-pick and adjust).
Quality bar (inherited from chriz-sod-rebalance): every change justified by evidence + design
rationale, fully reversible, idempotent, testable without wrecking a live save.

## Part 1 — SCS adjustments (components 100–199)

- **100 — Telekinetic Storm save fix** ✅ SHIPPED. Description promises "Saving Throw: 1/2"
  but no save type is set → no save ever rolled → always full 16d6–20d6 damage; also missing
  EE bypass-mirror-image convention for AoE damage. Diagnosis: `research/01`. Hotfixed in the
  live install 2026-07-02; component formalizes it. Upstream report draft: `research/02`.
- **101 — Adventurer's Mart Freedom scrolls** ✅ SHIPPED + live-installed 2026-07-11. SCS
  v34.3's `freedom_scrolls` spell tweak (5× scrl9z to Galoomp's Books + Adventurer's Mart)
  was orphaned in the v35 reorganization: dispatch row missing from `spelltweaks.2da`, so it
  never runs (and the surviving dead code lost the ribald target too). Confirmed
  unintentional. Component restores the Adventurer's Mart five, idempotently; live saves
  with the store cached were patched directly (34 saves; backups kept). Diagnosis:
  `research/03`.
- **121 — EEex ambient readiness at load** (user request 2026-08-23, research done,
  **primary**). Hostile casters (option: neutral casters carrying an SCS combat script) get
  their hour-plus buffs (Stoneskin/Ironskins, Mirror Image, Spell Shield, Armor, AoF,
  Barkskin…) applied instantly on sprite load via EEex, consuming slots and reusing SCS's own
  `_PREBUFF` clones — zero reaction latency, no `See()` gate, no polling. Optional measured
  "reaction" sub-feature later. Diagnosis + design: `research/08` §5-B/§7.
- **120 — SCS readiness vs. stealth openers** (optional, demoted): patch the compiled SCS
  scripts so the long tier + priests get the `Detect()/Range-20` path. Only if 121's
  ambient package leaves a gap. `research/08` §5-A.
- **Backlog:** catalog SCS components active in the target install + their balance
  touchpoints; identify small high-value tweaks. (Migrated from chriz-sod-rebalance "Part 3",
  which now points here.)

## Part 2 — Spell Revisions adjustments (components 200–299)

User cherry-picks: which SR changes to keep, revert toward vanilla, or re-tune. **Needs a
collaborative wishlist session** — the user has strong opinions here. Research doc TBD
(`research/10-sr-wishlist.md`): walk SR's component/spell list against the user's experience,
collect concrete gripes with numbers, then design per-spell adjustments.

- **200 — Hardiness restored** (user request 2026-08-19; live hotfix already applied).
  SR #65 "Revised Warrior HLAs" turns Hardiness (SPCL907 + Wish clone SPWISH12) from 40%
  physical into 20%-everything. Subcomponents: **40% physical (default)** or **30%**;
  whether to keep SR's 20% elemental/magic rider is an **open user decision**; fixes
  descriptions; idempotent over the live hotfix; predicate on SR #65. First of the 2xx
  "SR balances" family — each 2xx component gates on SR being installed. Diagnosis +
  hotfix record: `research/06`.

## Part 3 — Cross-cutting audits (components 300–399)

- **Save-for-half audit (candidate 300):** the generalized sweep from `research/scripts/`
  found the whole install has exactly 3 unique offenders (TK Storm; Aura's Spirit Blade katana
  + CDTweaks 2H clones; Aura's yuki-onna breath). The Aura items are parked as issues on
  `Aura_BG1_BG2_EET-Chriz-Balance-Patch` (user: low priority). A WeiDU-native generalized
  audit component is possible later but YAGNI until new offenders appear.
- **301 — Physical-resistance cap** (user request 2026-08-19, design phase). Stop
  physical-resistance stacking (Dwarven Defender-style kits + Defender of Easthaven + gear)
  from trivially reaching ~100% without nerfing individual abilities: hard cap at **90%
  (default)** or **80%** via an EEex listsResolved stat clamp (absolute writes only — see
  `research/07` cadence), **party members only** (enemy designed immunities — golems etc. —
  untouched; most are op120 anyway). **Planned 301c:** soft knee — points above 60% count
  half, then cap (user-endorsed). Reference build: the AK-overhauled Dwarven Defender reaches
  **90% physical while stanced** (kit passives 20 + stance 50 + Defender of Easthaven 20)
  without ever using Hardiness — cap 80 trims it, cap 90 doesn't. Sketch: `research/06` §4.
## Part 4 — Class and kit revisions (components 400–499)

- **401–403 — Cleric of Tempus Holy Power** ✅ IMPLEMENTED, pending independent review and live
  deployment approval. The three entries are one mutually exclusive compatibility family:
  automatic semantic detection (401, recommended), forced true-doubling (402), or forced
  additive Improved Haste treatment (403).
- Install after Spell Revisions, SCS, The Artisan's Kitpack, and other spell/kit changes. The
  component patches final resources, caps future Holy Power grants at five, and closes Divine
  Power stacking in both casting orders.
- Existing characters automatically receive the revised behavior through `OHTMPS1`. Branwen is
  level 13 with three uses and needs no save edit. A character already above level 25 can retain
  old excess charges in the save and needs a separately approved save repair if they are to be
  removed.
- Out of scope here: weapon-training, Chaos of Battle, the Divination drawback, and any EEex
  APR-cap change. Each remains a separate design/component decision.

## Method

Research → design (numbers + rationale) → user sign-off → tail-install WeiDU component →
cautious test on the live install. Never uninstall; resolve mod-added resrefs via `spell.ids`
symbols; components idempotent + predicate-guarded. Follow CLAUDE.md.

## Relationship to sibling repos

| Repo | Mission |
|------|---------|
| chriz-bg-rebalance (this) | SCS/SR-adjacent balance + spell-behavior fixes |
| chriz-sod-rebalance | SoD encounter remix + companion rebalance |
| chriz-bg-modpack | Consolidation of legacy install fixes |
| *-Chriz-Balance-Patch | Per-mod patches (Aura, Bardic Wonders, Kitpack) |
| chriz-bg-collection (future) | Manifest-driven umbrella: install order + presets + config, composing all of the above without redistributing third-party mods |

## Status

- [x] Repo scaffold, component 100 implemented, live-install hotfix applied (2026-07-02)
- [x] Aura findings filed on the Aura patch repo (issue #1)
- [x] Upstream SCS bug report — PARKED, will not be filed (user decision 2026-07-03;
      SCS author unresponsive on GitHub). Draft kept in `research/02`.
- [ ] SCS component catalog / touchpoint research (solo-able — see `docs/handover.md`)
- [ ] SR wishlist session with user
- [ ] Comp 100 formal tail-install into the live game (pending user sign-off)
- [ ] Components 401–403 independent review and controlled live deployment (no active-game write
      has occurred during implementation)
