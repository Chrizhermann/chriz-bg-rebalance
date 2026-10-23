# General spell balance: October 11 design review

Status: research and recommendations only. No new implementation, component IDs,
installer defaults, packages, game/save writes or gameplay tests. The existing
October 6 handover has unrelated local edits and was left intact.

## Recommendation and decisions

Keep the SR fork for its fixes and existing spell overhaul, with small selectable
BG Rebalance components for our balance preferences. Keep Aid as a cleric spell
and shorten it; copying Bardic Wonders' Heroism into its slot is a larger change
to class roles and cross-mod behavior than the current problem requires.

| Spell | Native BG2EE baseline | SR chriz.5 and current CEBG | Recommendation, not approval |
|---|---|---|---|
| Luck, wizard 2 | 3 rounds / 18 seconds | 5 turns / 300 seconds, fixed | 1 turn / 60 seconds, fixed |
| Bless, priest 1 | 6 rounds / 36 seconds | 5 turns / 300 seconds, fixed | 1 turn / 60 seconds, fixed |
| Aid, priest 2 | 1 round + 1 round/level; 1d8 HP | 1 turn/level; 1d8 + level HP, bonus capped at +10 | Keep current bonuses, shorten to 2 turns / 120 seconds |
| Chaotic Commands, priest 5 | Clerics and druids | Druids excluded | Restore druid access at the existing spell level 5 |

One round is six seconds; one turn is sixty seconds. These are running game
seconds, not promises about wall-clock duration when paused.

Already agreed: shorter Luck than the current version but longer than vanilla;
shorter Bless; Heroism should be unique. Exact durations, Aid's treatment and
Heroism-family exclusions remain open. Bardic owns the last of those.

Short decision list:

1. Luck: **60 seconds recommended**, with 30 or 120 seconds as alternatives.
   Bless: **60 seconds recommended**, with vanilla's 36 seconds as the tighter
   alternative. No new level scaling is recommended for either.
2. Aid: **keep it, with current bonuses for 120 seconds**. A tighter alternative
   is 60 seconds. Returning its HP bonus to vanilla's flat 1d8 is a separate,
   stronger nerf. Replacement by Heroism remains an option requiring a class/
   access and stacking decision.
3. Chaotic Commands: **restore ordinary druid access at level 5**; preserve
   cleric access, SR's current protections, touch range and duration. Changing
   its spell level or creating kit-specific exceptions is not part of that fix.
4. After those: prioritize Free Action and Protection from the Elements for
   duration review. Do not automatically cut every long protection spell.

## Aid versus Heroism

Aid resolves as `CLERIC_AID`, currently `SPPR201`. Both vanilla and SR give +1
attack, weapon damage and all saves. Vanilla's prose omits the damage bonus;
the effect uses [Aid opcode 129](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op129).
SR increases the HP bonus and extends duration dramatically: at caster level 10,
66 seconds becomes 600; at level 20, 126 becomes 1200. Its current touch range,
casting time 5 and exclusion from the druid spell list are unchanged proposals.
It already has SR's self-refresh handling. A duration adjustment must preserve
that behavior and must not silently extend the potion uniqueness policy to spells.

Heroism is supplied by **Bardic Wonders component 2008**, not SR. Current
`C0BW202` is a level-2 bard spell giving +10% base HP and THAC0 90% of base for
600 seconds. Current Greater Heroism `C0BW502` is level 5, +15% HP, THAC0 85%
and +2 saves for 600 seconds: already the Chriz rebalance, not upstream's larger
bonuses. The ordinary resources currently remove their own and each other's
effects before reapplication. This is source evidence, not proof that repeated
HP changes have no runtime artifacts. The Bardic owner handles that issue and
the open family-exclusion decision. Aid replacement would require an explicit
decision on whether clerics gain this bard mechanic and whether Aid shares its
exclusion family. Potion of Heroism remains under the separate potion policy.

## Chaotic Commands access

