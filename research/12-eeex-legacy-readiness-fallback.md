# 12 — EEex legacy ambient-readiness fallback

**Date:** 2026-09-02
**Status:** EEex v1.2 remains the primary target; v0.11.0-alpha/v1.0.0 fallback has
official-source, focused simulator, and full-suite evidence; corrected legacy gameplay
acceptance remains pending
**Scope:** component 121 clock, lists-resolved listener, and marshal-export compatibility

## Decision

Component 121 keeps the v1.2 contract documented in
[`11-eeex-v1.2-readiness-compatibility.md`](11-eeex-v1.2-readiness-compatibility.md) as
its primary path:

```lua
local ticks = EngineGlobals.g_pBaldurChitin.m_pObjectGame
    .m_worldTime.m_gameTime

EEex_Opcode_AddDeferredListsResolvedListener(callback)
EEex_Opcode_AddListsResolvedListener(ambient_confirmation_only_callback)
```

Only when the deferred listener is absent and
`EEex_Opcode_AddListsResolvedListener` is present does the runtime select the legacy path:

```lua
local ticks = EngineGlobals.g_pBaldurChitin.m_pObjectGame
    .m_worldTime.m_gameTime

EEex_Opcode_AddListsResolvedListener(callback)
```

The runtime registers exactly one scheduler in either mode. On v1.2 it deliberately also
registers the synchronous API as an ambient-only pending-confirmation observer: one deferred
scheduler plus one synchronous observer (`1/1`, total 2). Legacy registers one synchronous
full scheduler (`0/1`, total 1). Both modes use the same field. A missing or non-numeric value
fails closed before an effect, spell-slot debit, or queued cast. If the synchronous API is
missing on the v1.2 path, ambient fails closed while urgent may keep the deferred scheduler.

This is a narrow compatibility fix, not a change to the prebuff design. The shared field
returns raw world-time ticks, so schema-2 ledgers and the conversion at 15 ticks per gameplay
second remain shared.

## Clock provenance

The direct field is not inferred from the simulator. All three inspected official
EEex releases read and write the identical engine path in `B3TimeStep.lua`:

