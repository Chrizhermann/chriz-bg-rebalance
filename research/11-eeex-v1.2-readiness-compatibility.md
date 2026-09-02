# 11 — EEex v1.2 ambient-readiness compatibility correction

**Date:** 2026-09-02
**Status:** first v1.2 live pass diagnosed and corrected a bad timer-method assumption;
fresh-process gameplay rerun pending
**Scope:** component 121 clock, tick listener, and install-time EEex detection only

## Result

Component 121 now targets EEex v1.2.0 first. Its current runtime contract is:

```lua
local ticks = EngineGlobals.g_pBaldurChitin.m_pObjectGame
    .m_worldTime.m_gameTime
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

The separately maintained binding documentation describes
[`timer:GetCurrentTime()`](https://github.com/Bubb13/EEex-Docs/blob/master/source/EE%20Game%20Lua%20Functions/timer/timer_GetCurrentTime.rst)
and the paired
[`game:GetWorldTimer()`](https://github.com/Bubb13/EEex-Docs/blob/master/source/EE%20Game%20Lua%20Functions/game/game_GetWorldTimer.rst)
documents a game/timer relationship. That documentation does not establish that the embedded
`m_worldTime` userdata reached through `EngineGlobals` has the method. EEex v1.2's own
[`B3TimeStep.lua`](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/B3TimeStep.lua)
reads and writes that userdata's `m_gameTime` field directly. The Infinity Engine timing formula is
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

That copy supplied the exact v1.2 runtime transplanted into the disposable SCS/SR laboratory.
Its source tree itself was not modified.

The complete named runtime gate was also checked against that v1.2 tree. Explicit v1.2 Lua
definitions exist for the deferred and started-action listeners, game-object lookup, sprite
local/state access, conditional evaluation, pointer-list iteration, quick-list reset and
marshal handlers, resource demand, effect application, stack management, and queued response
actions. `EEex_GetUDAux` is the v1.2 alias for `EEex_GetUserDataAuxiliary`; `EEex_BAnd` is an
engine binding used throughout the official v1.2 scripts. The remaining
`Infinity_GetInCutsceneMode` global belongs to the base EE Lua surface and was independently
observed in the installed live probe. Thus all 16 globals capability-gated by the runtime
have current-source or direct installed evidence.

### 2026-09-02 live v1.2 correction

The approved disposable target was
`C:\Games\Baldur's Gate II Enhanced Edition modded - CBR Ambient Readiness v1.2 Test`.
It combined the audited SCS/SR EET snapshot with an exact 107-file transplant of the v1.2
runtime, then installed components 120 and 121 at the WeiDU tail. A fresh InfinityLoader
process loaded the staged save in `AR3000`.

A read-only remote diagnostic proved:

- `type(m_worldTime.GetCurrentTime)` was `nil`;
- direct `m_worldTime.m_gameTime` returned `74776073`;
- the userdata metatable exposed `m_gameTime` and its reference getter, but no timer method;
- component 121 selected the deferred listener but had already set both
  `ambient_faulted=1` and `urgent_faulted=1`; and
- the component therefore touched no slot, effect, or urgent queue.

The exact lab `EEex_scripts/B3TimeStep.lua` has SHA-256
`8B500C8901344A9B22B7959250C247401EC2C68F0978AB019A2F483BF16CDFAC` and reads the direct
field at lines 48-53. The loaded `EEex.dll` retained the donor hash
`B6C7C98804360CB46531DB75AB9608E378FD403D60C29C0E29946A60A334276A`.
Full session evidence is preserved outside the repo in
`C:\Users\chris\Documents\Codex\2026-09-02\cbr-ambient-v12-98d116c\live-v12-clock-diagnostic.md`.

## Root cause and invalidated evidence

There were two successive unsupported clock assumptions:

1. commit `58f124c` added `EEex_GameState_GetTime` to the fake simulator while the probe
   guessed that name and `Infinity_GetGameTime`, then fell back to `os.clock()`;
2. commit `0c89940` promoted the guessed name into the production ambient runtime; and
3. commit `fee4c3b` retained it as a required capability gate.

The 2026-08-31 correction removed those invented globals but then treated the published
`timer:GetCurrentTime()` page as proof of a method on the embedded `m_worldTime` userdata.
No live v1.2 method-surface check had established that inference. The first v1.2 run disproved
it directly; the official v1.2 `B3TimeStep.lua` had already provided the correct field access.

Neither guessed name appears in the official v0.11, v1.0, or v1.2 GameState modules. In the
2026-08-30 probe, both were absent and `os.clock()` supplied every purported “engine time.”
Accordingly, all exact latency numbers in `research/10-ambient-readiness-spike.md` are
withdrawn. Event ordering and separately observed non-clock data shapes remain evidence, but
the old spike did not validate timed retry, expiry, or rearm behavior.

The later v0.11 disposable-lab gameplay pass showed the practical result: eligible nearby
casters received no component-121 effects. The runtime's required-clock gate disabled it
before gameplay mutation. That failed pass is diagnostic evidence, not acceptance.

## Implementation correction

- The selected v1.2 production/probe path uses the source- and live-proven direct world-time
  field. The legacy branch uses the same field; only listener and marshal-export behavior
  differ by capability.
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

The regression was first changed to model a v1.2 world-time userdata with `m_gameTime` but no
`GetCurrentTime` method. Before the production fix it failed exactly as the live game did:
zero ambient applications and both feature fuses faulted. The minimal production change then
made both listener modes read the direct field. The fake method was removed from the default
simulator surface, and source tests now reject it in both production and probe code.

After the implementation change:

```text
python -m unittest tests.test_ambient_readiness_listener tests.test_ambient_readiness_installer -v
68 tests passed

python -m unittest discover -v
228 tests passed in 237.973s

.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
TP2 parsed successfully with WeiDU 24900
```

`git diff --check` also passed. Automated evidence does not replace the pending fresh-process
gameplay pass.

## Remaining acceptance boundary

The first v1.2 gameplay attempt is a diagnosed failure, not acceptance. The corrected runtime
is now placed in the same approved disposable lab with the game fully closed. Start a fresh
InfinityLoader process, confirm the raw field advances at 15 ticks per gameplay second, and
rerun the urgent/ambient matrix. Because component 121 is already installed at the tail,
do not uninstall it and do not rely on `--force-install-list 121`, which would be a silent
no-op. For this disposable lab, use a recorded direct-override hotfix of only
`override/M_CBRRDY.lua`, preserving the prior bytes and proving `WeiDU.log` unchanged. Fresh
installs receive the corrected runtime through component 121 normally. The old append-only
callback and sticky fault state must not be hot-reloaded into the rerun.

That lab-only deployment is now complete. With both game processes absent, the installed
runtime changed from SHA-256
`6835A6FD80B8716D357A5D2923F23DB8AF4001E8A53646FD0E55D588A88AC15D` to
`42191F6215E4DACD53CB9D998849A0BB35A018E8BCA2300138D89FBA7AE075E5`; `WeiDU.log`
remained byte-identical at
`6C988DE31A47812C692EEFBB7108D3B7A826FDD9CEA3DFC29A546C5A7132C2C0`. The patched file
parsed with the lab's bundled Lua interpreter. Gameplay acceptance is still pending the
fresh process and user-visible test.

Older EEex support remains second priority. A later capability adapter now selects
`EEex_Opcode_AddListsResolvedListener` plus direct `m_worldTime.m_gameTime` only when the
deferred listener is absent. It has official-source and fake-runtime coverage, including
repeated synchronous callbacks and v0.11's table-only marshal exporter contract, but no
corrected old-version live pass. The v1.2 stage above remains first.
