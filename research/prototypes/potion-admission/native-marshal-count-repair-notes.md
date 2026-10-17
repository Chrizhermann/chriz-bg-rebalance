# Native Marshal count correction proof

October 9, 2026. Offline evidence only; no game, native DLL, hook installation,
installed-resource or save execution/writes. This adds a bounded repair proof
to the retained failures in `native-marshal-copy-observer-notes.md`; it does not
erase those failures or establish a general save-abort mechanism.

## Pinned inputs

BG2EE 2.7.3.0 `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`:
SHA256 `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
All native addresses are image-relative RVAs. Adjacent EEex 1.3 sources:

| File | SHA256 |
|---|---|
| `EEex_Sprite.lua` | `3f691b79757ada3a33de04e7370f1792228ad02ae141cb9f33c17e77e3717c61` |
| `EEex_Sprite_Patch.lua` | `e301b46770477cf29e3d39d6591a5a9fba4f3aeafa03c3dbfa75f7ef6bc13b7f` |
| `EEex_Assembly_x86-64.lua` | `eb7c8e9307b1a150f1cd57ac91b3c497d1102454f1495083c4395cc28e606d62` |

## Proven count/address relation

Let `oldNormal` be native EBX at the stock OverrideSize hook, `newNormal` the
eligible native list count * `108h` after all exporters, and `extra` the complete
metadata allocation size from the original EEex collector. A Lua composition
can return **`extra + newNormal - oldNormal`**, preserving the stock hook's saved
OriginalMarshalSize value. Its writer can call the original writer at
**`passedMemory + newNormal - oldNormal`**. Both adjustments are needed.

The stock size hook at `1E5384` stores old RBX then executes `add rbx,rax` before
the original JLE. Its error path instead zeros RAX. The stock allocation-call
hook at `1E538D` passes allocated buffer + old OriginalMarshalSize to the writer,
then restores the allocation pointer. Source: `EEex_Sprite_Patch.lua:232..309`.
The Number-return template uses `lua_tointegerx` and stores its full qword result
(`EEex_Assembly_x86-64.lua:1548..1557`); it does not impose an unsigned size return.

After correction, RBX is `newNormal+extra`. Native `movsxd rcx,ebx` at `1E538A`
passes that size to allocation. The normal copy loop at `1E5392..1E5443` walks
the current list using the original onlyTiming9/excludeTiming2 filters. `1E5452`
returns EBX through EAX. With the shifted writer, metadata begins immediately
after the final eligible normal records. Preserve a bounded positive total
within native signed 32-bit allocation arithmetic; a negative *delta return*
is valid, whereas a negative final allocation size is not.

Concrete successful negative case: old three normal records (`792` bytes), all
removed during an exporter, metadata `264` bytes. Lua returns `-528`; stock
64-bit ADD produces RBX `264`, JLE falls through, native allocates/returns `264`,
and the complete metadata is written at the buffer start. An initially empty
list that gains records also passes: the updated ADD flags, rather than the
old TEST's zero flag, determine the original JLE.

## Copied-instruction probe

`probe_native_marshal_count_repair.py` executes the copied native full V2
Marshal function in Unicorn. It runs the **unchanged** local EEex Lua
collector/writer/reader under LuaJIT, with bounded byte-memory services and a
foreign exporter/importer. The only proposed logic is the two pure Lua
arithmetic wrappers above. The native list mutation is an explicit exporter
service double. Allocation, Lua ABI dispatch and the two stock hook dispatches
are services. The hook's exact x64 `ADD RBX,RAX` executes in a small instruction
stub, followed by the unchanged native JLE; negative results are supplied as
the full signed-integer qword documented by the inspected return template.
This does not execute the installed Lua binding or native EEex DLL.

All **90 cases passed**: empty/unchanged, additions, removals, all removed,
timing changes crossing eligibility, and reorder at equal count; each with
filters `(0,0)`, `(1,0)`, `(0,1)`, `(1,1)`, `(7,11)`, and short/long foreign
metadata. Assertions cover original/final native count, allocation and returned
size, output pointer, normal record order and bytes, exact intact metadata,
no writes beyond allocation, post-allocation canaries, foreign data round-trip,
and exactly one collector/writer/importer invocation. The probe requires an
actual negative Calculate result among its cases.

Retained controls, with the same actual Lua serializer:

- An uncorrected append overwrites the metadata at the old normal boundary.
- An exception **after** the original collector returns leaves its positive
  `MemorySize` state. Stock call_error supplies RAX zero, so the allocation is
  only the old normal size. The subsequent original writer writes outside it.
  Reproduced: normal allocation `264`, retained metadata `264`, writer begins
  at offset `264` and clears/writes through offset `528`. A thrown validation
  error alone is therefore not a safe native fallback.

Output:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-marshal-count-repair-result.json`.

## Limits for composition

The proof assumes the final count and payload remain unchanged between the
wrapper's final snapshot and the native copy. It does not solve a later mutator,
reentrant Marshal clobbering EEex's global collector state, allocation failure,
invalid metadata, corrupted native list/count, integer overflow, V1 serialization,
or arbitrary foreign replacement of stock hooks. Any exception fallback must
leave coherent collector/writer state; the root composition owns that policy.
It must preserve other exporters' metadata and normal native filter semantics.

No save/export module was changed by this evidence task. The earlier count-drift
diagnostic remains a genuine unsupported-state test until the composition is
updated and independently exercised. Offline success is not live save/load
acceptance or current-save safety.
