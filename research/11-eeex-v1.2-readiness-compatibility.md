# 11 — EEex v1.2 ambient-readiness compatibility correction

**Date:** 2026-08-31
**Status:** official-source and automated-test evidence complete; v1.2 gameplay acceptance
pending
**Scope:** component 121 clock, tick listener, and install-time EEex detection only

## Result

Component 121 now targets EEex v1.2.0 first. Its current runtime contract is:

```lua
local ticks = EngineGlobals.g_pBaldurChitin.m_pObjectGame
    .m_worldTime:GetCurrentTime()
```

The return value is raw world-time ticks. Component 121 converts gameplay seconds to ticks
with `seconds * 15` before comparing ambient expiry, the six-second early-removal tolerance,
the two-second urgent retry, or the six-second contact rearm. Its primary high-frequency hook
is `EEex_Opcode_AddDeferredListsResolvedListener`.

There is no `EEex_GameState_GetTime` or `Infinity_GetGameTime` dependency and no
`os.clock()` fallback. If the world-time userdata chain or value is unavailable, both
runtime layers fail closed before an effect, slot debit, or queued cast can occur.

## Official current-version evidence

The [official v1.2.0 release](https://github.com/Bubb13/EEex/releases/tag/v1.2.0) was labeled
Latest when rechecked on 2026-08-31. Its release notes introduce
`EEex_Opcode_AddDeferredListsResolvedListener` as the at-most-once-per-AI-tick alternative
to the legacy listener. The tagged
[`EEex_Opcode.lua`](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Opcode.lua)
defines that function and calls the older listener legacy.

The official binding documentation exposes
[`timer:GetCurrentTime()`](https://github.com/Bubb13/EEex-Docs/blob/master/source/EE%20Game%20Lua%20Functions/timer/timer_GetCurrentTime.rst)
on the world timer; the paired
[`game:GetWorldTimer()`](https://github.com/Bubb13/EEex-Docs/blob/master/source/EE%20Game%20Lua%20Functions/game/game_GetWorldTimer.rst)
documents the containing game/timer relationship. EEex v1.2's own
[`B3TimeStep.lua`](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/B3TimeStep.lua)
reads the same timer's `m_gameTime` field directly. The Infinity Engine timing formula is
`Gametime(ticks) + 15 * Duration(seconds)`, establishing the 15-tick conversion
([IESDP EFF timing](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/eff_v1.htm#effv1_Header_0xC_0)).

Do not substitute `Infinity_GetGameTicks()`: it is a separately scaled UI/engine helper and
is not the raw world-time value used for duration comparisons.

## Local v1.2 evidence

Read-only inspection of
`C:\Games\Baldur's Gate II Enhanced Edition modded - Copy - Copy` found:

- `EEex/EEex.tp2` declares `VERSION ~v1.2.0~`;
- Main is `LABEL ~B3-EEex-Main~ DESIGNATED 1`;
- LuaJIT is `LABEL ~B3-EEex-LuaJIT~ DESIGNATED 8`;
- `EEex/copy/EEex_scripts/B3TimeStep.lua` reads `m_worldTime.m_gameTime`;
- `EEex/copy/EEex_scripts/EEex_Opcode.lua` defines the deferred listener; and
- `EEex.dll` is 1,282,048 bytes with SHA-256
  `B6C7C98804360CB46531DB75AB9608E378FD403D60C29C0E29946A60A334276A`.

That copy is useful source/runtime evidence, but it has no SCS/SR and cannot by itself run
component 121's gameplay matrix. It was not modified.

The complete named runtime gate was also checked against that v1.2 tree. Explicit v1.2 Lua
definitions exist for the deferred and started-action listeners, game-object lookup, sprite
local/state access, conditional evaluation, pointer-list iteration, quick-list reset and
marshal handlers, resource demand, effect application, stack management, and queued response
actions. `EEex_GetUDAux` is the v1.2 alias for `EEex_GetUserDataAuxiliary`; `EEex_BAnd` is an
engine binding used throughout the official v1.2 scripts. The remaining
`Infinity_GetInCutsceneMode` global belongs to the base EE Lua surface and was independently
observed in the installed live probe. Thus all 16 globals capability-gated by the runtime
have current-source or direct installed evidence; gameplay behavior remains pending.

## Root cause and invalidated evidence

The missing API was local invention, not version drift:

1. commit `58f124c` added `EEex_GameState_GetTime` to the fake simulator while the probe
   guessed that name and `Infinity_GetGameTime`, then fell back to `os.clock()`;
2. commit `0c89940` promoted the guessed name into the production ambient runtime; and
3. commit `fee4c3b` retained it as a required capability gate.

Neither guessed name appears in the official v0.11, v1.0, or v1.2 GameState modules. In the
2026-08-30 probe, both were absent and `os.clock()` supplied every purported “engine time.”
Accordingly, all exact latency numbers in `research/10-ambient-readiness-spike.md` are
withdrawn. Event ordering and separately observed non-clock data shapes remain evidence, but
the old spike did not validate timed retry, expiry, or rearm behavior.

The later v0.11 disposable-lab gameplay pass showed the practical result: eligible nearby
casters received no component-121 effects. The runtime's required-clock gate disabled it
before gameplay mutation. That failed pass is diagnostic evidence, not acceptance.

## Implementation correction

- The selected v1.2 production/probe path uses the documented world-timer method with no
  silent rescue clock. A later legacy branch deliberately uses the separately source-verified
  direct field only when the deferred listener is absent.
- All duration seconds are converted to raw ticks at the comparison boundary.
- v1.2's deferred listener is primary; the legacy listener is not registered on the current
  path.
- The simulator models the nested `EngineGlobals` world timer and raw ticks instead of
  inventing public clock globals.
- A missing world timer is exercised and must leave effects, memorized slots, and the action
  queue untouched while each layer trips its independent fault fuse.
- The installer no longer assumes EEex component 0/1. `M___EEex.lua` proves the autoload
  bootstrap; the runtime proves the specific capabilities it needs. Component 121 itself
  does not use a LuaJIT-only primitive, so it does not impose a separate LuaJIT component
  predicate.
- The generated manifest records target v1.2.0, the deferred listener, raw engine ticks, and
  15 ticks per second. This is target metadata, not a claim of completed live acceptance.

`expected_expiry` in the marshaled ambient ledger now stores raw engine ticks. The ledger
schema remains version 1 because the old production runtime required the nonexistent clock
global in its registration gate: on a real EEex process it registered neither gameplay
callbacks nor marshal handlers and therefore could not create or save a version-1 ledger.
The failed disposable-lab pass confirmed that inert path. There is consequently no real-save
seconds-based ledger to migrate. The later legacy fallback preserves the same raw-tick unit,
so no schema bump is needed; its separate evidence is recorded in
`research/12-eeex-legacy-readiness-fallback.md`.

## RED/GREEN evidence

The focused tests were first changed to reject the fake clock surface, require the nested
v1.2 timer and deferred listener, exercise raw-tick conversion, require no mutation when the
timer is missing, and reject hardcoded EEex component predicates. Before the production fix,
those tests failed for the expected missing-v1.2 and lingering-invented-API reasons.

After the implementation change:

```text
python -m unittest tests.test_ambient_readiness_listener tests.test_ambient_readiness_installer -v
61 tests passed

python -m unittest discover -v
221 tests passed

.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
TP2 parsed successfully with WeiDU 24900
```

`git diff --check` also passed. These results are offline/source verification; they do not
replace the pending v1.2 gameplay pass.

## Remaining acceptance boundary

No game was installed, launched, or modified while making this correction. Before calling
component 121 compatible in gameplay, use one explicitly approved disposable SCS/SR test
copy running EEex v1.2, start a fresh InfinityLoader process, confirm the raw world timer
advances at 15 ticks per gameplay second, and run the urgent/ambient matrix in the live
checklist. The old v0.11 callback and sticky fault state must not be hot-reloaded into that
test.

Older EEex support remains second priority. A later capability adapter now selects
`EEex_Opcode_AddListsResolvedListener` plus direct `m_worldTime.m_gameTime` only when the
deferred listener is absent. It has official-source and fake-runtime coverage, including
repeated synchronous callbacks and v0.11's table-only marshal exporter contract, but no
corrected old-version live pass. The v1.2 stage above remains first.
