# 10 — Historical installed EEex ambient-readiness probe

**Date:** 2026-08-30  
**Install:** BG2:EE/EET 2.6.6.0, EEex through `InfinityLoader.exe`, SCS 35.21,
Spell Revisions 4.19  
**Purpose:** attempt to close component 121's live-engine capability gate; this was not a
component installation or acceptance test, and the clock portion was later invalidated.

> **Correction — 2026-08-31:** the probe did not close the clock/scheduling gate. Its
> `timestamp()` helper tried the nonexistent globals `EEex_GameState_GetTime` and
> `Infinity_GetGameTime`, then silently used `os.clock()`. Both guessed globals were absent,
> so every value below labeled “engine time” was process CPU time, not the engine world
> timer or reliable elapsed wall time. The quoted `+0.205`, `+0.570`, `+0.535`, `+0.871`, and
> `+0.938` deltas are invalid as timing evidence and must not be used for acceptance or
> tuning. The observed event ordering and independently inspected slot, action, effect,
> reset-listener, and Project Image shapes remain useful. The replacement current-version
> contract is documented in `research/11-eeex-v1.2-readiness-compatibility.md`.

## Safety envelope and cleanup

The user separately authorized this session-scoped probe. It ran only on the disposable
copy
`000000486-CBR Ambient Readiness Probe`, made from `000000474-demo`. No mod was installed,
no save was written, and the game resources were treated as read-only. The reviewable
`research/scripts/ambient_readiness_probe.lua` was sent through the already installed EEex
Remote Console protocol 1.1; it was never copied into `override` or indexed as a resource.
Only the console's transient command/result files existed while a request was in flight.

The final cutscene check intentionally entered cutscene mode. That suspended the remote
watcher before the queued `EndCutSceneMode()` recovery could execute, so the in-process
probe teardown could not be called. The session was therefore closed without saving. The
window accepted a normal close request but did not act on it while cutscene handling owned
the world screen; the already identified Baldur and InfinityLoader processes were then
terminated. Both were confirmed absent. Unsaved termination discarded every runtime
sprite/effect/slot mutation, including the one outstanding controlled debit.

Post-session checks established:

- the nine files in the disposable save are byte-identical to the nine source-save files;
- only `eeex_remote_ready.json` remains from the console, with no command, run, temporary,
  or result file;
- `WeiDU.log`, `dialog.tlk`, the four protection SPLs, the EEex Lua inputs, SCS's prebuff
  table, and all 585 `dw#mg*.bcs` files match their pre-probe hashes; and
- neither `Baldur.exe` nor `InfinityLoader.exe` is running.

Representative stable hashes (pre/post equal):

| Input | SHA-256 |
|---|---|
| `WeiDU.log` | `ac8f36cd73a444be0311f4979d343ab9bbed589b80a1203c785ba310469ea75f` |
| `lang/en_US/dialog.tlk` | `2daba5da0ac6810149e037c2f6d9cea8b72c8ad3ed0fa2e98c205bc749a67d51` |
| `override/SPWI611.spl` | `a230b85a361f8d3c2f6e4eb0717cfa43f275ad15f8ed629182663ca790c3521c` |
| `override/SPWI708.spl` | `e1888af2c41368389ee388bbf3b3c20e73559f00eb978ec913a71fc0eb09d5d3` |
| `override/SPWI808.spl` | `993d5d598b24fffda5ca65ace27f6b7376c759b0a1aa6eeaf42bee6f2f98ad28` |
| `override/SPWI907.spl` | `024c77beafed4cd7b8d7e3188c1bd719426695a99f1d0f2bdfc27dc2d18a347f` |
| `override/M_EEexRC.lua` | `17928ec474d5316d7cc87c20489fb2d93529971cb3ceea5cf64856f47fed3e3d` |
| `override/EEex_Action.lua` | `eafefd763a644277bf181f4c77c57f2d4a04abb4ce152665d5d132ea15ea19d0` |
| `override/EEex_Sprite.lua` | `b4c3650979b0163b0bac9c859b4d3100a9e94f956b3aa3ac536ee34ecbd0a589` |
| `override/EEex_Opcode.lua` | `ac0a6dda2e47a424c73777718e9daf7fa2be595b0c187ca44dea9bcfb0c2b982` |
| `override/EEex_Trigger.lua` | `ba939ec12e58b7afc3346d42760aaa85b063624bc879ded0a47f1f9e544f8dce` |
| `override/EEex_GameObject.lua` | `55eb80fc6d2cb6f9d7f5d50e2c8f844cc87365552ca0f91a5cd8ab9669bab650` |
| `weidu_external/data/STRATAGEMS/instant_prebuff_spells.2da` | `3fb7654bcf68b567458132b60a9159413be98bb1576b6803b84f0ed4044999f4` |
| sorted 585-file `dw#mg*.bcs` hash manifest | `ba1cf883b95c69f6490aa255dde0915c9bf9e351e67027cb899368bde7cbb2e7` |

