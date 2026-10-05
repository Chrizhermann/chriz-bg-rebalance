# Entropy Shield: installed comparison and unapproved balance options

Research date: 2026-10-06 (Asia/Seoul). Status: **research only; no balance choice approved, no component implemented, no live acceptance**.

This investigation was requested alongside the SR antimagic discussion. Entropy Shield itself comes from the IWD spell import, with an important SCS enhancement; it is not an ordinary SR spell. The current task explicitly prohibited game writes, installs, gameplay actions and publication. Only this research document was written.

## Evidence and provenance

The effective install examined read-only was `C:\Users\chris\Games\Chriz Easy BG\game` (CEBG). Its `WeiDU.log` records Spell Revisions **v4.21-chriz.5**, IWDification **v11** including the divine spell pack, and Sword Coast Stratagems **35.21** including spell tweaks and Smarter Priests. `override\spell.ids` maps `CLERIC_ENTROPY_SHIELD` to 1620, hence `SPPR620` on this install. This mapping is install-specific, not a future installer constant.

The old owner chat, **Find Entropy Shield counters** (`01a0df45-df6a-7cb1-9e6a-0f70435f4419`), examined a different game at `C:\Games\Baldur's Gate II Enhanced Edition modded` with SR 4.19. Its findings were treated as leads and independently checked against the current CEBG binaries.

The original baseline was read directly from `C:\Games\Icewind Dale Enhanced Edition\chitin.key`, resolving `SPPR615.SPL` into `data\SPLFILE.bif`. The local executable reports **2.7.3.0**. No override resource was used as the vanilla baseline. This is an **unmodified IWDEE KEY/BIF resource**, not a verified classic/pre-EE Icewind Dale binary.

The IWDification donor was also read from `game\iwdification\iwdspells\copyover\cleric_entropy_shield\sppr615.spl`. The effective descriptions were read from the respective English `dialog.tlk`. Effect groups were followed through the actual ability indexes, not assumed to start at effect zero.

| Resource | SHA256 |
|---|---|
| CEBG `override\SPPR620.SPL` | `cb10b1224061893766b7bb92571f42ffdd1c857423def72930cf6442da541f77` |
| CEBG `override\DWSP620.SPL` (SCS prebuff clone) | `a01fde327eb1eb7ffb1402e7751eb1b5270c69f8d0c1ddd1f3d972dda00f187d` |
| IWDification v11 donor `SPPR615.SPL` | `df4d8c57170cc444d076840e503010a647980f155203b7bca5acd0313f15c2b8` |
| Unmodified IWDEE KEY/BIF `SPPR615.SPL` | `3c5386075f6987902f1c8b72e0590d15aa79fa5a8ac6c011cf78ddb0ff3b1066` |

These hashes identify the inspected snapshot. They are evidence, not a proposed hardcoded compatibility fingerprint.

## What changed from IWD to the current install

| Layer | Unmodified IWDEE / imported donor | Current CEBG spell |
|---|---|---|
| Spell level; casting time; target | Level 6; casting time 9; self | Same |
| Armor Class | +6 bonus | Same: opcode 0, parameter 1 = 6, parameter 2 = 0 |
| Saving throws | +2 all saves | Same: opcode 325, parameter 1 = 2 |
| Elemental resistance | +50% acid, cold, electricity and fire | Same: opcodes 27, 28, 29 and 30, cumulative mode |
| Magic Resistance; magic-damage resistance | Neither is granted | Neither is granted |
| Missile and selected spell protection | Many projectile immunities plus specific resource immunities | Retained and adapted to installed resources, including Flame Strike helpers and relocated Icelance |
| Abjuration immunity | None | Added by SCS through opcode 204, school 1 |
| Secondary type | Raw value 2 | Value 1, `SPELLPROTECTIONS` |
| Duration | One round per level; donor headers extend to level 30 / 180 seconds | One round per level, capped at level 20 / 120 seconds |

Raw secondary type 2 corresponds to `SPECIFICPROTECTIONS` under BG2's normal category mapping. SCS's patch comment describes its change as away from combat protections, but that comment should not be substituted for the inspected byte. Breach's installed removal effects cover both categories 2 and 7; current Entropy Shield is category 1.

The effective spell has ten ability headers: the first uses minimum level 1 with 66-second effects (the ordinary level-11 duration), then levels 12 through 20 with 72 through 120 seconds. The donor and unmodified IWDEE resource have twenty headers through level 30. IWDification's `iwdspells_divine.tpa:12-13` sets the default import cap to 20 unless `no_cap_at_level_20` is enabled. Its resource-moving library deletes headers above that cap; this is not a new balance recommendation.

Current `SPPR620` has 75 projectile-immunity effects per ability and twelve resource immunities. It does **not** block every spell with a visible travelling animation. The unmodified IWDEE resource additionally blocks projectile index 54; IWDification removes that erroneous protection and fixes Flame Strike resource coverage. Do not restore that vanilla projectile bug when designing a weaker spell.