`CLERIC_CHAOTIC_COMMANDS` currently resolves to `SPPR508`. The native spell has
exclusion flags `0x00000000`; both SR's supplied spell and the effective game
have `0x80000000`. This is the documented druid/ranger exclusion bit at SPL
offset `0x1e`: see [IESDP exclusion flags](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/spl_v1.htm#splv1_ExclusionFlags).
The smallest change clears only that bit, retaining all other flags and spell
data. Ordinary rangers cannot memorize level-5 spells; an overhaul granting them
such slots would also see the restored class-list access. Sphere/kit systems
with their own spell-grant mechanisms need separate consideration, not blanket
claims of compatibility. Already-eligible vanilla input needs no mechanical edit.

SR also changes range from visual range to touch and casting time 3 to 5. The
duration remains one turn/level, with SR's headers extending through level 20
instead of the native level-18 final header. Those are separate from access.

## Focused next-review list

These comparisons use native archive spells, SR's actual supplied binaries and
effective CEBG resources, not descriptions alone. Recommendations below are open.

| Spell | Vanilla versus current | Priority and recommendation |
|---|---|---|
| Free Action, priest 4 | 1 turn + 1 round/level becomes 1 turn/level: 2 minutes versus 10 at level 10. SR also permits druids. | High duration-review priority. A fixed 3 turns is a candidate; keep current access/protections unless separately decided. |
| Protection from the Elements, wizard 7 | 1 round/level becomes 1 turn/2 levels: 2 minutes versus 10 at level 20. Native +75% elemental resistance becomes SR's 100% resistance settings plus explicit spell immunities. | High priority: duration and potency both increased. Consider 2 rounds/level first; changing immunity strength is a separate decision. |
| Protection from Energy, wizard 8 | 1 round/level becomes 2 rounds/level: 2 versus 4 minutes at level 20; SR also gives complete elemental/magic-damage protection and spell immunities. | Secondary priority. Keep the current duration provisionally while reviewing the level-7 spell; decide immunity strength separately. |
| Death Ward / Protection from Magic Energy | One turn/level already exists in vanilla. Death Ward becomes touch-range and slower to cast in SR. | Lower priority for duration cuts: their length is not an SR-added buff. |
| Stoneskin / Iron Skins | Native 12 game hours becomes SR's 8 hours (3600 to 2400 seconds). Druid Iron Skins is renamed Stoneskin and casting time falls from 9 to 1. | Review druid combat recasting before treating duration as an SR increase. Skins remain limited by hits. |
| Improved Haste | Native single-target double APR, 3 rounds + 1 round/level, becomes SR's area buff with +1 APR and +2 combat bonuses for 1 turn. | Already a substantial tradeoff, not just a longer or stronger version. Preserve the current 20-second bracers adaptation. |

Luck still gives its existing +1 luck, +1 saves and thief-skill bonuses; Bless
retains +1 attack/damage and SR casting time 5 instead of native 9. Do not infer
a doubled Bless area from the description: native text says 15 feet and SR says
30, but both use `SPARPUPA`, whose effective projectile is byte-identical to the
native archive. Duration edits should update associated icons and detection
markers together, preserving independent casting visuals. Luck's phrase
"next hour" should also be updated to the selected duration.

## Existing changes that must stay in the comparison

The previous handover's missing-integration status is historical. Current
installer development source pins **SR v4.21-chriz.5** and **BG Rebalance v0.8.1**.
Its feature definitions and recommended preset now include:

- **200**: Hardiness 40% physical only, default with SR Revised Warrior HLAs 65;
  **201** is the mutually exclusive 30% alternative; **202** independently adds
  20% elemental and magic-damage resistance and is optional/off in the preset.
  Normal and Wish Hardiness are covered. Magic-damage resistance is not MR.
- **210**: Pierce Magic's current-MR reduction, halving with a 10–40 point bound
  and zero floor for **five rounds**, refreshing the existing amount and combining
  with Lower Resistance. Requires EEex.
- **211**: Spellstrike's **15% arcane/divine spell failure for two rounds**,
  self-refreshing. The separate Entropy Shield owner handles its counter behavior.
- **220**, **301** and **320**: the SR bracers adaptation, Courage/Hope exclusion
  and 75% resistance for supported combat clouds, respectively.

Current CEBG's installation log also records the corresponding private tail
patches. The October 9 `CBR_GARITHOS_SPELLS` installer patches the actual normal/
Wish Hardiness and Spellstrike resources; its name does not mean a Garithos-only
copy. This review did not apply any of them, check saves or run engine tests.
The presence of installer source integration does not independently verify which
installer binary/version Christopher launches.

The SR fork additionally contains recipient-refresh fixes for the three energy
protection spells, NPC spellbook/selector migration, Rogue Rebalancing support
and selectable Lightning Bolt behavior. A replacement project would need to
retain those fixes and account for SR-aware AI, spell identities and descriptions.

## Ownership and implementation shape, if later approved

| Approach | Assessment |
|---|---|
| Small balance layer over our current SR fork | Recommended. Independent selectable components, clear ownership, easier to revise a disputed number. |
| Put all preferences directly in the SR fork | Suitable for shared fixes; balance preferences become harder to separate from the full overhaul. Continue maintaining the fork, but keep elective preferences in Rebalance. |
| Replace SR with a new full spell overhaul | A separate project, not a prerequisite for these changes. Requires a spell-by-spell keep/restore/redesign policy and deliberate compatibility ownership. Not approved. |

Aid/Luck/Bless SR-specific adjustments fit Rebalance's 2xx group, individually
selectable. If offered as general duration choices, support non-SR semantics
explicitly rather than requiring SR only because it was in the inspected game.
General druid-access restoration fits 3xx and need not require SR. No new IDs are
reserved in this review. Heroism-family changes remain in the Bardic fork.
Collection integration is a separate later deliverable once components and
user choices exist; this note changes neither pins nor defaults.

For implementation, identify owned gameplay effects semantically, including
linked payloads, and synchronize their duration-dependent presentation. Preserve
other mods' effects; do not require these captures' counts, order, values or
English text. A small focused test set should cover relevant variants and repeat
application. No new lab/game copies are needed for this design pass.

## Evidence and provenance

- SR source: [chriz-spell-revisions-patch](https://github.com/Chrizhermann/chriz-spell-revisions-patch)
  `v4.21-chriz.5`, commit `c8494181c224d22002b5f4ee6fc4411235dd4a9f`.
  `spell_rev/languages/english/arcane.tra`: Luck 427, Stoneskin 1059,
  Protection from Magic Energy 1798, Improved Haste 1874, Elements 2150,
  Energy 2509. `divine.tra`: Bless 3, Aid 214, Free Action 794, Death Ward 872,
  druid Stoneskin 1149, Chaotic Commands 1177. Raw SPLs are in the matching
  `spwiN##` / `spprN##` folders. `lib/refresh_non_stacking.tpa` includes Aid/Luck.
  `spell_rev/CHANGELOG.md` records the Chriz-specific fixes.
- Read-only current game: the owner's CEBG installation.
  Native baseline read via `chitin.key` from `data/Spells.bif`; effective resources
  read from `override`, descriptions from `lang/en_US/dialog.tlk`, installed
  components from `WeiDU.log`. No resource extraction wrote into the game.
- Heroism context: current game `BardicWonders/lib/new_spells.tpa` (descriptions
  from line 57; bard-class registration near 450); Bardic fork `README.md:44`.
  Potion policy: `research/2026-10-09-potion-uniqueness.md:19` of the
  `codex/potion-uniqueness-20261009` work; the shipped policy is
  [`2026-10-14-potion-uniqueness-heroism-family.md`](2026-10-14-potion-uniqueness-heroism-family.md).
- Rebalance source: this repository at `83e51d2727192ebeff5f7a470d58122cdba80735`,
  `setup-chriz-bg-rebalance.tp2:380` and `CHANGELOG.md` v0.8.1.
- Installer development source: chriz-bg-collection, `installer-v0-real-alpha`
  work, commit `f05da9602c33efc0481927420fe8c852a29f9325`;
  `manifest/mods/spell-rev.toml`, `manifest/mods/chriz-bg-rebalance.toml`,
  `manifest/collection.toml:3628`, `manifest/presets/chris-recommended.toml:193`.
  Current design-only scope: `docs/plans/2026-10-09-next-patch-batch.md:370`.
- Ownership: **Review Hardiness changes** handles this general-spell design;
  **Find Entropy Shield counters** handles Entropy Shield/counters/enemy Screen
  AI; the existing full Bardic audit chat handles Heroism and bard-specific work.

Evidence is static source/resource inspection, not new runtime acceptance.
