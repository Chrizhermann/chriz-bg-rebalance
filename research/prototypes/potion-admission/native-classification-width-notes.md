# Native classification and operand-width evidence

2026-10-09. Offline, pinned BG2EE 2.7.3.0 instruction evidence. This supports
the research compiler's classification, not live-game acceptance or a public
component. No game process, installation, save, or resource was changed.

## Reproduction and limits

The input executable is explicitly supplied:
`%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
Addresses below are RVAs, image base `0x140000000`. EEex reference is1.3.0;
these class probes execute original engine instructions without loading EEex.

Run `python -B research/prototypes/potion-admission/<script> --exe <path>
--python-libs <directory-containing-pefile-capstone-unicorn>`. The scripts
hash-check the image and print JSON; neither writes the executable or resources.

- `probe_native_cosmetic_protection.py`:37 cases, including native Apply,
  self OnAdd, Resolve through old/new deadlines where applicable, lifecycle
  signatures and actual immunity comparison instructions.
- `probe_native_potion_operands.py`:446 cases:240 finite additive/save-first-use
  boundary cases,176 setter/percentage cases and30 negative-THAC0 controls.
- `probe_native_potion_states.py`:107 cases, covering exact states/setters,
  native one-shot morale curing, a cumulative-morale negative control and
  ordinary Invisibility including its actual visual-message Run method.
- `probe_native_item_normalization.py`:20 direct item construction cases,
  proving the exact shared DecodeEffect raw-dword+20 sentinel normalization.
- `probe_native_projectile_resistance.py`:29 cases:12 projectile-immunity
  membership cases,15 fire-resistance setter boundaries and2 consumed-pool
  counterexamples. The last two justify retaining a capability diagnostic.
- `probe_native_movement_proficiency.py`:286 cases:180 movement setters,
  92 proficiency setters,11 native no-op bounds/modes and3 additive negative
  controls. These execute the native animation getter/setter methods as well.
- `probe_native_linked_resource_guard.py`:10 successful/failed predicate cases,
  testing native318 registration and actual non-consuming resource lookup.

Class instructions and effect bytes are real. Allocation, actor baselines,
derived-stat rebuild/reset, animation services and list insertion storage are
test doubles as identified in the scripts. The tests do not execute a complete
engine rebuild, native HP reconciliation, multiplayer scheduling, generated hook
assembly or actual save/load. No proprietary binary snippets are committed.

## Finite stat widths: classification is not fingerprint normalization

The compiler retains original signed32 `amount`, unsigned32 `mode` and every
other matching field. It uses the effective operand only to decide whether the
record belongs to the repeat policy. Thus raw1,65537 and-65535 remain different
keys although their signed LOW16 value is+1. Raw65535 acts as-1,32768 as-32768,
and65536 as0. Tests preserve these fields and exercise both compiler ports.

The following mode0 finite branches consume signed LOW16(amount). Native
timing0/10 has already become absolute4096 at application; the separate
permanent/timing9 branches must not be substituted for these finite branches.

| Opcode | Apply RVA | Accumulator or relevant instruction |
|---|---:|---|
|6 CHA|1A8090|ADD LOW16 at1A8211, actor+2ACA|
|10 CON|1A8230|ADD LOW16 at1A83B1, actor+2AC8|
|15 DEX|1ACEF0|ADD LOW16 at1AD124, actor+2AC6|
|19 INT|1B6250|ADD LOW16 at1B63D1, actor+2AC2|
|21 Lore|1B9910|actor+2AA4,1B9A6B|
|22 Luck|1B9A90|actor+2AB2,1B9C21|
|27–31 resistances|1C0B40,1C0CB0,1C0FD0,1C1140,1C12B0|actor+2A94/2A90/2A92/2A8E/2B2E|
|33–37 saves|see `STATS` in probe|SUB LOW16, actor+2A84/86/88/8A/8C|
|44 STR|1C2B50|actor+2ABE,1C2DD9|
|49 WIS|1CAD20|actor+2AC4,1CAEA1|
|54 THAC0|1C8F90|SUB LOW16, actor+2A80,1C9119|
|59 Stealth|1C6C90|actor+2AA8,1C6DFD|
|73 Damage|1AE760|actor+2AF0,1AE7BD|
|90 Pick Pockets|1C6940|actor+2AA6,1C6AD2|
|91 Find Traps|1C6F20|actor+2AAA,1C70B3|
|92 Open Locks|1C6B00|actor+2AAC,1C6C6D|
|275 Hide|1B54F0|sign-extend LOW16 at1B555C, then DWORD ADD+2AE4 at1B5560|

The saves' reviewed mode3 consumes the same LOW16 on its first update and clears
the first-call marker. A full32 subtraction exists in a permanent branch; it is
not evidence for classifying finite mode3 with the raw32 sign. Skills have
separate timing9 accumulators; permanent operations remain native.

| Setter/percentage opcode | Finite mode1 operand | Finite mode2 operand |
|---|---|---|
|6,10,15,19,44,49|signed32, clamp0..25|signed LOW16 × baseU8, /100, clamp0..25|
|90|signed32, clamp0..255|signed32 × baseU8 at1C69DC, /100, clamp0..255|
|91|signed32, clamp0..255|signed32 × current derivedI16 at1C6FBE, /100, clamp0..255|
|92|signed32, clamp0..255|signed LOW16 × baseU8, /100, clamp0..255|
|275|unsigned LOW8|signed LOW16 × baseU8, /100; DWORD result|
|54|signed LOW16, clamp0..25|signed LOW16 × signed baseI8, /100, then LOW16 and clamp0..25|

Finite91 percentage repeats can increase an already-derived skill; unlike90,
they are owned outside HP families too. Full32 multiplication needs explicit
overflow bounds before classification:90 accepts[-8421504,8421504] when an HP
ownership decision is required (any baseU8);91 accepts[-65535,65536] (any
derivedI16). Outside HP, base-derived90 remains native and needs no polarity
decision. These are arithmetic capabilities, not fixture values.

All reviewed54 setters belong to an HP package even when their clamped result
is0. HP percentage operands0..100 never exceed the native100%-clamped control
for any signed8 base. This is not a claim that clamping helps raw negative
THAC0: base-10 with90/100/150% all becomes0. A negative multiplier has opposite
polarity across actors: base20×-100% clamps0; base-10×-100% becomes+10. Therefore
HP negative-percentage records diagnose `BASELINE_CAPABILITY`; no actor baseline
is silently presumed. Existing outside-HP positive1..99 percentage handling is
retained. Amount>100 is not classified as a positive THAC0 bonus.

CON's finite positive/setter package remains HP-sensitive. The width fix also
prevents an effective CON penalty from incorrectly causing its cosmetic records
to enter HP policy. Unreviewed276/277 no longer inherit a raw-negative harmless
fallback; native width/polarity requires its own proof.

## Color and immunity classes

All listed constructors use non-dice fields. The reviewed classes use shared
scalar-deleting destructor14C8E0 and no-op OnAddSpecific/OnRemove1E1E0 except the
explicit101 removal exception below. The scripts check actual installed vtables.

| Opcode | Constructor / Apply | Proven behavior and compiler decision |
|---|---|---|
|7|19EC20 /1A98A0|Sets dirty+4BB8, appends range/color pairs to+1AD0, calls animation range/all setters. No gameplay-stat or original-effect-field writes. Range255 expands28 ranges. Native outside HP; finite HP cosmetic with `nonBlockingKeys`, like142.|
|102|1A0580 /1B6E10|Signed amount0..9 sets one table boolean at+14B8+4×amount; >9 no-op; negative indexes before the table and diagnoses. Native outside HP, finite HP mechanical companion.|
|101|1A0480 /1B6C10|Creates opcode pattern using LOW16(mode), ordinary mask+120; opcode24 uses+124. Native boolean immunity outside HP. OnRemove1E6C80 is nontrivial: it scans/removes matching entries by source/descriptor. HP lifetime/removal unsupported.|
|169|1A04C0 /1B6D20|Creates142 icon pattern, mask+124. Native boolean outside HP; HP expiry/rebuild still unsupported.|
|267|1A0440 /1B6B50|Creates139 string pattern, mask+128. Same narrow outside-HP classification.|
|296|1A0640 /1B6E50|Creates215 resource pattern, mask+12C. Same narrow outside-HP classification.|

Native OnList1F8E30 invokes equality1A4490, checks ordinary/mode/resource/amount
patterns and returns at the first match. One or two identical entries produce
the same boolean; no charge is consumed. CheckAdd1CD0A8 consults it before the
candidate acceptance hook. This does not prove arbitrary immunity removal or
expiry-side cache interactions safe for HP ownership. Original entries remain
unchanged. Opcode206 self-source policy and other resource guards remain a
separate unresolved problem; their provenance is not inferred from a resref.

## Magic resistance166 and remaining exclusions

Constructor1A1DC0 / Apply1C1B70: finite mode0 adds signed32 amount to signed16
derived MR+1146, then clamps[-128,127]. Mode1 sets with the same clamp. Neither
changes original matching fields; original lifetime extension survives tested
rebuilds/deadlines. Positive additive mode0 is owned; positive mode1 is native
outside HP and belongs to an HP package. Other modes remain explicit diagnostics.

The mode0 amount bound is exactly[-2147450880,2147450880]:
`INT_MIN - (-32768)` through `INT_MAX - 32767`. This prevents signed32 wrap for
every signed16 starting MR before native clamping. The native INT_MAX+baseline50
probe produces a negative result, so raw positive sign alone is insufficient.

Do not reinterpret221/337 as boolean protections:221 is DispelSecondaryType
(Apply1B2980);337 RemoveAllOfType (Apply1BF130) calls RemoveAllOfType1E7AD0 for
both effect lists. Source removal321 likewise changes which original bonuses
exist before admission. They need an ordering/removal policy, not a whitelist.
Invisibility20's mode1 OnAddSpecific1E5BA0 copies a mode0 effect and calls
AddEffect; only the independently reviewed mode0 below is now supported. These
exclusions remain visible in the captured capability report.

## Direct state/setter batch

The compiler now preserves proven native-only direct state behavior that was
previously rejected solely for lack of classification. Original records,
instant healing/cures, adverse effects and unrelated targets are retained.
The following constructors are non-dice; their installed vtables use shared
destructor14C8E0 and no-op OnRemove1E1E0. OnAddSpecific is also1E1E0 except20.

| Opcode | Constructor / Apply | Exact decision |
|---|---|---|
|23 morale|1A0CC0 /1BA440|Special0 rewrites amount=10/mode=1 at1BA449/1BA455 and sets Done=1 at1BA462, regardless of stored duration. It sets base morale+797 to10 unless the selected current/previous panic bit is set. It remains a native one-shot cure, including when delayed. Special-nonzero variants retain `MORALE_CAPABILITY`: mode0 demonstrably changes base10→11→12 on repeated Apply.|
|63 Infravision|1A06C0 /1B7440|Finite Apply only ORs derived state+1120 with0x20000. Parameters/Special are unused. Native outside HP; finite mechanical HP companion. Permanent timing1 also changes base state; permanent operations remain native.|
|76 Feeblemindedness|19FB60 /1B3B30|ORs state0x100000 and sets derived INT+1172 to3. Adverse native behavior is retained even inside an HP package.|
|106 morale break|1A0D00 /1BA520|Reviewed mode1 takes signed32 amount, clamps0..20 and sets derived DWORD+1188. It skips under panic, consulting+1120 or+1DC8 according to+4EA4. Native outside HP; HP package setter independent of actor-baseline polarity. Modes0/2 are separate additive/percentage paths and remain diagnosed.|
|282 scripting state|1A22C0 /1C4230|Unsigned mode<45 selects DWORD+1354+4×mode and stores raw32 amount. Out-of-range modes are native no-ops. Native outside HP; valid finite HP package setter. This does not label every scripting-state meaning beneficial in isolation.|
|20 ordinary Invisibility|1A0780 /1B76D0|Mode0 ORs derived invisibility bit0x10. Its real OnAddSpecific1E5BA0 returns without copying in mode0. Native outside HP; finite HP mechanical companion. Other modes remain diagnosed.|

Stable cases execute actual Resolve at1000,1450,1501 and1899 after changing only
the original deadline1450→1900. The actor baseline is reset synthetically, then
each original Apply runs twice without another reset to distinguish setters
from accumulators. Matching effect bytes, including firstCall1, stay identical;
the original stops applying at1900. Constructor callbacks are independently
checked. The morale cure deliberately changes its own amount/mode/Done and is
therefore kept native rather than misclassified as an owned timed bonus.

For Invisibility, Apply may allocate/queue `CMessageVisualEffect` (vtable598E60),
type2/value1. The probe executes its original Run219470, which dispatches type2
to21953C: it sets actor visibility flag+3F73 and ORs the same invisibility bit
in current/previous derived state. Repetition has no numerical potency/count.
Eight cases exercise both selected-stat paths, existing visibility flags and
forced visual refresh. Allocation, queuing, actor lookup/type are test doubles;
the original message handler executes. No save/object-lifetime claim follows.

Current captured gains from this batch are ordinary state/cure applicability,
not a new claim that all resources are covered. Projectile immunity's separate
consumer review is recorded below;233 proficiency alternate encodings,
200 consumed protection and other unreviewed classes are not silently ignored.

## Direct item construction: exact raw+20 sentinel

CItem::GetAbilityEffect1FB410 obtains the actual V1 record through
CResItem::GetAbilityEffect1148E0 at1FB498, then calls shared DecodeEffect1DE3D0
at1FB4B8. At1DE3E7–1DE3F6 the engine changes raw DWORD+20 from exactly
0xFFFFFFFF to0 before dispatching any opcode constructor. This is not confined
to SPL records. Non-dice constructors interpret that field as minimum level;
opcode18's dice constructor interprets it as dice size.

The direct-item probe executes actual CResItem::Parse114CF0, item ability/effect
selection, DecodeEffect, opcode constructors and the base constructor. Its
18/19/90/142 cases test0,65535,65536,0xFFFFFFFE and0xFFFFFFFF. Only the last is
normalized. The resulting original effects retain native sourceType2, item
source resref and caster/dispel level10. Resource demand/allocation and surrounding
services are test doubles; effect Apply/admission is not part of this probe.

Both compilers predict the normalized runtime field without editing input
bytes. The HP dice capability check uses the same normalized value; a zero
count with size sentinel is not falsely treated as a rolled HP effect. Other
nonzero counts/sizes retain the dice diagnostic, and other minimum levels above
65535 retain the separate admission-normalization diagnostic. Raw DWORD+1C has
no corresponding sentinel rewrite and is preserved exactly.

Sentinel and zero encodings intentionally share a logical fingerprint because
the native constructor makes them identical before admission. Duplicate records
still receive distinct dose quotas; raw source files remain byte-for-byte
unchanged. Other raw operands, including maxLevel and the effective-width aliases
described above, keep their original fingerprint distinctions.

## Projectile immunity83 and fire-resistance setter30

Opcode83's non-dice constructor is1A0500; its installed vtable uses shared
destructor14C8E0 and no-op specific OnAdd/OnRemove1E1E0. Apply1B6DE0 appends
unsigned32 parameter2 to the actor's derived projectile-immunity list+1410.
Parameter1 does not specify a consumed count. Actual CObList::Find4076F0
compares each stored QWORD at node+10 for equality and returns the first match
without changing the list or any entry. Duplicate entries therefore provide
the same boolean membership, not additional protection capacity.

The native consumers use unsigned16 projectile IDs: DeliverEffects at22F0DB,
AreaEffect at22A85D, BounceAI at22B631 and ColorSpray Fire at230C00. A match
skips delivery to that actor. A raw mode above65535 cannot match those queries;
the compiler preserves it as a native no-op rather than truncating its value.
The probe tests modes0/1/64/65535/65536/0xFFFFFFFF and amounts0/9. It executes
the original Apply, Resolve and Find instructions with one and two registrations,
including queries before/after the old deadline and until the new deadline.
Original effect bytes stay stable, matching never consumes entries, and expiry
stops reapplication. List storage allocation and rebuilds are test doubles.
The separate [projectile delivery proof](native-projectile-delivery-notes.md)
executes complete delivery branches with controlled membership; this probe
establishes the native membership semantics, not a new whole-engine replay.

Both compilers leave83 native outside an HP package. Within an HP package,
finite valid-ID records are mechanical companions and participate in ignore
repeat; they are not cosmetic/nonblocking keys. Original amount, mode and other
fields remain intact. Proven out-of-range no-ops do not keep an HP dose blocked.

Opcode30's non-dice constructor is1A1C00; Apply is1C1140. Its vtable has the same
generic destructor and no-op specific add/remove callbacks. The finite mode1
branch at1C120D takes signed LOW16 parameter1, writes derived fire resistance
at actor+113E and clamps to[-128,127]. Repeated application sets the same value;
it does not accumulate. The probe covers15 raw boundary/alias values including
-65535,32768,65535 and65537, retaining every original effect byte on repeated
Apply/Resolve through the extended deadline. Native self OnAdd is also executed.

The compiler preserves all mode1 setters natively outside HP, which proves
vanilla WAND16's SPIN713 branch has no owned bonus. Positive effective setters
inside HP are package companions; effective zero/negative forms remain native.
A positive setter can lower an already higher resistance: ownership describes
the package, not a guarantee of improvement against every actor baseline.
Raw fingerprints are unchanged. The separate percentage mode2 is still
diagnosed; this proof does not extend to it or to other resistance opcodes.

## Why the consumed pool200 is still unsupported

Native DecodeEffect dispatch for opcode200 reaches constructor19E620
(`CGameEffectBounceLevelDecrement`), whose Apply is1A7C20. With positive amount
and level<=9, Apply overwrites the corresponding derived bounce entry's count
at actor+1694+8*level. It does not add counts there, but that alone is insufficient
to classify the effect as harmlessly nonaccumulating.

CBounceList::Process14CC57–14CCA1 debits both equipped and timed originals using
ModifyAllOfType1E5480: opcode200, delta=-incoming power, add mode, no level or
timing filter. The helper adds that delta to parameter1 of every matching
original. It has no source-resource filter. A repeat with a fresh count6 can
overwrite the derived available count left by an old count1. After a debit1,
the originals retain0 and5 respectively. When two count6 originals receive a
debit6, both reach0 and each Apply dispatches its own exhaustion resource.

The two counterexamples execute the actual Apply and debit helper. Captured
BTEST1 uses amount6, mode1 and resource BTEST1B. The exhausted branch marks each
original Done; the test records the native FireSpell1E4570 calls without
executing the child spell. The class also has nontrivial OnRemove1E6BA0, which
queues a sound message. Full bounce/reflection scheduling and that removal
message are not replayed here. Mutable remaining capacity, repeat replenishment,
independent exhaustion payloads and nontrivial removal all need explicit policy
and lifecycle work. Both compilers retain `OPCODE_CAPABILITY` for finite200,
including duplicate or initially exhausted records; it is not whitelisted.

## Free Action's independent movement126 and proficiency233 setters

Vanilla POTN45 contains126(amount100,mode2) and233(amount1,mode131); the installed
SR/non-SR captures contain the latter. Class constructors1A0D40 and1A1480 are
non-dice, with generic destructor14C8E0 and no-op specific add/remove1E1E0.
The proof executes self OnAdd, original Apply/Resolve and the original native
animation getter/setter functions; no replacement stat formula is substituted
for those methods.

Movement Apply1BA6C0 uses animation vtable+A0 for default movement scale. If that
returns zero, it leaves movement unchanged. Otherwise mode1 takes unsigned LOW8
amount and calls SetMoveScale. Mode2 takes signed LOW16 amount, multiplies by
unsigned8 default speed, divides by100 with signed truncation toward zero,
and stores LOW8 of the result. These are setters independent of current speed.
The setter3373D0 only stores animation+0B; ordinary default getter327A90 reads
animation+0A. Ankheg getter327AA0 returns zero when its hidden-state DWORD+1BAC
is nonzero. The19 inspected vtables referencing these native default getters
all use setter3373D0. No pending message, nested effect or capacity is involved.

The180 movement setter cases cover both modes, default speeds0/9/255, ordinary
and visible/hidden Ankheg paths, and ten raw values including negative/low-word
aliases and wrapping results. Original effect bytes stay stable through repeat
Apply and expiry-only extension. The probe does not execute a complete movement
or derived-stat rebuild cycle; it resets the synthetic current speed between
rebuild observations and repeats each original without resetting it.

Modes0/5 are not setters: mode0 adds unsigned LOW8 amount to current speed;
mode5 scales current speed using signed LOW16 percentage. Counterexamples
9→10→11 and9→18→36 demonstrate accumulation and retain `MODE_CAPABILITY`.
Other modes take the native no-op branch. Modes1/2 remain native outside HP.
HP packages receive `HP_COMPANION_CAPABILITY`: class stability is proven, but
adverse versus beneficial movement, including modulo-byte percentage results,
needs an explicit package policy. No baseline or raw-sign shortcut was added.

Proficiency Apply1BCBB0 treats mode's low16 as a slot number and high16 as the
operation selector. High16=0 and slots89..134 assign raw32 amount to consecutive
derived DWORDs actor+1218..12CC. These are native nonaccumulating setters; the
amount and Special are not changed. The92 cases cover every slot with amounts
-1 and1, including POTN45's slot131. Repeated Apply preserves the complete
original effect and touches exactly the selected slot. Within HP, valid setters
are mechanical package states, consistent with the other reviewed fixed state
setters; this does not label every raw proficiency encoding beneficial alone.
Slots outside89..134 have no native table entry and remain native no-ops.

High16!=0 selects a distinct additive path. The common131 example consumes
firstCall at1BD0C9, derives parameter3 at1BD0DB, and adds it at1BD0E1. Special
can also change that derivation. The negative control observes0→1→2 and the
native first-call/parameter3 writes. These additive encodings retain a concrete
diagnostic; the setter proof does not support their mutable lifecycle. Source
and tests intentionally do not generalize the additive table from this one slot.

These changes remove independent126/233 diagnostics from captured POTN45 but
do not resolve its206 protection policy. No linked owner schema was changed.

## Native318 guards in otherwise unowned linked branches

The SCS DWTROLFI/DWTROLAC branches contain six-second resource guards for
DWTRRG2/4/12 and, in DWTROLAC, DWTFRG2. These accompany original source removal
and harmful/instant behavior rather than a finite potion bonus. The compiler
now proves and preserves this whole branch; it does not edit the shared SPL/EFF
or create child-dose ownership.

Opcode318 uses non-dice constructor1A03C0 and Apply1B69A0, generic destructor
14C8E0 and no-op specific OnAdd/OnRemove1E1E0. Apply calls the native protection
predicate24A3C0 with the original operands and actor/source context. False marks
the original Done at1B6A40. True creates a16-byte entry: resource8 bytes,
message=-1 at+8, includeItems=1 at+C, then appends it to actor+1880. No counter,
effect pointer or source provenance is stored in the entry.

CheckAdd at1CCCEF–1CCD1E queries the current/previous resource-immunity list
using incoming sourceRes and whether sourceType differs from1. Actual FindRes
1F8C90 compares the resource and optionally the includeItems flag, returning
the first matching entry without decrementing or altering it. Duplicate318
entries do not provide additional capacity. They also do not justify bypassing
any protection: unrelated indistinguishable entries still exist, and native
admission remains authoritative.

The ten cases execute native Apply/Resolve, resource constructor/copy and
FindRes. Five resources, including an arbitrary nonfixture resource, exercise
both predicate outcomes. Successful repeats retain original effect bytes and
produce identical boolean entries; repeated lookups with spell/item source
filters consume nothing. A failed predicate changes only Done. SourceID=-1
avoids object lookup; the predicate itself, allocation, local string lifecycle
and derived-list insertion/rebuild are controlled services. No particular
SPLPROT row meaning is assumed, and native admission/full linked delivery is
not part of this probe.

The capability boundary is structural: explicit resource, finite318 in a linked
branch, non-HP parent family, and a complete bounded traversal with no owned
child bonus. Predicate operands remain native; requiring the captured0/0 values
would not follow from the evidence. Direct318 and HP conditional guards still
diagnose. POTN10's318(145,111,DW#HDANI) therefore receives no blanket exception.
Existing conditional timing and missing/cyclic resource checks remain intact.

Traversal records each preserved guard's protected resource internally. If it
names any source in the parent's owned canonical/alias family, compilation fails
with `RESOURCE_GUARD_CAPABILITY`: keeping such a guard could reject repeats
before refresh admission. This mirrors the existing original-source-removal
constraint without inventing an immunity bypass or changing the emitted manifest
schema. Tests cover canonical and alias guards, changed predicate operands,
shared branches, unrelated damage/removals and bonuses before/after a guard.