## Historical timing observations — invalidated

This section is retained to make the mistaken evidence trail auditable. Its numeric values
are `os.clock()` readings and do not establish real-time or engine-tick latency.

### Hostile-at-load baseline

For the representative SCS mage, the historical log recorded first `See([PC])` at probe
reading `1582.426`, `caster_label_ini=1` at `1582.631`, and `instantprep=1` /
`inafight=1` with the long and short prebuff effects active at `1582.996`. These readings
preserve event order only. Their differences have no valid time unit and do not quantify a
vulnerability window.

### Neutral-to-hostile transition

A neutral SCS caster (object `235015681`) could see the party while EA 128, but retained
`caster_label_ini=0` and did not receive Stoneskin/preparation during the initial observation.
The historical log then recorded EA 255 at probe reading `3521.328`, the SCS batch at
`3521.863`, cosmetic-free `DWSW408` at `3522.199`, and `instantprep=1` at `3522.266`.
This proves the observed sequence, not the duration or a “sub-round” bound.

The event order was observed, but the elapsed-time claims are withdrawn. A current-version
live pass must measure the source- and live-verified world-time field before making any
scheduling claim.

## Capability verdicts

| Primitive | Verdict | Installed evidence and production consequence |
|---|---|---|
| Settled SCS caster | **Proven** | `caster_label_ini` changed 0→1 only after the actor's SCS fields settled. Classification waits for that label and a recognized SCS script. |
| Mage/priest availability debit | **Proven** | Clearing availability bit 0 on one exact memorized record and calling `CheckQuickLists(CAbilityId,-1,0,0)` changed both list and quick-button counts by exactly one. Reversing the bit and calling it with `+1` restored both. |
| Genuine spellbook reset | **Proven** | `EEex_Sprite_AddQuickListCountsResetListener` fired on engine `Rest()` and availability was restored. Elapsed time/save-load/area movement are not substituted for this hook. |
| Cosmetic-free delivery | **Proven** | `DWSW408` applied the expected opcode-218 Stoneskin child effects with source `DWSW408` and none of the normal `SPWI408` cosmetic effects. Delivery itself did not spend a slot. |
| Ambient transaction | **Proven** | Exact record debit, quick-list rebuild, delivery-effect confirmation, and exact record rollback can be checked independently. A failed stage can restore or fuse off without retrying every tick. |
| Current/queued action inspection | **Proven** | Current action is `m_curAction`; the installed queue is `m_queuedActions`; each entry exposes `m_actionID`, `m_specificID`, and CString resref through `m_string1.m_pchData:get()`. Observed IDs included RandomWalk 85, MoveToPoint 23, Attack 3, SpellRES 31, and RemoveSpell 147. Unknown representation fails closed. |
| Normal urgent cast | **Proven** | Queued `SpellRES("spwi708",Myself)` appeared as action 31, fired the started-action callback with exact resref, then consumed one slot, owned aura/casting time, and produced 13 `SPWI708` effects. |
| Started then interrupted cast | **Proven** | `SPWI611` fired the exact started callback. Replacing its current action with parsed `NoAction` before completion left no `SPWI611` effects and the engine preserved the slot. The contact episode is nevertheless spent at confirmed start, as approved. |
| Passive-only displacement | **Proven with allowlist** | Idle/no-action, RandomWalk 85, MoveToPoint 23, and their complete queued representation are inspectable. Attack 3, SpellRES 31, tactical/unknown actions, and any unknown queue are never cleared. |
| Visibility state | **Partially proven** | Moving the actor out of sight changed `See([PC])` to false and returning it changed the predicate to true. The claimed `>6 s` interval used the invalid clock and is not proven. A full-round rearm must be retested against the v1.2 world timer. |
| Project Image relation | **Proven** | `WIZARD_PROJECT_IMAGE` resolves to `SPWI703` on this install. The clone carried opcode 237 with parameter 2 (`m_dWFlags`) 2 and `m_sourceId=214305989`, the owner's object ID. The owner had general state 48 plus `SPWI703` lock effects (opcode 233 p1=2/p2=127 and opcode 20). Production resolves and stamps the symbol from final `SPELL.IDS`, so clones and locked owners can both be skipped without name heuristics or a stock-slot assumption. |
| Initial-SCS reimbursement | **Proven, narrow shape only** | Generic SCS prebuff is adjacent `ReallyForceSpellRES(delivery)` action 181 then `RemoveSpell(original)` action 147. The latter exposes the numeric spell ID in `m_specificID`. With two `SPWI212` copies, component debit 2→1 followed by the initial SCS pair changed 1→0 and activated `DWSW212`; restoring the component's exact debited record leaves the correct net one-copy spend. Free `_PRECAST` exceptions never enter this path. |
| Cutscene gate | **Proven read-only predicate** | `Infinity_GetInCutsceneMode()` exists. Entering cutscene mode hid the world UI and suspended the remote watcher, which is itself strong reason never to mutate or clear actions there. Production only reads the predicate. |
| Independent global dialogue predicate | **Ambiguous** | `worldScreen:GetInControlOfDialog()` returned true during ordinary play and is not a proven “dialogue active” boolean. Production must not invert or reinterpret it. Dialogue/cutscene/tactical actor actions are excluded by the exact action allowlist; any separately uncertain UI state fails closed. |