- [v0.11.0-alpha, lines 48–53](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/B3TimeStep.lua#L48-L53)
- [v1.0.0, lines 48–53](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/B3TimeStep.lua#L48-L53)
- [v1.2.0, lines 48–53](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/B3TimeStep.lua#L48-L53)

Each tagged function returns
`EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime`. The separately
maintained official binding documentation defines
[`timer:GetCurrentTime()`](https://github.com/Bubb13/EEex-Docs/blob/master/source/EE%20Game%20Lua%20Functions/timer/timer_GetCurrentTime.rst),
but the 2026-09-02 live v1.2 process exposed no such method on its embedded `m_worldTime`
userdata. Its metatable exposed `m_gameTime`, and the field returned a numeric raw tick value.
The narrowest source- and live-proven accessor is therefore the direct field, not a
speculative method call and not the private, optional-module helper
`B3TimeStep_Private_GetGameTime()`.

The Infinity Engine timing expression is `Gametime(ticks) + 15 * Duration(seconds)`
([IESDP EFF timing-mode formula](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/eff_v1.htm#effv1_Header_0xC_0)).
Accordingly, `m_gameTime` is consumed as raw ticks and component 121 continues to multiply
gameplay-second thresholds by 15 before comparing them.

## `EEex_GameState_GetTime` provenance correction

`EEex_GameState_GetTime` was invented locally; it was not an API removed by a newer EEex
release. A full-tree search found no definition or use in the inspected official
v0.11.0-alpha, v1.0.0, or v1.2.0 sources, including their complete GameState modules:

- [v0.11.0-alpha `EEex_GameState.lua`](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_GameState.lua)
- [v1.0.0 `EEex_GameState.lua`](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_GameState.lua)
- [v1.2.0 `EEex_GameState.lua`](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_GameState.lua)

Local history establishes the actual provenance: commit `58f124c` first added the invented
global to the simulator/probe surface, `0c89940` promoted it into the production runtime,
and `fee4c3b` retained it as a required capability. The old v0.11 live pass consequently
disabled component 121 at registration. That pass diagnosed the bad gate; it did not test
the corrected direct-field fallback.

## Listener availability and cadence

### v0.11.0-alpha

The tagged source defines
[`EEex_Opcode_AddListsResolvedListener(func)` at lines 6–12](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Opcode.lua#L6-L12)
and invokes every registered callback as `func(sprite)`
([lines 126–130](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Opcode.lua#L126-L130)).
Its patch has three `CGameSprite::ProcessEffectList()` success-path hook sites, each calling
the lists-resolved hook immediately
([`EEex_Opcode_Patch.lua`, lines 44–82](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Opcode_Patch.lua#L44-L82)).
There is no deferred/coalesced listener or end-of-`ProcessAI()` flush in this release.

### v1.0.0

The contract is the same: registration at
[`EEex_Opcode.lua` lines 6–12](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Opcode.lua#L6-L12),
callback delivery as `func(sprite)` at
[lines 126–130](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Opcode.lua#L126-L130),
and the same three immediate `ProcessEffectList()` hook sites at
[`EEex_Opcode_Patch.lua` lines 44–82](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L44-L82).

### v1.2.0

The tagged module explicitly labels the old callback legacy and defines both listener APIs
([`EEex_Opcode.lua`, lines 6–23](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Opcode.lua#L6-L23)).
Both receive a sprite
([lines 137–146](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Opcode.lua#L137-L146)),
but v1.2 adds a coalesced flush near the end of the sprite's real `ProcessAI()` pass
([`EEex_Opcode_Patch.lua`, lines 84–103](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L84-L103)).
The [v1.2.0 release notes](https://github.com/Bubb13/EEex/releases/tag/v1.2.0) describe the
deferred callback as firing at most once per sprite AI tick. That is why it remains the
primary path.

The legacy callback is synchronous with effect-list resolution and is not an exact clock.
On v1.2 that property makes it the pending-confirmation observer; on legacy it is the full
scheduler. Repeated effect-list resolutions can produce repeated callbacks, so component 121
continues to derive elapsed time from `m_gameTime` and keep each mutation idempotent.
Simulator cases exercise repeated callbacks and require that they do not duplicate the
spell-slot debit, effect application, or queued urgent cast.

## Marshal-export difference

All three releases define `EEex_Sprite_AddMarshalHandlers(handlerName, exporter, importer)`,
but their exporter contracts differ:

- v0.11.0-alpha requires every export to be a table. Its `addTableExport()` rejects any
  non-table value, including `nil`, with `Creature marshal handler must export table`, then
  passes every handler result directly into that function
  ([`EEex_Sprite.lua`, lines 1255–1274](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Sprite.lua#L1255-L1274)).
- v1.0.0 explicitly treats `nil` as “marshal no data” and otherwise requires a table
  ([`EEex_Sprite.lua`, lines 1268–1293](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Sprite.lua#L1268-L1293)).
- v1.2.0 retains the v1.0 behavior verbatim
  ([`EEex_Sprite.lua`, lines 1268–1293](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Sprite.lua#L1268-L1293)).

Consequently, an inactive, faulted, or externally owned ambient layer with no ledger exports
`nil` on the selected v1.2 path but an empty table on the legacy path. An existing valid
ledger remains a table and is exported/imported on both paths regardless of those gameplay
gates; retirement must not silently lose a real charge. Genuine quick-list-reset bookkeeping
is likewise gate-independent so a retired layer cannot retain a stale charge after a real
spellbook reset. Returning `{}` is the smallest cross-compatible “no data” representation
for v0.11 and is also accepted by v1.0. The saved schema-2 ledger continues to use primitive
numbers, strings, and tables, including numeric `0`/`1` flags.

## Remaining capability gate

The legacy fallback changes only the listener topology and no-ledger marshal result; valid
ledger lifecycle bookkeeping remains shared and gate-independent.
Official v0.11 and v1.0 sources also contain the other EEex globals required by component
121:

- queued actions and the started-action listener: v0.11
  [`EEex_Action.lua` lines 56–76](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Action.lua#L56-L76)
  and [174–184](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Action.lua#L174-L184);
  v1.0 [56–76](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Action.lua#L56-L76)
  and [174–184](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Action.lua#L174-L184);
- sprite state/local access, quick-list reset, and marshal registration: v0.11
  [`EEex_Sprite.lua` lines 579–600](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Sprite.lua#L579-L600)
  and [959–990](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Sprite.lua#L959-L990);
  v1.0 [579–600](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Sprite.lua#L579-L600)
  and [959–990](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Sprite.lua#L959-L990);
- game-object lookup/effect application, stack management/UDAux, resource demand,
  conditional evaluation, and pointer-list iteration: v0.11
  [`EEex_GameObject.lua` lines 60–77](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_GameObject.lua#L60-L77),
  [246–324](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_GameObject.lua#L246-L324),
  [`EEex_Assembly.lua` lines 806–835](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Assembly.lua#L806-L835),
  [1060–1072](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Assembly.lua#L1060-L1072),
  [`EEex_Resource.lua` lines 129–150](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Resource.lua#L129-L150),
  [`EEex_Trigger.lua` lines 23–40](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Trigger.lua#L23-L40),
  and [`EEex_Utility.lua` lines 95–101](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/copy/EEex_Utility.lua#L95-L101);
  v1.0
  [`EEex_GameObject.lua` lines 185–203](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_GameObject.lua#L185-L203),
  [371–449](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_GameObject.lua#L371-L449),
  [`EEex_Assembly.lua` lines 853–875](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Assembly.lua#L853-L875),
  [1304–1311](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Assembly.lua#L1304-L1311),
  [`EEex_Resource.lua` lines 129–145](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Resource.lua#L129-L145),
  [`EEex_Trigger.lua` lines 23–40](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Trigger.lua#L23-L40),
  and [`EEex_Utility.lua` lines 105–111](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/copy/EEex_scripts/EEex_Utility.lua#L105-L111).

`EEex_BAnd` is an EEex engine binding used by the tagged scripts rather than a Lua helper
defined in one of those modules. `Infinity_GetInCutsceneMode` is part of the base EE Lua
surface, not an EEex-defined function; it was present in the earlier installed v0.11 probe.
That observation establishes availability only, not corrected legacy gameplay acceptance.

The fallback remains runtime-capability based. It does not hardcode WeiDU component numbers:
the v0.11 main component is the first component (`0`), while v1.0 and v1.2 designate Main as
`1` ([v0.11 `EEex.tp2` line 16](https://github.com/Bubb13/EEex/blob/v0.11.0-alpha/EEex/EEex.tp2#L16),
[v1.0 lines 56–62](https://github.com/Bubb13/EEex/blob/v1.0.0/EEex/EEex.tp2#L56-L62),
[v1.2 lines 58–64](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/EEex.tp2#L58-L64)).
The existing Lua uses Lua 5.1/LuaJIT-compatible syntax; v1.0 support still presumes a
functional Lua-enabled EEex installation.

## RED/GREEN and review evidence

The fallback contract was added before production code. The first focused shell run failed
six assertions for the intended reasons: no legacy listener registered, no direct-field clock
branch existed, the legacy surface performed no readiness work, and inactive legacy marshal
exports were `nil`. The existing v1.2 cases stayed green.

The original listener-adapter implementation produced the following historical verification
on 2026-08-31:

```text
python -m unittest tests.test_ambient_readiness_listener tests.test_ambient_readiness_installer -v
68 tests passed

python -m unittest discover
228 tests passed in 215.979s

.\weidu.exe --parse-check TP2 setup-chriz-bg-rebalance.tp2 --nogame
TP2 parsed successfully with WeiDU 24900
```

An independent review also ran the 68 focused tests, the complete 228-test suite, and a
51-case runtime stress subset. It found no Critical or Important issue after stale
documentation and installer wording were corrected. `git diff --check` was clean, and the
final process check found no `Baldur.exe` or `InfinityLoader.exe` process. Those runs predate
the v1.2 delivery-accounting redesign and remain evidence for the legacy adapter only, not a
current live result. The corrected build now has 76 focused tests and all 253 repository tests
passing; corrected legacy gameplay remains untested.

## Acceptance boundary

EEex v1.2 is the supported primary target. Its deferred scheduler and synchronous
confirmation observer must remain distinct from the legacy single-scheduler fallback, and
its gameplay acceptance status remains the one recorded in research 11.

The v0.11.0-alpha/v1.0.0 fallback currently has official-source evidence and local simulator
coverage only. The simulator selects one legacy listener, reads raw `m_gameTime`, verifies
that repeated synchronous callbacks do not repeat gameplay mutations, normalizes all v0.11
marshal exports to tables, and fails closed when the raw clock is missing. That evidence does
not replace an installed-game pass.

No corrected v0.11 or v1.0 live gameplay test has been run. The earlier v0.11 pass used the
invented clock gate and is diagnostic evidence only. No game was installed, launched, or
modified, and no save was written or loaded, while performing this fallback audit and
recording this note.
