# Sprite allocation lifetime authority — inert offline prototype

`CBRPQSpriteLifetime.lua` closes the regeneration adapter's previously external
sprite-identity dependency for the pinned ordinary native construction/destruction
paths. It provides a pure registry and six inert hook descriptors. No hook,
global callback or JIT code is installed. Runtime/Lab/Core remain unchanged.
The observer must be composed before the sprites it will own are constructed;
it deliberately cannot adopt pre-existing pointers from an active game.

## Existing EEex facilities checked

Local EEex1.3 `EEex_Sprite_Patch.lua49–81` hooks the first base-constructor call in
both CGameSprite constructors and a destructor call, invoking compiled functions
`EEex::Sprite_Hook_OnConstruct/OnDestruct`. The inspected source
`EEex-f14a.cpp4740–4765` only inserts/removes entries in `exSpriteDataMap` and
removes UUID mappings. It does not invoke the commented Lua placeholders in
`EEex_Sprite.lua1074–1080`. Defining those placeholders would not supply a callback.
This is source evidence, not a claim that the installed DLL was rebuilt from the
retained source file.

`EEex_Sprite_AddLoadedListener` runs after effect-list unmarshalling through
`Sprite_Hook_OnAfterEffectListUnmarshalled`; the compiled path returns early for
`bNoUUID`. The UUID is restored/persisted through the EEEX_UUID creature local and
therefore is not an allocation lifetime. `EEex_GameObject_Hook_OnDeleting` uses
a game objectID for UDAux cleanup; it is not constructor coverage and does not
establish the identity of a new allocation before native loading processes effects.
None of these facilities alone supplies the required ordinary Lua lifetime API.

## Pinned native evidence

BG2EE2.7.3.0, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
All addresses below are RVAs. `probe_native_sprite_lifetime.py` validates the hash
and four source/normal-flow CFG cases without launching the executable.

| Boundary | Evidence |
| --- | --- |
| Default constructor1A3480 | Birth observer at entry, before any native memory read by the registry. All three CDerivedStats constructors1A35C4/1A35D0/1A35DC and equipped/timed list constructors1A391D/1A394F dominate ready1A3C50. That ready point dominates normal return1A3C69. |
| Data constructor341860 | Birth at entry. All three derived constructors3419E5/3419F1/3419FD and effect-list constructors341BF6/341C2A dominate ready34310E. Ready is immediately before the original Unmarshal CALL343114, which remains in place. |
| Constructor failure | CGameObjectArray::Add CALL3427FE can fail. The342810 virtual deleting-destructor call then precedes the jump to common return34379B. CFG verifies every path to return passes readiness or this destruction call. Publishing at the final epilogue alone would incorrectly inspect this destroyed object. The registry retires its pending token without ever publishing it. |
| Load-time effects | Unmarshal37A3E0 calls ClearMarshal at37A424, then ProcessEffectList at37B095 before returning to the data constructor. Readiness only at constructor return would miss possible native98 cache creation during load. |
| Initialized regenerated list | CDerivedStats ctor14EC10 calls native list ctor at14EF0F, zeroes counter at14EF14 and stores vtable58F528 at14EF21. The live member is sprite1120+derived8E8=sprite1A08. “Ready” means these relevant native data structures are initialized; creature data is still being unmarshalled. |
| Destruction | Sprite vtable598B68 points to scalar deleting destructor1A4630, which calls common343CC0 at1A463F. Entry343CC0 precedes original effect destruction and derived destructors3442C4/3442D0/3442DC. The live derived1120 destructor eventually clears regenerated8E8 at1A4109. The observer therefore cancels ownership before the embedded list dies. |
| Copy | Native Copy351240 allocates a fresh5388-byte sprite at3512C0 and invokes data constructor341860 at351310. It receives its own birth token regardless of any copied UUID, locals or resource names. |
| ClearMarshal |34FD30 invalidates contents and deletes timed/equipped effects, but does not free/reconstruct the enclosing sprite. Notify dependent content cleanup while preserving the allocation token. Destructor-internal ClearMarshal happens after the registry already retired that allocation, and is ignored. |

