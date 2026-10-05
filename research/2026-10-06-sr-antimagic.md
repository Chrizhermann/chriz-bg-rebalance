# SR anti-magic comparison and unapproved balance options

Research date: 2026-10-06. Owner: BG Rebalance, SR adjustments (2xx).
Status: **discussion only; no nerf selected or implemented**.

The temporary MR=0 effect belongs to **Pierce Magic**, not Pierce Shield, in the
current installation. Pierce Shield has no MR modifier at all. This distinction
matters before deciding which spell to change.

## Evidence and scope

Read-only reference game: `C:\Users\chris\Games\Chriz Easy BG\game`.
Its log records SR `v4.21-chriz.5`, IWDification `v11`, and SCS `35.21`, including
SCS's spell tweaks and smarter mage/priest components. Effective resources were
read from `override`, including the generated child spells. Vanilla counterparts
were read directly through `chitin.key` from the native `data\Spells.bif`;
they were not inferred from descriptions or from a mod's backup.

All five SR input SPLs below are byte-identical between the game's `spell_rev`
directory and fork commit `c8494181c224d22002b5f4ee6fc4411235dd4a9f`:
[SR fork source](https://github.com/Chrizhermann/chriz-spell-revisions-patch/tree/c8494181c224d22002b5f4ee6fc4411235dd4a9f).
Paths are `spell_rev/spwi5##/spwi514.spl`, `spwi6##/spwi608.spl`,
`spwi8##/spwi805.spl`, `spwi9##/spwi903.spl`, and `sppr5##/sppr509.spl`.
The installed versions include subsequent SR/SCS wrappers, markers and text edits.

No game writes, installer runs, gameplay experiments, publication, collection
source changes or new component IDs were part of this research. Static binary
evidence is not live acceptance or proof of optimal AI use.

## Comparison

Here, **pp** means percentage points: subtracting 20 pp changes 80% MR to 60%,
whereas SET 0 replaces the value with zero. The former effects are cumulative.
These are distinct opcode-166 modes, not two ways to describe the same mechanic.
[IESDP opcode 166](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op166).

| Spell | Vanilla BG2EE | Installed SR + SCS |
|---|---|---|
| Lower Resistance, wizard 5 | Subtracts 10 + caster level pp, capped at 30; 1 round/level, capped at 20 rounds | Subtracts 2 pp/level, capped at 40; same duration; removes no spell protection |
| Pierce Magic, wizard 6 | Subtracts 1 pp/level, capped at 20; 1 round/level, capped at 20 rounds; removes one spell protection up to level 8 | **Sets MR to 0 for 2 rounds (12 seconds)**; retains the level-8 spell-protection removal |
| Pierce Shield, wizard 8 | Subtracts 10 + caster level pp, capped at 30; 1 round/level, capped at 20 rounds; removes one spell protection up to level 9 | **No MR reduction**; removes one spell protection up to level 9 and all combat protections; also clears SR Dispelling Screen |
| Spellstrike, wizard 9 | Removes all spell protections up to level 9; no MR reduction | Same protection removal, plus 100% spell failure for the first round and 50% for the next, for both arcane and divine spells; clears Dispelling Screen; **no MR reduction** |
| Magic Resistance, priest 5 | Sets MR to 2%/level, capped at 40%; can therefore lower an enemy's higher MR | Adds 2 pp/level, capped at +40, with a self-immunity against repeat application; the hostile SET trick is gone |

The first ability headers use normal minimum acquisition levels: Lower Resistance
uses level-9 values, Pierce Magic level-12 values and Pierce Shield level-16 values.
Thus a nominal header labelled level 1 is not evidence for an uncapped linear
formula at very low caster levels. The tables stop at level 20.

The priest spell's vanilla duration actually rises from 72 seconds at level 9 to
126 at level 18, then remains 126 through levels 19 and 20. SR instead uses two
rounds per level, from 108 through 240 seconds. Its casting time changes from 9
to 5. The four wizard spells retain casting times 5, 6, 8 and 5 respectively.
Lower Resistance's school also changes from Abjuration to Alteration in SR.

The MR debuffs and Spellstrike failure effects allow **no saving throw** and
bypass MR. Their limited-duration effects use flags 2 (not dispellable, bypass
MR). This does not mean that the delivery ignores every protection: Spell Shield
can absorb the relevant anti-magic payload. The priest buff instead uses flags 3
(dispellable, bypass MR).

"One spell protection" is the normal timed-buff behavior of opcode 230. Its
documented implementation has separate searches for a non-equipped effect list
and an equipped-timing effect list; unusual resources can exercise both. No live
claim about that uncommon second case, or about choosing the highest-level
protection, is made here. [IESDP opcode 230](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op230).

## Installed implementation and SCS counterplay

`SPWI608`, `SPWI805` and `SPWI903` cast their respective `B` payload and then
their `C` Spell Shield remover. The decisive effects are:

- `SPWI608B`: opcode 230 `(8,1)` and opcode 166 `(0,1)` for 12 seconds.
- `SPWI805B`: opcode 230 `(9,1)`, opcode 221 `(9,7)` and SR's removal of
  Dispelling Screen category 23; no opcode 166.
- `SPWI903B`: opcode 221 `(9,1)`, opcode 60 for both casting types, and removal
  of category 23; no opcode 166. Its 100%/6-second and 50%/12-second effects
  overlap for the first six seconds, then only the 50% effects remain.
- Each `C` child removes Spell Shield category 19. These category numbers are
  from this installation; do not hardcode mod-added category numbers in a patch.
- Effective `SPWI519` has opcode-206 immunity to the three `B` children. A hit
  against active Spell Shield loses its main payload and strips the shield.

The source of that split is `spell_rev/lib/ardanis_spell_shield.tph`, especially
the anti-magic array and the payload/shield-clone construction. SR's
`spell_rev/lib/dispelling_screen.tph` separately handles Pierce Shield and
Spellstrike. An eventual tail patch must follow the **effective payload**, not
just edit the named parent spell or reinstall SR.

SCS's `stratagems/spell/antimagic_penetrates_ii.tpa` enables invisible targeting
for Pierce Magic, Pierce Shield, Spellstrike, Ruby Ray, Warding Whip, Spell Thrust
and Secret Word. It does not add that flag to Lower Resistance. Preserve that
delivery behavior and the spell-protection-removal effects when changing MR.

`stratagems/mage/ssl/combatblocks/attack_antimagic.ssl:149-180` explicitly uses
Lower Resistance and a triple-Lower-Resistance sequencer against resistant
targets. Pierce Magic is also in the spell-shield attack choices. This supports
a narrow MR-only change: SCS retains its established MR reduction and protection
removal tools. It does **not** establish that all generated AI will optimize a
new Pierce Magic value. Shared resource changes affect enemies as well as the
party; assess both sides in later testing.

## Other spells and nearby exceptions

Spell Thrust, Secret Word, Ruby Ray, Warding Whip, Breach and ordinary Dispel Magic
are not additional ordinary MR reducers. Removing a particular buff that grants
MR is distinct from directly debuffing innate or item-based MR. Vanilla
Spellstrike does not reduce MR, despite its name.

The independent inventory scan found no further ordinary learnable direct
negative/SET-0 MR spell beyond the family above. Two exceptions need to remain
visible in any broader balance discussion:

- **Wish** is normally learnable, but its "Magic resistance on everyone in the
  area, including enemies" outcome is not a targeted debuff. Effective
  `WISH25.DLG` invokes `SPWISH31`, which still uses native `25SPELLS.BIF` bytes:
  SET MR to 40, area-wide, for 126 seconds, no save, dispellable/MR bypass.
  Consequently it can lower MR above 40. This is separate from Pierce Magic.
- **Wrath of the Skies**, `C0WSHS6`, is a level-6 Artisan War Shaman kit spell,
  not a general wizard/priest spell. Its storm applies a -50 pp MR effect for
  six seconds per pulse, without a save or MR check. A complete MR audit should
  track it separately in its owning kit/mod context.

Current SR's normal priest Magic Resistance no longer provides the old hostile
SET-value tactic, as explained above. These findings concern installed resources,
not a promise that every generic spell is available in every shop or spell list.

Inventory coverage: 6,747 effective SPLs, 1,654 EFFs and 4,933 ITMs, using override
precedence and KEY/BIF fallback. Direct links through spell-casting opcodes and
scroll learning were examined. Wish's dialogue was checked specifically; this
was not an exhaustive simulation of scripted summons, shapeshifts, item attacks
or Lua-mediated abilities. Magic **damage** resistance (opcode 31) is a separate
stat and was excluded from the MR inventory. War Shaman provenance is in
`ArtisansKitpack/Shaman/WarShaman/2da/c0wsham.2da:4` and its description in
`ArtisansKitpack/lib/WarShaman.tpa:366` under the reference game.

## Options to discuss, not approved settings

All three options below keep Pierce Magic's protection stripping, Spell Shield
interaction, lack of saving throw and MR bypass. They do not alter Pierce Shield,
Spellstrike, Lower Resistance, or SCS AI.

1. **Restore vanilla MR arithmetic and duration.** Subtract 1 pp/level, capped
   at 20, for 1 round/level (maximum 20 rounds). This has a verified baseline and
   restores the distinction between general MR reduction and a combined
   protection-removal spell. At level 20, one cast changes 80% MR to 60%.
2. **Use vanilla arithmetic with SR's short window.** The same subtraction,
   but lasting two rounds. It retains SR's burst-combat intent and is the weaker
   of these two reductions. It may be too small a benefit for a level-6 slot
   compared with SR's stronger and longer-lasting Lower Resistance.
3. **Keep a stronger short burst without setting MR to zero.** As a concrete
   discussion example, subtract a fixed 30 pp for two rounds. An 80% target
   retains 50% MR. The number is a proposal, not a published or approved balance
   choice. Repeated application must be decided explicitly: normal additive
   effects can eventually reduce MR to zero; making them refresh-only would be
   an additional design change requiring separate stacking tests.

Option 1 is the conservative recommendation to discuss first. Merely shortening
SET 0 to one round would still entirely bypass very high MR during that window,
so it does not directly address the concern about nullification.

No blanket immunity is proposed. SR has no ordinary Spell Immunity spell to use
as the suggested counter. Entropy Shield's separate layers and existing SCS
counters are covered in [the Entropy Shield research](2026-10-06-entropy-shield.md).

## Binary fingerprints

SHA-256, from this read-only inspection:

| Resource | Native vanilla | Effective installed |
|---|---|---|
| SPWI514 | `0a62c094c4dccc1df0b4e06851c936ccfd7d3bb622c26c56563c34dd9a9821af` | `d42b3b376eac4afff10344b533947eb17d73012ed0283d47a845b4b00b91c9f5` |
| SPWI608 | `517282cb60c5009dc430a33ed732b79828d2e25c7953b17c33f1c66707599bb1` | `29706378a8ab045d6a5eb454c8d44bad1a7fc2e90a80c5e7b69bfc2c383337af` |
| SPWI805 | `3b3fcbb85ffdf099ee8120e03e6270bb727b2c6dca7c7c65fe9c7f293b2a0a44` | `9cc93f02be3e723ef9393e0bc2bdb1ef39c2ee35621987e97a4d5db73ebe25a5` |
| SPWI903 | `11d438348b41413495e3284272703fca5f7fd00577c60be1352e4e22d2ed75cf` | `392592dacba7c4ec8e9dab9aab13d269c947260c4a2e907ff140cec85ae42ae4` |
| SPPR509 | `b6d18bae548370ef85a48bf472ac33a1be6bd195813209809a1fc7a3996976df` | `d555f4686192e0cb5f26fd064f306f0b60f43a7d32d576b5a0de32adefc05e1c` |

Installed payloads:

- `SPWI608B`: `18dd2b677c8ee8a28ac8ee688b3ca2a23e3e593de0713f069246a31d74bb7ace`
- `SPWI805B`: `a58763de7572d5d23298de9648973d6a35ea776b1f43170b224fcd1b82e76543`
- `SPWI903B`: `12a070164176e642de3351c2f8706619e15ce900cc1c57e87de0cc4492c4d68e`

No checksum is a substitute for semantic compatibility checks. Source versions,
wrappers and other mod writers must be rechecked before any implementation.
