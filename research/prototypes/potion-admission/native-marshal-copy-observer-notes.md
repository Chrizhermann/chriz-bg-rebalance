# Native marshal context and live-copy observers

October 9, 2026. These modules are inert preparation: no automatic loader,
handler registration, ownership propagation, Runtime/Lab wiring, game process,
native EEex DLL execution, installation or save writes.

Executable: BG2EE 2.7.3.0, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`,
read from `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`.
All addresses below are RVAs relative to image base. The corresponding
`EEex\loader\v2.7.3.0\bg2ee\function_names.db` supplies the native names.
The local `EEex_scripts` are the inspected EEex 1.3 source. PE relocation
directory is empty; image-relative guards are not proof of OS relocation support.

## Marshal contract and boundaries

`CBRPQMarshalTransport.lua` exposes `validate(api, config, watchdog)` and
`install(api, config, watchdog)`. Composition supplies existing global functions
through `config.callbacks.enter`, `.counted` and `.leave`:

- `enter(originalEntryRSP, listPtr, versionByte, onlyTiming9DWORD, excludeTiming2DWORD)`
- `counted(originalEntryRSP, listPtr, normalBytesDWORD)`
- `leave(originalEntryRSP)`

All five entry arguments are numbers. Version zero selects V1; every nonzero
byte selects V2. Both filter DWORDs use native nonzero truth semantics. A future
adapter must normalize those explicitly without mistaking a raw version byte
for an on-disk effect format number. `listPtr` is borrowed, not userdata.
Every invocation is observed, including unowned/nested calls; ownership/context
stack policy belongs to composition. Callback return values are ignored.

`counted` reports the finalized **native** normal-effect byte count exactly once
per ordinary V2 invocation, before EEex CalculateExtra. There are two disjoint
native paths, requiring two observer sites while preserving the stock EEex hook:

- `1E5342`, five bytes `45 85 E4 74 3B`: when R12D (onlyTiming9) is zero,
  EBX already holds the final count times `108h`. With excludeTiming2 false,
  this derives from list+18; otherwise the native loop has counted non-2 records.
  The observer restores flags/registers and re-emits the original TEST and
  conditional jump to `1E5382`, or fallthrough `1E5347` when onlyTiming9 is true.
- `1E537B`, seven bytes `41 69 D8 08 01 00 00`: onlyTiming9's native count is
  R8D. The callback reports low32(R8D*108h), then restores the original IMUL.

Both report RDI as the list and body RSP+`1B8h` as the entry key. OnlyTiming9
overrides the preceding excludeTiming2 count, consistently with timing9 never
being timing2. No normal native CALL is moved. At `1E5382`, all V2 paths have
the final EBX consumed by stock EEex at `1E5384`; its two-byte TEST offers no
independent five-byte hook site without colliding with that existing hook.
V1 never reaches either counted observer.

The context adapter must require one counted event, matching entry frame/list,
a nonnegative bounded multiple of `108h`, and exact equality to the final
eligible-record count times `108h`. The callback reports native DWORD arithmetic;
it does not silently repair overflow or a corrupt cached list count. Native
path tests check counted once and equality to EBX at `1E5382` for every V2
case; generated instruction tests cover both branches, including skipped Lua
calls on the onlyTiming9 path, and preserve the original TEST/IMUL flags.

The entry hook is `1E50E0`, displacing exactly six bytes
`40 53 56 57 41 54` (push RBX/RSI/RDI/R12). Entry stack alignment is eight.
The complete prologue pushes six registers and subtracts `188h`, so the body
RSP is original entry RSP minus `1B8h`. At entry, the fifth argument is the
DWORD at `[RSP+28h]`; native reads it from body `[RSP+1E0h]` at `1E513E` (V1)
and `1E52F5` (V2).

All ordinary paths converge at `1E5454`. The leave hook displaces the eight
bytes `48 8B 8C 24 70 01 00 00` (load security cookie into RCX) and reports
body RSP plus `1B8h`. The native return-size value in EAX is preserved. Native
cookie call `1E545F`, stack restoration and sole RET `1E5474` remain in place.
Every decoded native jump stays within the function; V1's `1E52F0` jump and
V2's empty/nonempty paths all reach this common exit. Native exceptions or
nonlocal unwinding have no leave notification and require explicit reset policy.

The entire native function is guarded except two pre-existing EEex patch slots:

| Interval | Meaning |
|---|---|
| `1E50E0..1E5383` | Entry/frame, V1 path, V2 native count/filter decisions |
| `1E5384..1E5389` | Existing EEex OverrideSize conditional hook; excluded |
| `1E538A..1E538C` | Original allocation argument; guarded |
| `1E538D..1E5391` | Existing EEex WriteExtra allocation-call hook; excluded |
| `1E5392..1E5474` | Native normal copy and sole ordinary exit; guarded |

`EEex_Sprite_Patch.lua:184` wraps the sprite's Marshal call at `361767`.
Its before hook invokes `EEex::Sprite_Hook_OnBeforeEffectListMarshalled` and
stores the sprite pointer used by its two internal list hooks. It remains
untouched. The size/write hooks at source lines232/278 also remain untouched.
Exact guards reject collisions at our sites or changed native filter/copy code.
They **do not authenticate arbitrary foreign replacements in the two excluded
stock EEex slots**. Preserving the inspected collector/writer contract remains
a separate composition prerequisite.

## Exporter count changes are an unresolved native limitation

The original normal-effect count in EBX is computed **before** the EEex exporter
call at `1E5384`. EEex saves that old count as OriginalMarshalSize, adds only the
extra metadata byte count, then writes the metadata at buffer+OriginalMarshalSize
from the allocation-call hook. Normal native effect copying follows afterwards.

Consequently, the final-snapshot ownership wrapper can resolve a reorder at an
unchanged eligible count, but merely recalculating metadata size does **not**
repair a count-changing exporter. Appending an eligible native effect makes the
normal copy overwrite the already-written footer; removing one leaves a gap.
Detecting such a failure is not a native save-abort or rollback mechanism.

The retained test
`test_retained_counterexample_exporter_append_overwrites_footer_at_old_native_count`
executes the real count/allocation/copy instructions. It models the inspected
two EEex hook services and appends one eligible native effect during export.
The original count is `108h`, allocated bytes `210h`, and the second native
record overwrites `X-BIV1.0` at buffer+`108h`. This test passes by reproducing the
unsupported behavior; it is not evidence that the current exporter solves it.
Any earlier note/test claim about supporting late appended normal effects must
be read subject to this correction. No SaveExport implementation is changed here.

## CopyFromBase boundary and actual live-copy evidence

`probe_native_effect_copy.py` executes actual SPL constructors, virtual Copy
(vtable slot+8), GetItemEffect `1E4D50`, CopyFromBase `1DCAF0`, and
DecodeEffectFromBase `1E2D30` for these classes:

| Opcode | Virtual Copy RVA | Vtable RVA | Return from CopyFromBase | Object bytes |
|---|---|---|---|---|
| 0 | `1CE1B0` | `591768` | `1CE243` | `158` |
| 1 | `1CE9F0` | `5917C0` | `1CEA83` | `158` |
| 10 | `1CF860` | `591C38` | `1CF8F3` | `158` |
| 18 | `1D3590` | `591E48` | `1D3631` | `160` |
| 19 | `1D3860` | `591EA0` | `1D38F3` | `158` |
| 54 | `1DB790` | `592A50` | `1DB823` | `158` |
| 83 | `1D4360` | `5935A8` | `1D43F3` | `158` |
| 90 | `1DA710` | `593810` | `1DA7A3` | `158` |
| 92 | `1DA7C0` | `5938C0` | `1DA853` | `158` |
| 98 | `1D74E0` | `593AD0` | `1D7573` | `158` |
| 142 | `1D69E0` | `594AA0` | `1D6A73` | `158` |
| 146 | `1CFA70` | `594C58` | `1CFB03` | `158` |
| 206 | `1D3F40` | `595C28` | `1D3FD3` | `158` |

For each tested live Copy, the destination is a distinct new object of the
same native class and CopyFromBase's source is exactly original+8. The original
is unchanged. The stable serialized field projection `10..4F` plus `54..D3`
survives, with the proven uppercase/NUL normalization of operands `30/70/78`.
This is not an object memcpy:

- source ID `110` is passed through the live-copy constructor;
- done `114` and field `118` reset to zero;
- original duration `11C` becomes current duration `28` (tested active expiry
  1450, rather than the original 61);
- target ID `150` becomes `FFFFFFFF`;
- opcode18's private field `158` resets to one, not the tested source value77.

The saved-base decode path instead calls CopyFromBase at `1E2DAC`, returning to
`1E2DB1`. Its source is a serialized CGameEffectBase buffer, not necessarily a
live effect. Source ID/original duration/target ID become `FFFFFFFF/0/FFFFFFFF`.
A deliberate negative control passes a **known live original+8** to
DecodeEffectFromBase: its base fields still decode, but the caller remains
`1E2DB1`. Thus numeric sourceBase-minus-eight membership alone cannot distinguish
these operations. Retain the Decode caller exclusion as well as lifetime/class
validation; do not infer provenance just by pointer arithmetic or SPL resref.

`EEex_Opcode_Patch.lua:30` already excludes this same caller in its internal
OnCopy hook after the first resref copy at `1DCB20`. It examines `[RSP+38h]` and
passes RSI-minus-eight/RDI to EEex's internal bookkeeping. This is useful source
confirmation, not automatic propagation of our arbitrary Lua ownership map.

## Separate inert copy observer

`CBRPQCopyTransport.lua` uses the same validate/install API, with
`config.callbacks.copied` naming an existing global:

`copied(destination CGameEffect userdata, originalNumericPointer)`

The post-base-copy hook is `1DCCB0`, five original bytes `48 8B 4C 24 28`.
At that point RDI=destination, RSI=source CGameEffectBase, and `[RSP+38h]` is the
original CopyFromBase caller return. The callback receives RSI-minus-eight only
when that return is not imageBase+`1E2DB1`. Saved-buffer and live-base decode
controls both skip the callback while retaining normal native execution.

The module guards CopyFromBase's frame/body/return, excluding only the existing
EEex first-call patch at `1DCB20..1DCB24`, and guards the original Decode call and
return bytes `1E2DA3..1E2DB3`. Existing EEex copy bookkeeping is preserved. Reader
must still validate a known live source lifetime token, both actual classes,
and the proven copied-field relation before propagating metadata. Unsupported
class copies, foreign caller rewrites and allocation failures are not generalized
by this probe. No Copy hook is installed or wired into Runtime/Lab here.

## Offline verification and limits

The marshal and copy modules preserve volatile GPRs, XMM0..5 and flags around
Lua callbacks and the original watchdog helpers. They require the scoped
`CBRPQWatchdog.lua` adapter when watchdog is enabled; no ignore masks are widened.
Exact native-site validation occurs before patch preparation. A failed install
is non-retryable and has no claimed rollback. Composition owns callback error
containment, disabling/reporting, and native abort/reload reset policy.

The actual local EEex Lua preprocessor runs under offline LuaJIT. Generated x64
is assembled with local ML64 and executed in Unicorn using adversarial Lua and
watchdog helper doubles. Tests verify argument values, poisoned fifth-argument
neighbours, normal/error/skipped branches, register/flags/stack preservation,
watchdog snapshots and zero ignore masks. Native Marshal is separately executed
for60 empty/nonempty/filtered paths across version0/1/255; every path enters,
leaves and returns with the same original frame key. V1 is a context-path check,
not a claim of supported V1 saving or repair of its observed multi-record stride.

The independent copy probe has39 successful cases (13 live copies,13 saved
decodes,13 live-base decode negative controls). Allocation/free/resource/sound/
cookie services are explicit substitutes. Output:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-effect-copy-result.json`.

These are instruction and hook-generation checks, not actual EEex DLL execution,
combined in-engine interception, save/load acceptance, current-save migration,
or support for other executable/EEex versions.
