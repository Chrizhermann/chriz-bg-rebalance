# 09 — Kit-specific spell progression and independent caster levels

Date: 2026-09-19; updated 2026-09-20. Status: BG2EE/EET 2.7.3 user live check passed;
IWDEE 2.7.3 support verified offline, awaiting an in-game check.
The initial research below is retained as evidence. The implementation addendum records
the subsequent 2.7.3 verification and the approved, deliberately small acceptance scope.

## Result

True per-kit bard progression is a credible EEex extension. The native engine already
passes a kit identifier into its wizard-slot lookup, but the bard branch ignores that
identifier and selects the shared bard table. This gives us a specific place to intervene,
rather than a proposal to rewrite the entire spellbook system.

Ordinary WeiDU mods can already differentiate kit slot counts and emulate casting. That
does not mean arbitrary kit-to-progression-table routing is supported by the native engine.
The preferred design for this request is an opt-in kit-to-table mapping that changes base
slot calculations while retaining the normal wizard book, memorization, rest and casting.

The secondary premise needs correcting: a single-class thief does have an innate caster
level, normally its thief level. Its wizard caster level normally falls back to 1. The
spell's actual type and any child-spell delivery determine which path applies.

## Scope and evidence

- Read-only target: `C:\Games\Baldur's Gate II Enhanced Edition modded`.
- Installed `WeiDU.log` identifies EEex **v0.11.0-alpha** and CDTweaks **v18 #2270**.
- `Baldur.exe` reports **2.6.6.0**, SHA-256
  `fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580`.
- Current upstream EEex **v1.3.0**, released September 16, was checked at commit
  `9e8098ee696ca4b0bc055e7ff74b283704a8c02e`. Initial master inspection used
  `a0502166ea7aaeacc39c6349efe2fb40bbbe203e`; its only difference from the tag is two
  documentation-workflow files.
- Native findings below come from static disassembly of the on-disk executable, associated
  with EEex's 2.6.6 BG2EE function-name database and relevant signatures. No process was
  launched, attached to, or patched. These addresses identify this binary, not portable
  patch addresses.
- Mod examples were checked in installed source and effective SPL/2DA resources. No
  installed files, saves, or WeiDU entries were modified. Existing repository changes
  were left alone.

## Separate the four controls

| Control | Example | Why it matters |
| --- | --- | --- |
| Spell level | Fireball is level 3 | Spellbook tier and protection interactions |
| Slot progression | Two level-3 preparations at character level N | Number and availability of prepared spells |
| Spell access | Which spells a kit can learn or use | Separate from the capacity of its spellbook |
| Caster level | Cast Fireball as a level-12 caster | Ability-header selection, scaling and dispel metadata |

A new slot table alone does not grant spell knowledge, define school restrictions, or
change caster level. Raising caster level does not create higher-level spell slots, and
does not remove a spell's own damage/duration cap.

## What Tweaks Anthology changes

| Bard table | First level-7 slot | First level-8 slot |
| --- | --- | --- |
| Vanilla BG2EE | Never | Never |
| PnP, CDTweaks #2271 | Bard 25 | Never |
| Un-nerfed / IWD, CDTweaks #2270 | Bard 21 | Bard 29 |

Both CDTweaks options replace the same shared resource, `MXSPLBRD.2DA`.
The effective installed table uses the un-nerfed thresholds above.

Local evidence relative to the game root:

- `WeiDU.log:252`: component 2270.
- `cdtweaks/lib/comp_2270.tpa:17` and `comp_2271.tpa:13`: copies into the shared table.
- `cdtweaks/2da/un_mxsplbrd.2da:23,31`: first positive seventh/eighth-level entries.
- `cdtweaks/2da/mxsplbrd.2da:27`: PnP seventh-level entry; only seven columns.
- `override/mxsplbrd.2da`: effective install, including the extended rows through level 50.

