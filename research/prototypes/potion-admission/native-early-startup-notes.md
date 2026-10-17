# Early sprite-lifetime observation: bounded startup handoff

2026-10-09. Offline inspection and inert prototype only. No game, loader or DLL
was executed; no hooks were installed in a game and no installed files changed.

## Pinned evidence

- BG2:EE `Baldur.exe`, file/product version **2.7.3.0**, at
  `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`.
  SHA-256 `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- EEex source/package version **v1.3.0** (`EEex/EEex.tp2:3`). Sources below are
  from its `copy/EEex_scripts` and `loader` folders in that same captured tree.
- `InfinityLoaderDLL.dll` from `EEex/loader`, SHA-256
  `cf464444352e7279cc41ce5515728343f4703722023c10fc0d35ef80768363d1`.
  No file-version resource was reported. DLL findings below are static PE
  disassembly of this file, not an assertion that a captured upstream commit
  built it. DLL RVAs use its preferred base `0x180000000`; executable RVAs use
  `0x140000000`.
- Native function names are corroborated by the package's
  `loader/v2.7.3.0/bg2ee/function_names.db`.

## Two startup boundaries, and the correct global

`EEex_Main.lua` describes its invocation after the CALL selected by the
`Hardcoded_InternalPatchLocation` loader pattern. On the pinned executable,
`B918190000` matches SDL_main at RVA `13719C`; the configured `ADD -32` selects
the CALL at `13717C`. The subsequent native sequence is:

| Executable RVA | Operation |
|---|---|
| `13717C` | CALL `1366E0`; loader runs its Main Lua file at this boundary |
| `1371A1` | Allocate `CBaldurChitin` (`0x1918` bytes) |
| `1371B3` | CALL `CBaldurChitin::CBaldurChitin`, `130ED0` |
| `130F5D` | Constructor stores `this` in **`g_pBaldurChitin`, RVA `667548`** |
| `131028` | Constructor zeros `this+1090`, the game-object pointer |
| `1371BB` | SDL stores the constructed object in the distinct pointer at `667558` |
| `1371C2` | CALL `CBaldurChitin::Init`, `1331C0` |
| `1331F7` | CALL `CChitin::InitResources`, `419D50` |
| `419F5F` | InitResources tail-jumps to `dimmInit`, `4039C0` |
| `404F31` | dimmInit calls `uiDoFile` for the includes resource |
| `13354C` / `133559` | After resource initialization returns, allocate / construct `CInfGame` |
| `133574` | Store constructed `CInfGame` in `this+1090` |
| `1371F7` | CALL `CLUAConsole::LuaInit`; EEex's Initialized hook follows this CALL |

The actual global's eight file bytes are zero in the executable's `.data`.
The native tolua getter at `3F48C4` reads **`667548`**, independently confirming
the distinction from SDL's `667558`. The implementation uses a raw pointer
read of the actual global and does not depend on userdata-null conversion.

During early Modules loading the actual Chitin global is still zero. During
the normal includes/M_ stage Chitin exists, but `Chitin+1090` remains zero.
At the main menu, chargen, save/load and ordinary gameplay it is already too
late for this handoff. `AlreadyInitialized == false` is insufficient: EEex
sets that flag only after dispatching Initialized listeners. Likewise, a world
not currently initialized does not imply that no sprites previously existed.

The data sprite constructor requires a game object: `3422EE` loads the actual
Chitin global; `3422F5` reads `+1090`; `3422FC` dereferences game time at
`+3FA0`. **Do not generalize this to the default constructor.** Its
`1A3480..1A3C69` body has no direct game-pointer dependency, and its common
`CGameAIBase` constructor returns at `154A3E`. The game-pointer read at
`154A69` belongs to the separate `CGameAIGame` constructor. Consequently,
testing game-pointer-null only at late setup is not a proof that lifetime
observation began before every possible default sprite allocation.

## Modules invocation and file resolution

`EEex_Main.lua:81-105` first loads assembly support, native bindings, watchdog,
aliases, memory definitions and the configured startup-file list. Line 117
unconditionally calls `EEex_DoFile("EEex_Modules")`. The standard optional
module loop follows; `EEex_Active = true` is assigned only at the end.
`EEex_Modules.lua` is ordinary Lua configuration, not a deferred queue.

The DLL registers the formatted `{}DoFile` name at `2176B..217B7`, with native
callback `1CB50`. That callback reads its Lua string argument and directly calls
`3DC50`. This routine appends `.lua` and constructs, in precedence order:

1. `WorkingFolder/ScriptFolder/override/<name>.lua`, if present;
2. `WorkingFolder/ScriptFolder/<name>.lua` otherwise.

The pinned INI sets `ScriptFolder=EEex_scripts` (line 92). `3DF6C` calls the
imported `luaL_loadpathx`; `3DB8C` calls `lua_pcallk` synchronously with a null
continuation. There is no task, timer or later-module dispatch in this path.
`3DBC3..3DC26` prints a protected-call error and returns false internally, but
the outer `1CB72` returns **zero Lua results regardless of success**. Therefore
a caller cannot treat a returning `EEex_DoFile` invocation as a completion
receipt. Shadowed or failing scripts must leave the owned receipt absent.

The existing EEex installer copies the scripts into `EEex_scripts` and already
updates `EEex_Modules.lua` for a legacy option. A future tail installer could
preserve its existing configuration and add one owned early invocation, but
**this task adds no installer or configuration change**. It must resolve the
effective override path and preserve other mods' configuration, not blindly
edit the lower-priority file. A prior return/error in a modified Modules file
can skip the invocation; absence of the receipt must refuse later activation.

This is a bounded guarantee about the pinned native loader flow and the known
earlier startup files. The null-global check is not proof against arbitrary
replacement startup code that manually creates sprites or alters engine
globals before the observer is armed. No claim of universal startup ordering
across replaced loaders, altered early providers or other executable builds is
made.

## Inert module contract

`CBRPQEarly.prepare(api, parts, config)` captures capability identities only;
it performs no native read, assembly generation, patch or global publication.
`parts` contains the actual `spriteLifetime` module and optional watchdog helper.
`config` contains required `report` and optional `callbackPrefix` (default
`CBRPQ_Early_`) / `receiptName` (default `CBRPQEarlyReceipt`).

Explicit `bootstrap.arm()`:

- Requires `EEex_Active ~= true` and raw `ReadPtr(imageBase+667548) == 0`.
- Requires unchanged providers, vacant callback/receipt names and the actual
  SpriteLifetime module's six exact hook/vtable guards. Callback preflight uses
  a private API overlay, so failed preflight publishes no functions.
- Publishes the callback functions and installs all six descriptors with the
  existing watchdog wrapper and code-protection restoration.
- Rechecks phase, callback/method identities and registry health. Only after
  complete success does it return and publish a read-only receipt with the
  **same registry** and an opaque completion identity.

The receipt exposes:

- `registry`: the original allocation authority; no new registry or pointer
  adoption is performed at late setup.
- `completionIdentity`: one immutable opaque identity for this completion.
- `validateLate()`: returns true or raises. Requires the original published
  receipt/callbacks/providers, healthy unchanged registry, `EEex_Active == true`,
  actual Chitin pointer positive and raw `ReadPtr(Chitin+1090) == 0`.
- `attach(sinks)`: performs the same late checks and attaches exactly once;
  returns that same registry or raises. Required sinks are `onRetire`,
  `onContentsReset`, `onReset`, `report`. Functions are captured, so subsequent
  mutation of the caller's sink table does not replace lifecycle handling.

Before attachment, births, readiness, clears and destruction maintain their
ordinary allocation bookkeeping. There is no component-owned content yet, so
dependent cleanup notifications are harmless no-ops; failures remain in the
registry and prevent handoff. The test suite includes default construction
before attachment, which a new late registry would miss.

The root composition must finish its complete reversible preflight, call
`validateLate`/`attach`, then install its other observers while still inside
this late startup window. It must not reinstall SpriteLifetime observers,
reenable a failed registry, or manufacture a receipt after a missed early run.

After any installation attempt, failure is restart-only. Callback globals are
retained because a native hook might have been written before its provider
raised. No completion receipt is published, even if the sixth hook or
protection restoration fails. Native patch rollback is not claimed. Ordinary
Lua immutability rejects reassignment; explicit raw table tampering is detected
on late validation. This is integrity checking, not a security boundary against
arbitrary hostile code running in the same Lua state.

## Verification

`python -m unittest tests.test_potion_early_startup -q`: **19 tests passed**.
These compose the actual SpriteLifetime registry and descriptor generator with
explicit native-memory, code-patching and watchdog doubles. They verify early
and late phase guards, all-six completion, native rejection/partial failure,
namespace and callback replacement, immutable receipt, pre-attachment sprite
lifetimes, address reuse, cleanup failures and one-time sink binding. They do
not execute generated assembly or native loader code. Exact SpriteLifetime
instruction/ABI evidence remains in its existing focused native probe/tests;
the startup call ancestry above is static disassembly evidence.

Combined early-startup and SpriteLifetime suite with the captured EEex Lua
directory, executable and offline Python libraries supplied: **36 tests passed,
no skips**. This additionally reruns the existing pinned-site descriptor checks;
it still does not run the game or install any native hook.