The current timed protective effects have power 6 and resist/dispel flags 3. They are normally dispellable effects, but hostile abjuration-school delivery is intercepted by the separate SCS school immunity. Three duplicate opcode-204 effects are present, consistent with SCS cloning the portrait-icon effects; this is not three independent layers that must be individually removed.

`DWSP620` was independently inspected: it retains category 1 and the same defensive core, duration progression and markers as the normal spell. There is no evidence here of the historical SCS prebuff subtype bug on this install. A later existing-install adjustment must still account for this generated clone.

SCS explicitly explains its purpose: it fixes IWDEE's accidental projectile immunity, adds systematic abjuration protection to improve priest survivability, and makes Entropy Shield a spell protection so anti-spell attacks can remove it. [Official SCS explanation](https://gibberlings3.github.io/Documentation/readmes/subdocuments/spell_tweaks.html).

## Counterplay verified in the current binaries

The table reports **eligibility to remove Entropy Shield**, not a promise about which buff is selected first when several protections coexist.

| Installed spell | Relevant inspected removal effect | Entropy Shield eligible? |
|---|---|---|
| Secret Word (`SPWI419`) | Child `B`: opcode 230, maximum power 7, secondary type 1 | Yes |
| Pierce Magic (`SPWI608`) | Child `B`: opcode 230, maximum power 8, secondary type 1 | Yes |
| Ruby Ray (`SPWI704`) | Child `B`: opcode 230, maximum power 9, secondary type 1 | Yes |
| Warding Whip (`SPWI705`) | Child `B`: repeated opcode-230 effects, maximum power 8, secondary type 1 | Yes |
| Pierce Shield (`SPWI805`) | Child `B`: opcode 230, maximum power 9, secondary type 1 | Yes |
| Spellstrike (`SPWI903`) | Child `B`: opcode 221, maximum power 9, secondary type 1 | Yes |
| Spell Thrust (`SPWI321`) | Child `B`: opcode 230, maximum power 5 | No: shield effects have power 6 |
| Breach (`SPWI513`) | Child `B`: opcode 221 for categories 2 and 7 | No: wrong category and hostile abjuration delivery |
| Dispel Magic (`SPWI302`, priest equivalent) | School 1, ordinary dispel mechanics | Hostile cast blocked by school immunity |

Secret Word uses raw SPL projectile 1, corresponding to projectile index 0. The other five eligible counters use raw projectile 221, corresponding to index 220. Neither index is blocked by Entropy Shield. Parent and removal children use secondary type 4, `MAGICATTACK`; opcode 204 cannot block effects in that category. This explains why even the abjuration-school anti-spell attacks get through. [Projectile-immunity rule](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op83), [school-immunity exception](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op204).

The relevant removal effects have no saving-throw bits and bypass MR. Spell Shield / enhanced Impervious Sanctity, and other eligible protections, can complicate the first removal attempt. This research did not runtime-test the order or number of removals on a multiply protected target.

### Important opcode-230 caveat

The [IESDP opcode-230 documentation](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op230) describes the **first two valid parent resources**: one ordinary/non-equipped-timing resource and one with timing modes 2/5/8. It explicitly calls the second case uncommon because equipped items cannot normally be removed. Thus **one spell protection** remains a useful description for ordinary timed buffs; this does not mean two ordinary buffs routinely disappear. The unusual timing-mode case and exact selection order remain untested here and do not undermine Entropy Shield's counter eligibility.

SR has no ordinary learnable Spell Immunity spell. The abjuration immunity discussed here is an effect added directly to Entropy Shield; Spell Immunity is not proposed as a player counter.

## Published prior art: Tactics Remix

**Public source availability verified.** The author's [Tactics Remix page](https://www.morpheus-mart.com/tactics-remix) currently identifies **v8.2, September 7, 2026**, and links a public ZIP containing readable WeiDU implementation files. The package was downloaded and inspected in memory, without extracting/installing it into the game or repository. Publicly inspectable source does not by itself establish permission to redistribute it.

