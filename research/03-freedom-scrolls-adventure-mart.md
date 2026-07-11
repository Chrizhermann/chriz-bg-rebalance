# Research 03 — SCS v35 lost the Adventure Mart Freedom scrolls (orphaned spell tweak)

**Date:** 2026-07-11 · **Status:** verified, component 101 · **Upstream:** still orphaned in
v35.21 (latest release); known to the community, confirmed unintentional by DavidW (per user).
Not reported upstream (repo guardrail: no SCS reports).

## Symptom

No Scroll of Freedom is purchasable at the Adventurer's Mart (`ribald.sto`, Waukeen's
Promenade) in SoA chapters 2/3, although SCS's shipped documentation and default config say
the "Make Freedom scrolls available earlier" tweak is active. With SCS installed this bites
hard: Smarter Mages (#6030) / Spellcasting Demiliches (#8020) liches throw Imprisonment
(`stratagems/caster_shared/mark_imprisonment.tph`) long before the party can cast Freedom
(SPWI917, level 9), and vanilla SoA sells no Freedom scrolls at all in chapters 2/3.
User-confirmed missing in the live EET playthrough.

## Root cause chain

1. **v34.3 (last good):** `stratagems/spell/freedom_scrolls.tpa`:

   ```
   DEFINE_ACTION_FUNCTION freedom_scrolls BEGIN
       LAF add_items_to_store STR_VAR store=~shop08 ribald~ items=~scrl9z(5)~ END
   END
   ```

   → 5× `scrl9z` (Scroll of Freedom) added to **both** `shop08` (Galoomp's Books,
   Waukeen's Promenade) and **`ribald` (Adventurer's Mart)**. Enabled by default
   (`stratagems.ini` → `freedom_scrolls=1`).

2. **v35.0 rewrite** (commit `e071892b` "Collated v35 changes", 2023-11-27) did two things:
   - Rewrote the function to a raw `ADD_STORE_ITEM scrl9z AFTER scrla5 #1 #0 #0 IDENTIFIED #5`
     against **`shop08.sto` only** — the `ribald` target was dropped.
   - **Dropped the tweak's row from `stratagems/spell/data/spelltweaks.2da`** — the dispatch
     table that `spell/install_spell_resources.tpa` iterates (`2da_read` → `check_ini` →
     `LAF run`). No row ⇒ the function is never invoked at all, on any install.

3. **Installed v35.21 evidence (this install):**
   - `stratagems/spell/freedom_scrolls.tpa` exists (shop08-only version) — dead code.
   - `stratagems/spell/data/spelltweaks.2da` — no `freedom_scrolls` row (only
     `spellstrike_vs_pm_scroll` matches /freedom|scroll/).
   - `stratagems/stratagems.ini` line 19: `freedom_scrolls=1`;
     `spelltweaks_descriptions.ini` §162 still describes the tweak
     ("makes a few scrolls of Freedom available from Athkatlan stores (the Coppor Coronet
     and the Adventurer's Mart, in fact.)" — the store list in that text was already stale;
     shop08 is Galoomp's, not the Copper Coronet).
   - `SETUP-STRATAGEMS.DEBUG` (22 MB, full install log): **zero** occurrences of
     `freedom_scrolls`; no store backup for it under `weidu_external/backup/stratagems/`.
     (`SHOP08.STO` was touched only by component 2500's new-spell scroll placement.)
   - `override/ribald.sto` (157 sale entries) and `override/SHOP08.STO` (94): no `scrl9z`.
   - Community: reported on G3 as "orphaned in the v35 reorganization of the spell tweak
     components, and is currently unavailable".

## Store / item facts (this install)

- `scrl9z.itm` = "Freedom" scroll, teaches `SPWI917` (`spell.ids` 2917 `WIZARD_FREEDOM`).
- `ribald.sto` / `RIBALD2.STO` / `RIBALD3.sto` all named "Adventurer Mart" (strref 33292);
  RIBALD3 is the ToB-era stock and sells `scrl9z` **infinite** — that's vanilla ToB behavior
  (G3 fixpack ruled it Not-A-Bug), which is why the tweak matters only for SoA.
- Current `scrl9z` sellers (override scan): RIBALD3 + 25SPELL/25SPELL2 "Arcana Archives"
  (ToB), UDDUER01/02 (Underdark, ch. 5), OHB/OHN book merchants (Black Pits only),
  TRMER04A (3×) and TYPE3 "Copper Coronet" (1×) from other mods. **Chapters 2/3 Adventure
  Mart: none** — exactly the scarcity DavidW's tweak was written to fix.

## Fix — component 101 `cbr_scs_freedom_scrolls`

Restore the v34.3 behavior at the store the user asked for, the **Adventurer's Mart**:
add `scrl9z` `AFTER scrla5`, charges 1/0/0, `IDENTIFIED`, stock **5**, non-infinite —
byte-identical semantics to upstream's own line. Guards:

- `REQUIRE_PREDICATE GAME_IS ~bg2ee eet~` and `FILE_EXISTS_IN_GAME` ribald.sto + scrl9z.itm.
- SCS presence: `MOD_IS_INSTALLED stratagems 2000 (all spell tweaks) OR 5900 (AI init)` —
  covers both rationales (tweak family / Imprisonment-using AI); no-ops without SCS.
- Idempotent: patch-time scan of the sale list — if the store already offers `scrl9z`
  (added by a future fixed SCS, a v34 install, or a re-run) the component changes nothing;
  a zero-stock non-infinite entry gets restocked to 5; only a missing entry is added.

Deliberately **not** restoring the `shop08` (Galoomp's Books) half — the user's request was
the Adventure Mart. One-line follow-up if ever wanted.

Pristine pre-fix store: `research/originals/ribald.sto.orig` (4,828 bytes, mod-patched by
Bardic Wonders / RR / CDTweaks / IWDification et al., no SCS store touches).

## Live install application (2026-07-11, user-approved in-conversation)

1. **Tail-install:** mod deployed to the game dir (`chriz-bg-rebalance/` + setup exe from the
   v24900 `Setup-Branwen.exe` template) and installed with `--force-install-list 101`.
   WeiDU.log gained exactly one entry at the tail:
   `~CHRIZ-BG-REBALANCE/SETUP-CHRIZ-BG-REBALANCE.TP2~ #0 #101`. Nothing uninstalled.
   Component 100 deliberately NOT bundled (its formal install remains parked pending its own
   sign-off; the live hotfix already covers it).
2. **Override result:** `ribald.sto` 4828 → 4856 bytes, sale count 157 → 158, new entry
   `[144] SCRL9Z charges=1/0/0 flags=IDENTIFIED amount=5 infinite=0` directly after SCRLA5;
   purchases offset shifted +0x1C. Component log line: "added 5x scrl9z".
3. **Save-game store cache:** visited stores persist per-save inside `BALDUR.SAV`, so the
   override change alone cannot reach saves that already loaded the Adventurer's Mart.
   EET userdir on this machine is OneDrive-redirected:
   `C:\Users\chris\OneDrive\Documents\Baldur's Gate - Enhanced Edition Trilogy\save`
   (resolve via `[Environment]::GetFolderPath('MyDocuments')`, NOT `%USERPROFILE%\Documents`).
   Scan of all 190+ save folders: 38 had `RIBALD.STO` cached, all without `scrl9z`.
   - **34 saves patched** with `scripts/patch_sav_store.py` (sale entry appended at end of
     sale array, header offsets ≥ insertion +0x1C, SAV rebuilt with zlib-9): every patch
     self-verified (item present at amount 5, size +28, full SAV structural roundtrip)
     before writing; original kept as `BALDUR.SAV.bak-cbr101` beside each patched file.
     Read-back scan confirms `amount=5 infinite=0` in all 34.
   - **4 saves skipped on purpose:** `000000040-Interval-Save*` — a game session (other test
     install, same shared EET userdir) was actively rewriting these slots every ~15 min
     during the operation; patching them would race the engine and be clobbered from memory
     anyway. If a run is ever continued from one of these, re-run the patch script when no
     game is running, or just buy from the override-fixed store on any new area/store load.
4. **Rollback:** WeiDU-uninstall component 101 for the override layer (standard backup), and
   restore `BALDUR.SAV.bak-cbr101` files for the saves. (Never needed to date.)

## Reusable tooling

- `scripts/parse_sto.py` — dump STO V1.0 header, purchase categories, and sale entries
  (resref/charges/flags/amount/infinite). Offsets validated by exact file tiling
  (sale block + purchase block == file size on ribald.sto).
- `scripts/patch_sav_store.py` — scan/patch a named store inside save-game `BALDUR.SAV`
  containers (add a for-sale item if absent), with per-save backups, pre-write structural
  self-checks, and an `--exclude` guard for live interval-save slots.
