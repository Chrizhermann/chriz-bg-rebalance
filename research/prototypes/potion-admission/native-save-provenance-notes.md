# Linked potion save identity: bounded evidence and remaining integration

## Latest composition boundary

The inert Persistence/Linked/Runtime modules now compose all three EEex Lua
wrappers with the native marshal/unmarshal/copy observers. Extended composition
requires the completed `CBRPQEarly.lua` receipt and reuses its sprite registry;
creating a fresh registry during M_ setup missed earlier default sprites and
could reject their save before foreign exporters ran. The new connected test
covers an actor born before late setup, a save with no owned effect, and a
foreign exporter. See `native-early-startup-notes.md` for the exact startup proof.

`SaveExport.invalidate()` also handles a later policy failure after metadata
sizing but before the writer starts. It verifies the same pending collection,
placeholder and EEex numeric encoder, then changes the owned version1 to0
without changing encoded width or allocation size. Fresh import rejects the
invalid ownership marker while preserving foreign handler data. It retains
native serialization contexts until their observed return; failure is not a
reason to clear live native frames or pending allocation bookkeeping.

This does not provide native rollback for a broken context/collector or an
error after writing has started. The focused Lua/buffer tests demonstrate the
one-byte marker change and foreign-handler continuity, not a successful native
save/load. The first direct-only potion trial does not install these wrappers.

October 9, 2026. No game process, EEex DLL, save or installed resource was
executed/modified. `probe_native_potion_save.py` runs copied instructions from
BG2EE 2.7.3.0, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
The associated EEex source reference remains InfinityLoader commit
`f14a00527286f819b8034411bc92ca719cfe3c86`, not a rebuilt/proven-identical DLL.

## Native marshal and restore

`CGameEffectList::Marshal` at RVA1E50E0 receives list/output/version in RCX/RDX/R8,
an only-timing9 switch in R9, and an exclude-timing2 switch as the fifth argument.
The V2 path counts and copies eligible entries in linked-list order at
1E5302–1E5382 and1E53B0–1E5440. It copies each runtime object's bytes+08..+10F,
exactly0x108 bytes. It does not filter by `done`, current world time, source or
opcode. An ordinal in the **unfiltered** live list is therefore not always an
ordinal in the saved list.

The inspected `CGameSprite::Marshal` call at361767 passes version1 and
exclude-timing2=1. The branch at36171E chooses only-timing9=0 or1. A save metadata
exporter must know the actual call's filters, not infer them from the usual save
case or from `EEex.IsMarshallingCopy()`.

Native `CopyFromBase`1DCAF0 restores individual fields. It does not restore all
the bytes that Marshal wrote: runtime+50..53 and+D4 onward are not copied back.
It uppercases/zero-pads resource operands at+30,+70,+78, but copies sourceRes+94
verbatim. The helper at3FF880 copies eight bytes; normalization is400030.
Pointer, source actor ID, done, original duration and class-private tail state
are not durable identities.

The copied-instruction probe passes12 cases: empty and two reordered mixed
timing lists under all four filter combinations. It checks exact serialized
bytes/order, including Done-marked inputs, then executes real CopyFromBase for
all selected records. Heap allocation, memset and security-cookie services are
explicit substitutes. It is not native EEex save/load acceptance.

## EEex integration implications

Inspected `EEex_Sprite_Patch.lua`184–206 wraps the sprite's list-Marshal call;
232–272 invokes Lua export while computing extra size. The Lua exporter precedes
normal effect copying. The write-extra hook278–300 runs after buffer allocation,
not after copying every normal effect. Other handlers must not mutate/reorder
the relevant list between snapshot and serialization without detection.

In the inspected C++ `Override_Unmarshal`4935+, ordinary V2 entries decode and
AddTail in serialized order. An X-BIV1.0 block invokes the Lua importer instead
of becoming an effect. The later post-unmarshal hook updates EEex's UUID local.
Matching by a projection's relative occurrence, rather than a global list
ordinal, avoids unrelated UUID/local entries changing that occurrence.

`EEex::IsMarshallingCopy()`393 returns `bStripUUID`. It is not a substitute for
the native timing-filter arguments. Skipping all temporary-copy metadata without
understanding the caller could discard potion identity from a legitimate copy.

## Pure metadata candidate now implemented

`CBRPQSaved.lua` accepts the exact ordered serialized subset supplied by the
context adapter. It exports an owned item's source/key plus the occurrence within each
full stable native-field projection, counting identical unowned effects too.
The projection includes expiry and native source/caster metadata and normalizes
only the proven restore transformations above. It is hex encoded, with no
binary NUL in EEex marshal strings. No pointer is serialized.

