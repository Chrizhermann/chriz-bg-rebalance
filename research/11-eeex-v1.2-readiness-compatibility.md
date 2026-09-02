# 11 — EEex v1.2 ambient-readiness compatibility correction

**Date:** 2026-09-02
**Status:** corrected v1.2 ambient delivery and exact one-slot accounting passed live on all
four neutral Vigil casters; corrected neutral-to-hostile urgent path passed live on Brother Pol
**Scope:** component 121 clock, tick listener, deferred delivery, slot accounting, and
install-time EEex detection

## Result

Component 121 now targets EEex v1.2.0 first. Its current runtime contract is:

```lua
local ticks = EngineGlobals.g_pBaldurChitin.m_pObjectGame
    .m_worldTime.m_gameTime
```

The return value is raw world-time ticks. Component 121 converts gameplay seconds to ticks
with `seconds * 15` before comparing ambient expiry, the six-second early-removal tolerance,
the two-second urgent retry, or the six-second contact rearm. On v1.2,
`EEex_Opcode_AddDeferredListsResolvedListener` is the sole scheduler and one separately
guarded `EEex_Opcode_AddListsResolvedListener` callback is an O(1), ambient-only pending
confirmation observer. Expected counts are `1 deferred / 1 synchronous / 2 total`. Legacy
uses one synchronous full scheduler (`0 / 1 / 1`). If the synchronous observer is missing on
the current path, ambient fails closed while urgent may remain on the deferred scheduler.

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
definitions exist for both lists-resolved listeners and the started-action listener,
game-object lookup, sprite
local/state access, conditional evaluation, pointer-list iteration, quick-list reset and
marshal handlers, resource demand, effect application, stack management, and queued response
actions. `EEex_GetUDAux` is the v1.2 alias for `EEex_GetUserDataAuxiliary`; `EEex_BAnd` is an
engine binding used throughout the official v1.2 scripts. The remaining
`Infinity_GetInCutsceneMode` global belongs to the base EE Lua surface and was independently
observed in the installed live probe. Every named capability used by the corrected runtime
has current-source or direct installed evidence; fixed API-count claims should be regenerated
from the final runtime rather than copied from the earlier gate.

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

### 2026-09-02 corrected-clock rerun: delivery pass, accounting failure

After the clock-only hotfix was deployed and the lab restarted, the user loaded the staged
`AR3000` save, paused beside the Vigil group, and visually confirmed that their defensive
buffs appeared. A read-only inspection of that paused process established:

- `CBR_RDY_STATE.tick_listener_mode == "deferred"`, with neither runtime layer faulted;
- the two mages carried the expected `DWSW408` opcode-218 delivery effect and the two
  priests carried the expected `DWSP735` opcode-206 delivery effect;
- all four actors remained neutral (`EA=128`) with `caster_label_ini=1`, `instantprep=0`,
  and `inafight=0`, so the urgent layer and hostile SCS preparation were not responsible;
- every component ambient ledger was empty and every relevant spell had a session failure;
  and
- memorized availability was unchanged: `SHUGMG01` retained two `SPWI408`, `SHUPOL01`
  retained one `SPWI408`, and `SHUGAR01` / `SHUGOD01` each retained one `SPPR735`.

This is a live visual pass for cosmetic-free delivery, but a live failure of the agreed
one-slot accounting contract. The neutral session did not exercise urgent first-contact
casting.

The high-confidence cause is a callback-order mismatch. In exact EEex v1.2 source,
`EEex_GameObject_ApplyEffect(... immediateResolve=1)` resolves the outer opcode 146. Exact
BG2EE 2.6.6 disassembly then shows opcode 146 with `dwFlags=1` publishing its child through
`CMessageFireSpell` / `CGameAIBase::FireSpell`; it does not create action 181. The deferred
lists-resolved listener runs near the end of `ProcessAI()`, so the child effects are not
available to a same-callback scan. Production requested delivery, immediately scanned for
the marker, and disabled the spell before debit. The old simulator inserted the marker
synchronously inside its fake `EEex_GameObject_ApplyEffect`, masking the real ordering.

