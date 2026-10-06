# BG Rebalance v0.8.1 collection integration

Prepared October 7; publication and immutable pin verification are separate.
Current source worktree: `.worktrees/sr-antimagic-research`.
Build: `python tools/package_sr_antimagic.py`. Use the full mod archive for
fresh installs, not the private repair adapters or standalone tail packages.

## New choices

| ID | Label | Dependencies | Agreed selection |
|---|---|---|---|
| 130 | cbr_eet_elemental_arrows | EET; SCS 2000; four target arrow resources | Default EET balance rule |
| 200 | cbr_sr_hardiness_40 | SR 65 | Default; exclusive with 201 |
| 201 | cbr_sr_hardiness_30 | SR 65 | Optional alternative |
| 202 | cbr_sr_hardiness_extra_resistance | SR 65; 200 or 201 | Optional, off |
| 210 | cbr_sr_pierce_magic | SR 0; EEex | Approved SR profile |
| 211 | cbr_sr_spellstrike | SR 0 | Approved SR profile |
| 220 | cbr_sr_bracers_improved_haste | SR 0; BRAC16; SPELL.IDS | Default SR compatibility |
| 310 | cbr_party_physical_resistance_90 | EEex; SPLSTATE.IDS | Approved default 90% rule |
| 320 | cbr_damageable_combat_clouds | At least one supported form provider | Approved 75% rule |

Keep all existing choices and their provider guards. Do not expose reserved 311
as a 95% option: the engine limits the input before this hook, so that option is
not implemented. Entropy Shield, Wish Improved Haste, XP banking and other
design-only work are not included.

## Order

Use actual TP2 declaration order, not numeric order. The existing declaration
sequence is preserved; the three newly promoted components are appended:

`100,101,110,111,120,121,200,201,202,210,211,301,400,401,402,403,404,405,406,407,409,408,302,420,421,310,130,220,320`.

Omit unselected components while retaining that relative order. Hardiness must
follow SR 65; 202 follows 200/201. The late run follows SR, SCS and item writers.
Bracers 220 must follow Tempus Holy Power's donor changes (401–403), so its clone
retains the effective bridge. Elemental arrows 130 follow item changes. Clouds 320
follow SCS/Ascension/SR cloud providers. Existing declaration order for 302 is not
changed; no mid-stack repair is implied by this new source.

## Wording and boundaries

- Pierce Magic halves current MR, with a 10–40 point reduction and zero floor,
  rounding reduction upward; five rounds; recasts refresh rather than compound.
- Spellstrike: 15% arcane/divine failure for two rounds, no self-stacking.
- Bracers: SR +1 APR package, self-only/20 seconds/once daily; Wish unchanged.
- Party physical resistance: half effectiveness above 80%, maximum 90%; four
  physical types independently. No enemy, summon or elemental-resistance cap.
- Clouds: reduce cloud-granted immunity to 75%, not every protection from every
  source. Preserve regen/poison/quest protections and scripted death escapes.
- EET arrows: acid 1d3, cold/fire 1d2; remove fire +2 attack/physical bonus only.
  Preserve original saves and SCS helpers; no broad special-arrow normalization.

Package/source checks are not in-engine playtests. Current-game private repairs
are not proof that a newly built collection is installed, and do not authorize
reinstalling old WeiDU entries or modifying saves. Record actual release URL,
size/hash, tag and tested component expansion only after publication.