## Exact reimbursement boundary

SCS has two materially different paths:

1. generic `SpellPrecast` / `SpellPrecastLong`: force the `_PREBUFF` delivery and then
   `RemoveSpell(original)`; and
2. special Stoneskin, Mind Blank, and Ironskins `_PRECAST` blocks: force a delivery without
   `RemoveSpell`.

Component 121 may reimburse only when all of these facts are observed in the same initial
preparation episode:

- its ledger already charged the same original resref while `instantprep` was 0;
- the managed effect is active from the exact manifest delivery resref;
- started actions are the exact delivery action 181 followed by adjacent RemoveSpell 147;
- action 147's `m_specificID` is the same resolved spell number; and
- availability dropped by one across that pair.

The runtime then restores only its own previously debited memorized record. This leaves one
net unavailable copy, regardless of which identical record SCS removed. Missing adjacency,
wrong spell number, a renewal/combat episode, a free `_PRECAST` path, or any unobservable
delta receives no reimbursement.

## Corrected implementation decision

The installed v0.11 spike proved many non-clock primitives needed by both approved layers:

- ambient readiness can use a checked exact-record debit plus cosmetic-free SCS delivery,
  with the reset listener as the only charge reset; and
- urgent readiness can clear only a fully proven passive current/queued action set, queue
  one normal `SpellRES`, and disarm on exact started-action confirmation.

It did **not** prove a supported clock, timed retry, timed natural-expiry decision, or
full-round rearm. The later disposable component-121 gameplay pass produced no buffs because
production required the invented clock global and retired itself. The runtime as a whole was
therefore not validated by this spike.

The current path instead targets EEex v1.2.0, using
`EngineGlobals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime` and converting
duration seconds to raw 15-Hz engine ticks. Its corrected ambient accounting and
neutral-to-hostile urgent path later passed fresh-process v1.2 gameplay. The urgent pass also
corrected the spike's permissive mock: EEex requires an explicit Boolean argument to
`virtual_ClearActions`, so the passive-only replacement path uses
`virtual_ClearActions(false)`. Corrected legacy gameplay remains untested.

The runtime remains a transitional bridge. Ambiguous dialogue state, an unknown action or
queue, unresolved Project Image ownership, an unrecognized SCS reimbursement sequence, or
any callback failure means no action, not a guessed fallback.
