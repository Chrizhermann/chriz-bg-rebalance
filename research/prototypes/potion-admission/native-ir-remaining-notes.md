# Remaining IR/IRR native effects: 86, 120, 130 and 206

Native review and subsequent narrow compiler classification, 2026-10-09.
No runtime module changes, policy choice, live interaction, installation or
save edits. This does not resolve linked transport or the pending choice about
native potion self-protections.

Pinned BG2EE 2.7.3.0 executable:
`%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
Addresses below are RVAs, image base `0x140000000`. Names come from the local
EEex 1.3.0 `EEex/loader/v2.7.3.0/bg2ee/function_names.db` and are checked against
actual DecodeEffect-selected constructors/vtables, not inferred from names.

## Resource evidence

Read-only loose source corpora, not claims about installed profiles:

- IR: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions\item_rev\itm`.
- IRR: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions-4b10\ItemRevisions-4b10\item_rev\itm`.

All rows below are finite timing0; ordinals are zero-based within ability0.

| Corpus/resource | Offset / ordinal | Relevant native record |
| --- | --- | --- |
| Both POTN09.SPL / POTN41.SPL | 0x9A / 0 | 130 target1 amount2 mode0 Special0, 300 seconds |
| Both POTN11.SPL | 0xFA / 2 | 120 target1 amount0 mode2 Special0, 60 seconds |
| IR POTN18.SPL | 0x9A / 0 | 86 target1 amount20 mode0 Special0, 300 seconds |
| IRR POTN18.SPL | 0x9A / 0 | 86 target1 amount25 mode0 Special0, 60 seconds |
| IR POTN18.SPL | 0x21A / 8 | 206 target1 amount0 mode0, resource POTN18, 300 seconds |
| IRR POTN18.SPL | 0x21A / 8 | 206 target1 amount-1 mode0, resource POTN18, 60 seconds |
| Both POTN11.SPL | 0x2AA / 11 | 206 target1 amount-1, resource POTN11, 60 seconds |
| IRR POTN14.SPL | 0x1EA..0x45A / 7..20 | 206 target2 amount74011, multiple spell resources and POTN14, 60 seconds |

Representative original SHA256s:

| File | SHA256 |
| --- | --- |
| IR POTN09.SPL | `110e87673cf94d0c40f3ff84c3dede38b7bc6fe98eee48f8361061eae306713c` |
| IR POTN11.SPL | `856286d592ced5d4b6503dee4ce906fb741102f671ee267a5f8602d2c294cb93` |
| IR POTN18.SPL | `8a165ec862ef2bc615cfc45df86bd0cf76adfbfb4811045b8e4a4d22560487fc` |
| IRR POTN09.SPL | `14ef5648267df2412a7634b8b5c5eb20477ded07099562106b529a4ccca37a77` |
| IRR POTN11.SPL | `c275ebb35b8ab1afae055ba29cb5940cf25432f4807986950151457cbd3209fc` |
| IRR POTN18.SPL | `e56ef4889a8ecd5c2a899e148a73128dac9eedb8951affe80b774175d46c3d04` |
| IRR POTN14.SPL | `282b501dfbedad187092425aacf767495eaf68e20ee40de4c4389dc6da836e4f` |

## Construction and lifetime shared by the four classes

| Opcode | Class constructor | Installed vtable | Apply |
| --- | --- | --- | --- |
| 86 ResistSlashing | 1A1D80 | 5936B0 | 1C19C0 |
| 120 ImmuneToWeapon | 1A0200 | 5941B0 | 1B6420 |
| 130 Non_CumulativeBless | 1A0F00 | 594628 | 1BAAB0 |
| 206 ImmunitySpell | 1A0380 | 595C28 | 1B6900 |

All four call base constructor19DCB0 with UsesDice=false. Actual decoding and
construction preserve raw amount, mode and Special. Runtime dice fields are
zero; raw effect DWORD+1C maps to maxLevel+58 and raw DWORD+20 to minLevel+54.
The common DecodeEffect exact FFFFFFFF sentinel at raw+20 becomes0 before
construction. None has a class-specific parameter normalization after the
base constructor. All four real vtables use scalar destructor14C8E0 and no-op
specific OnAdd/OnRemove1E1E0. Self base OnAdd is executed in the probe.

For finite originals, repeated Apply/Resolve keeps the full 0x180-byte effect
unchanged, including parameter1, Special, firstCall and flags. Changing only
expiry1450 to1900 continues application before1900; native Resolve marks Done
without reapplying at1900. This is lifecycle evidence, not permission to label
every state beneficial or to change its admission policy.

## 86 is cumulative slashing resistance

The actual IR/IRR mode0 path at1C1B33 reads LOW16(parameter1), adds it to the
WORD accumulator actor+2A9C at1C1B38, then compares the signed result to100 and
caps only the upper side. IR20 gives20 then40; IRR25 gives25 then50. This is a
real finite bonus needing uniqueness handling, not a native nonaccumulating
ward. Original effect fields remain stable.

Classification must use signed LOW16, retaining the raw32 operand in matching:
65537 is+1,65535 is-1,32768 is-32768. The WORD addition happens before the
signed cap; extreme operands can wrap and must not be described as saturating
addition. The probe includes sixteen amounts, including actual records,
adverse values, zero, low-word aliases and overflow boundaries. No generalized
polarity promise is made for overflow against arbitrary other active bonuses.

The subsequent Python/Lua compiler classification supports finite mode0 with
effective signed LOW16 in1..32667. A finite native accumulator is in
[-32768,100]: the WORD establishes the lower bound and each additive Apply
caps above100. Adding1..(32767-100) cannot wrap over that entire interval and
cannot reduce the result after the upper cap. Effective0 remains native.
Positive32668..32767 can overflow from100; any negative can underflow from
-32768. Both receive `AMOUNT_CAPABILITY`, rather than being labelled beneficial
or harmless from the raw sign. Four native boundary cases demonstrate100+32667
→100,100+32668→-32768,-32768-1→100 and-32768+1→-32767. This guard applies only
to finite classification; instant/permanent operations remain native. Raw32
operands are preserved in fingerprints, including aliases like-65535 (=+1).

Source-only distinctions outside these actual mode0 resources: mode1 assigns
signed LOW16 to derived+114C and clamps to[-128,100]; mode2 scales the signed
base byte+5B8 by signed LOW16 percent before the same finite clamp. Other modes
return without change. Those extra branches are not granted capability here.
Timing1 instead alters the base byte and marks Done/Repass; it is not covered
by the finite-original result.

## 120 registers nonconsuming weapon predicates

Apply1B6420 allocates16 bytes, derives a predicate from mode via jump table
1B653C and appends it to actor+14E0 at1B6525. The entry contains a weapon-type
WORD+0, flag value DWORD+4, flag mask DWORD+8, and maximum enchantment DWORD+C.
It has no hit counter, remaining charges or original-effect pointer.

The captured mode2 takes1B6496, sets mask0x40/value0 and max enchantmentFFFFFFFF;
parameter1 does not affect that branch. Its classification is flag membership,
not additive potency. Mode0 uses raw32 parameter1 as an unsigned enchantment
threshold; modes1/2 use flag0x40,3/4 flag0x100,6/7 flag2,8/9 flag0x10,10/11
flag0x200 with alternating required-set/required-clear predicates. Mode5
requires clear0x100 with threshold0. Out-of-range modes append the all-zero
descriptor (matching any type/flags at enchantment0), not an empty no-op.

Native CImmunitiesWeapon::OnList1F9040 checks optional type, the five flag masks
and unsigned enchantment comparison1F9126, returning boolean1 on first match.
It neither changes the entries nor consumes capacity. The probe executes the
real consumer against seven flag combinations and four enchantments for each
mode0..12, with one and two duplicate descriptors. Duplicates do not increase
blocking capacity. This supports native preservation outside HP; a finite HP
package companion still needs explicit package ownership/admission treatment,
even though its native original fields and removal lifecycle are stable.
The compiler now preserves120 outside HP and retains
`HP_COMPANION_CAPABILITY` for finite120 within an HP family, including an alias
that inherits the family's HP policy. No whole-package reset proof is assumed.

## 130 is state-gated first-winner, with a morale side effect

Apply1BAAB0 tests bit23 of derived general state actor+1120. If already set it
returns without changes. Otherwise it sets that bit and performs:

- 1BAAC6: signed LOW8 amount adds to damage WORD+11A0.
- 1BAAD1: signed LOW8 amount subtracts from THAC0 WORD+1130.
- 1BAADC: raw LOW8 amount adds to morale BYTE+797, modulo256.

Mode and Special are not consulted. The first effect wins even when a later
one is stronger:2 then7 yields2;7 then2 yields7. This shared state also means
different potion families can interact through the engine's original blessing
rule. Matching must not rewrite this into maximum/last-wins semantics.

Two calls on the same derived state do not accumulate. Clearing only the
derived bit and recalculating reapplies the morale increment; with amount2,
morale10 becomes12,14,16,18 across four synthetic rebuilds. The complete engine
rebuild/morale-reset cycle is not executed, so this is a concrete warning
against treating the effect as a pure fixed setter, not a claim that normal
gameplay necessarily accumulates morale on every engine tick. No firstCall or
other original-effect field is consumed to suppress that side effect.

The HP ignore-repeat policy could suppress an incoming130 together with its
package while preserving the original native behavior. That recommendation
requires family lifetime/provenance integration; it does not follow merely
from the opcode's name or the unchanged object. There is no blanket refresh
recommendation for arbitrary130 packages from this evidence.

## 206 remains native source protection; bypass policy is unresolved

Apply1B6900 creates a16-byte descriptor: resource+0 (8 bytes), message+8 and
includeItems+C=0. At1B695A..1B696A amount0 is translated to message-1; nonzero
amount, including-1 and74011, is retained. **This translation is only in the
derived descriptor; original parameter1 remains unchanged.** Mode and Special
are not used by this Apply path. It appends to actor+1880 at1B6974.

FindRes1F8C90 returns the first matching resource entry and consumes nothing.
Its item-source filter excludes206 entries with includeItems0. In the native
CheckAdd source-resource query1CCCEF..1CCD1E, sourceType1 uses the spell filter;
other source types use the item filter. Thus an original linked SPL child can
be rejected by its self206 while a direct ITM source does not receive the same
protection from this list. The probe executes both filters and duplicate
lookups, preserving entry bytes and verifying first-entry selection.

The descriptor lacks original source/dose attribution. IR0 and IRR-1 produce
identical derived bytes; an unrelated ward for the same resource may also be
indistinguishable. Nonconsuming behavior establishes no safe bypass. Keeping
existing self-protection is also not proof of refresh support or global potion
uniqueness. The pending user policy and lead's linked provenance integration
remain required; this review makes no policy decision.

## Reproduction and limits

`probe_native_ir_remaining.py` produces75 passing cases:12 native construction,
16 slashing additive,4 slashing wrap boundaries,22 blessing width/state,
2 blessing order,13 weapon predicate and6 resource-protection cases.
Each case contains multiple observations.

Command (from this worktree):

```powershell
python -B research/prototypes/potion-admission/probe_native_ir_remaining.py --exe '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe' --python-libs '%USERPROFILE%\AppData\Local\Temp\cbr-potion-hp-research-20261009\pylibs'
```

JSON evidence is saved outside the repository at
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-ir-remaining-probe.json`.
Allocation/list insertion and baseline/list rebuilds are test doubles. Actual
native constructors, class Apply/Resolve and immunity consumers execute. Full
attack delivery, immunity/save/MR admission, engine morale scheduling, live
save/load and generated hook execution are not tested. Proprietary executable
or resource bytes are not copied into the repository.
