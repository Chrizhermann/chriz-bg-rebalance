# Unmarshal input interval and import identity boundary

October 9, 2026. Read-only native/source research and inert hook preparation.
No game, native DLL, installation or save execution. Executable and EEex Lua
inputs are the same pinned BG2EE2.7.3.0/EEex1.3 files documented in
`native-marshal-copy-observer-notes.md`. Executable SHA256:
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.

The C++ source is the captured
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\EEex-f14a.cpp`,
official InfinityLoader commit `f14a00527286f819b8034411bc92ca719cfe3c86`.
It is source evidence, not a rebuilt or proven-identical installed DLL.

## Actual destination list and input interval

The native effect-list Unmarshal **entry** is RVA `1E88E0` (not its internal
instruction at `1E89C0`). Scanning executable sections for direct E8 calls finds
exactly two callers, at `37AA92` and `22BCA6`. The mapped image has no absolute
pointer reference to the entry VA. This inventory does not rule out dynamically
constructed function pointers, EEex/Lua calls, or other DLL callers.

The sprite caller is `CGameSprite::Unmarshal` at `37A3E0`:

| Value at native call `37AA92` | Preparation |
|---|---|
| list (RCX) | `37AA8B: lea rcx,[rbx+4A00h]` |
| data (RDX) | CRE buffer R12 + DWORD[R12+2C4h] |
| size (R8D) | DWORD[R12+2C8h] times `108h` for V2, `30h` for V1 |
| sprite (R9) | RBX |
| version, fifth byte argument | byte[RBX+58Bh] != 0, written at caller RSP+20h |

This is directly `sprite.m_timedEffectList`, not a temporary list awaiting
transfer. Earlier `37A424` calls `ClearMarshal(34FD30)`: native code at
`34FF40..34FF54` destroys old timed effects and `34FF5B..34FF62` clears the list.
That supports an empty list in the inspected ordinary path. The actual entry
baseline must still be captured/validated, because foreign hooks may insert
effects; do not infer original serialized ownership from an assumed empty list.

The native serialized actor-copy path is also covered by this caller:
`CGameSprite::Copy(351240)` calls sprite Marshal at `3512B6`, then constructs
a new sprite at `351310` via `CGameSprite::CGameSprite(341860)`. Constructor
`343114` calls `Unmarshal(37A3E0)`, reaching the same `37AA92` list call.
`EEex.IsMarshallingCopy()` / bStripUUID is not an import-interval substitute and
must not blanket-disable this route.

The other native call, `22BCA6`, belongs to `CProjectileArea::CreateObject`:

- list=RBX+78h; data=RBP; size=R14D;
- sprite=null (R9=0);
- version=1, written at caller RSP+20h by `22BCA1`.

This is a nested/unowned sentinel observation, not support for potion ownership
on an area projectile. Its context prevents an unrelated invocation from being
mistaken for a pending sprite import.

## Source order of normal records, metadata and later callbacks

`EEex-f14a.cpp:4935` replaces effect-list Unmarshal. For each ordinary V2 record,
it calls DecodeEffectFromBase and **immediately AddTail's the returned pointer
to this list**. On an X-BIV1.0 block it calls
`EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal(sprite, baseMemory)`, obtains
the number of consumed `108h` records and advances the same input loop.
The V2 branch does not invoke each effect's OnLoad; the V1 branch does.

For a correctly sized stock footer-last stream, all normal saved records have
therefore been linked before ReadExtra starts. To establish that condition for
the actual invocation, retain `(data,size,list,sprite,version)` and require:

- V2, matching sprite/list, safe pointer arithmetic and bounded input size;
- metadata pointer within the input on a `108h` record boundary;
- complete bounded parse and `metadataPointer + consumedRecords*108h == data+size`;
- no ambiguous duplicate ownership block or unsupported earlier metadata block;
- actual normal-list baseline/order consistent with the serialized prefix.

The C++ loop otherwise allows metadata before later normal entries. A callback
name alone does not prove footer-last layout. Missing caller context (including
direct external DLL/Lua invocation) must not inherit an older sprite context.

`EEex_Sprite.lua:1347` parses the metadata. At lines1447–1450 it invokes each
handler's importer immediately, in **serialized handler order**, through
EEex_Utility_TryIgnore. A later importer may swap, delete, copy or otherwise
change the native list. An ownership handler cannot assume it runs first or
last. Matching relative occurrences after all handlers can misattribute two
byte-identical objects that were swapped earlier.

After the native list call returns, the existing EEex hook at `37AA92` calls
`Sprite_Hook_OnAfterEffectListUnmarshalled` (`EEex-f14a.cpp:4783`). It updates UUID
locals then invokes Lua UUID callbacks and every LoadedListener
(`EEex_Sprite.lua:1604`). Those listeners can mutate the list as well. With
bNoUUID enabled, the C++ function returns before that Lua hook, so a loaded
listener is neither a universal completion notification nor an immutable
snapshot of originals.

The lead's proposed composition avoids importer-order dependence: at exact
ReadExtra entry, validate the native input interval/footer-last condition,
capture normal-list lifetime identities in serialized order, and use a bounded
read-only parser to obtain only this component's metadata. Resolve and bind
that metadata atomically **before** invoking the original EEex reader/handlers.
Existing copy/destructor observers can then preserve/retire identities during
other handlers. Never dereference a removed snapshot object; use fresh live
enumeration and independent lifetime tokens. Handler errors, changed input,
incompatible metadata or absent context must not produce guessed ownership.
Parser, binding, and Runtime/Lab composition are outside this transport module.

## Inert caller observer

`CBRPQUnmarshalTransport.lua` exposes `validate(api,config,watchdog)` and
`install(api,config,watchdog)`. Existing global callback names are supplied in
`config.callbacks.enter` and `.leave`:

- `enter(callerFrameRSP, listPtr, dataPtr, byteSizeDWORD, spritePtr, versionByte)`
- `leave(callerFrameRSP)`

All arguments are numeric. Frame is the native **caller** RSP, before/after the
existing CALL wrapper, not the called function's entry RSP. Sprite and projectile
contexts can nest; composition owns the stack, empty/unowned sentinels, duplicate
metadata policy, failures and abnormal-exit resets. No list or userdata is read
by the observer itself.

| Site | Restored bytes | Captured context |
|---|---|---|
| sprite enter `37AA8B` | `48 8D 8B 00 4A 00 00` (7) | frame, RBX+4A00, RDX, R8D, RBX, byte[frame+20] |
| sprite leave `37AA97` | `0F B7 83 6A 05 00 00` (7) | frame |
| projectile enter `22BCA1` | `C6 44 24 20 01` (5) | frame, RCX, RDX, R8D, zero, one |
| projectile leave `22BCAB` | `0F B6 47 1B 48 8B B4 24 80 00 00 00` (12) | frame |

The sprite after-observer runs after stock EEex's UUID/loaded callbacks have
completed or been skipped. Both native CALL locations are preserved, including
the existing EEex sprite call wrapper at `37AA92`; the effect-list entry jump to
the C++ override is also untouched. Guards pin caller argument setup and each
observer site. They deliberately do not authenticate arbitrary third-party
replacement of EEex's existing call/entry patch slots.

The observer preserves volatile GPRs, XMM0..5 and flags, retains watchdog checks
without widened ignore masks, and fails before patching on native-site collision.
Partial patch failure has no claimed rollback or retry. Loading the file only
returns the module; nothing registers or installs itself.

## Offline verification

`test_potion_unmarshal_transport_preprocessor.py` runs the actual EEex Lua
preprocessor. `test_potion_unmarshal_generated_trampoline.py` assembles and
executes the generated code with clobbering Lua/watchdog service doubles; all four
sites, V1/V2 values and callback success/error paths preserve the displaced
native instructions' state and exact six entry arguments. Separate copied-native
instruction cases execute both callers' argument preparation, including native
version normalization, byte count and fifth stack byte. Static inventory checks
the two direct callsites and their original targets.

These tests do not execute EEex's native DLL override, a complete actor load/copy,
or a real save. Current-save safety and final linked-potion persistence acceptance
remain unproven.