Primary references: [Tweaks table comparison](https://gibberlings3.github.io/Documentation/readmes/readme-cdtweaks_tables.html#bard),
[IWDification](https://gibberlings3.github.io/Documentation/readmes/readme-iwdification.html),
[IESDP class tables](https://gibberlings3.github.io/iesdp/files/2da/2da_bgee/mxsplxxx.htm).

## What ordinary kit mods already achieve

The installed Bardic Wonders demonstrates real native spellbook adjustments:

| Kit | Level-1 CLAB entry | Effective SPL effect |
| --- | --- | --- |
| Dancer | `C0DANCE.2DA:4`, `AP_C0DANCER` | `C0DANCER.SPL`, effect offset `0xFA`: op42, -1, mask 511, timing 9 |
| Darkbloom | `C0BDD.2DA:6`, `AP_C0BDD#2` | `C0BDD#2.SPL`, `0x12A`: op42, +1, mask 511, timing 9 |
| Kapellmeister | `C0KAPEL.2DA:4`, `AP_C0KM#00` | `C0KM#00.SPL`, `0x9A`: op42, +2, mask 511, timing 9 |

The mask selects wizard spell levels 1–9. These are bonuses/penalties on a common base,
not separate table dispatch. Corresponding descriptions are in
`BardicWonders/lib/dancer.tpa:58`, `darkbloom.tpa:42`, and `kapellmeister.tpa:37`.

The key boundary is zero: [opcode 42](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op42)
cannot add the first slot to an unavailable spell tier. Its priest counterpart is opcode
62. Large negative adjustments can underflow the unsigned slot count; individual -1
effects stop at zero. A zero result also prevents subsequent bonuses from restoring slots
until the relevant suppression/base situation changes.

A conventional alternative is therefore a permissive shared table plus kit-specific
suppression. Current [Might & Guile source](https://github.com/UnearthedArcana/Might_and_Guile/blob/master/might_and_guile/components/400_revised_bards.tpa#L3486)
creates repeated -1 effects to remove ninth-level access. This is real prior art, but not
proof of a general drop-in solution for every bard kit. Ordering, bonus-slot equipment,
level drain, restoring suppressed access and existing saves still need treatment.

Other apparent exceptions use different mechanisms:

- Current Might & Guile revised bards use mage multiclass chassis; do not confuse these
  with native bard kits having independently selected class tables. Its separate component
  499 offers prepared spontaneous casting to traditional bards.
- [Tome & Blood](https://github.com/UnearthedArcana/TomeAndBlood/blob/master/README.md)
  implements alternative casting with custom selection, spell delivery and charge tracking.
  Its Arcanist separates native preparation capacity from a custom spontaneous-casting table.
  Source: `TomeAndBlood/lib/semi_sorcerer.tpa` around lines 349, 733 and 865–882;
  `comp/setup_multiclass_sorcerers.tpa:393–400` supplies a slot table to that system.

These approaches explain how unusual kits cast spells without proving that ordinary
KITLIST rows can name arbitrary native progression tables.

## The native EEex opportunity

`CRuleTables::GetMaxMemorizedSpellsMage`, VA `0x140241CD0`, already receives:

1. Rule-table object.
2. AI/class information.
3. Derived statistics, including class levels.
4. Kit/specialist identifier.
5. Requested spell tier.

In this x64 binary these are RCX, RDX, R8, R9D and the fifth stack argument respectively.
The bard path at `0x140241E94–0x140241F0F` selects the table at rule-tables offset
`0x738` (`m_tMaxSpellsMageBard`) without testing the kit.
The sorcerer path already special-cases Dragon Disciple kit `0x4023`, selecting table
offset `0x7A8` instead. Thus even the vanilla engine has a limited example of kit-specific
selection; the missing facility is a general configurable mapping.

There is no sixth-level clamp in this bard branch: the requested spell tier becomes the
table column and `GetRogueLevel` supplies the row. Character creation iterates nine arcane
tiers. Eight direct call sites were identified across character creation, level-up,
dual-class screens and level drain. At `0x1402C0279`, the level-up path calls the lookup
and then passes its result to `SetMaxMemorizedSpellsMage`. No ordinary save-load refresh
was established by this call-site scan; existing-save reconciliation is an open requirement.

The similarly named `GetMaxSpellLevel` and `GetMaxSpellsPerLevel` instead read
Intelligence and `INTMOD.2DA`. They are not the bard progression selector.

EEex's [function-name database](https://github.com/Bubb13/EEex/blob/v1.3.0/EEex/loader/v2.6.6.0/bg2ee/function_names.db)
names this routine and related slot setters. Its
[rule-table layout](https://eeex-docs.readthedocs.io/en/latest/EE%20Game%20Structures%20%28x64%29/CR/index.html#cruletables)
identifies the table fields. The installed executable provides the branching evidence.
The older documented [function signature](https://github.com/Bubb13/EEex-Docs/blob/35445db362f56095156e3b43aa8f6f0f50f728a0/source/EE%20Game%20Classes%20%28x86%29/CRuleTables/index.rst#L3154)
corroborates the argument meanings; x64 caller disassembly establishes their use here.

Neither the installed 0.11 Lua surface nor the inspected 1.3 scripts provides a ready-made
per-kit spell-progression registration API. This is a bounded source-search result, not a
claim that nobody has ever written an unpublished/private extension.
EEex does provide the assembly-hook infrastructure used by its own patches:
[assembly helpers](https://github.com/Bubb13/EEex/blob/v1.3.0/EEex/copy/EEex_scripts/EEex_Assembly_x86-64.lua#L654),
[sprite hook examples](https://github.com/Bubb13/EEex/blob/v1.3.0/EEex/copy/EEex_scripts/EEex_Sprite_Patch.lua#L84).

The existing quick-list listeners observe cast-count changes; they do not replace the
progression lookup. Likewise, changing a Lua convenience wrapper does not redirect native
C++ callers. A new native interception would be required for the recommended design.

### Proposed first implementation

Design proposal, not an existing API:

- Add an opt-in mapping from `(class, kit symbol)` to an ordinary 2DA slot table.
- Resolve kit symbols from the installed IDS/KITLIST data, rather than embedding numeric
  IDs for mod-added kits. Missing mappings preserve native behavior.
- Intercept base wizard-slot calculation for bards. Select the mapped table using the
  requested tier and the appropriate effective bard level.
- Keep equipment/kit bonuses separate from the base table. Define whether pre-existing
  Bardic Wonders adjustments remain additive or are explicitly replaced in a compatibility
  component; do not silently double-count them.
- Preserve engine behavior for unregistered kits, including third-party kits.
- Keep known spells, selected preparations and remaining castable copies distinct. A
  capacity recalculation must not refill spells that have already been spent.
- Version-gate the executable hook and check expected instructions/signatures before
  enabling it. A 2.6 address is evidence, not a safe cross-version implementation.

The follow-up user policy below now supplies concrete sixth-, seventh- and eighth-level
groups. This first phase concerns existing bard kits, not adding new kits.

A per-tick script that overwrites slot totals is a weaker foundation: it must reconstruct
bonuses, avoid repeated deltas, preserve depleted preparations, and race neither level-up
nor rest. Existing EEex effect-list callbacks are not a substitute for proving those
invariants. Prefer changing the calculation where the native engine requests it.

### Acceptance work still required

Use an isolated disposable install after explicit authorization for game testing.

1. Two different bard kits at the same level must receive different base slot tables
   simultaneously; an unregistered bard must retain native behavior.
2. Test boundaries before/at/after seventh- and eighth-level unlocks, including a zero
   tier, and more than one slot at that tier.
3. Confirm chargen, level-up preview/acceptance, joining NPCs, rest, save/reload, and
   already-created characters. Updating a table does not itself prove saved slot fields
   are reconciled correctly.
4. Confirm casting spends exactly one prepared copy, repeated recalculation grants no
   free casts, bonus-slot equipment behaves as designed, and loss of capacity handles
   excess prepared spells consistently.
5. Cover level drain/restoration, Project Image/Simulacrum, and kit changes if supported.
6. Check the native spellbook and Bubb's Spell Menu. Audit kit learning restrictions and
   any UI/engine maximum-tier checks; base capacity is not the entire access pipeline.
7. Keep SCS NPC spell allocations/scripts in scope separately if enemy kits are to obey
   the policy. A runtime capacity hook does not regenerate their install-time AI/loadouts.

Adding divine classes or genuinely noncasting base classes is a later phase: priest
auto-learning, wisdom bonuses, dual/multiclass selection, UI access and action-bar casting
need separate audits. Success with bards would not establish those cases.

## Secondary question: caster level

Static inspection of `CGameSprite::GetCasterLevel` at `0x14039C5F0` found this dispatch:

- Wizard spell type 1: wizard casting-level helper; a pure thief follows the fallback 1.
- Priest spell type 2: priest casting-level helper.
- Other types, including innate: average-class-level helper, minimum 1.

`CDerivedStats::GetAverageLevel` at `0x140152270` returns the primary level for a
single-class thief. Relevant multiclass paths use the rounded-up mean of two or three
class levels. Consequently, a true innate cast by a level-20 pure thief normally has
caster level 20; that thief casting a wizard-type resource can instead have level 1.

Do not infer a bug merely from the caster's class. Inspect the actual SPL type, selected
ability header, child spells, effect delivery mode and stored caster-level metadata.
Some delivery paths inherit their parent's level; others request the child's native
casting level or use an explicit override.

For a specific innate dispel, a broad engine rewrite is often unnecessary. Dispel opcode
58 can use an explicitly supplied dispel level. An innate with per-level ability headers
can encode a capped, stepped or otherwise chosen progression. An EEex callback can also
calculate a value from kit-specific data and alter the outgoing dispel effect. This
changes dispel strength without changing class levels or unrelated spell behavior.

The installed resources already illustrate explicit dispel scaling: `SPCL231.SPL` is
type 4, has 27 minimum-caster-level headers, and uses op58 explicit-level mode with
values beginning 1, 3, 4 and ending 39, 40. `SPIN112.SPL` has 40 innate headers and
ends at explicit dispel strength 60. These are descriptions of this modded install,
not vanilla claims or a provenance attribution. The native op58 paths narrow the incoming
dispel level to a byte; a custom provider should keep its intended range within 1–255.

For other spells, opcode 146 has delivery modes with an explicit casting-level parameter;
mode and inheritance rules must be selected deliberately. Opcode 191 is an additive
wizard/priest casting-level bonus, not a general absolute-level setter or an innate-level
policy. None of this requires changing the creature's actual class level.

For universal arbitrary caster levels, the cleaner design is a separate native resolver
interception before ability selection, with opt-in rules by kit, spell or creature.
EEex's existing `EEex_Sprite_GetCasterLevelForSpell` only queries the native resolver:
[source](https://github.com/Bubb13/EEex/blob/v1.3.0/EEex/copy/EEex_scripts/EEex_Sprite.lua#L682).
It is not a policy callback. An outgoing-effect mutator can change dispel metadata, but
cannot retroactively choose a different spell ability whose duration/damage was already
selected. Child spells, explicit-level item casts, contingencies and effect-stored levels
must agree with the intended policy.
Direct lower-level getter users also require auditing: engine-special effects such as
Mirror Image can query a class-specific casting level independently. Hooking one getter
must not be advertised as covering every effect before those callers are checked.

Related primary references: [opcode documentation](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op58),
[cast-spell opcode](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op146),
[casting-level bonus](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op191),
[EEex effect construction](https://github.com/Bubb13/EEex/blob/v1.3.0/EEex/copy/EEex_scripts/EEex_GameObject.lua#L312).

## Recommendation

Proceed first with a small EEex proof of concept for **native bard-kit base slot table
selection**. The identified routine already has the necessary kit context, making this a
well-founded engineering experiment. Keep flexible caster-level rules as a separate
module; solve individual innate-dispel problems locally where possible.

The research establishes a concrete implementation route and existing alternatives. It
does not establish a working, compatible mod or live-safe migration. No release, install,
game testing, or upstream message was performed.

## Follow-up: Artisan compatibility and collection default

User direction, 2026-09-19:

| Group | Base table policy | Highest normal spellbook tier |
| --- | --- | --- |
| Most ordinary bards, including unkitted Bard and Jester | IWD/un-nerfed curve, with level 8 and 9 columns zero | 7; first level-7 slot at bard 21 |
| Blade, Bardic Wonders Dancer, Skald | Vanilla BG2 bard curve | 6 |
| Bardic Wonders Kapellmeister | Full IWD/un-nerfed curve | 8; first level-8 slot at bard 29 |

This explicitly means **IWD capped at 7**, not the separate CDTweaks PnP table, whose
seventh-level unlock is bard 25. These are base capacities; preserve existing kit slot
modifiers unless a separate balance choice replaces them. Dancer retains -1, Kapellmeister
retains +2, and any supported Darkbloom retains +1. Consequently a one-slot base unlock
may not yet be usable for a kit with a -1 penalty. Do not bake a bonus into a custom table
and then apply its original CLAB bonus a second time.

The policy is the intended collection default, pending implementation and acceptance.
The collection's design targets BG2EE **2.7.3.0**; the native analysis in this note only
establishes the 2.6.6.0 boundary. Port and verify the hook on the intended target binary.

### Ownership and standalone distribution

Recommended architecture (not yet implemented):

1. One neutral EEex progression provider, maintained here, installed as an independent
   component without requiring the unrelated balance components. It owns the native hook,
   version/capability marker, table registration and fallback behavior.
2. Base-game Bard/Blade/Jester/Skald policy and corresponding descriptions live here.
3. Bardic Wonders-specific mappings and description edits belong in
   `Bardic-Wonders-Chriz-Balance-Patch`. Artisan's Kitpack-specific consumers belong in
   `The-Artisan-s-Kitpack-Chriz-Balance-Patch`. Detect actual kit symbols/capabilities so
   supported upstream and fork installations can use the same core.
4. The collection pins and installs the provider once and selects the policy. It does not
   absorb source from any of the independent mods.

Standalone Bardic Wonders usage can depend on EEex plus only the small provider component;
it does not require the collection or the other rebalance features. A one-download release
could bundle the exact same separately installed provider dependency, with its own WeiDU
identity/version and an explicit update/reuse rule. Do not maintain an independently
edited copy of the engine hook in each mod, or let several installers claim different
versions of the same runtime file. Packaging is still a proposal.

Only downstream features relying on custom progression need this prerequisite. Other
existing Bardic Wonders components need not acquire a blanket EEex/core requirement.
The balance feature and its matching description updates should install together.

Current Artisan's Kitpack has no ordinary bard-kit component; its NPC component 99001
assigns Bardic Wonders' Troubadour kit to Garrick. Bardic Wonders is the direct owner of
the bard kits in this request. The two forks contain no text-source writes to MXSPLBRD
in the inspected installer/Lua/table sources.

### Additional candidates and exclusions

These classifications are recommendations, not additional user-approved eighth-level kits:

- **Darkbloom (`C0BDD`)** is the strongest further candidate for IWD8: extra slots,
  expanded druidic spell access and spell-support features. The current fork explicitly
  excludes component 1006 from recommended Spell Revisions installations because its
  copied spells need a semantic compatibility repair. Progression support does not fix
  that independent issue; keep it gated in the SR collection.
- **Troubadour (`C0TRB`)** and **Deathsinger (`C0_DEATHSINGER`)** have healing and
  necromantic spell specializations, respectively. Keep at IWD7 by default; an expanded
  spell list alone does not require general eighth-level wizard access.
- **Strategist (`C0_STRATEGIST`)** has a casting stance that grants +1 slot and removes
  its caster-level penalty, but is otherwise a combat/casting hybrid. Keep at IWD7.
- **Storm Drummer** is an electrical-damage specialist; IWD7 is a reasonable baseline.
- Vanilla supplies Bard, Blade, Jester and Skald; none is an additional dedicated
  spellcasting-specialist kit. SCS's IWD bard-song option does not add one.
- Do not apply the ordinary-bard policy blindly to all class-5 kits. Bardic Wonders itself
  excludes `C0WLOCK` and `C0AURA` from its generic caster-level tweak. Warlock, Aura's
  Artificer and unfamiliar casting systems need explicit adapters or native fallback.
- Gallant is a paladin; the Mage/Bard and Fighter/Mage/Bard component uses multiclass
  representations. None should inherit the single-class bard policy automatically.

Caps refer to ordinary memorized spell progression. Kapellmeister's **Song of Universal
Harmony** deliberately includes selections from spell levels 1–9; its separate HLA
access is not automatically removed by an eighth-level spellbook table. Whether to change
that HLA is a separate balance decision.

Skald also retains its existing early-level limitations. Its CLAB applies `C0SKD01.SPL`
at levels 2, 3 and 4: early headers suppress slots, then leave only the -1 arcane caster
level modifier. Preserve this mechanism and test those three transitions rather than
duplicating the suppression in the new base table. Bardic Wonders component 2011's
class-wide caster-level adjustment remains a separate option.

### Descriptions and compatibility checks

Write the normal seven-level progression in the Bard class description. List eight-level
access as an advantage for registered specialist kits and the six-level restriction as
a disadvantage for the named restricted kits. Keep slot-bonus and caster-level lines
separate and correct. Say "spellbook progression" rather than forbidding all spells of
a higher level, which would incorrectly imply that scrolls and innate HLAs are forbidden.

Update the installed descriptions after the relevant upstream/fork description writes.
Use the final KITLIST HELP references and appropriate class-description references; keep
kit names and any full/brief description variants intact. Add localized strings for every
supported installer language. Generate the progression wording from the same selected
policy that supplies the tables, and make the text update idempotent. The corrected
`kit_strref.tpa` in the Artisan fork is a better model than copying the older Bardic
helper unchanged; the former handles row zero, failed lookup and aliases.

Validation should cover upstream and fork variants, each kit installed alone, combinations,
existing saves, Dancer/Kapellmeister modifiers, Skald levels 2–4, Strategist's stance,
and all supported languages. SCS's install-time enemy spellbooks remain a separate
integration concern; a runtime slot lookup does not regenerate their spells or AI.

Current primary kit descriptions:
[Bardic Wonders](https://theartisanbg.github.io/The-Artisans-Corner/bardic-wonders),
[Artisan's Kitpack](https://theartisanbg.github.io/The-Artisans-Corner/kitpack).
Local fork evidence includes `BardicWonders/lib/kapellmeister.tpa`, `darkbloom.tpa`,
`strategist.tpa`, `skald.tpa`, `spell_level.tpa`, and the Bardic fork's README exclusion.
Collection policy is also recorded in
`C:\src\private\chriz-bg-collection\docs\research\2026-09-19-bard-progression-policy.md`.

## Implementation addendum: approved 2.7 target

The user approved implementation and the proposed direction, including Darkbloom as
an eighth-level specialist when installed. Its SR exclusion remains. The user will do
a quick in-game XP/spellbook check; extensive compatibility testing is not a prerequisite
for this first free-mod build. Caster-level flexibility remains a separate future task.

The actual Steam BG2EE 2.7.3.0 executable was inspected read-only:

- SHA-256 `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- Native function VA `0x140241F30`; bard table selection VA `0x140242134`,
  RVA `0x242134`, file offset `0x241534`.
- Selection instruction `48 8D 8E 38 07 00 00` is `lea rcx,[rsi+0x738]`.
  EBX still contains the full kit identifier; native code already prepared the bard
  level row and requested spell tier. Replacing only RCX selects another C2DArray.
- Unique 24-byte signature:
  `488D8E380700004C8D45F0488D55F8E89830EDFF4C8D45E4`.
  It is absent from the inspected 2.6.6 executable.

Component 420 installs `M_CBRSP.lua`, three named tables, an API marker, registry,
shared installer helper and `EEex_scripts/extra_pattern_dbs/CBRSP.db`. The loader's
pattern map supplies the relocatable address. The DB disables caching; the installer
checks the supported instruction bytes before installing it because a missing loader
pattern prevents initialization. Future 2.7 builds need matching support rather than
being assumed compatible from their version prefix.

The runtime preserves the native LEA and then selects a persistent table pointer using
EBX. Only RCX changes; flags are preserved. There are no per-slot Lua calls, class-level
writes or spell-list rebuilds. Global userdata references keep the native tables alive,
and a load guard prevents repeat hooks or replacement of embedded table pointers.
Other-class registry entries are ignored by this bard-only hook. Unregistered bards
continue with the native shared table.

Component 421 registers the ordinary Bard, Jester, Blade and Skald and updates their
descriptions. Bardic Wonders fork component 3010 consumes the same installed helper
for its mappings and descriptions, with no duplicate hook. Existing slot effects,
innate/HLA access and caster levels remain untouched. No Kitpack edit is required
for Garrick's existing Troubadour assignment.

`CBRBG6` is derived from pristine BG2EE 2.7.3 `MXSPLBRD`, saved in
`research/originals/MXSPLBRD-2.7.3.2da` (SHA-256
`72fa6824e30d0f23db838f7c4b31b27d8c2922a3c631ab75b9d0e05fa9cbfb79`).
Rows 41–50 retain the final vanilla capacities. `CBRIWD7/8` use CDTweaks' documented
un-nerfed table through level 50, zeroing the disabled tiers. All three have explicit
columns 1–9 and a zero-capacity first character level.

Four focused offline tests cover the selected capacities/unlocks, LuaJIT initialization,
table ownership across reload, unknown-kit fallback, and refusing changed instructions
or conflicting registrations. Installer/adapter smoke checks use disposable fixtures.
These checks do not execute the native hook inside the game.

First live acceptance is the user's planned total 5,000,000 XP level-up and slot check.
The inspected XP table reaches bard 32 at 4,840,000 XP, comfortably above the level-29
eighth-level unlock. Exact expected counts and installation order are in
`docs/bard-progression-playtest.md`. Existing-save changes require normal level-up in
this first build; automatic load-time migration is not implemented. No game install,
process, save or WeiDU log was modified during development.

## Authorized installation: 2026-09-20

At the user's request, installed in `C:\BG-EET-RC-20260903\game` with the game closed.
Its executable matches the verified 2.7.3 SHA above. Its installed EEex is 1.2:
assembly, resource and watchdog scripts match the inspected 1.3 after newline
normalization, the initialization-listener implementation is identical, and the loader
supports extra pattern databases and NoCache. No EEex upgrade was required; dependency
wording now reflects verified 1.2/1.3 compatibility.

WeiDU 249 appended precisely `420`, `421`, then Bardic Wonders `3010`. No existing
entry was removed or reinstalled. The target's core source is v0.3.0 with unrelated
120/121 work, while this checkout is based on v0.2.0. Only the new helper include,
component definitions, strings and new files were merged into that target. Similarly,
only 3010 and its adapter were added to the installed Bardic Wonders v2.9c-balance.3
source. The existing version declarations were preserved; this is a local development
addition, not a published release carrying those version tags.

Post-install verification confirmed the unchanged executable and CDTweaks MXSPLBRD
hashes, unchanged prior WeiDU entries and prior TLK strings, correct 12 registry entries
(two trueclass representations and ten installed kits), ten kit descriptions and
campaign description links. Darkbloom is not installed and was skipped. The hook selects
private CBR tables for registered kits; unregistered bards retain the CDTweaks table.

Backups, installer logs and `verification.json` are in
`C:\BG-EET-RC-20260903\safety-backups\bard-progression-20260920-005421`.
No game process was launched and no save was modified by the agent. The user subsequently
reported "Works great" on 2026-09-20. This accepts the intended brief BG2EE/EET check;
it does not establish exhaustive coverage of every kit or IWDEE.

## Optional kits and IWDEE portability: 2026-09-20

Darkbloom is not a prerequisite. The Bardic adapter registers `C0BDD` only when its
installed KITLIST row represents a native bard, gives it `CBRIWD8`, and leaves its
existing bonus-slot effect intact. Three disposable, real-WeiDU component-3010
fixtures passed: Darkbloom absent, Darkbloom present, and Darkbloom present with only
provider 420 (without baseline 421). Other kit mappings and descriptions were identical
with/without Darkbloom; its bonus-slot SPL was unchanged. No SR prohibition was added
to progression. The separate Darkbloom copied-priest-spell issue remains unresolved.

3010 now requires only the shared provider/API and EEex. The base policy 421 is optional
for standalone use; the collection still selects 420, 421, then 3010. The provider-only
fixture preserved native-kit mappings/descriptions and configured the installed custom
kits. Missing recognized kits are skipped, and unknown casting systems keep native fallback.

The actual local IWDEE executable was inspected read-only at
`C:\Games\Icewind Dale Enhanced Edition\icewind.exe` (also identical to the Steam copy):

- Version 2.7.3.0; SHA-256
  `3458b17b1ac0e60d5798a4b2d2dcc62bb458521378564a109b1395c847b320f1`.
- Native function VA `0x140241FB0`; bard selection RVA `0x2421B4`, file offset `0x2415B4`.
- Same `lea rcx,[rsi+0x738]`, EBX kit identifier, table layout and prepared row/column.
- Its 24-byte sequence is `488D8E380700004C8D45F0488D55F8E82830EDFF4C8D45E4`.
  Only the relative CALL displacement differs from BG2EE 2.7.3.
- The masked signature `488D8E380700004C8D45F0488D55F8E8????????4C8D45E4`
  matches once in each inspected BGEE, BG2EE and IWDEE 2.7.3 executable. BGEE evidence
  helps establish the shared code pattern; the declared component scope is BG2EE/EET/IWDEE.
- IWDEE's KITLIST, KIT.IDS and CLASTEXT layouts match the helper. Its English native-bard
  descriptions do not contain contradictory maximum-tier claims.

The loader DB and runtime validation now ignore only those four displacement bytes.
InfinityLoader's `ini_util.cpp` confirms `??` means one wildcard byte. All opcode,
table-offset and frame-offset bytes remain checked, and the pattern DB remains uncached.
The installer locates a unique compatible sequence instead of requiring one file offset
or executable-version filename. Missing or ambiguous signatures must fail before copying
the loader DB, because an unresolved required loader pattern prevents Lua initialization.

Five focused LuaJIT tests pass, including initialization with IWDEE's CALL displacement.
These prepare the native hook against an API fixture; they do not execute it inside IWDEE.
The file-based WeiDU preflight accepts both actual executables with unchanged before/after
hashes. Disposable copies proved relocation and a changed CALL displacement are accepted,
while changed instructions, duplicate matches and a non-executable-section match fail.
Public components 420 and 421 installed successfully in an IWDEE-identified KEY/TLK
fixture using a copy of the real executable and real EEex helper scripts, without a
version-specific pattern DB marker. Refreshing the provider preserved registrations.
WeiDU parsing and whitespace checks passed. Fixture output is retained under
`%TEMP%/cbr-bard-preflight-a8mro9g3` and `%TEMP%/cbr-bard-iwdee-420-421-f8dnbjot`.
The already-working BG installation was left untouched during this portability work.
