# Native metadata of original mode1 linked-spell children

Offline research, 2026-10-09. This extends `native-linked-cast-lineage-notes.md`;
it does not implement linked ownership or rewrite any native effect fields.

Pinned BG2EE 2.7.3.0 executable:
`%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
Addresses are RVAs at native image base 0x140000000, named through the adjacent
EEex 1.3.0 `EEex\loader\v2.7.3.0\bg2ee\function_names.db`.

`probe_native_linked_construction.py` executes copied native CResSpell parsing
and indexing, CSpell effect construction, DecodeEffect, eleven opcode
constructors, the base effect constructor, resref helpers, FireSpell header and
ordinal iteration, specialist adjustment, duration arithmetic and op99 writes.
It reports **62 passing cases**, with additional variations inside several cases.
Result: `%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-linked-construction-result.json`.

Resource bytes/objects are synthetic; Demand, allocation, sound initialization,
CString bridges and GetCasterLevel's actor-dependent result are explicit services.
Child application is skipped to isolate construction. No game/DLL/EEex hook ran.

## Raw record to runtime effect

`CSpell::GetAbilityEffect 24EE30` calls real `CResSpell::GetAbilityEffectNo
1149C0`, `GetAbilityEffect 114930` and `DecodeEffect 1DE3D0`.
DecodeEffect at `1DE3E7..1DE3F6` changes raw dword+20 from FFFFFFFF to zero
**before** opcode dispatch. This mutation affects the in-memory resource record;
it is not a prototype change. A registry built from disk bytes must account for
this exact sentinel conversion when predicting construction.

The base constructor `19DCB0` copies/normalizes these fields:

| Raw V1 record | Runtime effect | Formula |
|---|---|---|
| word00, byte02, byte03 | +10 opcode, +14 target, +18 power | zero-extend |
| dword04, dword08 | +1C/+20 parameters | exact dwords |
| word0C | +24 timing | `word & ~0x300` |
| word0C bits8/9 | +5C resistance flags bits0/1 | each shifted right8 |
| dword0E | +28 duration; +11C originalDuration | exact dword |
| bytes12/13 | +2C/+2E probability words | zero-extend |
| eight bytes14 | +30 effect resource | uppercase ASCII; clear bytes after first NUL |
| dword24/28/2C | +40 save type/+44 save bonus/+48 special | exact dwords |

Only the two documented resistance bits become runtime resistance flags; other
high bits in the packed word stay in timing. The probe covers values0,1,2,3,4,
128,255 rather than silently discarding upper bits.

Dice interpretation is a **constructor argument**, not a generic interpretation
of V1 offsets1C/20. For non-dice constructors, raw1C becomes runtime maxLevel+58
and raw20 becomes minLevel+54; diceCount+38/diceSize+3C stay zero. For dice
constructors, raw1C/20 become +38/+3C and level bounds stay zero.
Native classes executed: op0,1,10,19,54,90,92,142,146,206 are non-dice; op18 is
dice. This is a tested class list, not a blanket rule for every opcode.

DecodeEffect finishes by writing current game time into +6C at `1E2755..1E275B`.
The base constructor initializes firstCall+CC=1. CSpell's raw construction has
source/target IDs -1 and points(-1,-1); FireSpell replaces those later. Target
bytes0 through9 are copied unchanged by these constructors. Routing decides
their meaning; it does not justify rewriting them to target1.

## SPL source metadata and specialist adjustment

After DecodeEffect, `24EEE7..24EF2F` overwrites:

| Runtime field | Native source |
|---|---|
| +4C school | zero-extended main SPL header byte25 |
| +D0 secondary type | zero-extended main SPL header byte27 |
| +90 sourceType | 1 |
| +94 source resref | exact eight bytes from CSpell+8 |
| +9C source flags | main SPL header dword18 |

Source resref copying uses `3FF880`; it does not perform the effect-resource
uppercase/NUL cleanup. The CSpell wrapper normally already holds its native
resref. Compare identifiers by the appropriate resref semantics; do not confuse
this source with the logical potion owner.

Power remains the raw effect byte03. It is not replaced by the SPL's spell level
or the parent op146 power. Mode1 creates the original SPL children rather than
copying the parent's item caster/dispel level.

For a sprite caster, `24EF4B..24EF73` subtracts2 from runtime saveBonus+44 when
school is nonzero and matches `MapCharacterSpecializationToSchool
24ADC0(actor word+79E)`. The native map recognizes kit-low-word40→school1,
80→2,100→3,200→4,400→5,800→6,1000→7,2000→8,4000→9. Other values return0.
This adjustment is not restricted here to mage-type SPLs or to records with a
nonzero save mask. Preserve the native dword arithmetic.

Then `24EF77..24EF8B` calls `sprite.GetCasterLevel(CSpell,true)` and writes its
sign-extended low16 result to +C8. A non-sprite caster instead gets1; a null
caster leaves the constructor default0. The probe executes these branches with
controlled GetCasterLevel results, including FFFF→-1.

`GetCasterLevel 39CC30` depends on spell type, class levels, current derived-stat
set and (for applicable mage casts with the true flag) wild-mage/rule-table state.
A read-only adapter should use/capture the actual native result at construction,
not infer it from the parent item, character level alone or SPL header level.
The probe does not claim to emulate those class/2DA/wild-mage calculations.

## Header selection and child ordinal

`CResSpell::Parse 114D30` reads main header dword64 as ability-array offset and
dword6A as effect-array offset. Ability stride is0x28; effect stride is0x30.
`GetAbilityEffect 114930` checks a signed nonnegative ability and ordinal, then
uses the selected ability's word1E count and word20 first index:

`rawEffect = effectArray + 0x30 * (ability.firstEffect + ordinal)`.

FireSpell gets its caster level independently with the native true flag,
sign-extends it, and clamps it to at least1 (`16AD21..16AD42`). It scans headers
in file order from index0, continuing while the current header's unsigned
word10 minimum level is <= that effective level. It selects the last header in
that **qualifying leading prefix** (`16AD60..16AD9C`). It is not a search for
the highest minimum across the entire file. Duplicate qualifying minima select
the last consecutive match; an early high-level header stops the scan even if a
later header would qualify. No qualifying first header yields no selected header.

The native effect loop iterates ordinal0 through selected count-1. Its zero-based
ability index is `[nativeRSP+50]`, ordinal EDI, original child RBX at16B047.
The probe covers reordered/noncontiguous effect regions, gaps/unrelated records,
multiple effects and headers, duplicate minima, nonmonotonic minima, no match,
no headers and different header/effect offsets. These are fixtures, not product
preconditions requiring their counts or order.

## FireSpell writes and duration scaling

After CSpell construction, `16AFD7..16AFF5` supplies source/target points and IDs
from the actual caster/target sprites. Target1 later sets resistance flag bit8
at16B068; target2 can also set that bit for the native self-target condition.
Projectile attachment writes projectile type+A0 as documented in the earlier
instant-projectile note. These are native delivery mutations; do not freeze a
pre-dispatch fingerprint and then reject the same original effect for them.

For original op146 mode1, Run passes a null optional parameter block, so its
additional save/duration/projectile adjustment branch is absent. Actor duration
modifiers still apply. The selected percentage is a signed16 field:

| SPL type | Actor field if +4EA4 nonzero | Field otherwise |
|---|---|---|
| 1 | +11A6 | +1E4E |
| 2 | +11A8 | +1E50 |
| 5 | +11E2 | +1E8A |
| other | 100 | 100 |

`op99 Apply 1B3120` writes the low16 of parameter1 to the first column's fields,
for parameter2=0/1/2 respectively. It does not add or multiply that percentage.

At `16B02B..16B044`, unless percentage=100, native arithmetic is:

`duration = floor(unsigned32(rawDuration * signed16(percent)) / 100)`.

The product wraps to32 bits before unsigned division. Ordinary positive values
give the familiar percentage result; do not replace overflow/negative cases
with floating-point arithmetic or invented clamps. The code has **no timing-mode
test** here. The probe covers timing1/9/10/4096 as well as0, spell types0/1/2/4/5,
percentages0/50/100/150/-1 and the alternate derived-stat set. OriginalDuration
+11C remains raw while duration+28 is scaled. Later ResolveEffect's seconds-to-
ticks conversion is a separate stage.

Header choice and each child's C8 are separate native calls, and immediate child
effects can change caster state before a later record is built. Capture actual
construction/admission values where needed; a single inferred permanent caster
level or percentage is not a general fingerprint.

## Global effects: specific mode1 omission

The earlier bounded FireSpell probe omitted its tail, so this check explicitly
examines the tail's casting-effect gates. Original CMessageFireSpell::Run writes
argument8=1 at212E63. FireSpell at16B46B reads it and at16B480 skips
`CGameSprite::ApplyCastingEffect 387930` when it is nonzero. The analogous
16B55A check skips `ApplyCastingEffectPost 388060`.

The new probe executes both native gates: argument8=1 calls neither; the
argument8=0 control reaches both (their bodies are recorded services in this
branch check). `ApplyCastingEffect` is the actual caller of
`CSpell::GetCastingEffect` at387DE5. Thus the proven original mode1 route does
not deliver SPL global casting records; this does not mean globals are ignored
by ordinary spell casting or every FireSpell caller.

Separately executing `GetCastingEffect 24F060` shows its distinct construction
path: it uses `GetCastingEffectNo 114A20` and raw ordinal indexing from the
effect-array start (`1149F0`). It does not add main-header word6E to the index.
It invokes DecodeEffect but lacks GetAbilityEffect's subsequent school,
secondary, sourceType/resref/flags, specialist and caster-level writes. Those
helper-level defaults were tested; this is not a claim about every later global
delivery mutation. The linked registry should mark these globals as native-
undelivered for this route, rather than invent children for them or reject a
valid SPL simply because global records coexist with its abilities.

## Validation boundary

The read-only registry can predict fixed fields from the raw record/SPL header
using the formulas above, retain arbitrary valid ability/effect layout, and
compare the observed ability/ordinal to its exact logical child path. Dynamic
native caster level, specialist adjustment and duration state require capture
or a native read at the correct construction point. Preserve the separate
logical potion owner, native SPL source and effect-lifetime identity.

No hooks, save provenance, native global application, real resource-manager
loading, multiplayer delivery or live-game behavior are validated here. The
eleven executed constructors support the stated mapping list; new opcodes need
their constructor interpretation checked rather than assigned a blanket rule.