Restore validates the whole group count and each owner against a supplied
current-manifest verifier, returning a new lifetime map only after validation.
Six LuaJIT tests cover identical foreign/potion spell effects, duplicate counts,
changed data, normalization, filtered-out originals and malformed metadata,
including a65536-record roundtrip. The bound follows native signed byte capacity,
not an arbitrary unsigned-WORD list limit.
These tests do not exercise an EEex serializer or the game's load path.

## Actual EEex Lua serialization and final snapshot

`tests/test_potion_saved_eeex.py` now runs the installed EEex1.3 Lua
size/write/read functions unchanged, using bounded byte-buffer substitutes for
native memory operations. The metadata survives sparse owned occurrences across
the255/256 numeric-width boundary, another handler's data and EEex's missing-
handler fallback/re-export. This is Lua serialization evidence, not a native
game save/load or proof that fallback metadata remains valid while the component
is absent and effects continue changing.

A retained counterexample establishes why an ordinary exporter is insufficient:
another exporter swaps two byte-identical effects after the ownership snapshot.
The bytes and group counts still match, but relative ownership is wrong. The
test deliberately reproduces that wrong attribution; it is not accepted behavior.

`CBRPQSaveExport.lua` implements an inert composition correction. Its exporter
returns an owned placeholder. Its `calculate` wrapper lets the original EEex
routine finish every exporter, then reads the current ordered list under the
exact native timing filters, fills only that placeholder and recalculates the
allocation size using the original EEex sizing function. It returns extra bytes
plus the change in normal-effect bytes. Its paired `write` wrapper shifts the
footer pointer by that same change: allocation-only correction is insufficient.
Other exporters run
once; their data stays unchanged. It neither registers a handler nor replaces
an EEex function on load.

`probe_native_marshal_count_repair.py` executes the copied native Marshal with
the actual EEex Lua collector/writer/reader in90 cases: additions, removals,
all removed, initially empty, filter eligibility changes and noncanonical native
boolean arguments. A negative size correction remains valid in the native64-bit
ADD. Retained negative controls reproduce overwritten metadata from a stale
footer address and out-of-bounds writes when a post-collector Lua error leaves
EEex's nonzero MemorySize paired with the native error-path RAX0.

`CBRPQMarshal.lua` and its guarded transport now expose the exact version/filter
and normal byte count with balanced native entry/exit identities. Both wrapper
functions must be installed together. They still rely on the pinned writer and
no later hook mutating the list between
the final snapshot and native copy. Recursive serialization is diagnosed because
the inspected EEex collector itself uses global per-sprite state. An error is
not a save-abort/rollback mechanism. Recoverable metadata-only errors now emit
one explicit invalid marker, retain old owned-handler tables in its `previous`
field, preserve foreign handler data, recalculate consistent allocation/footer
sizes, and disable potion ownership. They do not silently choose stale metadata.
Corrupt context/collector state and native allocation failures remain outside
that recovery guarantee.

## Restore before foreign importers and native copies

`CBRPQSavedBinary.lua` bounds every read of the exact X-BIV1.0 interval before
the original EEex importer runs. It skips foreign64-bit values without rounding
them through Lua doubles and validates our own table/keys/counts. The normal
effect count and footer padding must match the actual native input interval.

`CBRPQUnmarshal.lua` records both input bounds and ordered pre-existing effect
lifetime identities; importing into a nonempty list does not invent new owners
for its old prefix. Its transport observes the pinned sprite and projectile
callers separately, including unowned sentinels. `CBRPQSaveImport.lua` restores
validated native bindings before ANY foreign importer can reorder identical
effects or copy/remove an owned original. An invalid ownership marker or schema
disables ownership but lets stock and foreign importers proceed. Binary/context
corruption still diagnoses rather than claiming native load rollback.

`CBRPQCopyTransport.lua` observes completed CopyFromBase and excludes the exact
DecodeEffectFromBase caller. `Native.copyLinked` propagates only a currently
owned source lifetime, verifies constructor/class/source/caster fields, and
creates a fresh destination identity. The actual EEex serializer tests include
foreign identical-effect swaps and an importer that copies then removes its
owned original. Native decode/construction/list operations remain doubles there.

Still required before enabling linked persistence:

- Compose the implemented context/import/copy/lifetime modules without clearing
  an in-flight native context when ownership is disabled.
- Native context wiring and guarded registration of both export wrappers;
  establish the remaining interval through normal copying, including hook conflicts.
- Deliberate handling of saves lacking provenance, changed component policies,
  missing-handler fallback, character export, actor copies and failed loads.
- Saving with surviving dose/cast delivery cannot assume native messages are
  persisted; a bounded unsupported-case response is needed before activation.

The module is inert and unregistered. No current-save migration or native save
safety is claimed. It does not infer potion ownership from a shared SPL name.