- [Author-linked v8.2 ZIP](https://www.dropbox.com/scl/fi/bbkvordy8lca6p0na49rr/Tactics-Remix-8.2.zip?dl=0&rlkey=bq8q4thyheihmgk48dtuzvfjl&st=e8gzllu1)
- ZIP size: 377,603,834 bytes.
- ZIP SHA256: `0644a4f49afc9ff31753b4aef482d4e28d03b7e48e8622fb4ca4b17645a311ef`.
- `tactics-remix/tactics-remix.tp2:10` declares `v8.2`.
- `tactics-remix/components/spells/revise_iwd.tpa:80-89` resolves `CLERIC_ENTROPY_SHIELD`, removes opcodes 27-30, rewrites opcode-328 tracking, and replaces the description with `@6038`.
- That source file's SHA256: `6dc8262923d527ceefd68d3a4174f9efcf371de4bc55dcdbea0a0bfdd858bbec`.
- The author's [published spell description](https://assets.zyrosite.com/mk3Dw8kZMRcqKkOm/spell-descriptions-FFotoYsAhHxpeNF0.txt) retains +6 AC, +2 saves, missile protection and Flame Strike protection, with no elemental resistance.

This is a verified implementation of **removing the elemental resistance package**, not merely a speculative suggestion. The local Entropy Shield block does not change AC, saves, duration or projectile protection.

Do not copy the TR component wholesale into this stack. Its Entropy block rewrites opcode-328 markers to 64 broadly, which is tailored to TR's own AI system and would misrepresent the distinct SCS markers here. The author explicitly describes TR as incompatible with SR and with SCS's AI/core spell-system components. It is useful balance precedent, not an integration recommendation. No additional published numerical Entropy Shield nerf was source-verified in this bounded review.

## Balance diagnosis and three unapproved options

The concern is the amount of protection bundled into one sixth-level slot: missile immunity, selected direct-spell immunity, half of four elemental damage channels, substantial AC, better saves, and SCS's protection of other buffs against ordinary hostile dispelling. Its elemental bonuses are additive, making full resistance easier to reach with other effects or equipment. The spell grants neither general Magic Resistance nor magic-damage resistance, and should not be described as universal spell immunity.

**All three options below are unapproved proposals. No default, component ID or implementation is assigned.**

1. **Remove all four elemental bonuses; retain the rest.** Preferred first discussion option. This follows the verified Tactics Remix balance change while retaining SCS's abjuration immunity, spell-protection category, removal counters, duration and projectile identity. Elemental damage becomes a clearer opening without changing SCS's spell-counter model.
2. **Reduce the four bonuses from 50% to 25%; retain the rest.** A gentler compromise proposed here, not a verified published mod implementation. It reduces how efficiently the spell combines with other resistance sources but keeps some broad protection.
3. **Remove elemental bonuses and reduce AC from +6 to +4.** Retain +2 saves, projectile/resource protection, SCS abjuration immunity and existing duration. This stronger reduction is also a new proposal, appropriate if melee protection remains excessive after considering option 1.

Deleting abjuration immunity is a distinct, larger redesign and is not part of these three options. It would reopen ordinary hostile Dispel Magic, but changing the binary alone would leave misleading SCS detection/renewal assumptions. Similarly, a short fixed duration needs more thought because SCS's prebuff source explicitly assumes at least one round per level.

## SCS compatibility constraints for any later approved work

- Resolve the installed spell dynamically from `CLERIC_ENTROPY_SHIELD`. Treat `SPPR620` and `DWSP620` as observations from this install, not universal filenames.
- Cover the normal resource and any generated prebuff clones for existing installs. A tail patch that edits only the normal spell would leave enemy behavior inconsistent.
- Preserve self-refresh, projectile/resource immunity and category 1 if the approved change only removes/reduces numeric defenses.
- Preserve truthful, separately meaningful markers. The inspected spell includes `SI_ABJURATION` (56), `BUFF_PRO_SPELLS` (66), `ENTROPY_SHIELD` (30), and other installed markers. Do not apply TR's blanket opcode-328 rewrite.
- SCS's `library_iwd_divine.slb:9-14` avoids arrow, Magic Missile and Flame Strike attacks against `ENTROPY_SHIELD`; leaving those immunities intact preserves those assumptions.
- `priest/ssl/generalblocks/renew.ssl:149-160` uses `WIZARD_SPELL_IMMUNITY` to decide renewal. The shield sets the associated legacy state through opcode 282. Removing school immunity without handling detection could cause wasteful or incorrect renewal behavior.
- `priest/ssl/prep/short.ssl:1-28` places Entropy Shield among prebuffs assumed to last at least one round per level.
- `mage/ssl/combatblocks/attack_antimagic.ssl:54-67` and `ssl/library.slb` show anti-spell targeting/Secret Word decisions. Retaining the spell-protection marker/category retains that existing counterplay path.

Installed source paths above are relative to `C:\Users\chris\Games\Chriz Easy BG\game\stratagems`. Additional direct source evidence is `stratagems\spell\entropy_shield_abjuration.tpa:9-20` and `iwdification\iwdspells\lib\iwdfix.tph:13-22`.

## Verification limits and later acceptance

This record establishes source and static binary evidence only. It does not prove new live casting behavior, SCS decisions during combat, buff-selection order or final balance quality. No game files, saves or installed components were modified.

After an explicit balance decision, appropriate focused checks would include normal/prebuff parity, all ability headers, unchanged removal categories and blocked-projectile list, numeric changes confined to approved effects, duration/marker expiry, refresh behavior, and idempotent install/uninstall fixtures. Separate authorized live acceptance should cover removal against both an isolated shield and multiple protections, the opcode-230 timing-mode caveat, Impervious Sanctity/Spell Shield interaction, and enemy priest renewal. None of those live checks has been performed here.
