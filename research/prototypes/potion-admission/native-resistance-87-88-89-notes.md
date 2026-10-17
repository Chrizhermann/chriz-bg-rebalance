# Physical resistance opcodes 87, 88 and 89

2026-10-09. Independent native evidence and narrow compiler classification for
crushing, piercing and missile resistance. No game, native DLL, installer,
resource, save or generated EEex hook was executed or changed. Opcode 86's
existing policy is unchanged; its source pattern alone was not used as proof
for these three classes.

Pinned BG2EE 2.7.3.0 executable:
`%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
All addresses are RVAs, image base `0x140000000`. Local EEex 1.3.0 class names
come from `EEex/loader/v2.7.3.0/bg2ee/function_names.db`; actual DecodeEffect
construction independently confirms each selected class and Apply address.

## Resource evidence

IR loose source corpus:
`C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions\item_rev\itm`.
IRR loose source corpus:
`C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions-4b10\ItemRevisions-4b10\item_rev\itm`.
These are source files, not a complete installed profile.

Both `POTN18.SPL` files contain opcodes 87/88/89 at ability 0 ordinals 1/2/3,
offsets 0xCA/0xFA/0x12A. All are target 1, mode 0, timing 0, Special 0,
probability 100/0. IR uses amount 20 and duration 300; IRR uses amount 25 and
duration 60. Their other records, including native resource immunity 206, are
preserved and remain separate compatibility obligations.

Original hashes, also recorded in `native-ir-remaining-notes.md`:

- IR POTN18.SPL: `8a165ec862ef2bc615cfc45df86bd0cf76adfbfb4811045b8e4a4d22560487fc`.
- IRR POTN18.SPL: `e56ef4889a8ecd5c2a899e148a73128dac9eedb8951affe80b774175d46c3d04`.

## Constructors and finite arithmetic

| Opcode / class | Constructor | Vtable | Apply | Finite WORD bonus | Base signed byte |
|---|---|---|---|---|---|
| 87 ResistCrushing | 1A1B80 | 593708 | 1C0E20 | actor+2A9E | actor+5B9 |
| 88 ResistPiercing | 1A1D40 | 593760 | 1C1810 | actor+2AA0 | actor+5BA |
| 89 ResistMissile | 1A1D00 | 5937B8 | 1C1660 | actor+2AA2 | actor+5BB |

All three constructors use UsesDice=false, preserve amount/mode/Special, and
map raw effect DWORD+1C to runtime maxLevel+58, raw+20 to minLevel+54. Runtime
dice fields are zero. Common DecodeEffect normalizes only the exact raw+20
FFFFFFFF sentinel to zero. Vtables use scalar destructor 14C8E0 and no-op
specific OnAdd/OnRemove 1E1E0. Base self OnAdd also executes in the probe.

The finite mode-0 branches are independently present at:

| Opcode | Read LOW16 amount | ADD WORD | Signed comparison to 100 | Upper-cap write |
|---|---|---|---|---|
| 87 | 1C0F93 | 1C0F98 | 1C0F9F | 1C0FAE |
| 88 | 1C1983 | 1C1988 | 1C198F | 1C199E |
| 89 | 1C17D3 | 1C17D8 | 1C17DF | 1C17EE |

The WORD addition wraps before the signed upper cap. There is no lower
saturation in these additive branches. Raw 65537 and -65535 both add 1;
raw 32768 adds -32768; raw 65536 adds zero. Raw operands remain unchanged in
native objects, resources and manifest fingerprints.

BonusInit 150FBF and 150FC3 clear the qwords containing offsets +2E/+30/+32 of
the bonus stats at actor+2A70, including all three accumulators. Each finite
additive application thereafter leaves its signed WORD in [-32768,100]. For
every baseline in that interval, adding 1..32667 cannot overflow and cannot
reduce the value after the cap. The upper endpoint is `32767 - 100`.

Explicit native controls establish the boundary, rather than assuming
saturating arithmetic:

- `100 + 32667` becomes 100 after the cap.
- `100 + 32668` wraps to -32768.
- `-32768 + (-1)` wraps positive and becomes 100.
- `-32768 + 1` becomes -32767.

Thus the compiler owns effective positive signed LOW16 values **1..32667**,
keeps effective zero native, and diagnoses negative finite operands or larger
positives with `AMOUNT_CAPABILITY`. A negative diagnostic does not mean that an
ordinary penalty was turned into a buff: its input is untouched and that source
is explicitly unsupported until its policy is reviewed. No coverage is claimed
for the rejected resource, and no global engine overflow repair is attempted.
The same positive additive ownership applies in an HP-sensitive family; it is
a mechanical companion, never a nonblocking cosmetic key.

Finite mode 1 writes signed LOW16 into derived resistance and clamps it to
[-128,100]. Mode 2 reads a signed base byte, multiplies by signed LOW16, divides
by 100, narrows to WORD and then clamps. Those source branches are outside this
bounded classification/probe and retain `MODE_CAPABILITY`; in particular,
percentage polarity must not be inferred from a positive raw value with a
negative resistance baseline. No additional HP setter policy is introduced.

Timing 1 uses a distinct base-byte branch, sets Done/Repass and is a native
instant/permanent operation. It is not treated as a stable finite bonus, even
when the raw amount would fail the finite capability guard.

## Native lifetime and compiler verification

`probe_native_resistance_87_88_89.py` passes **96 native instruction cases**:
32 per class, comprising 3 constructor/sentinel cases, 17 finite amount cases,
8 explicit arithmetic endpoints and 4 instant controls. Finite cases observe
five accumulator baselines, first and repeated Apply calls, and times before
and after the old expiry. Changing only expiry from 1450 to 1900 preserves the
full original 0x180-byte object during every recalculation, including amount,
Special, firstCall=1 and source metadata. Native Resolve stops applying at 1900.
The finite branch writes Done=0, preserving a live original's existing value.

Actual constructors, base self OnAdd, Apply and Resolve execute in Unicorn.
Actor baselines and stat resets are controlled; the complete ProcessEffectList,
damage calculation, native admission/save/MR, linked transport and generated
hooks are not exercised. No live acceptance or current-save safety follows.

`tests.test_potion_opcode_87_88_89` passes **12 compiler methods**. Every successful
manifest is compared in full between Python and Lua. Fixtures cover both
policies, signed-width boundaries and raw aliases, exact input preservation on
success/failure, HP companions and partial SCS aliases, reordered/duplicate
records, multiple abilities, shared linked payloads, the two observed IR/IRR
potencies/durations, untouched native conditions and unrelated effects, and
remaining linked protection diagnostics. Tests do not require IR/SR or fixture
record counts. Original effect ordinals and counts are read from each input.

```powershell
python -B research/prototypes/potion-admission/probe_native_resistance_87_88_89.py --exe '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe' --python-libs '%USERPROFILE%\AppData\Local\Temp\cbr-potion-hp-research-20261009\pylibs'
python -B -m unittest tests.test_potion_opcode_87_88_89 -q
```

Native JSON output:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-resistance-87-88-89-probe.json`.