The binary target for that distinction is the lab's 7,182,336-byte BG2EE 2.6.6
`Baldur.exe`, SHA-256
`FC821A4806A0305B84FD85F1AAD2BD472C8DB642ED34B4494AE62351CAE1C580`. In
`CGameEffectCastSpell::ApplyEffect` at `0x1401A82A0`, the effect's `m_dWFlags` field at
`+0x20` is read at `0x1401A82E6`. The nonzero branch used by `dwFlags=1`,
`0x1401A830A..0x1401A8393`, constructs `CMessageFireSpell`; its `Run` path calls
`CGameAIBase::FireSpell`. Only the `dwFlags=0` branch constructs
`CMessageInsertAction`. This agrees with the lab's exact official EEex v1.2
`EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua:110-126`
([tagged source](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Opcode_Patch.lua#L110-L126)):
that hook describes and patches the opcode-146 `param2=0` ForceSpell queued-action branch by
changing its inserted action to SpellNoDec under the special-bit condition. It is not
evidence that the `dwFlags=1` direct fire-spell branch emits action 181.

The correction keeps one primitive pending transaction per actor and spell. The deferred
scheduler requests delivery once and stores the exact primitive spellbook locator, original
flags/count, and deadline. When the child marker resolves, the synchronous confirmation-only
observer re-resolves that record and requires the exact marker, unchanged original flags and
availability count, and an empty ledger before clearing one availability bit and committing.
A two-game-second no-marker deadline fails closed without a debit or retry; paused time cannot
exhaust it, and marker confirmation is checked before timeout. Maintenance uses the same
observer but remains free.

The fact that component delivery creates no action 181 makes an exact SCS action 181 during
first-delivery pending distinguishable. With `instantprep == 0` and the baseline unchanged,
it arms a candidate; only an immediately following action 147 with the same resolved spell
number advances it. Started-action callbacks precede the engine mutation, so a later
reconciliation must see both the exact child marker and an exact one-slot loss. That treats
SCS's debit as the cycle's one charge without a component debit or reimbursement. An
unchanged count waits only to the bounded deadline; any other delta fails closed.

After an ordinary component debit, the persisted version-2 record retains the exact locator
and its original and debited flags. One later exact SCS `181 -> 147` pair, with current
`instantprep == 0` at both action starts, may reimburse only that component-debited record,
and only when a later callback observes SCS's exact one-slot loss. Restoration requires the
current flags to equal the captured debited flags, restores the exact original flags, repairs
quick lists, and verifies the baseline. Canceled,
non-adjacent, renewal, combat, or ambiguous sequences never reimburse. Reset/import,
recycled sprites, changed flags/counts, and quick-list failures invalidate transient state.
A narrow lifecycle boundary can leave one already-queued finite child effect without debit
or ledger; it is not retroactively charged from the ownership-ambiguous generic marker and
never receives free maintenance. Failure reasons remain available for read-only diagnosis.

Persisted accounting is not retired with gameplay behavior. Marshal export/import of an
existing ledger and genuine quick-list-reset bookkeeping run independently of the ambient
enable, external-owner, and fault gates: a retired/faulted layer must neither lose a valid
charge on save nor retain it after the actor's real spellbook reset. Generic confirmation
and action handling remain existing-session-only. One narrow exception prevents a save/load
or hot reload before the first deferred tick from defeating later reimbursement: an exact
SCS action 181 plus known delivery may reconstruct an otherwise empty session from an
already-existing, valid, charged/reimbursable schema-2 UDAux record, without allocating new
UDAux. All transient pending state is still discarded.

In the pre-confirm SCS-paid race, SCS may commit the one charge before the component's already
queued child publishes. That later child is accepted only as a bounded redundant finite
effect. It causes no component debit, creates no new ledger or maintenance entitlement, and
does not change the already-proven SCS-paid charge.

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
- v1.2 registers one deferred scheduler and one synchronous ambient confirmation observer;
  legacy registers only one synchronous full scheduler. Hot reload must not increase either
  count.
- The simulator models the nested `EngineGlobals` world timer and raw ticks instead of
  inventing public clock globals.
- A missing world timer is exercised and must leave effects, memorized slots, and the action
  queue untouched while each layer trips its independent fault fuse.
- The installer no longer assumes EEex component 0/1. `M___EEex.lua` proves the autoload
  bootstrap; the runtime proves the specific capabilities it needs. Component 121 itself
  does not use a LuaJIT-only primitive, so it does not impose a separate LuaJIT component
  predicate.
- The generated manifest records target v1.2.0, the deferred scheduler, synchronous
  confirmation observer, raw engine ticks, and 15 ticks per second. This is target metadata,
  not a claim of completed live acceptance.

`expected_expiry` in the marshaled ambient ledger stores raw engine ticks. Ledger schema 2
also persists the exact spellbook locator plus original and component-debited flags needed
for strict later reimbursement. The old clock-gated runtime created no real live ledger, and
the corrected-clock lab run failed before committing one, so the disposable evidence does
not contain a valid version-1 charge to migrate. The legacy fallback preserves the same raw
tick unit; its separate evidence is recorded in
`research/12-eeex-legacy-readiness-fallback.md`.

## RED/GREEN evidence

The regression was first changed to model a v1.2 world-time userdata with `m_gameTime` but no
`GetCurrentTime` method. Before the production fix it failed exactly as the live game did:
zero ambient applications and both feature fuses faulted. The minimal production change then
made both listener modes read the direct field. The fake method was removed from the default
simulator surface, and source tests now reject it in both production and probe code.

After the clock implementation change:

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

The later delivery-order regression first reproduced the corrected-clock live shape: the
effect became active only after the callback, while availability remained `1` and no ledger
record was committed. Further RED cases covered independently delayed spells, deferred
maintenance, unchanged-time repeated callbacks, exact memorized flags/counts, import/reset
boundaries, component-versus-SCS delivery attribution, pre-confirm SCS-paid charging,
post-action reimbursement, canceled/non-adjacent sequences, gate-independent ledger/reset
bookkeeping, v2-ledger-only session reconstruction, and late-child redundancy. The corrected
build now has 76 focused tests and all 253 repository tests passing. The subsequent fresh
process passed ambient delivery and accounting. The earlier `61 listener / 17 installer`
green result belonged to a superseded intermediate transaction and is not current evidence.

## Live acceptance

The first v1.2 attempt found the invalid timer method; the corrected-clock rerun passed visual
delivery but failed slot accounting. Broad verification then succeeded, and with both lab
processes confirmed closed the corrected runtime was deployed to the same approved disposable
lab as a recorded one-file direct hotfix. The prior bytes were preserved and `WeiDU.log`
remained unchanged. A third fresh process then passed ambient delivery and accounting on all
four neutral Vigil subjects. Do not uninstall component 121 and do not rely on
`--force-install-list 121`, which would be a silent no-op.

The accepted ambient rerun verified each active marker, exact one-slot delta, and schema-2
charged ledger together. The synchronous confirmation observer reconciled the first use
during child-effect resolution; a separate later deferred scheduler pass was not needed as
the acceptance mechanism. All four subjects were neutral (`EA=128`), so this pass did not
exercise urgent first contact.

The earlier clock-only lab deployment changed the installed runtime from SHA-256
`6835A6FD80B8716D357A5D2923F23DB8AF4001E8A53646FD0E55D588A88AC15D` to
`42191F6215E4DACD53CB9D998849A0BB35A018E8BCA2300138D89FBA7AE075E5`. With both game
processes again absent, the accounting candidate `870B4C6F...` was preserved and the final
verified runtime was deployed at SHA-256
`EF38A1A0BF942A2B3AB294FAE48DA2548E9413DBD5FE7CB255406C413E06DD3D`.
`WeiDU.log` remained byte-identical at
`6C988DE31A47812C692EEFBB7108D3B7A826FDD9CEA3DFC29A546C5A7132C2C0`. The final file
parses with the lab's bundled Lua interpreter, retains the installed manifest prefix, and has
an exact production suffix. That runtime is the accepted ambient build, not the final urgent
correction.

### Urgent `virtual_ClearActions` correction and acceptance

The first urgent attempt showed no reaction to the attack order, then SCS-visible buffs after
the first hit. The component diagnostic had `urgent_faulted=1`; Brother Pol had no component
contact attempt, so the component had not started its normal cast. The attack order itself did
not change a neutral actor's `EA=128`; the first damaging hit changed him to hostile and made
the urgent predicate eligible.

The callback fault was the no-argument call to `current:virtual_ClearActions()`. Exact
`LuaBindings.dll` SHA-256
`BA84C42FB4B045A585ED5CFD38C1DC487BB9D7052D11D5D4FEC198F1155B2DB7` checks Lua argument
2 at `0x1802B9D3C..0x1802B9D44` and passes its Boolean in `EDX`. Exact BG2EE 2.6.6
`Baldur.exe` SHA-256
`FC821A4806A0305B84FD85F1AAD2BD472C8DB642ED34B4494AE62351CAE1C580` branches on that
Boolean at `CGameAIBase::ClearActions+0x14` (`0x140155D44`): `false` clears the full queue;
`true` preserves queued entries with action-flags bit 0. Because production already admits
only known passive current/queued actions, the correct call is
`current:virtual_ClearActions(false)`. The simulator now rejects missing/non-Boolean arguments
and asserts `false`; the exact urgent-normal-cast test was RED before the fix and GREEN after it.

With both lab processes absent, the one-line correction was deployed without changing
`WeiDU.log`; the final stamped runtime SHA-256 is
`9957348E7DB69EE24CA149787887B9AD36012B0F34A2D665CE041611F32B3D08`. On the retest the
visible timing was intentionally the same: no response to an attack order while neutral, then
the reaction after the first hit established hostility. The paused diagnostic then found
`urgent_faulted=0`; Brother Pol's exact component contact was `attempts=1`, `spent=1`, empty
pending resref, and a recorded queue tick. That spent transition occurs only when the exact
normal action-31 `SPWI708` start callback matches the component's pending cast. His Mantle
spellbook had zero of one copy available and exact `SPWI708` opcode-120 effects were active.
The generic mage had no component contact attempt and was already executing non-passive action
22, so it was correctly not interrupted. This accepts the current-version neutral-to-hostile
urgent path; it does not claim that every row in the broader live matrix was exercised.

Older EEex support remains second priority. A later capability adapter now selects
`EEex_Opcode_AddListsResolvedListener` as the full scheduler plus direct
`m_worldTime.m_gameTime` only when the deferred listener is absent. On v1.2 the same
synchronous API is confirmation-only. The legacy path has official-source and fake-runtime coverage, including
repeated synchronous callbacks and v0.11's table-only marshal exporter contract, but no
corrected old-version live pass. The v1.2 stage above remains first.
