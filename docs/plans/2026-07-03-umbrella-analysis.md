# Umbrella analysis — should chriz-bg-modpack become the collection?

**Date:** 2026-07-03 · **Status:** DECIDED — user approved the recommendation 2026-07-03.
`chriz-bg-collection` bootstrapped the same day (manifest captured: 414 components / 84 mod
folders); chriz-bg-modpack stays the fixes mod. Optional fixpack rename remains open.
User question was: "chriz-bg-modpack … might become my umbrella mod? What do you think?"

## Recommendation: No — keep the modpack as the fixes mod; the umbrella is a different kind of artifact.

### Why not merge

1. **Node vs. graph.** chriz-bg-modpack is an installable WeiDU mod — *one node* among the
   ~414 entries in the reference install's order. The umbrella is the *graph*: the manifest
   and orchestration of all entries, third-party mods included. Merged, the repo would be
   both an entry in its own manifest and the manifest itself — circular, and every consumer
   of one half drags in the other.
2. **Different artifact types, different lifecycles.** The modpack versions with *your fixes*
   (changes when a bug is found); the umbrella versions with *the ecosystem* (changes when
   any of ~67 third-party mods updates). Different changelogs, different CI (WeiDU
   parse-check vs. download/checksum/install-order validation), different release cadence.
3. **Protect Phase 2.** The modpack has 22 well-scoped mechanical components in flight
   (plus uncommitted WIP on `feat/cbm-uai-caster-level` as of 2026-07-03). Bolting
   collection scope onto it is exactly the mission creep the repo split avoided.
4. **Standalone value.** Someone (including future-you) may want only the fixes without the
   whole collection — the "every submod independently usable/overridable" requirement.
5. **Ecosystem precedent.** Project Infinity and the EE Mod Setup Tool — the two working
   "install a curated modded BG" solutions — are both orchestrators that never bundle mods.

### What the modpack contributes to the umbrella

- It (like chriz-bg-rebalance, chriz-sod-rebalance, the *-Balance-Patch repos) becomes a
  pinned entry near the tail of the collection's install order — the "chriz layer".
- Its `extras/snapshot/` pattern informs the collection's archive strategy for mods whose
  download links die (private-repo archiving is fine; if the collection ever goes public,
  archived third-party mods must be dropped in favor of links + licensing review).

### Naming (optional, user's call, zero urgency)

"modpack" *sounds* like the umbrella. If that nags: rename `chriz-bg-modpack` →
`chriz-bg-fixpack` (GitHub auto-redirects old URLs), and reserve `chriz-bg-collection`
for the umbrella. Purely cosmetic; open issues/CI survive a rename.

## Umbrella bootstrap plan (when greenlit — after 2xx/3xx mature)

1. New repo `chriz-bg-collection` (Chrizhermann, private).
2. **Manifest generation** (read-only against the reference install):
   parse `WeiDU.log` (414 entries) → `manifest/install-order.tsv`
   (position, mod folder, tp2, component #, component name, version);
   cross-reference mod download sources from `EET_MODDING_GUIDE.md` and the local mod
   archive (`C:\Games\Baldurs Gate 1 and 2 mods\`) → `manifest/mod-sources.tsv`.
3. **Presets:** `presets/chris-full.tsv` = the exact current selection, first preset;
   later `minimal`, `no-npc-mods`, etc.
4. **Config layer:** per-preset overrides; fine-tuning via the mods' own ini files
   (SCS `stratagems.ini` model) captured as documented diffs.
5. **Install driver:** script (PowerShell/Python) that fetches each mod, verifies checksum,
   and runs `Setup-<mod>.exe --force-install-list <components> --language 0 --no-exit-pause`
   in manifest order; halt-and-resume support. Project-Infinity-compatible metadata later.
