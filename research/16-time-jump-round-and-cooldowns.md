# 16. Personal rounds and cooldowns across world-time jumps

**Component 361 · Windows x64 2.7.3.0 · 2026-11-18**

Sections 1–7 record the Phase 1 design. The [Phase 2D verification](#phase-2d-review-fixes-and-verification) records the current hook, toolbar behavior, multiplayer scope and lab results.

A character can finish casting, travel for hours, and still have a used aura. The world clock advances in one write. The engine later compresses some area and effect timers, but it leaves the sprite's cast counter, attack-round phase, Hide in Shadows lockout and contingency polling throttle untouched. The four counters have different owners and completion rules. A fifth field, script-imposed unselectability, also counts down on AI updates and shares storage with an effect.

**Recommendation.** Observe a *committed forward jump*, age the independent recovery counters once, and leave action execution to the engine. Do this for locally owned party members and materialized sprites in loaded areas. Use one validated native hook, discovered at runtime with EEex under either Lua 5.2 or LuaJIT. The most consequential acceptance checks are an interrupted first rest, an in-flight action, and the first clickable frame of a paused ambush.

## Evidence and address conventions

Read-only static analysis used the three Steam executables, their PE sections, x64 instructions, unwind/function boundaries, relative calls/tail jumps, jump-table dispatch, vtables, the installed loader databases and Lua bindings. The two installed EEex source trees, v1.2.0 upstream sources and the named local mods were compared. No engine was started. The hook, tables below marked **proposal**, and tests are specifications. Static reads establish what these paths do when reached. They do not measure a live frame, establish synchronization with every engine thread, or enumerate arbitrary third-party native writes.

All addresses are hexadecimal **RVAs** from image base `140000000`. Structure offsets are hexadecimal bytes. Decimal durations and action IDs are labelled or written without code formatting where ambiguity matters. The BG and BG2 columns below were independently checked. SoD uses its BG executable and EET its BG2 executable. The existing component 360 installer records byte identity for Steam BG2 `Baldur.exe` and GOG `BaldurII.exe`. GOG was not an independently sampled fourth binary.

| Steam PE | File bytes | PE stamp | `.text` virtual size | File SHA-256 |
|---|---:|---|---|---|
| BG:EE, including SoD | 7,145,352 | `6A18D6DC` | `588510` | `187f89e1033999b2c8eae6591641325ba012071030364767f42221ecae92372a` |
| BG2:EE, including EET | 7,202,696 | `6A18D73D` | `588510` | `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57` |
| IWD:EE | 7,403,912 | `6A18D7E9` | `58A5A0` | `3458b17b1ac0e60d5798a4b2d2dcc62bb458521378564a109b1395c847b320f1` |

All three report file/product version 2.7.3.0, machine `8664`, and `.text` RVA `1000`. For the **specific instructions cited below**, a single BG/BG2 RVA in a timer, AI-base, area, message, UI, game, or sprite-constructor routine maps to IWD **+`80`**. A single BG/BG2 RVA in sprite routines from `CGameSprite::AIUpdate` onwards maps to IWD **+`30`**. The engine Lua wrapper at `3F32F9` also maps by +`30`. Data addresses have their own mapping. These are local correspondence rules for the cited evidence, not an executable-wide relocation rule.

| Function or object | BG:EE | BG2:EE/EET | IWD:EE |
|---|---|---|---|
| `CTimerWorld::AddCurrentTime / AdvanceCurrentTime / CheckForTriggerEventPast` | `251200 / 2512B0 / 2513A0` | `251200 / 2512B0 / 2513A0` | `251280 / 251330 / 251420` |
| `CGameAIBase::ProcessAI / CGameArea::CompressTime` | `162D90 / 17DBB0` | `162D90 / 17DBB0` | `162E10 / 17DC30` |
| `CInfButtonArray::SetState / UpdateButtons` | `266000 / 267800` | `266000 / 267800` | `266080 / 267880` |
| `CInfGame::RestParty / RestPartyPrivate` | `287D00 / 288140` | `287D00 / 288140` | `287D80 / 2881C0` |
| World asynchronous update / world map `EnterArea` | `2EB8E0 / 2FEC40` | `2EB8E0 / 2FEC40` | `2EB960 / 2FECC0` |
| Sprite constructor / `AIUpdate / CompressTime` | `341860 / 3447F0 / 3500F0` | `341860 / 3447F0 / 3500F0` | `3418E0 / 344820 / 350120` |
| `Attack / CheckModal / DoAction / ExecuteAction` | `388D40 / 38CF00 / 392650 / 395FF0` | same | `388D70 / 38CF30 / 392680 / 396020` |
| `Hide / ProcessAI / ProcessEffectList / Rest` | `39DBB0 / 3A9EC0 / 3AB9D0 / 3B1B90` | same | `39DBE0 / 3A9EF0 / 3ABA00 / 3B1BC0` |
| `Spell / SpellPoint / Swing / UseItem / UseItemPoint` | `3B4180 / 3B5EC0 / 3B8610 / 3BAF00 / 3BC000` | same | `3B41B0 / 3B5EF0 / 3B8640 / 3BAF30 / 3BC030` |

The function names come from `EEex/loader/v2.7.3.0/{bgee,bg2ee,iwdee}/function_names.db`. The field names were checked against generated native bindings and the instruction widths against the executable. An exact-displacement census also catches direct accesses outside the named functions. Paired wider stores, computed addresses, indirect calls, unnamed code and extension DLLs require separate interpretation. [Upstream 2.7.3.0 binding declarations](https://github.com/Bubb13/InfinityLoader/blob/f14a00527286f819b8034411bc92ca719cfe3c86/Core-Shared-Files/generate_bindings/in/Baldur-v2.7.3.0.h)

## 1. Which changes to world time count

`CInfGame+3FA0` embeds `CTimerWorld`. Its `+0` is the unsigned 32-bit world tick, `+4` is the active byte, and `+5` is timer state. The game also has a separate field at `+953C`. Recording whichever integer happens to change between frames cannot distinguish travel, pausing, loading or network correction.

### Clock writers and callers

| Origin | BG/BG2 evidence | Unit, ordering and consequence |
|---|---|---|
| BCS `AdvanceTime`, action 353 | `160980–16099C → AddCurrentTime` | Multiplies the integer argument at `+448` by **15**. Add uses an unsigned `cmp edx,384h / jbe`. Only a delta **greater than 900 ticks** commits. |
| Normal and waylaid travel | `30119E → AddCurrentTime` | The host/single-player path supplies the selected trip's tick count. A zero-duration branch skips the call at `3010A9–3011B5`. |
| Party rest | `28878B → AddCurrentTime` | Commits elapsed rest only on the branch described below. |
| BCS `DayNight`, action 66 | `15D8EE → AdvanceCurrentTime` | Converts the requested hour to 4,500 ticks per game hour. The callee accepts a **target time of day**. |
| Multiplayer change request | `143A6C → AdvanceCurrentTime` | Same target-time calculation. Both timer methods take a network request path on a non-host. The authoritative clock write is decisive. |
| Engine Lua `CTimerWorld:AdvanceCurrentTime` | `3F32D3–3F32F9 → AdvanceCurrentTime` | Converts Lua number to integer and passes it in EDX. This interface accepts the target in ticks. No multiplication by 15 here. |
| Authoritative time-sync broadcast | `2086F7 → OnTimeSynchBroadcast`, `143ADB–143B1B` | Old EDI, new EBX. With SIL=1, writes the clock and queues `new-old`. With SIL different from 1, can snap excess network drift. Track only the forced forward event. |
| World-screen key handler | `2F655D–2F656C` | Adds the hour constant, **4,500**, directly and calls the trigger checker. This path bypasses both bulk timer functions and the posted delta. |
| Normal simulation | `2EC1B9 → UpdateTime 251DC0`, increment `251DEB` | Active timer, even engine frame (`+FA0`), increments by one. `StopTime` can decrement one at `251D44`. Neither operation is a jump. |
| Initialization and save restore | `2511F9`, `27A1DE`, `293180`, `294289` | Construction initializes the clock, game initialization seeds it, unmarshalling restores saved seconds ×15. Even a large forward difference between two saves is ineligible. |
| Debug key-up loop | `2F7984`, `2F7990–2F7992` | Repeats an engine update and a single increment. Exclude this caller of the trigger checker. |

Across the three images the direct `E8/E9` caller census of `AddCurrentTime` was **3/3/3** and of `AdvanceCurrentTime` **3/3/3**. The eight direct callers of the common trigger checker were `143AFB, 251289, 25136E, 27A1E4, 293182, 29428B, 2F656C, 2F7992` in each BG image, and `143B7B, 251309, 2513EE, 27A264, 293202, 29430B, 2F65EC, 2F7A12` in IWD. Ordinary time, save restoration, controls, and the bulk-event network paths were examined separately. An external plugin can always directly assign through a clock pointer.

```asm
; BG/BG2. EBX is the actual elapsed delta at both successful commits.
251251  mov edx,[rcx]           ; AddCurrentTime
251253  add edx,ebx
251255  mov [rcx],edx
251289  call 2513A0
25129C  mov [rcx+9E0h],ebx      ; posted world-screen delta

2512F2  cmp ebx,384h            ; AdvanceCurrentTime, after day-wrap calculation
        ; jbe exits without a clock write
251336  lea edx,[r9+rbx]
25133A  mov [rdi],edx
25136E  call 2513A0
251381  mov [rcx+9E0h],ebx
```

The day is 108,000 ticks (`1A5E0h`). For a valid time of day, `AdvanceCurrentTime` computes `target − (now % 108000)` and adds one day when the target precedes the current time of day. The native threshold applies to that difference, including a zero difference. Neither bulk primitive has a Time Stop veto. No ordinary update caller of either primitive was found. A negative BCS argument can look large to the unsigned comparison. The proposed signed-forward rule below prevents that from granting readiness.

One game hour is **4,500** ticks, eight hours are **36,000**, and 54,000 is twelve hours. A six-second input is 90 ticks. A literal sixty-second input is 900. Both are ignored by these bulk functions. The stock BG/BG2 `GTIMES.IDS` in the KEY/BIFs gives `ONE_TURN` the value **61** (915 ticks, accepted). The sampled stock IWD table contains day constants and does not define that symbol. The Chriz Easy IWD override defines `ONE_ROUND` as 6 and has two `EIGHT_HOURS` entries, 2400 and 2401. Use numeric inputs and record the effective IDS when comparing editions. A fresh cast counter needs **100 eligible increments**. Conventional six-second rounds and this native threshold are distinct quantities.

### Travel, area creation and local transitions

`CScreenWorldMap::OnAreaMouseClick 301D50` builds the route (`301F2B`), rolls for an encounter (`3021B1–302228`), accumulates completed legs and uses half the encounter leg (`30228A–3022AA`) or the full normal leg (`3022BA–3022C4`). `302575/302582` passes the resulting duration to `EnterArea`. A forced encounter branch at `2FED2D` can zero it. Multiplayer map-announcement paths also call `EnterArea` at `13EF5C/13F219`.

Within `EnterArea` the destination load call is at `2FF11D`. Actor remove/add virtual calls occur at `2FF5F7/2FFC69` and `2FF8E7/2FF90D/2FFF56/2FFF79`. Selection/toolbar paths run at `2FFAEF/300112`. Visible-area activation has branches at `300B19/300B3B` and later at `3015D1/3015F3`. The duration commit at `30119E` follows the transfer block. On return the map handler can also clear group actions (`3025CD`). This makes party IDs important during a move. It also explains why replacing the current action in the clock hook would race native travel semantics.

`OnCreation()` has two stages. The AI-base constructor queues trigger `0x36` (`154986–15499F`, `SetTrigger` and the first-call flag). Area load/unmarshal constructs scripts (`27F492`, `18DE18/18DE78`). Script selection consumes pending triggers later (`1631E8`); the ordinary world pass processes a posted time delta at `2EC272` before area AI at `2EC6E2`. Destination creation/trigger *queuing* can precede the travel commit. The ordinary subsequent area AI sees the committed time. This does not establish the first render/input order of every scripted area or network branch.

Local doors, travel regions, `MoveBetweenAreas` and `LeaveAreaLUA` have no independent bulk-clock caller in the census. A zero-duration move therefore grants zero recovery. An area revisited after an absence can nevertheless receive `CompressTime` during `CGameArea::Unmarshal`. At `18BB93–18BBC5` it computes elapsed time from a saved area timestamp. It dispatches object vslot `+58` at `18C8A4, 18CCD5, 18CE7C, 18CFFC, 18D31B, 18D5AB, 18D758, 18D98E, 18DBF2`. Hooking every sprite compression would turn an old area timestamp into a second source of personal-round credit.

`MoveToCampaign 283C10` calls `SetCampaign` (`283C49`) and its expansion-map path (`283CF4`). These are not independent bulk-clock writers. Chapter moves, the Pocket Plane, cutscenes, stores and movies are not proof of elapsed time by themselves. A chapter or voyage script can call an identified timer action. Store UI includes clock stop/start handling; accepting one of the committed origins gives the correct result regardless of the reason the script or UI used it. Installed campaigns' individual scripts were not exhaustively enumerated.

## 2. Rest and interrupted rest

There is no single synchronous `Rest → sprite.Rest → advance clock` sequence. The party coordinator is `CInfGame::RestParty → RestPartyPrivate` (`288054`). Screen and multiplayer callers also enter the private function at `2ED840/2FBA4A`.

| Single-player path | Observed order | Expected 361 behavior |
|---|---|---|
| Completed inn/outdoor/dungeon rest | Completed-period count R13D starts at zero (`288348`). The coordinator calls `HealParty` (`288380`), conditionally checks for encounter, then increments completed count (`2883EE`). At `28876D` a positive count permits `AddCurrentTime(period × count + partial)` at `28878B`. Per-member queued action ID is copied at `2888ED–2888F5` and the message submitted at `28898A`. | Age on the actual commit. Leave memorization, charges, healing, rest messages and their order to native code. |
| Monsters interrupt first attempted rest | Where the rest flags permit, `2883D4 → CGameArea::CheckRestEncounter 17BF60`. It rolls by game hour (`17C013–17C052`), records completed hours plus a random fraction of the encounter hour (`17C0C4–17C0F8`), can spawn monsters, and returns true at `17D1A7`. The caller jumps to `288420` before incrementing R13D. `28876D: test r13d,r13d / jle 288E1B` skips **both** the clock call and per-member rest-action enqueue. | A four-hour roll on this path supplies **zero committed ticks**. Keep the existing recovery. Granting four hours here would change the world's rest rules. `HealParty` was already called earlier in the coordinator. |
| Other rest outcomes / multiplayer | Another encounter call at `2886E0`, interrupted action selection at `2886E9–288703`, and common positive-count check at `28876D`. The chosen action changes from 96 to 243 on the interruption branch. The common addition includes a partial **if** that branch reaches it with a positive completed count. | Observe the commit and its owner. Record the network branch and completed count in a lab before promising multiplayer equivalence. |
| Scripted `RestParty()` | AI-base action 230 temporarily sets game `+9754` around `15F6E1 → RestParty`. `2883AA–2883E9` bypasses the encounter roll when this flag applies. Outdoor eligibility and inn flags also enter this branch. | Same committed-jump rule as UI rest. |
| `Rest() / RestNoSpells()` on one actor | Sprite action 96 passes true at `39724D`, 243 passes false at `39725F` to `CGameSprite::Rest 3B1B90`. The method deals with spell lists, quick lists and eligible item charges (`3B1DC7` through `3B23D5`, item block `3B2366–3B248C`). Direct effect and character-creation callers exist as well. | These actions alone do not call either world-time advance function. No explicit reset of aura, stealth lockout or attack frame occurs in sprite rest. |

## 3. Personal action and attack state

The area asks the sprite's virtual `DoAIUpdate` whether to process it (`178CA6–178CAD`). `CGameSprite::DoAIUpdate 353150` reads the speed mask (`+58`, byte) and object ID (`+48`, dword) and compares their masked frame phase (`353165–353189`). `ProcessAI` calls `DoAction` on different branches at `3AB5E8` and `3AB995`. Other direct callers are `CheckForDead 3BE086` and `ResolveInstants 3BF1FB`. Calling `DoAction` repeatedly would run game logic, including action execution. The base `ProcessAI`, sprite virtual dispatch and action-ID dispatch are separate stages.

| Sprite member | Initial / armed state | Ordinary transition and gating |
|---|---|---|
| `+4990 m_castCounter`, **signed i16** | Constructor `34222E` and quick load `366FCD` set **−1 = free**. Starting a normal spell or item sets **0**. | While nonnegative, `392665–3926E2` increments, compares signed against **100**, and sets −1 only if `+4998 == 0`. This field also measures a spell **in progress**. |
| `+4994 m_bStartedCasting / +4998 m_bInCasting`, 32-bit Boolean fields | `SetCurrAction` clears at `3B39DC / 3B3A08`. Constructor and quick-load explicitly clear `+4994`. | Spell sets `+4998` when it acquires aura. Item sets `+4994` when it acquires aura. The current-action ID is `+3F8` (i16), `+3EC` the signed action step count. These are transaction fields. |
| `+4B9A m_attackFrame`, **signed i16** | Constructor `34223C`, quick load `366FAF` set **−2 = ready**. Attack can arm it to **−1** at `3894BB/3894CA`. `Swing` sees −1 and starts zero at `3B8928/3B8942`. | `3926EA–39270C` increments values greater than −2 and resets at **100 → −2**. The spell-specific haste suppression is absent. `Swing` can also explicitly reset at `3B9B64`. |
| `+4B4C m_speedFactor`, `+4BA8 m_canDamage`, `+4BAC m_leftAttack`, `+4BB0 m_halfAttack`, `+4CA0 m_startedSwing` | Native swing state. `SetCurrAction` clears several fields at `3B39C1–3B39EF`. | Weapon speed, handedness, fractional APR (`+5338` also used), damage eligibility and projectiles participate in a swing. An elapsed interval never earns retroactive attacks or changes which hand is next. |

```asm
; BG/BG2 CGameSprite::DoAction, normal recovery path abbreviated
392684  cmp r8w,r14w             ; r14w = -1
392688  jle 3926EA               ; ready
392698  test dword ptr [rax+rcx],8000h
        ; hasted and c > 0: compare (engineFrame & 1) with (spriteId & 1)
3926C6  inc r8w
3926CA  mov [rdi+4990h],r8w
3926D2  cmp r8w,64h
3926D7  jl 3926EA
3926D9  cmp dword ptr [rdi+4998h],0
3926E0  jne 3926EA
3926E2  mov [rdi+4990h],r14w
3926EA  movzx eax,word ptr [rdi+4B9Ah]
3926F1  cmp ax,-2
3926F5  jle 392713
3926F7  inc ax
392701  cmp ax,64h
        ; at/above threshold store -2
```

**Spell, point and innate.** Normal spell / `SpellRES` share action 31, `SpellNoDec` is 191; their dispatcher calls `Spell` at `396B5D`. Point actions 95/192 reach `SpellPoint` at `39723B`. Object-targeted acquisition is `3B471D–3B473B` and point acquisition is `3B63B6–3B63D4`. The running spell compares `m_castCounter` with `10 × GetCastingTime` and animation timing (`3B4F25–3B4F3B, 3B4FD0, 3B5051`, point `3B6BCD, 3B6C63, 3B6CE1`). A normal innate/special ability ultimately selects a spell action and uses the same gate. Resource, target, ability mode and charges can independently prevent use. `ReadyOffInternalList 3688A2` and the special use-button subtype 3 branches in `UseMagicOnGround 299D9D / UseMagicOnObject 29A561` can explicitly restore free aura. Forced spell and point variants run through `CGameAIBase::ForceSpell / ForceSpellPoint`, including `16CA07/16CA23, 16DB7A/16DB96`. Preserve such bypasses.

**Improved Alacrity.** Stat 76, `CDerivedStats+0C8 m_bAuraCleansing`, is written by the aura-cleansing effect (e.g. `1A75F3`). `Spell` checks it at first action, selecting `sprite+11E8` or `+1E90` via `+4EA4` (`3B4217–3B4231`), then sets the counter to −1 (`3B4283`). The point counterpart is `3B5F6D/3B5FBC`. `UseItem` has its own gate. 361 must not introduce a blanket alacrity interpretation for items.

**Items.** `UseItem`, quick-slot and slot-ability forms dispatched through action 34 call `396BCE`; action 97 calls the point form at `396BDB`. The ordinary scroll, wand, potion and usable-item paths that use these actions share the same `+4990`. Object path `3BB898/3BB8A9/3BB8B3` tests −1 and starts zero. The point path is `3BC59C/3BC5AD/3BC5B7`. The object path separately examines the item's type, `+3EC` and `+4994` (`3BB8C8–3BB8F5`). Type 9 selects a zero action-step wait here and the other branch selects 20. Preserve both item consumption and queued execution.

**Attack.** `AttackReevaluate, ProtectObject, ProtectPoint, RunAwayFrom, OneSwing` and `ExecuteAction` have additional phase accesses. It is possible to carry an elapsed attack recovery after its originating action. Resetting an armed swing, attack count, or hand flag during a projectile transaction could change damage output. A hasted and a slowed attack have different numbers of eligible AI updates in the same virtual interval.

### Direct reference census

Each row lists every explicitly addressed instruction for that displacement found in each BG image. The IWD column gives the exact translation for every listed address in its row. The counts include reads, comparisons and writes. The cited constructor also initializes some adjacent members with wide writes.

| Offset / count per executable | BG and BG2 instruction RVAs | IWD RVAs |
|---|---|---|
| `4990`, 32 | `299D9D 29A561 34222E` | listed RVAs +`80` |
| ↳ | `366FCD 3688A2 392665 3926CA 3926E2 3B4231 3B4283 3B471D 3B4729 3B473B 3B4F2D 3B4FD0 3B5051 3B5F6D 3B5FBC 3B63B6 3B63CC 3B642B 3B6A75 3B6B07 3B6BCD 3B6C63 3B6CE1 3BB898 3BB8A9 3BB8B3 3BC59C 3BC5AD 3BC5B7` | listed RVAs +`30` |
| `4B9A`, 25 | `34223C` | `3422BC` |
| ↳ | `366FAF 3894BB 3894CA 3894DC 389DCD 389DDC 389E01 3926EA 3926FA 39270C 396BEF 397456 3A724E 3A72E6 3AE968 3AE977 3AEE37 3AEE46 3B30F0 3B30FF 3B8928 3B8942 3B8A57 3B9B64` | listed RVAs +`30` |
| `4E70`, 10 | `268557 34332F` | `2685D7 3433AF` |
| ↳ | `344AB6 344AC3 367D31 38DC1F 398EF2 39DC20 39DD7A 39DFFC` | listed RVAs +`30` |
| `5040`, 4 | `14DFD6 14E018 / 3BE35A 3BE366` | `14E056 14E098 / 3BE38A 3BE396` |

## 4. Other counters and their owners

**A** means that a finite elapsed-time recovery or eligibility throttle can demonstrably survive a committed bulk jump. **B** covers native action state, effect ownership, intentionally sampled gameplay and clocks the engine already compresses. **C** identifies the domain already managed by component 360. The suggested handling of a field in A is a design decision. Discovering a countdown does not prove that executing its pending action would be appropriate.

| Class | Mechanic | Evidence and proposed handling |
|---|---|---|
| A | Spell/innate/item aura, `+4990` | Age the spent, no-longer-executing action to −1 at 100. Leave ongoing spell/item transactions to their owner. |
| A | Residual weapon attack round, `+4B9A` | Age a completed swing's remaining recovery to −2 at 100. Armed or executing attacks retain their native phase. There is one verified round field shared across hand/attack paths. |
| A | Failed or broken Hide in Shadows, `+4E70 m_nStealthGreyOut`, signed i32 | Starts zero (`34332F, 367D31`). Hide/break/failed-check/feedback branches assign the constant **90** (`39DC20, 39DD7A, 39DFFC, 38DC1F, 398EF2`). `AIUpdate 344AB6–344AC3` subtracts one while positive. Age positive values to **0**. A pending action, a successful Hide and an unrelated invisibility effect are different states. |
| A | Contingency eligibility throttle, `+5040`, signed i32 | Paired initialization with `+503C` (e.g. `3430DE, 367EEF`). `ProcessAI 3AAC59 → ContingencyCheck` subtracts one when time is active and the value is positive (`3BE351–3BE36C`). `CContingencyList::Process 14DFD6–14E018` rejects positive values and seeds **100** on a permitted check. Age to **0/due**. Native code decides whether and when to test a condition or release a payload. |
| A/B | Script-imposed unselectability, `+4E60`, i32, type `+4E64` | Action 182 (`397C0D–397C20`) writes seconds ×15. `3AAC3B–3AAC50` ticks it, `3A75DC` reads it for orderability, status triggers compare it at `395A1F/30/41`. `CGameEffectMakeUnselectable 1B9C4A–1B9C73` writes the **same member** from unsigned `(deadline−world)/15` or `INT_MAX` for timing 1. Removal at `1E6E12` clears its state. The finite script case can outlast travel. Its source cannot be recovered from the value alone. Keep it out of the four-field write set pending a source-aware design. |
| B | Modal cadence / hiding persistence | `+3A29` is modal mode, `+4E4C m_modalCounter` a u32 phase, `+4E50 m_bHiding` a flag, `+3A4` an AI pass counter. `CheckModal 38CF23–38CF5E` compares `pass % 100 == objectID % 100` and increments modal phase. At mode 3, `38D93B–38D94B` tests phase modulo **3**. Successful Hide clears phase and sets hiding (`39DFD0–39DFD7`). Stealth invisibility has a separately constructed **world + 300** deadline (`39DF61, 38DB2D`). Grant no Hide success or invisibility extension on skipped pulses. |
| B | Find Traps / Detect Illusions, Turn Undead, Bard Song, Shamanic Dance | `3AB4AA → CheckModal`, dispatch `38D208–38D232`. Stock modal IDs in the three games are 0 none, 1 song, 2 find traps (also the detection path), 3 stealth, 4 turn, 5 dance. Per-mode rules apply where available to the actor/game. No second generic re-entry lockout analogous to `+4E70` appeared. Leave phase, targets, rolls, summons, turning and pulse effects on ordinary AI. |
| B | Command pauses, queued action, casting/swing/damage progress | `+4AB8 m_userCommandPause / +4ABA m_nCommandPause` (i16) are consumed at `3AAF83/8A, 3AB76D/79, 3AB85B/65` and checked near `3AB4AF`. `+3E8, +3EC, +4994/+4998, +4AD8/+4AE0/+4AE8` and native queue/action methods own execution. Advancing the command step would execute gameplay out of order. |
| B | Timers, local/global variables, weapon expiry, rest charges | AI timer list `+3A8` is compressed by `CheckTimers 155DEA` with integer `delta/15` from the base/sprite compression paths (`1560DA, 350149`). `SetGlobalTimer` uses the world clock (`1739B5`). `+503C m_nLastExpiryCheck` is **already** reduced by delta at `35014E` and rearmed at `38BB0D–38BB30`. Charge recharge/memorization belongs to the eligible rest path. No extra item charge, daily use, spell slot or weapon-expiry application. |
| B | Tracking, regeneration, proficiency and backstab | Tracking effect assigns `+4F10 = deadline − world` at `1C93FA`. AI also counts it down (`344A7F`) and rendering reads it (`36BAB6`). It is an effect-owned display counter. `+4E54 m_lastRegenerationTime` is a world timestamp (`3ABC50–3ABC67, 3ABCEE`). Proficiency/weapon lists (`+4AF4/+4B44`) and `GetBackstabDamageMultiplier 3540F0` feed resolution. No independent short recharge for backstab, proficiency or Turn Undead was identified in these paths. |
| B | Pending work and presentation | `+4F04 m_nBounceCounter` rearms at 25 and services `CBounceList::Process` (`344A85–344AB0`). This is a queue poll. `+4E3C` attack sound deadzone, `+4CAC/+4CB4` dialogue wait/talking, `+4940` movement block, `+49A0/+49A2` render-order movement, `+4B84..+4B98` animation/search/recoil, `+47FA` marker and `+3C68` presentation tick are tied to active work (`344BD6, 345205, 345342, 345BE3, 3461E4, 3AB1D8`). `+5330/+5334` synchronization and `+52E8` death state are also outside recovery. No past projectiles, dialogue, path searches, bounces, effects or network updates should be synthesized. |
| C | Effects, Time Stop and periodic workers | 360 `CBRTC.Entry/Dispatch` owns absolute timing mode 4096, relative mode 10 handling, and periodic workers for opcodes 25/78/98/272 on its supported BG2/EET setup. `3ABA9D, 226513, 226543, 1BEDD6, 1BBB09, 1B1894, 1B1AC1, 1BFEC8` are its eight documented sites. It distinguishes ordinary elapsed=1 from native compression and shifts frozen effects. 361 owns no effect deadline, phase, poison, disease, regeneration, repeating EFF or Time Stop duration. |

The inventory covers the named native AI, effect, combat, timer, rest and travel paths and the directly addressed candidates above. Registers carrying nested pointers and arbitrary script-, opcode- or mod-defined timers preclude a proof of *every possible* countdown. The decision to keep a command, presentation or pulse clock on ordinary updates is deliberate. In particular, the already elapsed attack recovery and eligibility for the next contingency poll have direct independent evidence; replaying all missed attacks or polls would be a different feature.

## 5. Paused arrival and native compression

The action bar is an embedded `CInfButtonArray` at `CInfGame+4140`. It caches a disabled dword at `buttonArray + slot × 2A0h + 29Ch`. The following data flow was present in all three images.

| Producer or consumer | BG/BG2 RVAs | IWD RVAs | Behavior |
|---|---|---|---|
| `UpdateButtons` | `2678CF, 268557–26855F` | `26794F, 2685D7–2685DF` | Clears each slot's flag, then reapplies restrictions. Hide reads the selected leader's `+4E70` and disables when positive. |
| Drawing and clicking | `265C6C, 265943, 263641` | `265CEC, 2659C3, 2636C1` | Pre-/post-render consume the cache. A disabled click takes the early return. Changing only the sprite cannot retroactively change a populated slot. |
| Native Hide transition to zero | `344AC9–344B10` | `344AF9–344B40` | Only for one selected actor who is leader and outside toolbar states 101–106 and 111, calls `ResetState`. `265DF9 → SetState`; `2675AA → UpdateButtons`. |
| Loaded world, paused or running | `2EC113, 2EC127, 2EC18E, 2EC1B9, 2EE2EF` | `2EC193, 2EC1A7, 2EC20E, 2EC239, 2EE36F` | The inactive-clock branch rejoins the world pass. It calls `UpdateTime(false)`, which can return without a tick, and the eligible world pass still calls `UpdateButtons`. |

For ordinary spell, quick item and innate buttons, the direct `+4990` census contains **no** `CInfButtonArray` access. The native cast gate is in action execution. A player can enter a menu or queue a spell while aura is recovering; observing a clickable icon alone does not establish cast readiness. Item stock, ability availability, selection and other restrictions can still gray a button. Hide is the demonstrated case with a cached cooldown-dependent disabled flag. A modded menu can also display the cast counter directly.

The stock outer update calls Chitin's asynchronous vslot `+E8` before its synchronous vslot `+0` (BG/BG2 `41CBE5 / 41CC29`, IWD `41D895 / 41D8D9`; vtable entries BG `58DDE8 / 58DD00`, IWD `58FDE8 / 58FD00`). The world async wrapper jumps to the loaded-world pass at BG `2FCBB5`, IWD `2FCC35`. The world synchronous wrapper calls `CInfGame::SynchronousUpdate` at BG `2FCCA8`, IWD `2FCD28`. On a normal complete world pass with the commit before `UpdateButtons`, the **next draw can already be correct while paused**. A stale value can survive until that pass if the commit occurs after it, during a screen switch, or input is delivered first. There is no native promise of instantaneous invalidation, and no unpaused AI tick is intrinsically required.

**UI design.** Do not enter `SetState`, rebuild the bar, or overwrite a cached slot from the clock hook. The selection and screen can still be in transition; foreign listeners can run when toolbar state changes. Use the native paused world refresh initially. Hard acceptance is the **first visible and first input-accepting** world frame of normal travel and waylay. If native ordering misses either, mark a nonpersistent UI generation dirty when a selected Hide lockout expires. Consume it on the world UI thread *before* the first action-bar render or click that would read stale state. Reacquire the current world, array and selection, call `UpdateButtons` once, guard reentry, and consider a normal `UpdateButtons` completion a successful consume. Cover both render and input (including a click arriving before draw), panel replacement and a load between mark and consume. Discard the mark on teardown. This conditional fallback must pass the same tests with Spell Menu and uncapped FPS. For an ordinary spell, test the queued action and its first legal execution after resume.

**What native time compression already owns.** `CScreenWorld+9E0` contains one pending delta. The writers assign it, not add to it. `2EC235–2EC2B6` walks 12 `CInfGame+6598` area slots and clears the pending value. `CGameArea::CompressTime` resolves IDs from three render lists (tail anchors `+CB0, +C40, +C78`), tests local ownership in multiplayer, and calls object vslot `+58` at `17DC1A/17DC6A/17DCBA`. The under-list at `+CD8` is absent from this walk. The sprite vtable entry at BG `598BC0` / IWD `59ABC0` points to sprite compression. It updates ordinary timers (`350149`), subtracts delta from `+503C` (`35014E`), clears overhead tick state (`350154`) and visits persistent effects (`350212`). It can obtain a next action (`3503D9`), replace the current action (`3503E4`), call `ClearAI` (`350423`), or remove an object from the area (`350E6E`). The four A recovery fields have no direct update in this routine. Both indiscriminate object compression and replaying AI are unsafe substitutes for the four scalar updates.

## 6. Proposed component 361

### Hook site, provenance and native contract

Use one after-commit observation point inside `CTimerWorld::CheckForTriggerEventPast`. Apply it **before** its day/night bookkeeping and before the native area-compression post. Match the full 31-byte sequence in executable PE sections. It occurred **exactly once per executable**. Match relative call origins separately and verify their commit instructions, register identities and decoded return addresses before enabling the hook.

```text
48 89 5C 24 08 48 89 74 24 10 57 48 83 EC 20
8B 39 B8 71 6E B0 36 F7 E7 8B C7 48 8B F1 2B C2
```

| PE | Match / patch / resume | Original seven bytes | Replayed instructions |
|---|---|---|---|
| BG:EE / SoD | `2513A0 / 2513AF / 2513B6` | `8B 39 B8 71 6E B0 36` | `mov edi,[rcx]`, `mov eax,36B06E71h`; resume `mul edi` |
| BG2:EE / EET | `2513A0 / 2513AF / 2513B6` | same | same |
| IWD:EE | `251420 / 25142F / 251436` | same | same |

| Admitted origin | BG/BG2 call → return | IWD call → return | Signature at call and actual delta |
|---|---|---|---|
| `AddCurrentTime` commit | `251289 → 25128E` | `251309 → 25130E` | `E8 12 01 00 00`. EBX holds elapsed. |
| `AdvanceCurrentTime` commit | `25136E → 251373` | `2513EE → 2513F3` | `E8 2D 00 00 00`. EBX holds normalized elapsed. |
| Forced remote clock commit | `143AFB → 143B00` | `143B7B → 143B80` | `89 19 E8 A0 D8 10 00` includes the store. Admit SIL=1. Delta is unsigned EBX−EDI before replay destroys old EDI. |
| World-screen direct hour | `2F656C → 2F6571` | `2F65EC → 2F65F1` | `01 01 E8 2F AE F5 FF` includes the add. EAX still holds the amount from the validated hour-constant load. |

At the patch PC, RCX is the committed timer. The original function has saved RBX and RSI, pushed RDI and subtracted `20h`. Its caller return address is **`[rsp+28h]`** and RSP is 16-byte aligned. The prologue has preserved the incoming values of EBX, SIL, EDI and EAX needed above. Save any needed input before reusing its register. Resume with RCX intact, the two replayed outputs, all nonvolatile registers and RSP as expected. Incoming arithmetic flags are not consumed before native `mul/sub`; leave unrelated state untouched. No condition flags generated inside the stub may leak into a conditional native continuation. Use a near rel32 jump plus two padding bytes at the seven-byte window, range-check it, and jump back after replay. Do not enter the routine at its beginning a second time.

**Preferred implementation.** Lua performs discovery and setup. A hand-audited x64 leaf performs the arithmetic and bounded game-object walk. It makes no Lua/engine/Win32 calls while visiting sprites, never yields, and stores no actor pointer after its current iteration. No allocator, `ffi`, native exception handling through Lua, marshal handler, saved local variable, or per-tick listener is required by the scalar fix. Use volatile scratch and fixed spill slots with a documented stack layout. If code generation creates another stack frame or spills nonvolatile state, provide the corresponding Win64 unwind metadata. Verify unwind behavior for PCs in generated code as well as the original function. No `pcall` can recover an invalid native dereference.

`EEex_GenLuaCall` is a viable *setup-independent* way to enter a Lua callback and can wrap Lua failures, but would introduce Lua-state availability, stack/unwind, callback reentrancy and userdata-lifetime requirements at travel/rest/network time. An x64 gate plus Lua helper is suitable for limited lab instrumentation. Prefer the leaf for the installed correction.

**Alternative site.** BG/BG2 `35014E`, IWD `35017E`, matches `29 9F 3C 50 00 00 C7 87 C0 04 00 00 FF FF FF FF` exactly once in each image. RDI is a sprite and EBX the delta. Replay the six-byte `sub [rdi+503Ch],ebx` with its flags before resuming. The world-area dispatch return PCs are BG `17DC1D/6D/BD` and IWD `17DC9D/ED/17DD3D`. Qualifying by these prevents area-unmarshal credit. This approach inherits native lifetime/ownership at dispatch, but excludes some sprites, the direct-hour path and information lost when two pending deltas overwrite one another. It is insufficient as the only observation point.

### Object lifetime and authority

1. Reacquire the engine singleton (BG/BG2 data RVA `667548`, IWD `66D548`) and its current game (`+1090`). Require the observed timer to be this game's embedded `+3FA0`. Only admitted origins can reach the walk. Initialization, unmarshal, ordinary sync and debug update have already exited. A transition flag alone would discard real world-map travel.
2. Enumerate the active native object registry once per commit. BG/BG2 **max signed slot, serial bound, slot base** are `68F8F4 / 68F8F8 / 68F910`. IWD uses `6958F4 / 6958F8 / 695910`. The base is an **inline array**, obtained by `lea`, not a pointer variable to dereference. A slot is 16 bytes, with signed 16-bit generation at `+0` and an object pointer at `+8`. `Add 26CBCE–26CBEB` packs `slot << 16 | generation`. `Delete 2724E0–2724EC` marks both pieces −1. `Clean 271F06–271F58` gives a native bounded-walk example. `GetDeny 276700 / 276780` checks index, serial bound and equality. Treat a negative max as empty and honor the 15-bit index domain and PE array bounds.
3. Filter valid generation, non-null/non-tombstone pointer, full object ID (`+48`) matching the slot, and native sprite type **`31h`** in object `+8`. Constructor `341FEB/341FF2` loads the type from BG `59971F`, IWD `59B71F`. Resolve a sprite only inside the owning engine dispatch. Respect a still-constructing/unmarshalling object (sprite `+4EC0`). In network mode mirror `17DBF5–17DC15`, comparing object owner `+50` against local network ID `+374` when session byte `+2C9` is set.
4. Eligible membership is the union of the six current `m_characters` full IDs (`game+6600`, portrait order at `+6618`, count `+6630`) and sprites whose non-null `m_pArea` (`+18`) equals a current loaded-area pointer in `game+6598[0..11]`. Compare area pointers without dereferencing them. Iterating slots once deduplicates party members appearing in an area and includes an in-transfer party member with no area. Include enemies, summons and other actors in loaded areas. Exclude off-area global-list-only NPCs (`+6638`), disk-only areas/CREs, deleted IDs, remote-controlled mirror objects and unconstructed sprites. This defines a temporal policy for newly materialized actors; their normal initial sentinels generally make the update a no-op.
5. **Thread ownership is an implementation condition.** `GetDeny` on these builds is lookup-only and acquires no lifetime lock. Native world updates and message dispatch exhibit serialized paths (e.g. `2086F7` dispatches time sync); the stock frame order is documented above. The same handler can also be reached by the message pump in a store and world input. The bytes of `GetDeny` cannot certify an arbitrary Lua or third-party calling thread. Establish the owner thread at initialization, verify each admitted call context and object destruction/reuse under both EEex versions and uncapped FPS. Do not ship an unguarded table walk in an unestablished thread context. If a supported origin is off-thread, marshal the **event by value** to the owning world dispatch before its next relevant action/UI read, retain a game-lifetime epoch and ordered deltas, and discard stale events on teardown. A cached sprite pointer or retry after object replacement is unsafe. This is the outstanding native safety acceptance condition.

### Arithmetic and transaction boundaries

Recover `old = (new − delta) mod 2^32`, or use old EDI on forced sync. Admit exactly `0 < signed32((new − old) mod 2^32)` for the four recognized origins. Compute counts in at least 64 bits and saturate before narrowing. This accepts a genuine small forward wrap, rejects zero/backward or ambiguous half-range jumps, and leaves native clock handling alone. Do not impose a second 900-tick threshold. Ordinary Add/Advance have already filtered those inputs; a genuinely committed short delta still has a proportional meaning.

Native `ProcessEffectList` loads masks **normal 1, haste 0, slow 3** (`3ACD12, 3ACD7A, 3ACDD5, 3ACDDC`). `DoAIUpdate` first compares `frame & mask` to `id & mask`. Two nominal engine frames span one world tick. The scheduler has additional eligibility tests; unloaded actors or a skipped simulation have no historical AI frame stream to replay. Define the following deterministic extrapolation. It models the normal rate of an eligible actor and pays no ticks of queued gameplay.

- For a committed interval of `d` world ticks choose the canonical virtual starting frame `F = 2 × oldWorld`. Let `U(m)` be the number of integers `k` from 1 through `2d` satisfying `((F+k) & m) == (id & m)`. It gives `d` normal updates, `2d` hasted updates and roughly `d/2` slowed updates. For masks 0/1/3 count residue classes modulo 1/2/4. For any byte mask count full blocks of 256 and the remaining at most 255 residues. Never loop over elapsed hours. Anchoring on world time makes adjacent jumps compose even when no real engine frame runs between them. A slowed odd-length interval has a defined one-update phase choice; the actual engine frame at a discontinuity need not have that phase.
- Compute `H = U(m)` unless the actor's selected derived state is hasted (`8000h`). For haste use `U(m | 1)`, plus one only when `c == 0` and the first eligible frame exists and fails the ID's parity test. `392698–3926C6` explicitly permits the first increment at zero on either parity. The normal positive haste aura gains about **one** per world tick, while the attack field can gain **two**. Use the speed/state snapshot at commit. A temporary speed effect that would expire during a skipped interval has no observable sequence of intermediate AI updates. This is a short-jump approximation; ordinary accepted hour-scale jumps saturate the four normal recoveries.
- Aura is eligible when `c >= 0`, `m_bInCasting == 0` and no started current item transaction (`action 34/97 && m_bStartedCasting != 0`) owns it. With at least one eligible AI update write `−1` if `c+H >= 100`, else `c+H`. Leave a free sentinel alone. A waiting next spell with spent prior aura can acquire the newly free aura through native execution. Never clear `m_bInCasting` or `m_bStartedCasting` to make it eligible.
- Attack is eligible when `a >= 0` and no current armed/active weapon transaction owns it. Preserve `−2` (ready) and `−1` (armed). Exclude active swing/projectile/damage flags and current native attack-producing actions. The dispatcher at `3960C7/3960D0` maps 3/98/105 to attack, 105/134 to reevaluation, 38/339 to `OneSwing`, 27/87 to protection, and 29/184/354/355 to `RunAwayFrom`. For an eligible residual phase, `a+U(m) >= 100 → −2`, otherwise write the sum. Do not reset hand/APR flags, clear the action queue, remove a projectile, or force an animation.
- For Hide or contingency, write `max(0, remaining − U(m))` only for a positive remaining value. Never issue `Hide`, `CheckModal`, `Process` or activation/feedback messages. A due contingency can be considered by its existing native handler, including its own paused-world rules.
- Treat active Time Stop as a separate condition from an ordinary paused screen. Reuse the native owner/immunity predicate (`game+9690, +9694`, selected derived `+2D8`; `38CF94–38CFBB, 3AB5BA–3AB5D5`). **Proposal:** freeze the four recovery credits for a stopped nonowner without immunity during this bulk event. Age the caster and immune sprites normally. This follows 360's treatment of compression for frozen sprites. It is a gameplay choice for 361, not a claim that every native polling counter tests Time Stop at its decrement. Map-load pause alone never suppresses elapsed credit.
- Normal-speed examples: `c=40, hide=90, d=15 → c=55, hide=75`. `c=0, a=0, d=90 → c=90, a=90` for idle residual state. `c=10, d=90 → −1`. For `d=36,000` all four finite baseline recoveries expire. The first two are arithmetic fixtures for actual commits; issuing the corresponding short BCS action alone does not create that commit.

Compression may subsequently cancel or move a previously active action. The conservative write set protects the transaction as it existed at commit. A cast that was **still in progress at commit and cancelled afterwards** can consequently leave native residual recovery. Test that case explicitly. If the agreed gameplay rule is to credit a later cancellation too, instrument the native action-change boundary and hand off only the elapsed credit for the same game epoch, full actor ID and action instance. Never apply old credit to a replacement cast. The four-field design needs no per-save timestamps.

### EEex discovery, installation and coexistence

`M_CZFT.lua` in `chriz-fast-traps` and `M_CZOH.lua` in `chriz-overhead-text` implement the useful multi-game precedent. They obtain the loaded image base, read the PE header and executable section bounds, reconstruct binary strings in bounded chunks (including embedded NULs from `EEex_ReadLString`), use plain `string.find(...,1,true)`, validate matches and generate near x64 trampolines. A chunked implementation must overlap by `patternLength−1` or assemble the section before matching. File offsets are inappropriate for loaded memory. Compare restored bytes immediately before publication. One match in each unmodified Steam file is established above; an ambiguous, missing or already foreign-patched native window should leave the native routine running and produce a log diagnostic.

| Dependency | v1.2.0 and v1.3.1 evidence | Consequence for 361 |
|---|---|---|
| Build and OS-specific labels | The v1.2.0 archive supplies `loader/v2.7.3.0/{bgee,bg2ee,iwdee}/function_names.db`, including the clock checker and `DoAction`. The BG lab and Easy IWD v1.3.1 copies expose the corresponding build databases. A debug function name in this database is not automatically an available `EEex_Label`. | Use the unique memory match and decoded native sites. A whole-file hash is an evidence identifier, not a runtime gate. |
| Assemblers and Lua entry | `EEex_Assembly.lua` defines `EEex_JITAt` at 189 and `EEex_JITNear` at 316. `EEex_Assembly_x86-64.lua` defines `EEex_GenLuaCall` at 1375. Both source files were byte-identical between the v1.2.0 tag and the two v1.3.1 installs. | “JITNear” assembles machine code through InfinityLoader. It does not require the LuaJIT interpreter. No generated Lua calls needed for the production gate. |
| Memory API | Both loader DLLs contain the image-base, binary read, allocation and code-protection primitives. `InfinityLoaderDLL.dll` SHA-256 prefixes v1.2.0/v1.3.1 are `f5519cffd3ca12 / cf464444352e72`. The **2.7.3.0** `LuaBindings.dll` prefixes are `0c6a86dbb402aa / 0a09a17d169235`. | Runtime-check the used `EEex_GetImageBase, Read8/16/32, ReadLString, JITNear, JITAt` and code-protection helpers. `EEex_Malloc` is available via the loader API on both lines. The scalar leaf requires no call to it. |
| Lua runtime | `INTERNAL` is a loader mode. Optional EEex component 8 replaces the internal runtime with LuaJIT. The engine's embedded Lua 5.2 does not supply default `io/os` file APIs. The PE scanner needs only string/table/arithmetic plus EEex memory reads. | Avoid `io.open`, `os`, `ffi`, Lua 5.3 bitwise/integer syntax and assumptions about LuaJIT `bit`. Use `print` for the log, `Infinity_DoFile` for a second module. Test actual loading on all target combinations. |
| Accessors/listeners | `EEex_Sprite_GetCastTimer` returns `sprite.m_castCounter` in both, at lines 641/655 respectively. The percentage accessor derives display from the same counter. Initialized listener exists in both. Action and sprite patch scripts were byte-identical in the sampled versions. | One game-state-initialized installation per process, guarded against a second loader invocation. Reading the new value requires no accessor override or save migration. |

Upstream release/source references for checking these API claims are [EEex v1.2.0](https://github.com/Bubb13/EEex/tree/v1.2.0/EEex) and [EEex v1.3.1](https://github.com/Bubb13/EEex/tree/v1.3.1/EEex). The project's native call-gate and effect-work precedent is [research 10](10-timestop-haste-engine-clocks.md), [CBRTC.lua](../chriz-bg-rebalance/lua/CBRTC.lua) and [its shared installer](../chriz-bg-rebalance/lib/time_stop_haste_clocks.tpa).

**Direct discovery versus a loader database.** A dedicated `extra_pattern_dbs/*.db` with `NoCache=1` can expose a named label using the common checker pattern and a `+0F` offset. It still needs origin verification and game-specific registry references. It adds a loader-time dependency, an installed file and version-specific loader error behavior. The earlier game can fail before mod Lua handles a missing label. Use direct in-memory discovery to keep 361 independent of game-directory database rewrites and cached labels. Neither method should modify the shared `InfinityLoader.db`. If a site has foreign native bytes, decline the hook coherently and log the site.

**Publication.** Use the `M_CBRTC` initialized-listener pattern and the sibling mods' preflight. Verify every mandatory function, PE architecture, executable section, candidate, call target, writable-data location and rel32 destination before touching the hook. Stage code and validate byte count while the original site is intact. Install in the engine's safe initialization window, with protection restoration on every exit and instruction-cache handling through the loader's code-writing facilities. Verify final bytes. On an installation failure restore only this attempted patch and its original protection. A second invocation recognizes this instance's recorded site/target. Distinguish a different owner's detour. Keep runtime diagnostics in the log. No check of a spell, item, old effect, old description, mod version, SR/SCS footprint or campaign content participates.

| Neighbor | Inspected behavior | Interaction to verify |
|---|---|---|
| 360 `CBRTC` | Eight distinct effect-clock hooks. `M_CBRTC` loads its core at initialization. Existing 360 is BG2/EET-only; its installer has its own native requirements. | 361 is separately selectable, including on BG/IWD. Combine on BG2/EET. Preserve 360's ordinary/large-elapsed and Time Stop handling. |
| 121 `ambient_readiness` | `M_CBRRDY` uses deferred/list-resolved EEex callbacks for ambient spell readiness. | Its decisions may see ready aura sooner. 361 neither generates nor starts a cast. |
| 310 / 411 | 310 implements party physical-resistance policy; 411 changes Alaghor weapon access. | Independent data/effect or equipment policy. No shared clock hook. Do not write either policy's fields. |
| 420 / 421 | `M_CBRSP` hooks kit spell-progression table selection. 421 registers bard progressions. | Do not alter spell tables or learned/memorized spell lists. Spell resource availability continues to come from the installed setup. |
| EEex `B3TimeStep`, UncapFPS | TimeStep explicitly reads/writes world time to compensate the engine's one-tick pause reversal (`B3TimeStep.lua` 49–66). UncapFPS hooks presentation/update scheduling, including `CChitin::SynchronousUpdate`. | A frame-step/pause cycle must never grant a round. Verify first render and first click with FPS uncapping both off and on. |
| EEex action/sprite patches | `EEex_Action_Patch` includes the default branch of `CGameAIBase::ExecuteAction`; `EEex_Sprite_Patch` hooks sprite events. | No overlap found at the 361 patch bytes. No second call to action dispatch, sprite AI, or effect resolution. |
| `bg-eeex-buffbot` / Bubb's Spell Menu | `BfBotExe.lua` uses both normal `SpellNoDecRES` and deliberate `ReallyForceSpellRES` paths. `B3SpelEx.lua` registers `EEex_Actionbar_AddListener`. | Test normal vs forced casting and opening a spell menu while paused. Never replace an active menu or reinterpret a forced cast. |
| `chriz-overhead-text` / `chriz-fast-traps` | `M_CZOH` touches overhead text/rendering. `M_CZFT` changes modal detection cadence. | Preserve overhead fields and modal pulse counters. 361 only releases the separate Hide re-entry lockout. |
| `chriz-iwd-party-dialog` / `chriz-bg-script-engine` | `M_CIPDLG` has dialogue/hold call gates. BGSE reads `EEex_Sprite_GetCastTimer`, `m_nStealthGreyOut`, `m_bHiding` and `m_modalCounter`. | Dialogue/hold retains ownership of its current action. BGSE sees canonical state without an integration shim. Test observers and queues in an IWD party. |

These are source-level ownership comparisons. Combined live gameplay and install-order permutations were not exercised.

### WeiDU, standalone and IWD collection

The root `setup-chriz-bg-rebalance.tp2` ends with `BEGIN @360 DESIGNATED 360 GROUP @1300` and `PRINT @9365`. Append `BEGIN @361 DESIGNATED 361 GROUP @1300 LABEL ~cbr_time_jump_round_cooldowns~` **after** it. Use a dedicated shared installer function, English/localized TRA text following project conventions and the game predicate `GAME_IS ~bgee bg2ee eet iwdee~` (SoD uses BG:EE). Require EEex availability, e.g. the shipped `M___EEex.lua` capability marker. Verify executable capabilities at native setup. Keep unrelated components' existing predicates.

Proposed standalone tree mirrors [the existing standalone installer](../live-patch/CBR_TRUE_TIMESTOP/setup-cbr_true_timestop.tp2). Track `live-patch/CBR_ROUND_CLOCK/setup-cbr_round_clock.tp2` and its README. During packaging, arrange its shared installer, translations and identical `lua/CBRRC.lua` and `lua/M_CBRRC.lua` from the main source, using `tools/package_timestop.py` as the packaging precedent. Both shapes install the same two override resources. Use separate WeiDU backup directories and reciprocal ownership predicates for **this** component (standalone `DESIGNATED 361`). Avoid two installers taking independent backup ownership of the same resource. A phase-2 rerun must overwrite the two mod-owned payloads even if someone edited them. No live hotpatching or uninstall of an existing installation was performed for this study.

`chriz-bg-collection/recipes/iwd-current` declares EEex, offers its optional components, and includes the `eeex-1.3.1` artifact. Its inspected manifests contain neither a rebalance 361 feature nor the proposed standalone. **After implementation**, Easy IWD can select either standalone 361 after EEex or 361 alone from the main package with the expanded game predicate. Integrating an archive/feature into that recipe is separate work. There is no technical need for Easy IWD to install BG2-only 360 or the rest of the rebalance.

## 7. Verification matrix for Phase 2

Every expected value below is a proposed acceptance check. Preserve the before state, actual world delta, actor full ID, speed/mode, current action and after state. Report native behavior, corrected behavior and unexplained differences separately.

| Layer | Cases | Pass condition |
|---|---|---|
| Native PE contract | Each of the three identified images; test scanner on section boundaries, NULs, partial instructions, two matches, changed patch bytes, cross-image RVAs and foreign detours. | Unique 31-byte signature, exactly seven whole bytes displaced, four validated origins, correct data-section targets, restored original behavior at other origins. Exercise Win64 stack/unwind, register/flags preservation and protection restoration on setup failure. |
| Python scalar and phase simulation | Native single-step oracle vs arithmetic over IDs of both parities, masks 0/1/3 and extra byte masks. Use deltas 0, 1, 15, 89/90, 99/100, 899/900/901, 915, 4,500, 36,000, near signed half range and wrap. | Match the specified virtual-phase tick model, including the first haste increment, partial slow round, negative sentinels, saturation, positive chained jumps and independent timers. A signed backward sync changes nothing. |
| Event model | Native additions vs target-time wrap, host/client forced and drift sync, duplicate same-time sync, two jumps before a world update, pause reversal, load older/newer save, initialization, debug hour and single-stepped time. | One update per committed forward event, even when the native posted delta is overwritten. Ignored short inputs grant zero. No accumulating credit across save load. |
| Object lifetime and transactions | Party transferred between areas, party temporarily without area, loaded enemy/summon, under-list, non-sprite, deleted/recycled slot, remote copy, newly materialized actor, inactive global, actor removed during compression. Test an already queued next action, in-flight spell/item, projectile, swing/half-APR, cancellation and Time Stop exemption. | Locally authoritative eligible IDs visited once. No stale/recycled pointer, award to replacement action, double release, charge refund, hidden attack, message replay or queued-action rewrite. Establish thread ownership for every supported origin. |
| Standalone WeiDU 249 fixtures | BG:EE, BG:EE+SoD, BG2:EE, EET, IWD:EE × main or standalone. Install, reinstall, changed owned Lua, other descriptions, missing/extra spell effects, base/modded data, missing EEex, wrong native byte fixture, and competing owner. Uninstall/reinstall **only in disposable synthetic fixtures**. | Identical intended payloads for each game, component/label/backup ownership correct, content-independent install, clean uninstall from fixture restores its own baseline, native integrity issue logs safely, no unrelated writes/warnings. Test plain Lua and LuaJIT parser/API setup as appropriate. |
| Live build/runtime coverage | Quiet 2.7.3.0 labs. Run common smoke and paused-waylay/short-input checks on BG/SoD, BG2, EET and IWD. Exercise **EEex v1.2.0 and v1.3.1 × internal Lua 5.2 and LuaJIT** on BG2/EET and IWD. Include stock timing and uncapped FPS. | Log build, runtime, unique hook PC, old/new ticks, signed delta, actor lifetime and first eligible world/UI updates. Compare with the same lab natively; verify no crashes on repeated area changes/load/quit. |
| Travel and AI | Finish Stoneskin/Invisibility, drink potion, read scroll, use wand, activate innate; then do an eight-hour trip and a forced/normal waylay. Repeat as party members, summoned ally and enemy, with normal/haste/slow/Improved Alacrity. Exercise zero-duration forced encounter and repeated doors. | When elapsed, completed aura, Hide and residual swing recover as specified; forbid infinite casts from doors. Queued spell starts exactly once and consumes the normal slot/item. First resumed attack has the proper hand/APR. |
| Paused UI | Before travel fail Hide. Enable map-load, enemy-sighted or trap auto-pause separately. Hold pause across entry, examine first drawn spell/item/innate/Hide buttons and click before any unpause. Repeat single-/multi-selection, active menu and early input. | Record cached `+29C` and underlying counter at commit, first paint, first input and next ordinary AI. Hide can be clicked on the first eligible display/input, previous UI page survives, normal spell is accepted/queued while paused and executes on resume. |
| Rest/scripts/Time Stop | Inn and eligible outdoor/dungeon rest; first attempt interrupted at a known reported hour; script `Rest, RestParty, RestNoSpells, AdvanceTime(1/6/60/61), DayNight` into same/earlier/later hour. Campaign transfer alone and with an explicit skip. `B3TimeStep`, Time Stop by player or foe, immune/nonimmune actor and 360 off/on where supported. | Verify actual world time before judging any cooldown. First failed rest on the traced SP path yields no time credit; successful rest retains native resources. No elapsed damage, song, reveal, summons or contingency casting is manufactured by 361. |
| Other affected mechanics and mods | Break stealth, fail Hide, successful hide with continuing invisibility, Find Traps/Detect Illusions, Turn Undead, song/dance, armed contingency, finite script selection lock vs effect/permanent lock. Exercise BuffBot, Spell Menu, BGSE, party dialogue, 121/310/411/420/421 where installable. | Re-entry becomes ready on an elapsed jump. Each periodic worker first fires on its normal native eligibility. Preserve effect durations, command pauses, finite/permanent selection semantics and established mod ownership. |

**Review decisions.** The four-field recovery set, same-event Time Stop freeze, protection of an in-flight transaction and world-based phase for tiny jumps are proposed gameplay semantics. The script-only unselectability case is confirmed and intentionally excluded from that set because both script and effect paths write the same field. The immediate paused-frame contract and native object lifetime/thread model still require lab evidence. No installer, hook, test fixture, live save or release was created by Phase 1.

## Phase 2A native checks, 2026-11-18

The implementation uses the review's single x64 caller/thread filter and Lua recovery core. These are static checks of the three Steam images identified above. Both permitted installed EEex source trees identify themselves as v1.3.1. Their x64 assembly file has SHA-256 `fa0b63523aa331557359666a38bd4c695c4f59c9e1da4b0f95fc0b6277c41033`. The v1.2.0 source comparison is recorded in §6.

- **Stack and broadcast.** `EEex_HookBeforeRestoreInternal` (897–929) jumps to the watchdog entry, supplied assembly, watchdog exit, restored instructions and continuation, in that order. The optional watchdog entry balances its pushes and destroys its shadow space before the supplied assembly. The checker prologue in all three files pushes only RDI and reserves 32 bytes. The return PC is at entry RSP+0x28 (after 128 bytes of flags/GPRs and 96 bytes of XMM saves it would be +0x108). The fast filter reads it after saving flags, RAX and RDX, at **+0x40**. At BG/BG2 `143ABA–143AE1`, IWD `143B3A–143B61`, EBX receives the new time from the packet, ESI zero-extends its next byte, EDI loads the old time, and SIL equal to 1 branches to the store. A drift correction can also reach that store. The checker has not yet overwritten these registers at the hook.
- **Sprite lifetime.** The constructor calls Unmarshal at BG/BG2 `343114`, IWD `343194`. Unmarshal sets the dword at +4EC0 to 1 at `37A417 / 37A447` and clears it using zeroed R14D at `37AD43 / 37AD73`. CheckStatsChange branches out when it is nonzero at `34E844 / 34E874`. Zero admits a completed sprite. The AIUpdate countdown for Hide is a separate dword at +4E70.
- **Time Stop and haste.** The two Time Stop decisions at BG/BG2 `3AB5BA / 3ABA67`, IWD `3AB5EA / 3ABA97`, read game +9690/+9694 and immunity at selected derived stats +2D8. The selector dword +4EA4 equal to zero selects sprite +1DC8 (immunity +20A0), otherwise +1120 (+13F8). DoAction tests 0x8000 in the first dword of the same stats at `392698 / 3926C8`.
- **Registry and field widths.** All three images agree on the structure offsets in §§3–6. +1090 belongs to **Chitin** and points to the game. The network singleton is a separate pointer at RVA `667560 / 66D560`. Area compression reads its byte +2C9 and its dword +374 against object +50. Timer +3FA0, the 12 area pointers +6598, party IDs +6600 and signed word count +6630 match. GetDeny reads signed words for max/serial, compares the slot generation and loads the pointer from inline slot +8. The constructor sets capacity to 0x7FFF at `26BAB9 / 26BB39` and Add requires the next index below capacity. The highest legal index is 0x7FFE. The sprite constructor writes type byte 0x31 (+08). The area pointer (+18), full ID (+48), speed byte (+58), action word (+3F8), cast word (+4990), dword flags (+4994/+4998), attack word (+4B9A), **byte** damage flag (+4BA8), dword swing flag (+4CA0) and dword countdowns (+4E70/+5040) have the same widths in all three builds.

Phase 2B can measure the first paused Hide paint and click using the sequence in §5. If either sees a stale +29C, mark a selected actor's positive-to-zero Hide transition, consume the mark once before the first world-toolbar draw or input, reacquire the current selection and call UpdateButtons on the UI thread. Clear the mark on an ordinary refresh or session destruction. Phase 2A relies on the native toolbar refresh.

### Offline verification of the native gate

All three executables convert the full RDX integer in `lua_pushinteger` at RVA `0D5A97`. Their embedded `lua_pcallk` reads the continuation at `0D6717` and the context at `0D6750`, corresponding to the caller’s outgoing RSP+40 and RSP+32. With the enclosing shadow space already allocated, EEex v1.3.1 expands the nested alignment by zero. The gate explicitly clears both outgoing slots before the generated Lua call.

The installed EEex assembler and hook generator produced identical trampoline assembly under Lua 5.2 and LuaJIT 2.1. An isolated Win64 host assembled and executed the gate with synthetic caller frames and Lua C API stand-ins. Thirteen dispatches covered the four admitted origins, foreign callers, forced-sync filtering, a second OS thread, disablement and both error exits. The host checked the callback arguments, stack alignment, RSP, all 15 GPRs, flags, XMM0–5, counters and replay of both displaced instructions. In-game execution and the paused toolbar check belong to Phase 2B.

The repeatable component suite passed all 32 tests, including the three local Steam images, with `python -B -m unittest -v tests.test_round_clock tests.test_round_clock_installer tests.test_round_clock_standalone`. WeiDU 249 installed both packages on five synthetic editions and restored pre-existing override bytes on uninstall. Package path checks used case-sensitive POSIX names and a lowercased installation tree on Windows.

Full discovery with `python -B -m unittest discover -s tests -p "test_*.py" -v` ran 989 tests in 579.052 seconds. All 963 executed tests passed. The 26 skips belonged to existing tests requiring private captures for dragons (23), Flail of Ages (2) and SR bracers (1).

## Live 2.7.3.0 Lab Verification (Phase 2B)

On 2026-11-18 the Phase 2A build reproduced a first-frame Stealth input failure in both BG2:EE and IWD:EE. The revised 361 enabled the button on its first paused paint and accepted a press delivered even earlier in the same frame. The build also recovered the four personal cooldowns across the qualifying jumps below. Native area compression still controls action cancellation.

### Installations and observations

| Game | Installation and first playable screen | Startup and loaded game |
|---|---|---|
| BG2:EE `Baldur.exe` | Standing Magic Lab, EEex v1.3.1 components 0, 1, 8 (LuaJIT). WeiDU 249 installed 360 and 361 together. `000000010-BuffBot Clean Baseline` loaded in `BFQAAR` with `WORLD_ACTIONBAR`. The temporary quicksave retained the test thief for the revised build. | 361 installed and enabled, 0 Lua errors, 0 off-thread skips. 360 installed and enabled, 0 errors. The log printed `[CBR Round Clock] on (BG2:EE / EET 2.7.3.0)` and `[CBR Time Stop/Haste] on`. |
| IWD:EE `icewind.exe` | Disposable Steam 2.7.3.0 copy, offline profile, Steam DLL disabled. EEex v1.3.1 components 0, 1, 8 with LuaJIT. Standalone `CBR_ROUND_CLOCK` 361 from the worktree packager. A new default party reached `AR1006`. The prologue dialogue was advanced to the world action bar. | 361 installed and enabled, 0 Lua errors, 0 off-thread skips. The log printed `[CBR Round Clock] on (IWD:EE 2.7.3.0)`. The Lua 5.2 configuration is recorded below. |

The BG2 executable SHA-256 was `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`. The IWD executable SHA-256 was `3458b17b1ac0e60d5798a4b2d2dcc62bb458521378564a109b1395c847b320f1`. The revised `CBRRC.lua` installed in both games had SHA-256 `2d9c649ae9037539d4e9d5cf9b15c992f0148d4cd744a3718b1010cdb4c93965`.

The remote observer bracketed the real component callback with reads. At callback entry the engine has already written `m_worldTime.m_gameTime`. The previous clock in the tables is the stored new clock minus the actual signed delta. Each UI sample records its own world tick and paint frame. Pausing can move the visible clock back one tick. Counters restart on session destruction.

### Paused Stealth paint and input

The probe selected one party thief, triggered a failed or broken Hide with the normal toolbar action, and waited for both `sprite+0x4E70 > 0` and a disabled type-11 button. In both games that button occupied slot 5. Each disabled reading came from `game+0x4140+5*0x2A0+0x29C`. A before-item-render listener sampled the first eligible Stealth item after the stock enabled predicate. The click invoked its stock `OnLButtonPressed(5)` action. Modal 3 records the accepted request to enter Stealth. The eventual success of a Hide skill roll is a separate event.

| Build and game | Paused clock before → after | Commit frame → first Stealth paint | Lockout and cached disabled state | Click on that paused frame |
|---|---|---|---|---|
| Phase 2A BG2, `DayNight(15)` | 35144 → 67500 | 9411 → 9411 | Hide 90 → 0, disabled 1 at first paint | disabled 1, modal 0 → 0 |
| Phase 2A IWD, `DayNight(15)` | 32476 → 67500 | 9337 → 9337 | Hide 90 → 0, disabled 1 at first paint | disabled 1, modal 0 → 0 |
| Revised BG2, `DayNight(3)` | 67977 → 121500 | 1833 → 1834 | Hide 90 → 0, disabled 1 at commit exit, 0 at first paint | disabled 0, modal 0 → 3 at 121500 |
| Revised IWD, `DayNight(3)` | 67969 → 121500 | 1829 → 1829 | Hide 90 → 0, disabled 1 at commit exit, 0 at first paint | disabled 0, modal 0 → 3 at 121500 |

On a later still-paused read of the original build the disabled flag had reached 0 at the same world tick 67500, by BG2 frame 9624 and IWD frame 9550. A delayed probe would have missed the failed first click.

A second test issued `DayNight(8)` from slot 0's paused render, before slot 5's enabled query. Immediately before the press, both games still held disabled 1 with Hide 0. The press changed it to 0 and modal to 3. The first subsequent slot-5 paint saw 0 in the same frame. The click and paint occurred at tick 144000, BG2 frame 2715 and IWD frame 2711. No unpaused AI update intervened.

The Phase 2B implementation marked a selected actor's positive-to-zero Hide transition and used a natural rebuild or session destruction to clear it. The world UI resolved the selection and button array on read, press or key. The Win64 helper rechecked the owner thread and activation flag before calling `CInfButtonArray::UpdateButtons`. Phase 2C reproduced a race in that completion listener. Phase 2D changed when a mark is created and who can consume it.

### Natural aura, committed jumps and follow-up casting

With no jump, the BG2 normal Armor (`SpellRES("SPWI102",Myself)`) started at 34401. The cast ended with `m_castCounter=90` at 34491, when a second Armor was queued. It started at 34501. IWD gave 32015, 32105, 32115 respectively. Both start-to-start intervals were 100 world ticks (about 6.67 seconds at 15 ticks/s), with 10 ticks remaining after this slow spell finished. Both commit counts stayed at zero.

For each row, the source was normal Armor or actual `UseItem("POTN08",Myself)`. A separate party actor started a real swing and stopped attacking, leaving an idle attack frame. The selected thief had a real Hide lockout. The caster's native contingency-poll countdown was sampled directly. The harness replenished a prepared Armor slot and supplied potion charges between trials. The field tuple is **caster aura, idle attack frame, thief Hide lockout, caster contingency poll**. All twelve after-tuples were **(−1, −2, 0, 0)** at the commit. The last column measures the first `m_bInCasting=1` for the follow-up from the observed resume tick.

| Game | Source and jump | Old → new world tick | Origin / delta | Before tuple | Commits | Resume → new cast (ticks) |
|---|---|---:|---:|---|---|---|
| BG2 | Armor, `AdvanceTime(2400)` | 144193 → 180193 | 1 / 36000 | (91, 34, 4, 7) | 2 → 3 | 180192 → 180193 (+1) |
| BG2 | Armor, `AdvanceTime(61)` | 180385 → 181300 | 1 / 915 | (91, 34, 55, 8) | 3 → 4 | 181299 → 181300 (+1) |
| BG2 | Armor, `DayNight(6)` | 181490 → 243000 | 2 / 61510 | (90, 33, 56, 9) | 4 → 5 | 243000 → 243001 (+1) |
| BG2 | Potion, `AdvanceTime(2400)` | 243106 → 279106 | 1 / 36000 | (1, 3, 87, 95) | 5 → 6 | 279105 → 279106 (+1) |
| BG2 | Potion, `AdvanceTime(61)` | 279211 → 280126 | 1 / 915 | (1, 3, 87, 95) | 6 → 7 | 280125 → 280126 (+1) |
| BG2 | Potion, `DayNight(22)` | 280229 → 315000 | 2 / 34771 | (0, 2, 88, 96) | 7 → 8 | 315000 → 315001 (+1) |
| IWD | Armor, `AdvanceTime(2400)` | 144191 → 180191 | 1 / 36000 | (90, 35, 55, 9) | 2 → 3 | 180190 → 180191 (+1) |
| IWD | Armor, `AdvanceTime(61)` | 180382 → 181297 | 1 / 915 | (90, 35, 56, 9) | 3 → 4 | 181296 → 181297 (+1) |
| IWD | Armor, `DayNight(6)` | 181487 → 243000 | 2 / 61513 | (90, 34, 56, 9) | 4 → 5 | 243000 → 243001 (+1) |
| IWD | Potion, `AdvanceTime(2400)` | 243104 → 279104 | 1 / 36000 | (0, 2, 89, 97) | 5 → 6 | 279103 → 279104 (+1) |
| IWD | Potion, `AdvanceTime(61)` | 279219 → 280134 | 1 / 915 | (0, 14, 77, 84) | 6 → 7 | 280133 → 280134 (+1) |
| IWD | Potion, `DayNight(22)` | 280244 → 315000 | 2 / 34756 | (0, 9, 81, 89) | 7 → 8 | 315000 → 315001 (+1) |

In the first BG2 and IWD `AdvanceTime(2400)` and `(61)` runs, a follow-up queued before the world consumed its pending native compression disappeared and never began during the observer's 900-frame window. The table uses a command issued while paused once world-screen `+0x9E0` reached zero. Native contingency processing can rearm `+0x5040` to 100 between the commit and the next order. The hook's zero was measured at commit exit.

The first-build action-order trials gave these commit ticks and follow-up start times. Each pair of columns uses the same cast or item and script action as its row.

| Source and native action | BG2 commit tick / follow-up start | IWD commit tick / follow-up start | Commit count in both |
|---|---|---|---|
| Armor, AdvanceTime(2400) | 104326 / none by trial deadline | 104325 / none by trial deadline | 1 → 2 |
| Armor, AdvanceTime(61) | 105689 / none by trial deadline | 105687 / none by trial deadline | 2 → 3 |
| Armor, DayNight(3) | 121500 / 121501 | 121500 / 121500 | 3 → 4 |
| Potion, AdvanceTime(2400) | 157709 / none by trial deadline | 157710 / none by trial deadline | 4 → 5 |
| Potion, AdvanceTime(61) | 159073 / none by trial deadline | 159072 / none by trial deadline | 5 → 6 |
| Potion, DayNight(9) | 256500 / 256501 | 256500 / 256501 | 6 → 7 |

### Travel, rest, short advances and Time Stop

| Scenario | World clock and commits | Cooldowns and input |
|---|---|---|
| BG2 `LeaveAreaLUA` between the quiet interiors | `AR0331` → `AR0330`, 91012 → 91012, commits 1 → 1. Both showed `WORLD_ACTIONBAR`. The reverse direction was also traversed. | A spent Armor aura went 90 → 91 and contingency 95 → 94 on arrival. |
| IWD `LeaveAreaLUA` | `AR1006` → `AR1000`, 315801 before → 315800 at the paused arrival, commits 8 → 8. | Armor aura 90 → 92, contingency 6 → 4. |
| `AdvanceTime(6)` (90 requested ticks) | Both games 315192 → 315194 over the observation interval, commits 8 → 8. | BG2 tuple (90, 33, 56, 9) → (92, 35, 53, 7). IWD (90, 34, 56, 9) → (92, 37, 53, 7). These were ordinary updates. |
| BG2 completed `RestParty()` | 316133 → 352133 (+36000), commits 8 → 9. | (1, 3, 86, 78) → (−1, −2, 0, 0). Follow-up started at 352133, one tick after resume at 352132. |
| BG2 first-attempt monster interruption | 352740 before and after `game:RestParty()`, commits 9 → 9. | (1, 3, 87, 97) on both sides. The live rest-encounter fixture enabled one `GIBBER01` with day and night counters of 200. The first attempt spawned the monster, consumed the day counter to 100, and left night at 200. |
| BG2 op231 while 360 and 361 ran together | At 68434 the stop had 539 ticks left. Paused `DayNight(20)` committed at 90000, origin 2, commits 0 → 1, actors credited 1. | The owner matched the caster ID (139135050), whose spent potion aura went 1 → −1 and poll 71 → 0. The thief (139200587) had derived Time Stop immunity 0 and kept Hide 89. The frozen third actor kept poll 70. The stop still read 539 at callback exit and 360 reported 0 errors. |

**BG2 world-map travel.** The live map screen used a real route, with the local host control bit supplied by the lab driver. The stock Lua map-view opener sets that bit to zero. The driver selected a valid revealed destination and called the stock Travel button's `TravelToSelected()` action. The engine selected the route, loaded the destination, and supplied the duration through `CScreenWorldMap::EnterArea` / `AddCurrentTime`. The driver did not write the timer. The initial single-caster route ran 91944 → 181944, commits 1 → 2, aura 90 → −1 and poll 66 → 0. A separate disposable save placed all three healthy party members at the City Gates entrance for the simultaneous four-field cases.

| Actual route | World clock | Commits | Tuple at callback entry → exit | Resume → follow-up |
|---|---:|---|---|---|
| City Gates `AR0020` → `AR1100`, potion | 67864 → 157864 | 0 → 1 | (0, 3, 88, 36) → (-1, -2, 0, 0) | 157864 → 157864 (next paint frame, +0 world ticks) |
| `AR1100` → `AR0020`, Armor | 158755 → 248755 | 1 → 2 | (90, 35, 55, 15) → (-1, -2, 0, 0) | 248755 → 248755 (next paint frame, +0 world ticks) |
| `AR0020` → `AR1100`, potion, thief reselected on arrival | 249434 → 339434 | 2 → 3 | (1, 3, 88, 22) → (-1, -2, 0, 0) | 339434 → 339434 (next paint frame, +0 world ticks) |

The ordinary arrival selected a toolbar with no Stealth slot. In the reselected case the thief occupied the first portrait. Departure had Hide 88 and disabled 1. On arrival the first eligible Stealth paint was frame 24322 at tick 339434, still paused, Hide 0 and disabled 0. Its click changed modal 0 → 3 in that same frame. The unpaused follow-up cast started at frame 24333.

### In-flight spell and same-process reload

- With the Phase 2A hook, both engines committed `AdvanceTime(2400)` at 292618 during a slow Armor. BG2 kept (aura 16, in-cast 1, action 31) across the callback. IWD kept (15, 1, 31). The native engine subsequently ended the active action. The first observed idle state in each case was (16, 0, 0) at 292618. The revised BG2 build repeated the preservation at 376280, (15, 1, 31) on both sides, commits 3 → 4. At 376281 it read (16, 0, 0).
- Each game saved with `SaveGame(1)` after setting a test global to 36101. The running game then changed it to 36102. Each reloaded `000000001-Quick-Save-2` in the same process, restored 36101, and reported one ended session with a fresh commit count of 0. BG2 reloaded in `AR1100` and committed `DayNight(11)`, 182238 → 265500, to 1 commit and 70 actors. IWD reloaded in `AR1000` and committed `DayNight(13)`, 315965 → 382500, to 1 commit and 29 actors. Both reported enabled, 0 Lua errors and 0 off-thread skips. BG2's 360 again reported 0 errors.

### Embedded Lua 5.2 on IWD:EE

A fresh disposable copy used EEex v1.3.1 components 0 and 1 with the standalone 361, `LuaPatchMode=INTERNAL` and `LuaVersionInternal=5.2`. The `#8` runs above used `LuaLibrary=lua51.dll`, `LuaPatchMode=REPLACE_INTERNAL_WITH_EXTERNAL` and `LuaVersionExternal=5.1-LuaJIT`.

With the file-based remote bridge present, startup stopped after its missing-`io/os` diagnostic. One process exited with `0xC0000409`. Removing that LuaJIT-only loader from the disposable override let 361 initialize under the embedded interpreter. The next driver reached the title and timed out waiting for Single Player while the campaign logo was still on screen. After the driver clicked the stock IWD logo and Single Player, the test completed with all process exit codes zero. The test ran a lab-only menu callback and wrote its measurements to `InfinityLoader.log`.

At both the campaign and main title, 361 reported installed and enabled with zero Lua errors and off-thread skips. The party loaded in `AR1000` with saved marker 36101. Kirika occupied the first portrait and was selected. While paused at 315809 she had Hide 90, slot 5 disabled 1, and 0 commits. `DayNight(19)` moved the clock to 409500 and the counter to 1. Before input the cache still read 1. The stock click produced Hide 0, disabled 0, modal 3 while paused. The first recorded Stealth paint, frame 166 at the same tick, read Hide 0, disabled 0, modal 3. The component still reported zero errors and off-thread skips. The full twelve spell/potion cases above used LuaJIT.

### Quiet-run exits and teardown

All game processes launched through `bg_lab_slots.py run` on the hidden, muted, windowed desktop. Audio preflights exited 0 with every visible session providing a meter reading. Every run recorded **audio_peak = 0.0**, `tripped=false`, `guard_error=null`, identical initial/final pointer clips and zero remaining job processes. The slot wrapper exited 0 for each launch. Its child exit codes distinguish gameplay completion from a contained process failure.

| Guarded game and build | Elapsed seconds | Job process exit codes | Outcome |
|---|---:|---|---|
| BG2 Phase 2A | 717.9 | 0x00000000 ×3 | Baseline, paused defect and in-flight cast |
| IWD Phase 2A | 717.9 | 0x00000000 ×3 | Baseline, paused defect and in-flight cast |
| BG2 revised, first run | 603.8 | 0x00000001 ×3 | Paused fix, mixed trials, rest and interruption measured before a diagnostic crash |
| IWD revised, LuaJIT | 692.9 | 0x00000000 ×3 | Mixed trials, zero-time transition, save/reload and post-reload commit |
| BG2 revised, fresh process | 883.1 | 0x00000000 ×3 | Time Stop, interiors, timed world-map routes, save/reload and in-flight repeat |
| IWD revised, Lua 5.2 with file bridge | 6.0 | 0x00000000, 0x00000000, 0xC0000409 | Stopped during startup after the bridge diagnostic |
| IWD revised, Lua 5.2 without file bridge | 82.1 | 0x00000000 ×3 | 361 initialized. Driver timed out on the campaign screen and shut down |
| IWD revised, Lua 5.2 without file bridge | 9.0 | 0x00000000 ×3 | Title, marked save, paused first input and first paint |

The BG2 diagnostic crash was `0xC0000005`. The stack identifies a lab remote command that supplied a number where `EEex_Sprite_GetAllOfTypeInRange` expects a `CAIObjectType`. Its preceding rest proof had already returned. The fresh BG2 process exited cleanly with 361 installed/enabled, 0 Lua errors, 0 off-thread skips, and 360 at 0 errors. In the IWD bridge-enabled Lua 5.2 attempt the exact faulting instruction was not established.

WeiDU 249 completed each component install and reinstall and the standing BG2 uninstall with exit 0. The 361 focused host suite passed 23/23. The first full offline discovery ran 993 tests in 591.770 seconds with 967 passes and 26 private-fixture skips. The same command, `python -B -m unittest discover -s tests -p "test_*.py"`, ran with the archived dragon, flail and bracer fixtures in 580.105 seconds. **All 993 tests passed, 0 skipped, exit 0.** The 51 private test files staged for this rerun were removed afterward.

The standing BG2 restore used a pre-run byte copy and SHA-256 inventory of the entire game and profile. After uninstalling the two temporary components and restoring the changed files, an independent full comparison returned **0 extra, 0 missing and 0 changed** for all 4,521 game entries (4,343 files, 3,952,935,051 bytes) and 31 profile entries (25 files, 1,504,640 bytes). The override digest hashes compact UTF-8 JSON of sorted pairs of game-relative Windows paths and lowercase file SHA-256 values.

| Standing baseline after restore | SHA-256 or exact inventory |
|---|---|
| `WeiDU.log` | `42ccdaa02fc3e66e9da969b737c45fc7780e155935831561aef957ccecaefadb` |
| 918 override files, sorted relative paths and file hashes | `1db7fe6a7b4552ac7da99c60b3e938285126a0a2b809fa439e7035e8f663d4c7` |
| Profile `Baldur.lua` | `bc017b41227553379315118a0addc02edb464ec4582721c7e560f45b4d309edc` |
| `save/` directories | `000000000-Auto-Save`, `000000001-Quick-Save-4`, `000000004-Quick-Save-TOB`, `000000010-BuffBot Clean Baseline` |

Both the disposable IWD game directory and dedicated Documents profile were removed. The verified recycler handled the OneDrive directory after its test files were deleted. Coverage is single-player Windows BG2:EE and IWD:EE 2.7.3.0 on these fixtures. Multiplayer, other executables, custom action bars and waylaid routes were outside this live run.

The task scratch directory and private fixture copies were removed. The final slot check reported all five slots free and the exclusive `bg-game-install.lock` free. `git diff --check` passed. The three Phase 2B files also passed explicit whitespace checks.

## Phase 2D review fixes and verification

This revision addresses the Phase 2C review of `5489490`. BG2:EE supplied the fresh single-player smoke test. The IWD:EE LuaJIT and embedded Lua 5.2 gameplay results above are from Phase 2B. Waylaid travel, custom action bars and live multiplayer remain open.

### Win64 stack walks and hook publication

In EEex v1.2.0 and v1.3.1, the x64 function-table writer uses declared prologues to emit `UWOP_ALLOC_SMALL` and saves of nonvolatile registers. The old hook adjusted RSP with pushes, LEA and shadow space. Its runtime entry chained straight into the engine checker with zero local slots. The old standalone toolbar helper had no registered entry. Giving the chained hook its own nonempty prologue still let Windows recover the wrong RBX and RSI from the checker's home slots. The fixed hook therefore calls the dispatcher at the checker's original stack depth. The dispatcher, Lua bridge and toolbar helper each own an independently registered function. [EEex v1.2.0 writer](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_Assembly_x86-64.lua#L517-L639) · [EEex v1.3.1 writer](https://github.com/Bubb13/EEex/blob/v1.3.1/EEex/copy/EEex_scripts/EEex_Assembly_x86-64.lua#L517-L639) · [Windows x64 unwind format](https://learn.microsoft.com/en-us/cpp/build/exception-handling-x64?view=msvc-170).

| Registered interval | Stack at a nested call | BG2 lab UNWIND_INFO bytes before any chain descriptor |
|---|---|---|
| Checker trampoline | Same RSP as the original checker body before the CALL | `21 00 00 00` and the original checker RUNTIME_FUNCTION |
| Clock dispatcher | 120 bytes below its function entry | `01 23 01 00 05 E2 00 00` |
| Lua bridge for `CBRRC_Commit` | 120 bytes below entry, RBX saved at RSP+112 | `01 0F 03 00 0A 34 0E 00 05 E2 00 00` |
| Toolbar Lua C function | 40 bytes below entry, RBX saved at RSP+32 | `01 0A 03 00 0A 34 04 00 05 42 00 00` |

The Win64 test calls `kernel32.RtlLookupFunctionEntry` and `RtlVirtualUnwind` at the protected Lua call (`Hardcoded_lua_pcallk`), `CInfButtonArray::UpdateButtons` and `Hardcoded_lua_pushboolean`. It replays the lab's AsmJit instruction windows, including each six-byte CALL and its return PC. With the release scripts supplied, it also runs the real EEex preprocessor, Lua-call generator and function-table writer under Lua 5.2 and LuaJIT. Keystone assembles the output and Unicorn executes it to each exact call, supplying the stack bytes to Windows. Every step checks RIP, RSP and the nonvolatile registers. Moving the RBX save by one slot in each captured unwind record made Windows recover a wrong RBX at both the call and return PC for all three targets. Normal return also preserves the gate's volatile registers, arithmetic flags and XMM values through callees that clobber them. The BG2 process independently resolved all three call sites in its own EEex allocations and walked its registered tables with Windows. The walk reached the checker caller in three frames and the toolbar caller in one. Component 361 itself uses neither FFI nor LuaJIT-specific facilities. [Win64 regression test](../tests/test_round_clock_unwind.py).

The published near jump must resolve to user code outside the entire loaded PE image. EEex packs its code pages bytewise, so a valid trampoline can be unaligned. The injected `E9 F8 FF FF FF 90 90` resolves to `site - 3`. Startup rejected it, restored both original instructions and kept the gate disarmed.

### Selection, toolbar generations and installer identity

The actor loop ages the four scalar fields of every eligible sprite. A positive Hide lockout reaching zero on any actor publishes one new generation after the loop finishes. The first world toolbar read, press or key reacquires the live selection. A successful native refresh consumes the generation it started with. An earlier buttons-updated dispatch can finish after a new jump without erasing that jump. Session destruction discards pending UI work and resets the counters, retaining `lua_errors` when the gate is disarmed.

Binding is optional and runs on initial load and menu reload. Each callable is wrapped independently on the binding metatable or its table-valued `__index`. A replacement method receives a new wrapper. Host tests on both Lua runtimes cover missing and protected bindings, callable userdata and tables, reload on the same metatable, selection changes while paused and an upstream completion listener firing across a newer commit. [Lua regression tests](../tests/test_round_clock.py).

Both WeiDU 249 installer forms probe the first existing entry in stock InfinityLoader's priority list, `Baldur.exe`, `BaldurII.exe`, `icewind.exe`, `SiegeOfDragonspear.exe`. Synthetic SoD installs verified the alias alone, both outcomes of `Baldur.exe` taking precedence, and restoration after standalone uninstall. [Full installer tests](../tests/test_round_clock_installer.py) · [Standalone installer tests](../tests/test_round_clock_standalone.py).

### Multiplayer thread context on the three Steam executables

The single direct call to `CBaldurMessage::OnTimeSynchBroadcast` is inside the message pump. The normal pump runs inline on the game-loop thread. Disassembly and loader symbols establish the following path independently on each of the three 2.7.3.0 images listed at the top.

| Call or virtual dispatch (hex RVAs) | BG:EE and BG2:EE | IWD:EE |
|---|---|---|
| WinMain → SDL_main → CChitin::WinMain | `5672CF → 137150`, `137203 → 41CD90` | `56815F → 1371D0`, `137283 → 41DA40` |
| Game loop → CChitin::Update, then vslot +E8 | `41CFCB → 41CAC0`, call at `41CBE5` | `41DAAB → 41D770`, call at `41D895` |
| CBaldurChitin vtable slot → AsynchronousUpdate → message pump | `58DDE8 → 131C10`, `131C4E → 205060` | `58FDE8 → 131CA0`, `131CDE → 2050E0` |
| Message pump → OnTimeSynchBroadcast → post-store clock checker | `2086F7 → 143A80`, `143AFB → 2513A0` | `208777 → 143B00`, `143B7B → 251420` |

The constructors load the relevant vtables at BG/BG2 `130EEC` and IWD `130F0C`. The five other direct calls into the same pump are the close-session poll, store buy click, two world updates and ground click. BG/BG2 call sites are `13D33F, 2E2E31, 2EBF2E, 2EBF80, 2F38DC`. IWD sites are `13D3BF, 2E2EB1, 2EBFAE, 2EC000, 2F395C`. These calls dispatch on their invoking thread. The native area compressor compares the network byte at `+2C9` with exactly 1 before comparing the actor's owner with `network+374` (BG/BG2 `17DBF5–17DC15`, IWD +`80`). The host tests verify 0, 1, 2 and 255.

**Multiplayer has static verification only and has never been live-tested.** Only an admitted call on the thread captured at initialization enters Lua. On any other thread the gate increments `off_thread_skips` and immediately returns to the native path. The engine has already stored the new clock. The skipped delta grants no personal recovery and is never replayed.

### Focused BG2:EE 2.7.3.0 quiet run

WeiDU 249 installed components 360 and 361 together in the standing BG2 Magic Lab with EEex v1.3.1 and LuaJIT. The worktree and installed `override` files matched byte for byte by SHA-256.

| File | SHA-256 in the final smoke |
|---|---|
| `CBRRC.lua` | `37e7a2d1879eb3f8972638ab248c36e9cffde043d54b99c653ef628bef02f584` |
| `M_CBRRC.lua` | `758b00a84b3f1ad1ebb5b14c61b53aa3363e9252ccd29056e90976b1c8bc1584` |

The driver loaded a disposable copy of `000000010-BuffBot Clean Baseline` with the first portrait set to Thief. It paused the world, seeded the four cooldown fields on that character and selected the stock Thief action bar. During the render of slot 0, the driver issued the engine action `DayNight(13)`. A read-only observer sampled the counters around `CBRRC.Commit`. The first slot-5 paint listener ran after the stock enabled predicate and pressed `buttonArray:OnLButtonPressed(5)`. All four samples below were on **paused frame 391**. The disabled flag is the dword at `game+0x4140+5*0x2A0+0x29C`.

| Paused sample | World tick | Cast aura +0x4990 | Attack round +0x4B9A | Hide +0x4E70 | Contingency +0x5040 | Slot 5 disabled | Modal |
|---|---:|---:|---:|---:|---:|---:|---:|
| Before `DayNight(13)` | 31506 | 36 | 27 | 90 | 82 | 1 | 0 |
| Commit exit | 58500 | −1 | −2 | 0 | 0 | 1 | 0 |
| First Stealth paint | 58500 | −1 | −2 | 0 | 0 | 0 | 0 |
| After stock click | 58500 | −1 | −2 | 0 | 0 | 0 | 3 |

`CBRRC.Status()` reported installed and enabled, one commit, three actors, zero Lua errors and zero off-thread skips. `CBRTC.Status()` reported installed and enabled with zero errors. Audio preflight read all seven session meters. The 16.1-second hidden-desktop run recorded `max_job_audio_peak = 0.0`, three process exits of `0x00000000`, matching initial and final pointer clips and an empty job.

WeiDU removed both test components with exit 0. The pre-run and post-restore manifests map each relative path, using forward slashes, to its file SHA-256 or JSON null for a directory. The manifest digest covers UTF-8 `json.dumps(entries, sort_keys=True, indent=1)` with no trailing newline. Independent comparisons returned **0 extra, 0 missing, 0 changed** for each root. All five lab slots and `bg-game-install.lock` were free.

| Restored root | Files / all entries | SHA-256 of both manifests |
|---|---:|---|
| `C:\Users\chris\CEBG-Tests\Magic-Lab-20261104\bg2ee` | 4,343 / 4,521 | `c64ea97503bc30aa754767088818ae2143f4d122b919632d7610c7a358efa792` |
| `C:\Users\chris\OneDrive\Documents\Chriz BG Magic Lab BG2EE - 20261104` | 25 / 31 | `2f445be2b7fadfe73854ce43c08cfeae9d6683e36ecfe07de6f6e820c6e864a4` |

#### Earlier Phase 2D run at `a030734`

The two trials below used `CBRRC.lua` SHA-256 `780fb70715e4443b67df3d852a12d0f3a4aea7f33115d6b2f1f77926598607fc`. They ran in one guarded process using the BuffBot Clean Baseline save. The lab driver prepared the thief in memory. Each trial began with a normal Armor cast, a stopped attack and a thief with a positive Hide lockout and slot 5 disabled. The observer bracketed the real commit and sampled the first Stealth paint after the stock enabled predicate. The press used the stock button handler on that same paused frame.

| Scripted action | Old → new world tick | Aura, idle attack, Hide, contingency at commit | Commit / first paint / click frame | Resume → follow-up Armor start |
|---|---|---|---|---|
| `DayNight(13)` | 31763 → 58500 | (90, 33, 56, 38) → (−1, −2, 0, 0) | 922 / 922 / 922 | 58500 → 58501 |
| `AdvanceTime(2400)` | 58920 → 94920 | (90, 33, 56, 83) → (−1, −2, 0, 0) | 1768 / 1768 / 1768 | 94920 → 94921 |

In both trials the slot's `+0x29C` was 1 at commit exit and 0 on the first paint. The click changed modal 0 → 3 at the same paused tick. The follow-up spell was queued after native area compression drained. Final status was 361 installed and enabled, two commits, six actors credited, zero Lua errors and zero off-thread skips. Component 360 was enabled with zero errors.

The audio preflight returned 0. The 167.2-second run closed the remote bridge on game shutdown. The guard measured audio peak 0.0, three process exits of `0x00000000`, no guard trip and no remaining job process. After uninstalling the two test components, a fresh SHA-256 and path comparison against both pre-run snapshots returned **0 extra, 0 missing, 0 changed** for the game (4,521 entries, 4,343 files) and profile (31 entries, 25 files). All five lab slots and the exclusive install lock were free.

### Offline verification and package identity

The six-module focused suite passed **78 tests in 38.467 seconds, zero skips**. With a throwing `__tostring`, both Lua 5.2 and LuaJIT preserved the stock paint and click return values through six failed refresh attempts, including two key presses. Each host recorded one refresh diagnostic even when its logger raised. Once the selection recovered, the pending bar refreshed, and `CBRRC_Commit` still returned 0 with `lua_errors = 0`. The startup loader also reported an unprintable error and normalized a multiline error on both runtimes. [Fault-isolation tests](../tests/test_round_clock.py).

The bytes defining `BuildGate`, `commitBridge`, `CBRRC_CaptureThread` and `CBRRC_UpdateButtons` matched `a6205aa`. The Win64 audit walked the recorded call sites and generated fresh frames using the EEex v1.2.0 and v1.3.1 writers. For fresh Win64 frame generation, put the libraries from `research/timestop-lab/requirements-native.txt` on the Python path and set `CBR_EEEX_SCRIPTS` to the release script directories, separated on Windows by a semicolon. [Win64 regression test](../tests/test_round_clock_unwind.py).

Full discovery with `python -B -m unittest discover -s tests -p "test_*.py"` ran **1,010 tests in 658.718 seconds**. There were 1,009 passes, zero failures, zero errors and one skip. `test_sr_bracers.BracersTests.test_captured_stream_install_and_tempus_helpers` reported `private captured resources not present` for `.worktrees/sr-bracers-captures`. The run used the archived dragon and flail fixtures, a standalone interpreter in `CBR_LUA`, and copies of all three 2.7.3.0 executable images with the SHA-256 values in the evidence table.

The earlier Phase 2D full discovery at `a030734` passed all 1,002 tests in 567.953 seconds with zero skips, including 45 Round Clock tests. That run used the archived dragon, flail and bracer fixtures and removed the 51 staged files afterward.

The Phase 2D package build keeps the installer version at `v0.8.11`. Four archive names are also used by the published release, so the branch builds are local verification artifacts. The Round Clock standalone is the fifth archive. Two independent invocations of `python -B tools/package_timestop.py --output <temporary-directory>` produced byte-identical ZIP pairs with matching SHA-256 sidecars and valid member CRCs.
