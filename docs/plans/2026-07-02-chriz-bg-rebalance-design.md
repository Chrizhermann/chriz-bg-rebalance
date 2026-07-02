# chriz-bg-rebalance — Design (approved 2026-07-02)

Approved by user in brainstorming session, 2026-07-02.

## Trigger

Discord report (Reeca / Epicfurylol / Anterwaare, Nov 2025): SCS 2024's Telekinetic Storm
never rolls its promised save. Verified in the target install and in SCS master source.
User decision: seed a new repo for SCS/SR-adjacent balance work with this fix, and start the
planning phase.

## Decisions made

1. **Name:** `chriz-bg-rebalance` — covers SCS *and* SR adjustments together (user: "I like a
   lot of SR changes, but not all of them. SCS is already doing a great job overall").
2. **Credits are a feature:** README prominently praises and recommends SCS (DavidW) and SR
   (Demivrgvs/G3); genuine bugs get reported upstream, not just fixed locally.
3. **Fix routing by ownership:** TK Storm (SCS) → this repo. Aura Spirit Blade katana +
   yuki-onna breath (same bug class) → issues on `Aura_BG1_BG2_EET-Chriz-Balance-Patch`
   (user: "I don't care about Aura", low priority). CDTweaks katana clones are covered by
   patching post-install.
4. **Scope split:** `chriz-sod-rebalance` narrows to SoD remix + companions; its "Part 3:
   Minor SCS + base-game rebalances" migrates here (pointer left behind).
5. **Hotfix now:** SPWI820.spl patched directly in the live override 2026-07-02 (user
   approved); component 100 is the durable, idempotent formalization.
6. **Hosting:** GitHub `Chrizhermann` (personal), private, MIT.

## Repo shape (approach B of 3 considered)

Installable WeiDU mod skeleton + research/design discipline from day one, rather than a
research-only repo (A) or routing the fix through chriz-bg-modpack (C, rejected by user).
Component numbering: 100s SCS / 200s SR / 300s cross-cutting; labels `cbr_*`.

## Umbrella architecture (user's "big configurable modpack" question)

User vision: their whole mod collection installable & configurable by others — recommended
setup, adjustable presets, every submod overridable.

**Principle: bundle the recipe, not the mods** (licensing + freshness). Future meta-repo
`chriz-bg-collection` contains:

- **Manifest** — full mod list, pinned versions, download URLs, checksums.
- **Install order** — canonical sequence derived from the proven WeiDU.log, with the chriz-*
  repos injected at their tail positions.
- **Presets** — component-selection files: `recommended` (the user's setup) + variants.
- **Config layer** — coarse = component toggles; fine = ini files (the SCS
  `stratagems.ini` model).
- **Install driver** — script that downloads mods from their sources and runs WeiDU in order;
  optionally Project Infinity-compatible metadata for a mod-manager UI.

Each concern remains an independent repo/mod ⇒ independently installable, skippable,
forkable — which satisfies "change every submod however they want". **Not built now**;
designed when this repo has enough real components to compose.

## Component 100 — implementation notes

- Resolve resref dynamically: `IDS_OF_SYMBOL(spell, WIZARD_TELEKINETIC_STORM)` = 2LNN →
  `SPWI(LNN).spl`. Never hardcode SPWI820 (SCS allocates slots at install time).
- Patch: for every ability header (empirical layout: nFx @ +0x1e, firstFxIdx @ +0x20), for
  every op12 effect with special bit 8 (save-for-half) set: `savetype |= 0x1000001`
  (bit 0 save-vs-spell + bit 24 EE bypass-mirror-image). `BUT_ONLY`, idempotent over the
  already-applied hotfix.
- Matches upstream intent: sibling spells in SCS's `extra_arcane_spells.tpa` use
  `s_save_vs_spell=1 s_save_for_half=1 s_bypass_mirror_image=1`.

## Implementation plan / next steps

1. ✅ Scaffold repo, write docs, implement component 100, commit, push (this session).
2. ✅ Live-install hotfix (this session; recorded in `research/01`).
3. ⬜ User reviews `research/02-upstream-scs-report-draft.md` → file on
   Gibberlings3/SwordCoastStratagems.
4. ⬜ File Aura findings as issues on the Aura patch repo (this session if remote reachable).
5. ⬜ Update chriz-sod-rebalance scope doc Part 3 → pointer (this session).
6. ⬜ SR wishlist session with user → `research/10-sr-wishlist.md` → design 200-series.
7. ⬜ SCS component catalog research → candidate 1xx components.
8. ⬜ When 2xx/3xx mature: design `chriz-bg-collection` umbrella.
