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
- **Backlog:** catalog SCS components active in the target install + their balance
  touchpoints; identify small high-value tweaks. (Migrated from chriz-sod-rebalance "Part 3",
  which now points here.)

## Part 2 — Spell Revisions adjustments (components 200–299)

User cherry-picks: which SR changes to keep, revert toward vanilla, or re-tune. **Needs a
collaborative wishlist session** — the user has strong opinions here. Research doc TBD
(`research/10-sr-wishlist.md`): walk SR's component/spell list against the user's experience,
collect concrete gripes with numbers, then design per-spell adjustments.

## Part 3 — Cross-cutting audits (components 300–399)

- **Save-for-half audit (candidate 300):** the generalized sweep from `research/scripts/`
  found the whole install has exactly 3 unique offenders (TK Storm; Aura's Spirit Blade katana
  + CDTweaks 2H clones; Aura's yuki-onna breath). The Aura items are parked as issues on
  `Aura_BG1_BG2_EET-Chriz-Balance-Patch` (user: low priority). A WeiDU-native generalized
  audit component is possible later but YAGNI until new offenders appear.

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