The CFG treats calls as returning and proves ordinary branch paths, not C++
exception unwinding. It neither runs whole constructors nor proves arbitrary
native extensions that bypass these constructors/destructors. Such unsupported
control transfers are not silently converted into pointer-based ownership.

## Registry API and composition

```lua
local registry = Lifetime.new({
    imageBase = imageBase,
    readPtr = readNativePointer,
    onRetire = function(spritePointer, oldToken)
        regenAdapter.onSpriteDestroy(spritePointer)
    end,
    onContentsReset = function(spritePointer, sameToken)
        regenAdapter.callbacks.clear(spritePointer + 0x1A08)
    end,
    onReset = function()
        regenAdapter.reset()
    end,
    report = reportError,
})
-- Supply registry.identity as RegenAdapter.api.spriteIdentity.
```

`registry.callbacks` supplies beginDefault/beginData, readyDefault/readyData,
destroy and clear. Bind them to the separately prepared descriptors before the
relevant allocations are created. `identity(pointer)` returns an opaque table
only after a matching observed birth and structural-readiness event; unknown or
pending allocations return nil. No address, objectID, UUID, userdata equality or
loaded-resource fingerprint creates a lifetime token.

Birth reads no uninitialized native fields. Readiness validates the exact sprite
and regenerated-list vtables. Destruction invokes onRetire while the old token is
still available, then retires it even if cleanup throws; native destruction will
continue. Duplicate births, unmatched readiness or mismatched native classes
halt/report the registry rather than inventing ownership.

The separately established game-reset observer must call `registry.reset()`.
It first calls onReset to clear dependent effect/cache state, then replaces token
epochs for all still-observed live allocations, without native reads. Reset is
not a destructor: retaining the birth records until their actual destructors
allows genuine surviving allocations to remain authoritative and prevents a
second constructor at the same address from being mistaken for the old object.
These maps/tokens are never marshalled or saved. Copies/load after reset follow
the native constructors normally. If reset cleanup fails, token rotation does
not occur and the registry halts; it does not claim successful cleanup.

Callbacks catch/report errors and return false, which does not alter native
execution. `identity` and `reset` throw when halted and must be protected by the
outer composition. None of the supplied cleanup/report functions may perform
new gameplay work; they are bookkeeping operations.

## Inert hook API and preservation

`Lifetime.prepare(api,config,watchdog)` returns
`{base,watchdog,descriptors}` using the same descriptor shape as RegenLifecycle:
`{key,address,restoreSize,stackMod,labels,assembly}`. It performs read-only byte
and vtable validation plus assembly generation. There is no install/JIT method.
The future composer must use scoped CBRPQWatchdog preservation when emitting the
six BeforeRestore hooks. Existing EEex constructor first-call hook sites are not
overwritten; original calls stay at their original addresses.

## Verification

-12 pure registry tests cover both constructors, deferred readiness, pending
  destruction, same-address reuse, content clear, independent copies, reset order,
  unknown pointers, failure reporting and class/capability mismatches.
-3 tests compose the actual registry with the actual RegenAdapter/Cache/Recovery
  modules and explicit byte-memory/service doubles. They verify loading-time
  lineage before constructor return, ClearMarshal cancellation with stable sprite
  identity, and destructor notification before token retirement.
-2 descriptor tests check inert preparation and every pinned byte/vtable conflict.
-1 native test method executes12 generated ML64/Unicorn trampolines (six sites,
  success/error), comparing all GPR/XMM/flags, original stack and replayed memory
  writes with the original native bytes. Lua/Watchdog calls are clobbering stubs.
-4 CFG/source cases verify the constructor, early destruction, load, copy and
  embedded-list facts above.

The combined regeneration and sprite-lifetime test suite currently passes108
methods with real local EEex preprocessing and optional generated-instruction
checks enabled. This closes the concrete observer/capability implementation,
while full Runtime/JIT composition, full save/load and live-game acceptance remain
separate work. No game process, EEex DLL, installation or save was executed/edited.
