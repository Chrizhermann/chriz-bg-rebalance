# Detect Illusion276 and Set Traps277

2026-10-09. Bounded native review and compiler classification for the
original-effect admission research prototype. No live game, DLL, installer,
resource, save or generated-hook execution. This does not settle opcode206
self-protection policy or establish whole-profile runtime support.

Pinned BG2EE2.7.3.0 executable:
`%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
All addresses below are RVAs, image base `0x140000000`. Local EEex1.3.0 names
come from `EEex/loader/v2.7.3.0/bg2ee/function_names.db`; actual DecodeEffect
constructor/vtable selection is independently executed, not inferred from names.

## Original resource evidence

IR source corpus: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions\item_rev\itm`.
IRR source corpus: `C:\Games\Baldurs Gate 1 and 2 mods\ItemRevisions-4b10\ItemRevisions-4b10\item_rev\itm`.
These are loose resources, not complete installed profiles. All three records
below are target1, amount20, mode0, timing0, duration300, Special0 and100/0
probability. Ordinals are zero-based in ability0; original bytes remain intact.

| Corpus / resource | Offset / ordinal | Opcode | Original SHA256 |
|---|---|---:|---|
| IR POTN39.SPL | 0x9A / 0 | 276 | `e88a6cc804e6f84c413e6f386be67f4fd54ada0d301d4429f02b7384d8712ba4` |
| IRR POTN39.SPL | 0xFA / 2 | 276 | `79cbec7d07b03f2b024a5284969a6f8f17c8c198aab9419fed218f16fe9d614a` |
| IRR POTN36.SPL | 0x15A / 4 | 277 | `048e781ed7d6aff4032906d159ee51a58f652c647bca4d63d3ecd4dc2068ec6c` |

The inspected direct POTN36/POTN39 resources in default-SR, non-SR and vanilla
profiles did not contain these opcodes. Classification does not depend on SR,
IR, names, reference amounts or reference record positions. Review remaining
resource diagnostics before treating any of these complete potions as supported.

## Native operations and lifecycle

| Opcode / class | Constructor | Vtable | Apply | Base U8 | Derived DWORD | Bonus DWORD |
|---|---|---|---|---|---|---|
| 275 HideInShadows, control | 19FF70 | 597330 | 1B54F0 | actor+59D | +1194 | +2AE4 |
| 276 DetectIllusion | 19F4A0 | 597388 | 1B14F0 | actor+5BC | +1198 | +2AE8 |
| 277 SetTrap | 1A2740 | 5973E0 | 1C60D0 | actor+5BD | +119C | +2AEC |

All three constructors use UsesDice=false. Original amount, mode and Special
are unchanged. Runtime dice fields are zero; raw effect DWORD+1C maps to
maxLevel+58, raw+20 maps to minLevel+54. The shared DecodeEffect exactFFFFFFFF
sentinel at raw+20 becomes0 first. All use scalar destructor14C8E0 and no-op
specific OnAdd/OnRemove1E1E0; the probe executes base self OnAdd too.

Finite mode0 sign-extends LOW16(amount), then adds to a DWORD bonus accumulator:
275 at1B555C/1B5560,276 at1B155C/1B1560,277 at1C613C/1C6140.
Positive effective values nominally improve the corresponding skill; negatives
reduce it. Raw65537 and-65535 both add1; raw32768 adds-32768; raw65536 adds0.
Fingerprints and original native operands retain the full raw dword.

Mode1 takes unsigned LOW8(amount) and assigns the derived DWORD, at1B5537,
1B1537 and1C6117 respectively. Mode2 multiplies the base U8 by signed
LOW16(amount), divides by100 with truncation toward zero and assigns the
derived DWORD. The maximum product magnitude is255*32768, within signed32.
Repeated calls without stat reset produce the same value for both modes;
neither consumes first-use state, charges or a protection count.

BonusInit150FE7 clears the276/277 accumulator pair. DerivedStats operator+=
15040E–15041D merges all three DWORD bonuses. CheckLimits15195B–15199D clamps
their signed results to0..255. Reload1539B3–1539BE loads base Detect Illusion
and Set Traps bytes. ProcessEffectList calls Reload3AC4F8, BonusInit3AC563 and
the merge3AC5BC; the probe does not execute that complete rebuild.

**Overflow boundary:** the additive DWORD and later merge can wrap before
CheckLimits. Controlled INT_MAX+1 becomesINT_MIN and then0; INT_MIN-1 becomes
INT_MAX and then255. Even merging bonusINT_MAX with base1 wraps. Nominal-sign
classification does not repair this engine behavior or promise monotonic benefit
for every pathological aggregate. Suppressing repeated same-potion accumulation
intentionally changes that aggregate, including possible overflow. Other native
effects, arithmetic, final limits and raw operands remain untouched.

Timing9 uses a separate raw32 persistent accumulator (+2D08/+2D0C/+2D10), not
the finite signedLOW16 branch; permanent operations remain native.

## Compiler policy and evidence limits

- Finite mode0: own positive effective signedLOW16 bonuses; leave zero and
  negative effective operands native. Raw upper bits are not rewritten.
- Mode1: native nonaccumulating outside an HP family. In an HP family, a
  positive LOW8 setter is a package companion and is ignored on active repeat,
  even if it would lower an unusually high baseline; zero remains native.
- Mode2: native base-derived setter outside an HP family. Within an HP family,
  own effective percentages>100; preserve neutral/adverse forms. These are
  mechanical companions, never nonblocking cosmetic keys.
- Unknown modes retain MODE_CAPABILITY; delayed owned lifetimes and unsupported
  owned transport retain their existing specific diagnostics. This change adds
  no opcode206 bypass, source rewriting or runtime lifecycle normalization.

`probe_native_skill_276_277.py` passes174 cases:58 per opcode including275 as
the comparison. Per class:3 real construction/level-sentinel cases,51 finite
mode/amount cases over baselines0/50/255,3 wrap controls and1 timing9 control.
Each finite case checks repeated native Resolve/Apply through the old deadline
after changing only expiry1450→1900. The entire original0x180-byte effect stays
unchanged between recalculations, including firstCall1, Special and source
metadata. Application stops at1900. The exact three native merge pairs and
full CheckLimits execute; actor resets, list state and unrelated engine services
are controlled. Native delivery/admission, full rebuild ordering, actual saves
and generated EEex hooks are outside this probe.

Run from this worktree:

```powershell
python -B research/prototypes/potion-admission/probe_native_skill_276_277.py --exe '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe' --python-libs '%USERPROFILE%\AppData\Local\Temp\cbr-potion-hp-research-20261009\pylibs'
python -B -m unittest tests.test_potion_opcode_276_277 -q
```

The local native result is
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-skill-276-277-probe.json`.
The11 compiler tests compare complete Python/Lua manifests, both policies,
LOW16/LOW8 boundaries, native setters versus HP companions, reordered copies,
multiple abilities, linked aliases/shared counts, distinct potion families,
metadata, sentinel construction, instant/permanent/adverse preservation and
concrete unsupported-mode/transport diagnostics. They do not emulate native
skill arithmetic or claim engine admission success.
