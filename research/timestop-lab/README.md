# Time Stop / Haste observation lab

This is disposable research infrastructure, not a balance component. The observer records
native decisions without correcting clocks, rebuilding buffs, replacing healing,
or changing attack/movement scheduling. A separate correction prototype, `CBRTFix.lua`,
corrects two clocks for one selected subject and the two lab fixtures only
([below](#correction-prototype-cbrtfixlua)). No hooks activate merely by loading
either Lua module. The startup and hook-integration smoke test passed on EEex 1.3.1
([below](#engine-smoke-test-eeex-131-2026-10-20)). So did the first native baseline
capture, `baseline_01` ([below](#baseline-capture-baseline_01-2026-10-20)), the two
native Time Stop captures, `timestop_01` and `timestop_02`
([below](#time-stop-captures-timestop_01-and-timestop_02-2026-10-23)), and the four
native Haste captures, `haste_01` to `haste_04`
([below](#haste-captures-haste_01-to-haste_04-2026-10-23)). The first four corrected
captures followed on 2026-10-23
([below](#corrected-captures-fixctl_01-fixstop_01-fixhaste_01-and-fixhaste_02-2026-10-23)).
They cover the fixture cases of the acceptance plan, not all of it. The clock fix itself is
a separate EEex mod, Chriz BG Time Clocks. A second lab built from the same scripts, the
[Time Clocks lab](#time-clocks-lab-2026-10-23), measured it against the native game
([results](#time-clocks-captures-2026-10-23-and-24)).

The diagnosis, instruction evidence and open design questions are in
[`../10-timestop-haste-engine-clocks.md`](../10-timestop-haste-engine-clocks.md).

## Isolation and provenance

- Game: `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0`.
- Engine/profile name: `CBR TimeStop Lab 2730`. The profile is resolved through
  Windows Known Documents; on this machine that is
  `%USERPROFILE%\OneDrive\Documents\CBR TimeStop Lab 2730`.
- Source: pristine Steam BG2:EE 2.7.3.0, copied as physical files. No existing
  saves or settings are imported. The source tree is hashed before and after setup.
- Executable SHA256:
  `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
- EEex 1.3.1, tag commit `a6d21abe44e20509f5d0259ccc6c7e7f9d12b285`, the version
  Christopher chose for everything on 2026-10-18; official components 0, 1 and 8
  (core, main, LuaJIT). The staged `EEex` tree (134 files, 33,554,881 bytes) has the
  lab digest `cd776455c2c9202dcffa526d7ccd81c496bbf8c99d9cd4e260e9ed4bc3b826bd`.
  This replaces the earlier EEex 1.3.0 pin (`9e8098ee696ca4b0bc055e7ff74b283704a8c02e`).
- WeiDU 25100, SHA256
  `0d17e26e3f3ef5b36796eb0ee8ae73cb851d8b62c9702c2e224da2945caafb75`.
- Remote Console 0.2.0, commit
  `661927e56e28435541a3128568cd4ee6d5d80164`; only its Lua/menu files are
  staged in this lab. Diagnostic resources are also staged directly and recorded
  separately from the official EEex installation.

EEex component 9 (Attack Info) is not installed, and a WeiDU.log line for it is
refused. The component only sets `Enable=1` for the Attack Info module in `EEex.ini`
(default `0`), an in-game to-hit display this observation does not need. Its TP2
declaration is unchanged since 1.3.0, which excluded it in the same way.

Compared with 1.3.0, the 1.3.1 tag changes the TP2 version line, UI, keybinding and
utility Lua modules, translations, the pattern database and the loader/EEex DLLs.
Every Lua file that defines an EEex function `CBRTObs.lua` calls, the
`Data-CGameEffect::vftable` pattern and the 2.7.3.0 `function_names.db` are
byte-identical, so the instruction evidence in the research note still applies.
The native primitives (`EEex_Read32`, `EEex_Malloc` and others) come from the changed
DLLs. This is a static comparison; only `CBRTS.Inspect()` and `CBRTS.Install()` in the
engine show that the observer works with 1.3.1.

The game and profile carry matching ownership markers. Paths outside the exact
lab are rejected. Junctions, symlinks and hard links are rejected; verified
Microsoft Cloud metadata is permitted only along Known Documents and this
profile, because OneDrive uses non-redirecting reparse points there.

The setup derives safeguards from `bgee-itemrandomiser-fix/tests/runtime/` and
its handover. Its older, hardcoded EET runner is not used against this lab.
The active modded game remains a read-only reference.

## Offline preparation

Use PowerShell 7 from the repository root. Inputs must match the fingerprints
above. The archive argument is the parent of the extracted `EEex` directory.

The EEex input is a `git archive` export of the pinned tag commit, extracted with
`Expand-Archive`. With `core.autocrlf=true`, Git writes its text files with CRLF line
endings on every platform, as the digest requires. The same command reproduces the
1.3.0 digest from that tag. The release asset `eeex-v1.3.1.zip` (SHA256
`9c8104bd63fe7e7dfff889d89ab2d98e158b6e552846370a924ed7eacea4ecf3`) contains the same
134 files, but 113 text files have LF line endings, so its tree digest
`67e86dbabefa412ce0d510270e95d99e45b9a0356308802b687918fa37609e1a` is refused.

```powershell
$eeex = Join-Path $env:TEMP 'cbr-timestop-lab-20261018'
git clone https://github.com/Bubb13/EEex.git "$eeex\repo"
git -c core.autocrlf=true -C "$eeex\repo" archive --format=zip "--output=$eeex\EEex-v1.3.1.zip" a6d21abe44e20509f5d0259ccc6c7e7f9d12b285
Expand-Archive -LiteralPath "$eeex\EEex-v1.3.1.zip" -DestinationPath "$eeex\EEex-v1.3.1"
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Copy `
  -EEexArchiveRoot "$eeex\EEex-v1.3.1" `
  -WeiduPath "C:\Games\Baldur's Gate II Enhanced Edition modded\Setup-Branwen.exe"
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Install
pwsh -NoProfile -File research/timestop-lab/Prepare-Lab.ps1 -Phase Validate
git -C C:\src\private\eeex-remote-console worktree add --detach "$eeex\rc-661927e" 661927e56e28435541a3128568cd4ee6d5d80164
pwsh -NoProfile -File research/timestop-lab/Stage-Diagnostics.ps1 -RemoteConsoleRoot "$eeex\rc-661927e"
pwsh -NoProfile -File research/timestop-lab/Invoke-Lab.ps1
```

Staging copies the Remote Console files only from a clean checkout whose HEAD is the
reviewed pin. `-RemoteConsoleRoot` names that checkout or worktree. The default, the main
checkout, is refused as soon as its HEAD moves on, even by a documentation-only commit.
Staging also builds the lab's QA copy of `UI.MENU` from the lab's own stock file
([fresh test party](#fresh-test-party-in-the-hidden-game)).

These commands do not launch the game. Copy resumes only matching owned files;
an uncertain installation stops for inspection. There is no uninstall or reset
operation. The ownership markers bind the EEex commit, so a lab created under the
1.3.0 pin is refused (`INVALID_OWNERSHIP_MARKER`). A leftover profile folder without
its lab blocks Copy (`PROFILE_ALREADY_EXISTS_UNRELATED`). Neither is removed
automatically. Staging refuses differing assets unless `-Refresh` is supplied and the
existing hashes still match its previous ownership manifest.

The manifests, source inventory and installation logs remain in the disposable
lab. The repository contains no game executable, save or copied proprietary data.

## Runtime coordination

`Invoke-Lab.ps1` without `-Launch` is the read-only preflight. It checks the ownership
markers, the installed EEex files, the executable and the staged diagnostic assets.

On Christopher's PC the game starts only through the verified quiet runner
`lab_quiet_run.py` from the local lab tools. It uses a hidden desktop, a muted windowed
profile, a job object, and guards that stop the game on audio, a pointer clip, a gamma
change or a foreground window. `Invoke-Lab.ps1 -Launch` is not that runner: it starts the
loader with a plain `Start-Process` on the user's desktop, so do not use it there.

Before the first quiet run:

1. Rename the lab copy's `steam_api64.dll` to `steam_api64.dll.bgse-disabled`, so that
   Steam Cloud cannot sync this profile. The runner refuses an active Steam DLL.
2. Run `python -I lab_quiet_run.py prepare <lab> <profile>`. It makes the profile
   windowed and sets every volume to 0, keeping `Baldur.lua.before-quiet-lab` as a backup.

Install, staging and the preflight refuse while a process runs from the lab or from the
source game, and while a `Baldur.exe` or `InfinityLoader.exe` runs whose image path cannot
be read. Other labs' games do not block them: since 2026-10-18 the parallel lab slots
(`bg_lab_slots.py`) let up to five hidden lab games run at once, and these scripts touch only
this lab. (Until 2026-10-23 any running game refused them.)

The Time Stop captures took the exclusive `bg-game-install.lock` of the shared lab
coordination folder, waited until no BG game ran, then ran
`python -I lab_quiet_run.py run <lab> <profile> <out.json> 600`. The slots start nothing
while that lock is held. The Time Clocks lab runs through a slot instead:
`python -I bg_lab_slots.py run <lab> <profile> <out.json> <seconds> --owner … --purpose …`,
which waits only for its own lab and refuses while OBS or Streamlabs runs. Either way the
run ends at its time limit, on a message box, or when the game exits; `<out.json>` records
the guards' result. A lock or slot is released by renaming it only after no process runs
from the lab, and only by its holder.

A failed or uncertain startup is an inspection point, not permission to retry
repeatedly. A surviving process still blocks the next run.

Use only this lab's `override` for Remote Console commands, one command at a time.
First verify the running executable path and perform the client's `ping` and
watchdog checks; a leftover ready file is insufficient. An action-queue response
does not prove the action executed. Check resulting actor/effect state after
engine ticks. Do not import a playthrough save for convenience.

## Fresh test party in the hidden game

The hidden game gets no mouse or keyboard input, and the Remote Console polls only while
START or WORLD_ACTIONBAR renders. A new game therefore goes through the game's own buttons,
clicked with `Infinity_ClickItem`, Christopher's choice on 2026-10-20.

- **QA menu.** `qa_menu.py` reads the stock `UI.MENU` from `chitin.key`/BIF and writes a
  lab-only copy. It names 18 stock items (`CBRTSQA_*`): the SoA logo, Single Player, New
  Game, the character-creation buttons, Import's Character File, the Done buttons, the
  difficulty and the dialogue confirm button; since 2026-10-23 also the quick save button of
  the world's left sidebar, Single Player's Load Game and the LOAD screen's Load button. Each
  name is added only where exactly one item with the stock action exists. It also adds an
  inert START label (2.7.3 reopens START after the campaign choice only on the next mouse
  event) and a 1×1 polling widget to the 13 menus that cover START during character
  creation, dialogue and loading. The builder is idempotent and
  refuses unknown actions, ambiguous or missing items and name collisions.
  `qa_menu.py describe <lab>` prints the expected hash. `Stage-Diagnostics.ps1` builds the
  copy into the lab (`cbr-generated-qa-menu-<sha16>`), stages it as `override/UI.MENU` and
  records the builder, stock and output hashes. The preflight checks it like every other
  staged asset.
- **Client.** `lab_rc.py` (`procs`, `ready`, `lua`, `collect`) talks only to this lab's
  `override`, requires exactly one `Baldur.exe` from the lab, and refuses while a request is
  pending. A request that times out is never resent: `collect` waits for the same request,
  because the console stays deaf during a cutscene. `--arg` values reach Lua as decimal
  byte escapes in `ARGS`, never as code. `--delay` waits before sending, for a timed case.
  A game that exits can never answer: `--expect-exit` (for `rc/quit.lua`) and `collect`
  end with status `exited` once the lab's game is gone, and move a request file the game
  never claimed out of `override`, so that no later start runs it. Every exchange is logged
  under `<lab>\cbr-timestop-output\rc-log\`.
- **Requests.** `rc/*.lua` holds the requests. Read-only: `ping`, `state`, `menus`,
  `status`, `subject`, `nearby`. Changing: `watchdog`, `install`, `arm`, `stop`, `export`,
  `start-soa`, `click`, `pick-character`, `set-name`, `dialog`, `pause`, `queue`, `quit`,
  and `fix` for the [correction prototype](#correction-prototype-cbrtfixlua), whose
  `op=status` only reads. Each changing request checks its precondition first (menu on the
  stack, no transition, paused game, armed or disarmed capture, the subject's name).
- **Time Stop trigger and clocks.** `queue what=timestop` makes the controller in portrait 1
  wait `SmallWait(N)` AI updates and then apply `CBRTSTP` to itself, so it is the caster
  and the subject is frozen. It refuses without an armed capture, without exactly one of
  each fixture on the subject, while a stop runs, with a busy controller, or with the subject
  as controller. `queue what=fixtures` refuses while a fixture from an earlier case is still
  on the subject. `subject` also reports each actor's current action and the raw counters
  behind native effect timing on 2.7.3.0:
  - `+0x3A0`: the full effect check runs only when this value mod 15 equals the actor ID
    mod 15 (`0x3ABB7C–0x3ABBC5`).
  - `+0x1A08+0x38`: the regenerated periodic list's counter, which the dispatcher copies into
    each worker (`0x22653D`).
  - `+0x520C`: the frozen-actor marker (`0x3ABA9D`).
  - `+0x4BA4`: `m_newEffect`, which is set when a stop ends (`0x3ABACE`).
- **Haste trigger.** `queue what=haste` makes the subject wait `SmallWait(N)` AI updates and
  then apply `CBRTHST` (Haste) or `CBRTIHS` (Improved Haste) to itself. It refuses without
  an armed capture, with a busy subject, with a Haste fixture already on it, with a partial
  or doubled fixture set, or while a stop runs. `subject` lists the Haste fixtures with their
  deadlines. Its `ai_speed` is `m_AISpeed` (`+0x58`): 1 at normal speed, 0 while hasted.

The 2026-10-20 sequence: `ping`, `watchdog`, `ping`, `state`, `install`, `status`, then
`start-soa`, `click` Single Player and New Game, `click` Import and Character File,
`pick-character "Abdel - Fighter - Neutral Good"` (the pregenerated character shipped with
the game), `click` Appearance, colors Done and sounds Done, `click` Name,
`set-name "CBRTS Subject"`, `click` Accept and the difficulty. During the SoA opening the
console was deaf for about two minutes, so `collect` picked up the menu probe. Then
`dialog confirm-on`, 11 `dialog step` requests through Imoen's dialogue (first reply each
time), `pause paused`, `dialog confirm-off`. Imoen joins and is the second actor. In
AR0602 the nearest hostile, a Smoke Mephit, stood about 1,200 pixels away. The caged
NPCs and the Jailkeep Golem are neutral.

## Diagnostic controls

`M_CBRTS.lua` loads `CBRTObs.lua` and `CBRTFix.lua` and exposes `CBRTS` and `CBRTF`.
It does not install hooks. The first engine session must verify the command surface and
hook integration before measuring any gameplay behavior. The steps below are the
observer's; the correction prototype's controls are
[further down](#correction-prototype-cbrtfixlua).

1. `CBRTS.Inspect()` checks the owned lab, image identity, vtables and all eight
   instruction windows. Unexpected bytes stop installation before the first patch.
2. `CBRTS.Install()` compiles recording bodies and explicitly installs the hooks.
   They remain disarmed. An interrupted installation requires a clean process
   restart; do not try to undo or reapply partially installed hooks in place.
3. In a fresh test game, pause and choose one nonimmune, noncaster subject with
   missing HP. A second actor is the Time Stop controller.
4. `CBRTS.Arm(0)` selects portrait zero, records its pointer plus object ID, and
   opens one capture epoch. Arm **before** applying the fixtures so construction
   and worker lineage are visible. Existing workers cannot be retroactively linked.
5. Apply the exact native fixtures below, unpause, and observe one short case.
6. Pause, call `CBRTS.Stop()`, then call `CBRTS.Export("baseline_01")` in a
   **separate** command. Export refuses an existing filename. Read `CBRTS.Status()`
   for overflow, session destruction or other incomplete-capture indicators.
7. Decode the resulting file offline. Export before rearming. Never carry an armed
   capture across load, area travel, actor replacement or a return to the main menu.

Native recording uses a bounded 8,192-record buffer, preserves flags/registers,
and makes no Lua callbacks or file writes in the intercepted timing paths.
Overflow disarms instead of overwriting earlier evidence. Each record is committed
last; the decoder flags incomplete reservations. These choices reduce disturbance;
they do not establish engine-thread quiescence, negligible timing overhead or live
safety. First compare an uninstrumented control with installed-but-disarmed hooks.

| Fixture | Native effect | Purpose |
|---|---|---|
| `CBRTBUF` | op0, -2 AC, six seconds | One simple finite buff |
| `CBRTREG` | op98, p1=2/p2=3, twelve seconds | One native HP every two seconds |
| `CBRTHST` | op16, p2=0, twenty seconds | Native Haste control |
| `CBRTIHS` | op16, p2=1, twenty seconds | Native Improved Haste control |
| `CBRTSTP` | op231, encoded twelve seconds | Native six-second Time Stop request |

The engine must confirm actual durations. These resources have one single-target
ability and one effect, no TLK or secondary-resource dependency, and no area effect.
Baseline fixtures ignore MR and are nondispellable; use explicit source removal
for the first removal test, not a dispel check that cannot affect this fixture.

## Evidence and smallest next test

Eight sites cover parent pre-expiry/removal, regeneration worker creation/copy,
pre/post dispatch, native healing submission and worker destruction. The binary
schema is `CBRTS001`: 128-byte header and 128-byte records. Addresses are diagnostic
identities scoped to a capture; the decoder tracks generations and rejects ambiguous
reuse. A healing submission is not counted as successful healing by itself; the
decoder pairs pre/post-worker HP readings. This first buffer observes regeneration,
not every periodic opcode or arbitrary removal route.

```powershell
python -B research/timestop-lab/decode_trace.py `
  '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\cbr-timestop-output\baseline_01.bin' `
  --json '%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\cbr-timestop-output\baseline_01.json'
```

Decoder exit 0 means structurally complete evidence, **not** gameplay acceptance.
Exit 1 means incomplete/ambiguous capture; exit 2 means invalid input or I/O failure.
Time Stop records are sampled observations, not invented exact start/end edges.

The engine sessions have four bounded steps:

1. A fresh baseline with the one subject, buff and regeneration effect. Verify
   native HP amount, buff expiry, worker construction and rebuilding, and complete
   trace decoding. **Done on 2026-10-20** as `baseline_01`
   ([results](#baseline-capture-baseline_01-2026-10-20)), after the startup/IPC and
   hook-integration smoke test.
2. Repeat with a separate controller's Time Stop when about twenty game ticks
   remain on the buff, away from a pulse boundary. Measure the native expiry and
   periodic phase through the stop; do not correct either yet. **Done on 2026-10-23**
   as `timestop_01` and `timestop_02`
   ([results](#time-stop-captures-timestop_01-and-timestop_02-2026-10-23)).
3. Repeat without Time Stop, entering/leaving native Haste midway through a pulse
   interval. Compare native healing cadence in world ticks. Movement and attack
   controls become acceptance requirements when a correction is proposed. **Done on
   2026-10-23** as `haste_01` to `haste_04`
   ([results](#haste-captures-haste_01-to-haste_04-2026-10-23)).
4. Correct both clocks for the subject and the two fixtures, then repeat the control, the
   Time Stop case and Haste entering and ending. **Done on 2026-10-23** as `fixctl_01`,
   `fixstop_01`, `fixhaste_01` and `fixhaste_02`
   ([results](#corrected-captures-fixctl_01-fixstop_01-fixhaste_01-and-fixhaste_02-2026-10-23)).

Steps 1 to 3 resolved the disputed engine paths, and step 4 tested the first
actor/effect-scoped correction against them. Attack and movement rates, caster/immune
behavior, Slow, area effects, SR/SCS maintenance graphs, consecutive stops,
removal/refresh and save/load remain explicit later gates. This lab has no current-save
safety claim.

## Engine smoke test (EEex 1.3.1, 2026-10-20)

This covered only README step 1: startup, Remote Console and hook integration at the fresh
main menu. Nothing was armed or measured, and no save was created or loaded.

- **Build.** The `git archive` export of the tag commit reproduced the pinned tree digest.
  Copy, Install, Validate and staging passed. `WeiDU.log` lists exactly components 0, 1 and
  8 at v1.3.1. The Remote Console files came from a clean worktree at their pin.
- **Runs.** There were two quiet runs through `lab_quiet_run.py run`, 600 s each, while
  holding the exclusive lock. Neither tripped a guard: audio peak 0.0, pointer clip
  unchanged, no message box, nothing left in the job. Both ended at their time limit.
- **Remote Console.** Each run rewrote the ready file. `ping` answered. A runaway loop
  stopped at a 2,000,000-instruction watchdog, and the game answered again afterwards.
- **Run 1.** `CBRTS.Inspect()` passed: image base `0x140000000`, 8 sites, 2.7.3.0.
  `CBRTS.Install()` stopped in its fresh-main-menu check, at `CBRTObs.lua:66`: "attempt to
  call method 'GetActiveEngine' (a nil value)". The EEex binding object
  `EngineGlobals.g_pBaldurChitin` has no such method. The engine global `e` is the same
  object and has it, and the bound field `pActiveEngine` equals `m_pEngineStart` at the main
  menu. Nothing was patched: `installed` and `failed` stayed false, no buffer was allocated,
  and all eight sites kept their original bytes.
  - Fix: the check reads `chitin.pActiveEngine`.
  - `test_observer.py` now runs `Install()`'s precondition with bindings shaped like 1.3.1.
    With the old accessor, its new tests fail with the lab's error.
- **Loader cache.** Run 1 also showed that InfinityLoader adds its own cache to
  `InfinityLoader.ini`: one `CachedExeTime=` and four `CachedAddress=` lines under
  `[Auto-Generated]`. The preflight compared raw hashes, so it refused every launch after
  the first.
  - It now ignores exactly those loader lines; every other byte must still match the
    validated installation.
  - `Test-LabGuards.ps1` covers both cases. Mutants that keep the raw hash, strip such
    lines anywhere in the file, or accept any value all fail.
- **Run 2.** This was a fresh process with the fix re-staged (`-Refresh`). The preflight
  passed after the earlier launch, and `Inspect()` passed again. `Install()` returned
  `installed=true`, 8 sites and `armed=false` in 10 ms. `Status()` showed `failed=false`,
  `reserved=0`, `overflow=0` and no active recorder. All eight sites now start with `E9`, a
  jump to their hook. Ping and status still answered a minute later.

## Baseline capture `baseline_01` (2026-10-20)

This was step 1 of the engine sessions: measurement only, no clock correction.

- **Run.** One quiet run through `lab_quiet_run.py run … 1800`, holding the exclusive lock,
  ended after 864 s by `rc/quit.lua` (the stock `Infinity_ShutdownGame`, no save). No guard
  tripped: audio peak 0.0, pointer clip unchanged, nothing left in the job. The QA menu was
  `61dd3832…8b78`, built from the stock `7987e9d3…31fe` in `data/Patch2.bif`.
- **Party.** A new SoA game on Venture through the [fresh-party
  sequence](#fresh-test-party-in-the-hidden-game). Portrait 0: "CBRTS Subject", the
  pregenerated fighter Abdel, 98 HP, in AR0602. Portrait 1: Imoen. AI speed byte 1
  (normal) and no Time Stop throughout. While the capture was disarmed,
  `ApplyDamage(Myself,20,0)` lowered the subject from 98 to 83 HP. That 20 requested
  crushing damage removed only 15 HP was not investigated; the fixtures do not depend on it.
- **Case.** At world 33172, paused: `Arm(0)` (epoch 1), then the queued `ApplySpellRES` of
  `CBRTBUF` and `CBRTREG`. Both ran within that paused request: a probe at the same tick
  already showed deadlines 33262 and 33352, timing `0x1000`. The game ran from 33172 to
  33434 (262 ticks, about 17.5 s). Then `Stop()`, and `Export("baseline_01")` as a separate
  request: 451 records, no overflow, no failure, no active recorder. The file is the 8-byte
  magic, the 128-byte header and 451 records. It stays in the lab, with its decoded JSON/CSV
  and the request log.
- **Decoding.** `decode_trace.py` exited 0: status complete, 451 of 451 records committed, no
  issues, 179 paired dispatches, 436 fixture events and 15 unattributed lifecycle events.

| Check | Native result |
|---|---|
| HP amount | 6 healing submissions, each +1 HP within its paired dispatch: 83 → 89. The live probe afterwards agreed (89/98). |
| Pulse times | Worlds 33192, 33207, 33237, 33267, 33297, 33327: 20 ticks after the application, then 15, then every 30. |
| Worker dispatch | 179 dispatches, one per world tick from 33173 to 33351. Remaining duration fell by 1 per dispatch. The list counter stayed world − 31498. |
| Construction and rebuild | Two passes at the application (33172) each constructed a worker; the second one ran. Then one tick after every heal (33193, 33208, 33238, 33268, 33298, 33328) the live worker was destroyed and a new one constructed from the parent. Seeded remaining duration = parent deadline − world (180, 159, 144, 114, 84, 54, 24). Seeded phase = floor((world − origin)/15) mod 2 (0, 1, 0, 0, 0, 0, 0). The engine also copies the worker at each heal and each pass; a copy lives until the next pass or heal and is never dispatched. |
| Worker end | The last worker reached 0 at 33351, set done and was destroyed. There was no seventh heal. |
| Buff expiry | A parent is removed only during an effect-list pass. `CBRTBUF` (deadline 33262) went at 33268, 6 ticks late, in the rebuild after the heal at 33267. `CBRTREG` (deadline 33352) went at 33364, 12 ticks late, in a pass without a heal. Pre-expiry checks ran only at 33172, at the six post-heal rebuilds and at 33364. |
| Other actors | 15 unattributed copy/destroy events at 33221–2, 33311–2 and 33401–2 (every 90 ticks), remaining duration about 2^30: another creature's permanent worker of the same class. They are not fixture evidence. |
| Time Stop | Counter 0 and caster −1 in all 451 records. |

What this shows:

- **Pulse rule.** At each dispatch the list writes its counter into the worker, which adds 1.
  The worker's period counter advances when the result is a multiple of 15 (here world ≡ 12
  mod 15), and it heals at 2. The first heal came at the second such boundary after the application (33177,
  33192). The rebuild at 33193 seeded phase 1, one whole second after the origin, so the next
  heal came one boundary later. From the 33208 rebuild on, the elapsed whole seconds were
  even at every rebuild: phase 0, 30-tick spacing. Two clocks thus set the pulses: the list
  counter's 15-tick boundary, and the parent origin, read again at every rebuild.
- **Static path confirmed.** This matches the research note's seeding (`0x1BED5F–0x1BED76`,
  `0x1BED97–0x1BEDD2`), the 15-tick boundary (`0x1A5D74–0x1A5D7A`) and one dispatch per world
  tick for an actor at normal speed.
- **Expiry is not detected at the deadline tick.** A heal-driven rebuild removed the buff 6
  ticks late. Without a heal, the regeneration parent stayed 12 ticks. This trace does not
  show what started the pass at 33364.

For steps 2 and 3:

- Fixtures queued while paused apply at once. A case's origin and deadlines are known
  before the game runs.
- Pulse boundaries follow the list counter, which started with the game, not the
  application tick. Read them from the case's own origin and counter.
- The buff's removal can ride on a regeneration rebuild. Step 2 must note whether its
  removal pass coincides with one.
- Each pause toggle read the world time one tick lower afterwards than just before
  (33104 → 33103, 33173 → 33172, 33434 → 33433); unpausing did not. Use the trace's own
  world values, not the pause probe.

## Time Stop captures `timestop_01` and `timestop_02` (2026-10-23)

This was step 2: native Time Stop through the fixtures, measurement only, no clock correction.

- **Run.** One quiet run through `lab_quiet_run.py run … 1800`, holding the exclusive lock.
  Another session's lab game had to end first. The run ended after 590 s through
  `rc/quit.lua`, without a save. No guard tripped: audio peak 0.0, pointer clip unchanged,
  nothing left in the job.
- **Party.** The [fresh-party sequence](#fresh-test-party-in-the-hidden-game) again, sent by a
  scratch driver that checks the menu after every click. The same actor IDs came back:
  subject 132974572, Imoen 131401684. `ApplyDamage(Myself,20,0)` again left the subject at
  83 of 98 HP.
- **Trigger.** Each case started paused:
  1. `Arm(0)`, then the fixtures, then a `subject` probe.
  2. `queue what=timestop`: Imoen runs `SmallWait(N)`, then applies `CBRTSTP` to herself. N
     came from the probe's list counter, so that the stop would begin at least six ticks
     from a pulse boundary.

  Both stops began on the planned tick, N + 1 ticks after the application. The game then
  ran for 20 s without a pause, about 300 ticks. After that came the pause, then `Stop()`,
  then `Export()` as a separate request.
- **Decoding.** `decode_trace.py` exited 0 for both traces. Both are complete, with all
  records committed (443 and 426), no issues, and 179 paired dispatches each, one per
  world tick. The files stay in the lab with their decoded JSON/CSV and the request log.

| Check | `timestop_01` (buff nearly out) | `timestop_02` (early stop) |
|---|---|---|
| Application | 33004. Deadlines 33094 (buff) and 33184 (regeneration). | 33311. Deadlines 33401 and 33491. |
| Stop | Frozen dispatches 33078 (application + 74) to 33166, caster Imoen. The buff had 16 ticks left. | 33348 (application + 37) to 33436. The buff had 53 ticks left. |
| Stop counter | 178 at the first frozen dispatch, then −2 per world tick down to 2. The encoded 12 s thus froze the subject for 89 dispatches, about 6 s, as IESDP describes. | Same. |
| Frozen worker | Dispatched every tick and returned at its Time Stop gate. Remaining duration held (106, then 90), the period counter held, no healing submission. The list counter still rose by 1 per tick. | Held 143, then 83. Otherwise the same. |
| Buff | Removed **during the stop** at 33094, its deadline. | Removed **during the stop** at 33408, 7 ticks after its deadline. |
| Rebuild in the stop | The removal pass rebuilt the regeneration worker with remaining 90 = deadline − world. The held 106 was dropped. | Remaining 83 = deadline − world. The held 143 was dropped. |
| Stop end | At the first free tick, 33167, the list was rebuilt (`m_newEffect`): remaining 17 = deadline − world, phase 0. | 33437: remaining 54, phase 0. |
| Pulses | Heals at 33027, 33042 and 33072, all before the stop: 83 → 86. None during or after it. | 33341 before the stop and 33461 after it: 86 → 88. |
| Regeneration end | Worker done at 33183, parent removed at 33184 (the deadline). | Worker done at 33490, parent removed at 33498 (deadline + 7). |

What this shows:

- **The frozen subject keeps losing buff time.** The full effect check still runs for a
  frozen actor. It finds the expired buff and removes it. In both cases the buff ended inside
  the stop, at its absolute deadline or at the actor's next check tick after it. Neither
  removal rode on a regeneration rebuild, because nothing heals during a stop.
- **The regeneration worker is gated, but every rebuild reseeds it.** While frozen, it
  neither heals nor counts down. A rebuild reseeds remaining duration from deadline − world
  and the phase from the origin. Two rebuilds did that here: the pass that removed the buff,
  and the forced one at the end of the stop. So the frozen time is lost, and the regeneration
  ends at its absolute deadline. It delivered 3 and 2 HP, against 6 in the baseline. There
  was no catch-up burst.
- **After the stop, pulses follow the absolute grid.** The list counter kept counting
  through the stop, and the phase was reseeded from the origin. In `timestop_02`, the next
  heal was 23 ticks away when the stop began; it came 24 ticks after the stop ended. A
  90-tick stop is three heal periods long, so the grid put the pulse almost back in its old
  phase. A stop of another length would move it.
- **The full effect check runs once per second, at a phase set by the actor ID.**
  `ProcessEffectList` runs `CheckEffects` and the rest of its full pass only in three cases
  (`0x3ABB7C–0x3ABBC5`):
  - the counter at `+0x3A0`, mod 15, equals the actor ID mod 15;
  - `m_newEffect` is set;
  - `+0x4E44` is set.

  From each case's probe, the check ticks were predicted as world ≡ 4 (mod 15) for
  `timestop_01` and world ≡ 3 for `timestop_02`. All four parent removals fell on those
  ticks. This also explains why `baseline_01` removed its regeneration parent 12 ticks late
  (33364 ≡ 4).
- **A pause can move both phases by one tick.** During `timestop_01`, world − list counter was
  31498; during `timestop_02` it was 31497. Between them, a pause read 33312 and then 33311,
  but the subject's counters did not go back. Pulse boundaries and check ticks follow the
  actor's own counters, not world time.

For step 3 and a later correction:

- Preserving a buff through Time Stop must reconcile the selected parent's deadline before
  the frozen actor's next full effect check. A repair after the stop comes too late.
- Each rebuild reseeds the worker from the parent's deadline and origin. A preserved
  remaining duration must therefore survive in the parent. The pulse phase also depends on
  the shared list counter, which keeps running through the stop.
- For the Haste case, `queue` and the `subject` clocks can align the Haste start to the list
  counter in the same way.

## Haste captures `haste_01` to `haste_04` (2026-10-23)

This was step 3: native Haste and Improved Haste through the regeneration fixture, without
Time Stop. Measurement only, no correction.

- **Run.** One quiet run through `lab_quiet_run.py run … 1800`, holding the exclusive lock.
  It ended after 953 s through `rc/quit.lua`, without a save. No guard tripped: audio peak
  0.0, pointer clip unchanged, nothing left in the job.
- **Party.** The same [fresh-party sequence](#fresh-test-party-in-the-hidden-game) and the
  same actor IDs. `ApplyDamage(Myself,20,0)` again left the subject at 83 of 98 HP. Between
  cases, a disarmed run let every lab fixture run out, Haste included, and `ApplyDamage`
  topped the missing HP back up to at least 13.
- **Trigger.** Each case started paused with `Arm(0)`.
  - *Entering* (`haste_01` Haste, `haste_02` Improved Haste): the fixtures, a `subject`
    probe, then `queue what=haste`. The subject runs `SmallWait(N)` and then applies the
    Haste fixture to itself. N came from the probe's list counter and the baseline heal
    rule, so that Haste would begin 7 ticks after the third native heal, midway through a
    15-tick pulse interval. Both began on the planned tick.
  - *Leaving* (`haste_03`, `haste_04`, both Haste): Haste first, applied while paused, then
    about 14 s of hasted running, a pause and the fixtures. Haste's deadline fell 76 and 87
    ticks after the fixtures. `haste_03` was not aligned further. For `haste_04` the driver
    predicted from the probe's counters which full pass would first reach the Haste
    deadline (rules below). It was ready to shift the subject's pulse grid by one tick per
    short pause cycle until a scheduled pass between two pulses would end Haste; the first
    probe already qualified.

  Then 20 s of running without a pause, the pause, `Stop()` and `Export()`.
- **Decoding.** `decode_trace.py` exited 0 for all four traces. All are complete, with all
  records committed (732, 656, 668 and 710) and no issues. A hasted tick has two paired
  dispatches, a normal tick one. The files stay in the lab with their decoded JSON/CSV and
  the request log.

Times are world ticks; +n counts from the fixtures' application.

| Check | `haste_01` (Haste in) | `haste_02` (Improved Haste in) | `haste_03` (Haste out) | `haste_04` (Haste out, mid-interval) |
|---|---|---|---|---|
| Fixtures | 32993. Deadlines 33083 (buff) and 33173 (regeneration). | 33432. Deadlines 33522 and 33612. | 34107. Deadlines 34197 and 34287. | 34667. Deadlines 34757 and 34847. |
| Haste | Began at +71, 7 ticks after a heal. Still on at the end. | Began at +79, 7 ticks after a heal. Still on at the end. | Deadline +76. Removed at +79 by the pass that the heal at +78 forced. | Deadline +87. Removed at +89 by a scheduled pass, 4 ticks after the pulse at +85. |
| Heals | +19, +34, +64; hasted +82, +90, +105, +112, +120, +135, +142, +150, +165, +172. | +27, +42, +72; hasted +83, +90, +105, +113, +120, +135, +143, +150. | Hasted +11, +26, +33, +48, +56, +63, +78; then +93, +123, +153. | Hasted +10, +25, +33, +48, +55, +63, +78, +85; then +97, +127, +157. |
| HP | 83 → 96 | 81 → 92 | 80 → 90 | 80 → 91 |
| Buff removed | At its deadline, in a heal rebuild. | Deadline + 1, heal rebuild. | Deadline + 4, heal rebuild. | Deadline + 8, heal rebuild. |
| Regeneration removed | Deadline + 3, scheduled pass. The worker was done 4 ticks before the deadline. | Deadline + 4, scheduled pass. The worker ran dry 15 ticks before the deadline. | Deadline + 10, scheduled pass. | Deadline + 14, scheduled pass. |

For comparison, `baseline_01` healed at +20, +35, +65, +95, +125 and +155: 6 HP.

What this shows:

- **Haste and Improved Haste double the subject's effect clocks.** Both behaved the same. The
  subject got two AI updates per world tick (`ai_speed` 0), as the static `m_AISpeed` gate
  predicts. Each update dispatched the regenerated list once and advanced its counter. So
  the counter rose by 2 per tick, the worker's remaining duration fell by 2 per tick, and
  pulses came every 7.5 ticks instead of 15. The check counter `+0x3A0` kept pace, so the
  full pass also ran twice per second: hasted removals came 3 and 4 ticks late, against up
  to 14 at normal speed.
- **Hasted regeneration healed up to 2.75 times as often, not twice.** Hasted heals came
  mostly 15, 7–8 and 8–7 ticks apart. Per 30 hasted ticks the four captures gave 2.75, 2.38
  (with the dry stretch below), 2.66 and 2.70 heals, against 1 at normal speed and 2 for
  plain doubling. Every heal here was followed by a rebuild, which reseeds the phase from
  world time in 15-tick steps: floor((world − origin)/15) mod 2. At normal speed that agrees
  with the pulse grid. Hasted, two pulses fall into each step, so 20 of the 32 hasted
  rebuilds started at phase 1, and the next pulse healed at once. Between Haste's start and
  the regeneration's end, `haste_01` healed 10 times in 109 ticks. Normal speed would give
  about 3.6, plain doubling about 7.3. An actor at full HP, whose heals change nothing, was
  not tested.
- **The duration stays in world time, but the worker can run dry first.** No parent deadline
  moved. Each rebuild reseeded remaining = deadline − world, but in between the worker
  counted down twice as fast. In `haste_02` the last rebuild set a remaining duration of 29.
  It ran out 14 ticks later, 15 ticks before the deadline, and that stretch had no pulse.
- **Entering Haste forces a rebuild with a world-time phase.** Applying Haste rebuilt the
  list on the same tick. Both cases began 7 ticks after a heal. `haste_01`, 71 ticks after
  the fixtures, got phase 0 and healed 11 ticks later. `haste_02`, at 79 ticks, got phase 1
  and healed 4 ticks later.
- **Leaving Haste waits for the next full pass, which rebuilds too.** Haste's own deadline is
  checked like any other parent's. In `haste_03` the pass that a heal forced removed it.
  In `haste_04` a scheduled pass removed it, 2 ticks after the deadline and midway between
  two pulses. Both passes reseeded the worker by world time, to phase 1 both times. So the
  first normal-speed pulse, 14 and 8 ticks later, healed, and the 30-tick cadence was back.
- **Three rules replay all five captures without Time Stop.** They were checked against
  `baseline_01` and the four Haste traces, 51 heals and 10 parent removals:
  - every construction seeds remaining = deadline − world and phase =
    floor((world − origin)/15) mod 2;
  - a pulse falls on the update whose list counter + 1 is a multiple of 15, and the phase
    heals when it reaches 2;
  - a full pass runs at the update whose list counter + 1 matches the actor ID mod 15 (the
    step-2 rule; the counter equalled `+0x3A0` in every probe), and at the update after a
    heal or another change to the list.

  One detail is still loose: which tick takes the first hasted update after a pause. It was
  the paused tick in `haste_03` and the next one in `haste_04`. So the `haste_04`
  prediction (34755) came one tick early, still inside the window it aimed for.

For a later correction:

- Under Haste the per-actor counters run twice as fast, and so does every clock that hangs
  on them, the expiry check included, while durations stay in world time.
- The rebuild's world-time phase reseed causes the extra hasted heals. It also causes the
  short second interval at normal speed (+20, then +35 in `baseline_01`). A correction that
  owns a worker's phase must keep it across rebuilds.
- Movement and attack were not measured. They become acceptance requirements once a
  correction is proposed.

## Correction prototype `CBRTFix.lua`

`CBRTFix.lua` is the first clock correction, made for step 4 only. It acts on one selected
subject and on two effects: `CBRTBUF`, and `CBRTREG` (op98 p2=3, a regeneration worker that
counts its phase up to the period and then heals). Both must have absolute timing
(`0x1000`). No other effect, opcode or actor is touched. At normal speed it keeps the
native heal pattern, including the 15-tick second interval after the first heal; it only
removes the influence of Time Stop and Haste (Christopher's choice on 2026-10-23).

Four hooks do the work. Their windows were decoded from the pinned executable like the
observer's, and none overlaps an observer window.

| Hook | Site | What it does |
|---|---|---|
| Frozen | `0x3ABA9D`, after the engine marks a frozen noncaster | In each world tick in which the subject is frozen, once: moves each selected parent's deadline one tick later, and the regeneration's origin (`+0x6C`) with it. This happens before that pass checks for expiry. |
| Dispatch | `0x226543`, after the list counter is copied into the worker | Admits the tracked worker once per world tick. Its counter becomes the subject's active time (world time minus its frozen ticks) plus an offset, taken from the first admitted dispatch so that the native pulse grid is kept. A second dispatch in the same tick runs as a no-op: counter 0, elapsed 0. Any other regeneration worker of the subject stays native and is counted as unmatched. |
| Construct | `0x1BEDD2`, after the regeneration seeds its worker | A rebuilt worker of the tracked parent gets the kept phase back, if the parent's origin moved by exactly the frozen ticks counted since. Another `CBRTREG` parent, or one whose origin does not fit, becomes the new tracked entry with the native seed. |
| Worker exit | `0x1A5F19`, the regeneration AIUpdate epilog | Records the worker's phase. After a heal it records the phase that a native rebuild on the next un-hasted tick would seed: floor((active time + 1 − active origin)/15) mod period. |

Controls, also available as the Remote Console request `fix` (`op=install`, `select`,
`verify`, `status`, `disable`):

1. `CBRTF.Install()` at the fresh main menu. It first runs `CBRTF.Inspect()`, which checks
   the lab, the image base and timestamp, the regeneration vtable and all four windows.
   Then it compiles the bodies and installs the hooks, disabled.
2. `CBRTF.Select(0)` while paused, **before** the fixtures, so that the regeneration's first
   construction is tracked. It disables the correction first, so a refused selection leaves
   it off. It clears the counters and the tracked entry and stores the subject's pointer, ID
   and timed-list offset. The frozen hook walks that list natively. It stays idle until the
   walk is proven on the subject's own effects; an empty list proves nothing.
3. Apply the fixtures, then call `CBRTF.Verify(0)` while paused. It requires the selected
   subject, at least one timed effect, and a native walk that matches the EEex iterator. A
   mismatch disables the correction.
4. `CBRTF.Status()` reports the counters (frozen ticks, deadline shifts, admitted, suppressed
   and unmatched dispatches, restored phases, new parents, heal reseeds) and the tracked
   entry.
5. `CBRTF.Disable()` needs no pause. One aligned store turns it off, and every later pass is
   native. Destroying the game session disables it too.

The request refuses `select` and `verify` unless the game is paused and portrait 0 carries
the subject's name.

## Corrected captures `fixctl_01`, `fixstop_01`, `fixhaste_01` and `fixhaste_02` (2026-10-23)

This was step 4: the correction prototype through the fixtures, with the observer recording.

- **Run.** One quiet run through `lab_quiet_run.py run … 2100`, holding the exclusive lock,
  after a `-Refresh` restage. At the fresh main menu, `CBRTS.Install()` installed its 8
  sites and `CBRTF.Install()` its 4, disabled. The run ended at its 2,100 s limit, which
  closed the game without a save. No guard tripped: audio peak 0.0, pointer clip
  unchanged, nothing left in the job.
- **Party.** The [fresh-party sequence](#fresh-test-party-in-the-hidden-game) and the same
  actor IDs. `ApplyDamage(Myself,20,0)` again left the subject at 83 of 98 HP. Between
  cases, the correction was disabled, a disarmed run let every lab fixture run out, Haste
  included, and `ApplyDamage` restored at least 6 missing HP.
- **Trigger.** Each case started paused: `Arm(0)`, `fix op=select`, the fixtures,
  `fix op=verify`, a `subject` probe, then the case's own event. The game then ran without a
  pause for 20 s, 26 s in the stop case. The pause, `fix op=status`, `Stop()`, `Export()`
  and `fix op=disable` followed.
  - `fixctl_01`: no event, the corrected control.
  - `fixstop_01`: `queue what=timestop`, planned as in step 2. The stop was to begin 70 ticks
    after the fixtures, with 20 ticks left on the buff and 7 ticks after a pulse boundary.
  - `fixhaste_01`: `queue what=haste` with `CBRTHST`, 7 ticks after the third predicted
    heal, as in `haste_01`.
  - `fixhaste_02`: Haste first, applied while paused, then about 14 s of hasted running and a
    pause. The fixtures came while hasted, 79 ticks before Haste's deadline, as in
    `haste_03`.

  The stop and the Haste began on their planned ticks.
- **Decoding.** `decode_trace.py` exited 0 for all four traces. All are complete, with all
  records committed (451, 650, 699 and 651) and no issues. The files stay in the lab with
  their decoded JSON/CSV, the request log, and each case's plan and correction status.

Times are world ticks; +n counts from the fixtures' application. "Predicted" applies the
native un-hasted rules from step 3 to the case's own probe counters, in active time.

| Check | `fixctl_01` (control) | `fixstop_01` (Time Stop) | `fixhaste_01` (Haste in) | `fixhaste_02` (Haste out) |
|---|---|---|---|---|
| Fixtures | 32993. Deadlines 33083 (buff) and 33173 (regeneration). | 33308. Deadlines 33398 and 33488. | 33743. Deadlines 33833 and 33923. | 34397, while hasted. Deadlines 34487 and 34577; Haste's 34476. |
| Event | None. | Frozen from 33378 (+70) to 33466: 89 ticks. | Haste from 33811 (+68), still on at the end. | Haste removed at 34482 (+85), 6 ticks after its deadline. |
| Heals | +19, +34, +64, +94, +124, +154 | +18, +33, +63; after the stop +182, +212, +242 | +16, +31, +61, +91, +121, +151 | +27, +42, +72, +102, +132, +162 |
| Against the prediction | Same ticks. | Same ticks in active time. The gap across the stop is 119 = 30 + 89. | Same ticks. | One tick early each, same spacing. |
| HP | 83 → 89 | 89 → 95 | 85 → 91 | 84 → 90 |
| Buff removed | 33088, deadline + 5, heal rebuild. | 33491: shifted deadline 33487 + 4, heal rebuild. | 33833, its deadline, scheduled hasted pass. | 34497, deadline + 10, scheduled pass. |
| Regeneration removed | 33184, deadline + 11, scheduled pass. | 33588: shifted deadline 33577 + 11, scheduled pass. | 33923, its deadline, scheduled hasted pass. | 34587, deadline + 10, scheduled pass. |
| Correction counters | 179 admitted, 0 suppressed, 0 unmatched; 7 phases restored. | 268 admitted, 0 suppressed; 89 frozen ticks, 178 deadline shifts; 8 restored. | 180 admitted, 112 suppressed; 9 restored. | 180 admitted, 84 suppressed; 9 restored. |

Every case had 6 heal reseeds and 1 new parent, and no dispatch went unmatched. For
comparison, the native captures gave 3 and 2 HP through a stop (`timestop_01`,
`timestop_02`), 13 HP with Haste entering (`haste_01`) and 10 with Haste ending
(`haste_03`).

What this shows:

- **Time Stop: lifetime and phase survive the stop.** The frozen hook moved both deadlines
  and the origin by the 89 frozen ticks before an expiry check could see them. The buff had
  20 ticks left when the stop began. It survived and was removed 4 ticks after its shifted
  deadline, by a native heal rebuild. The worker's counter stood still through the stop
  (1880 at every frozen tick) and resumed with 1881. Its remaining duration held at 110,
  and the rebuild at the end of the stop reseeded exactly 110 from the shifted deadline.
  The next heal was 23 ticks away when the stop began, and came 23 ticks after the first
  free tick. All 6 HP arrived, none inside the stop, without a catch-up burst.
- **Haste: the worker keeps world time.** Each hasted tick had two dispatches, and the second
  ran as a no-op. The worker counted down 1 per world tick and kept the 15-tick grid, so both
  Haste cases healed 6 times with the native spacing, like the control.
- **Rebuilds keep the phase.** Every rebuild of the tracked worker got its phase back: after
  each heal, at Haste's start and end, at the buff's removal and at the end of the stop. No
  rebuild added or lost a heal, and the short second interval after the first heal stayed.
- **The control is native.** With nothing to correct, `fixctl_01` matched the native rules
  tick for tick: heals, removals and the worker's counters.
- **Expiry timing stays native.** Deadlines move, but removals still wait for the subject's
  next full pass. Under Haste that pass still runs twice per second, so hasted removals
  come at most about 7 ticks late instead of up to 14.

Two one-tick residuals remain, both under Haste:

- **Grid anchor when the regeneration is applied to a hasted subject while paused.** In
  `fixhaste_02` the first update after unpausing came at the paused world value 34397, as
  natively in `haste_03` but not in `haste_04`. The dispatch hook took its offset from that
  update, so every pulse came one tick earlier than an un-hasted subject with the same
  counters would have had. Such a subject has no un-hasted grid to keep, since its list
  counter already ran at double speed. Still, whether that update comes depends on Haste.
  Suppressing it alone would not help: a suppressed dispatch still advances the list
  counter (3438, 3439, … in `fixhaste_02`), so the next admitted dispatch would take the
  same offset. A fix (R7) would record the list counter, the world value and `+0x3A0` when
  the parent is first constructed. Since `ProcessEffectList` increments `+0x3A0` at its
  start, the hook could then admit a dispatch at that world value only from the same call
  (or after a rebuild of the same parent in it), and take the offset from the recorded
  counter.
- **Worker end after a rebuild in the second hasted update.** In `fixhaste_01` the buff's
  removal pass at 33833 ran in the subject's second update of that tick, after the admitted
  dispatch. It reseeded remaining = deadline − world, which the no-op dispatch then did not
  count down. From there the remaining duration was one tick longer than at normal speed,
  and every later heal rebuild in the same position kept it so. The worker ended at its
  deadline, 33923, instead of one tick before it, as in the control (33172, deadline 33173). No pulse fell on that tick; one that did could
  heal once more than at normal speed. A fix (R8) would take one tick off the seeded
  remaining duration when a rebuild follows the tick's admitted dispatch.

Not covered yet:

- Attack and movement rates under Haste. The correction leaves actor scheduling,
  `m_AISpeed` and `+0x3A0` alone, but that is not measured.
- Corrected Improved Haste, SR-shaped Haste, and Slow. The dispatch hook can only drop
  dispatches, not add them, so a slowed subject would keep its native slower cadence.
- A pause during a corrected regeneration. A pause steps world time back one tick, and the
  repeated tick after it is suppressed, so the corrected grid is locked to world time where
  the native one shifts (step 2).
- Consecutive stops, removal or refresh during a stop, an application mid-stop, explicit
  removal, caster and immune subjects, save/load, time compression and area travel.
- There is no removal hook. A parent re-added at the same address counts as new only when its
  origin differs from the tracked one.

Christopher closed step 4 on 2026-10-24 with these results. R7, R8 and the open items above
go into the next lab run.

## Time Clocks lab (2026-10-23)

A second lab, for the clock fix itself: the EEex mod Chriz BG Time Clocks (local repository
`chriz-bg-time-clocks`, not published). The Time Stop lab above belongs to another session, so
the same scripts build a lab of their own with `$env:CBR_LAB_VARIANT = 'timeclocks'`:

- Game `%USERPROFILE%\Games\CBR-TimeClocks-2.7.3.0`, engine and profile name `CBR TimeClocks Lab
  2730` (`%USERPROFILE%\OneDrive\Documents\CBR TimeClocks Lab 2730`), the same pins as above
  (executable, EEex 1.3.1 with components 0, 1 and 8, WeiDU, Remote Console). Copy, Install,
  Validate and staging as in [Offline preparation](#offline-preparation); `steam_api64.dll`
  renamed and `lab_quiet_run.py prepare` as in [Runtime coordination](#runtime-coordination).
  Every script refuses the other lab's identity.
- **The mod.** `Install-TimeClocks.ps1 -ModRoot <clean checkout> -Components 100,200` installs
  it with the lab's WeiDU, after uninstalling the components installed before (newest first)
  and checking that `override` and `EEex_scripts` are back to the inventory recorded before the
  first install. The checkout's files must equal its HEAD. `cbr-timeclocks.json` records the
  commit, components, switches and installed files; the preflight checks them like the staged
  assets.
- **Fixtures.** Besides the five above, `build_fixtures.py` stages:

  | Fixture | Effect | For |
  |---|---|---|
  | `CBRTSLW` | op40 Slow, 20 s | Slow |
  | `CBRTSRH` | op176 +6, op1 +½ attack, op142 icon 38, 20 s: Spell Revisions 4.19's Haste, no op16 | SR-shaped Haste |
  | `CBRTDIS` | op78 type 0, 2 HP each second for 8 s (1 HP on the lab's difficulty) | a periodic effect besides regeneration and poison |
  | `CBRTSTL` | op231, 15 s Time Stop | area cases: time to act in the stop |
  | `CBRTDMG` | op12 5 crushing, instant | area case F |
  | `CBRTCON` | op232 contingency: Magic Missile at whoever hits the bearer | area case E |
  | `CBRTHIT` | op54 +20 to hit | area cases E and F |
  | `CBRTSAV` | op33 −20 to saves vs. death | area cases A and B: no save against Stinking Cloud |

  Sessions n1 and n2 had a `CBRTDIS` with 0 HP, which shows no pulse.
- **Spell Revisions' Cloudkill** (case G) without installing SR:
  `Stage-Diagnostics.ps1 -SpellRevisionsRoot <folder with spell_rev>` runs `sr_cloudkill.py`,
  which builds SR 4.19.rc5's own projectile `DVCKILL.PRO`, the stock `PROJECTL.IDS` with
  `DVCKILL` added (346), and SR's Cloudkill as `CBRTSRCK.SPL`, from SR files pinned by hash.
  Every later refresh needs the switch again.
- **Requests.** `rc/tc-queue.lua` queues script steps on one creature (wait, mark, apply, cast,
  castpoint, hostile, attack, damage, spawn, move, destroy) while paused. `rc/tc-probe.lua`
  reports the party's and named creatures' tracked effects with their deadlines, the clock
  counters, the stop and the mod's status and switches. `rc/sampler.lua` records, once per
  frame and only on change, each tracked creature's HP, AI speed and tracked effects, the stop
  counter and caster, and every projectile from its decode to its end with its area counters
  (arrival, remaining explosions, pulse countdown); `rc/sampler-export.lua` writes them as
  `<capture>.samples.jsonl`. `rc/save.lua` clicks the quick save, `rc/load-save.lua` loads a
  named save, `rc/party-ai.lua` turns the party's AI off.
- **Driver.** `tc_session.py TAG --mod STATE (--fresh NAME | --save FOLDER) --cases …` runs a
  session case by case, every step one console request, and stops at the first unexpected
  answer (it then creates `--stop-file`, which ends the slot's run). It first checks that the
  mod is absent or active with exactly the switches of STATE. Between cases it waits until no
  lab effect, stop or tracked projectile is left, walks Imoen back to her place and lowers the
  subject's HP to at least 13 below its maximum. Each case records its probes, the sampler
  file and, for the clock cases, the observer trace (`TAG_case.bin`). Every area case spawns
  its own Bounty Hunters and removes them afterwards. Saves are copied to named lab folders
  (`000000800-…`) with the probe at saving beside the captures (`saves/<folder>.json`).
  `test_tc_session.py` runs every case against a scripted game first, with `tc-queue.lua`'s
  own checks.
- **Reading.** `tc_report.py <capture>.samples.jsonl` lists the stop, the marks, every HP and
  speed change, every tracked effect with its deadline, moves and removal, and every projectile.
- **Runs** go through a parallel lab slot (`bg_lab_slots.py run … --stop <file>`), with the
  checks for OBS and Christopher's game before each.

## Time Clocks captures (2026-10-23 and 24)

Without the mod (`n`), with its decided components 100 and 200 (`d`) and with one option each
(`o`), all with the same driver, sampler, observer and fixtures, and all but n1 from n1's save
`CBTC n1 base`. Each session ran through a parallel lab slot while other sessions' labs ran in
others; no guard tripped except once in d1.

| Session | Components | Cases | Notes |
|---|---|---|---|
| n1 | none | base, stop74, haste, slow, srhaste | Made the party and its save; stopped at its sixth case on a console label with `+` (fixed). |
| n2 | none | hastedis, areaa–areag | Void for disease (`CBRTDIS` with 0 HP) and for E and F (Imoen's attacks on neutral targets never hit); its marks were unlabelled. |
| n3 | none | dis, hastedis, areaa–areag | |
| n4 | none | areae, areaf | E and F again, with two attack rounds. |
| n5 | none | stop37, stopnew, caster, ihaste, hasteout, save, savestop | |
| d1 | 100, 200 | base to slow (9 cases) | Ended after 420 s: the quiet runner's guard saw the display gamma change (PC-wide, cause unknown), restored it and closed the game. |
| d2 | 100, 200 | the other 13 | |
| d3 | 100, 200 | load | Loaded d2's save made after a stop, in a new process. |
| o110 | 100, 110, 200 | stopnew, stop74 | |
| o120 | 100, 120, 200 | caster, stop74 | |
| o210 | 100, 200, 210 | haste, hastedis, slow | |
| o220 | 100, 200, 220 | slow, haste | |
| o230 | 100, 200, 230 | haste, ihaste | |

The mod's status line read `active` with the expected switches in every `d` and `o` session.
Captures are in `<lab>\cbr-timestop-output`: `tc-driver-<session>.jsonl`, and per case
`<session>_<case>.samples.jsonl` (with `.report.json` from the current `tc_report.py`; those
of its earlier versions are in `superseded-reports\`), for clock cases also the observer trace
`.bin`; the console log in `rc-log\`, the kept saves' probes in `saves\`.

**Clock cases.** +n counts world ticks from the fixtures' application: the buff `CBRTBUF`
ends at +90, the regeneration `CBRTREG` (1 HP every 2 s) at +180. Each stop lasted 6 s, 89
ticks with the counter set.

| Case | Without the mod | With 100 and 200 |
|---|---|---|
| `base` | n1: 6 heals, +25 to +160; buff removed +92, regeneration +182. | d1: 6 heals, +22 to +157, the same pattern; +91 and +181. |
| `stop74`: stop 74 ticks in | n1 (stop from +67): 3 heals; buff removed +96, in the stop; regeneration +180. | d1: both deadlines moved 90 ticks, one per frozen pass, to +180 and +270; removed +182 and +272; 6 heals, the last three 91 ticks later than in `base`. |
| `stop37` | n5: 3 heals; buff removed +102, in the stop; regeneration +192. | d1: moved 90; removed +186 and +276; 6 heals. |
| `stopnew`: buff put on 20 ticks into the stop | n5: buff from +60 removed +153, after 68 of its 90 ticks frozen; 3 heals. | d1: buff from +62 moved 68 to +220, removed +224; the regeneration moved 90; 6 heals. |
| `caster`: Imoen's own buff too | n5: hers removed +97, the subject's +95 in the stop. | d1: hers not moved, removed +98; the subject's moved 90. |
| `haste`: Haste midway between two pulses, after the third heal | n1: 11 heals. | d1 (Haste at +67): 6 heals, +16 to +151, 30 ticks apart after the second. |
| `ihaste`: the same with Improved Haste | n5: 11 heals. | d1 (at +78): 7 heals (below). |
| `hasteout`: fixtures 14 s into Haste, which ends 70 ticks later | n5: 10 heals. | d1: 6 heals. |
| `slow` | n1: 3 heals, 60 ticks apart; removals 11 and 23 ticks late. | d1: 6 heals; removals 10 and 22 late. |
| `srhaste`: SR 4.19's Haste | n1: AI speed stays 1; 6 heals; removals 5 late. | d2: the same; 6 heals in the native pattern. |
| `dis` | n3: 8 losses, 15 ticks apart; removed at its deadline. | d2: 8 losses, 15 ticks apart. |
| `hastedis`: disease and Haste together | n3: 15 losses, 7–8 ticks apart. | d2: 9 losses, 15 ticks apart; the ninth fell on the deadline tick after a one-tick step of the subject's counters. |
| `save`: saved after a stop | n5: saved at +182, regeneration deadline unmoved (+180). | d2: saved at +211 with the regeneration deadline at +270. d3 loaded it: the same deadline, one more heal, removed 4 ticks after it. |
| `savestop`: saved in a stop | n5: the game refused the save. | d2: refused. |

With one option each:

| Option | Case | Result |
|---|---|---|
| 110: effects put on during a stop run on | `stopnew` | The buff put on in the stop kept its deadline (+147), removed +149; the regeneration from before moved 90. `stop74` as with the defaults. |
| 120: the caster's effects wait too | `caster` | Imoen's buff moved 89, removed +191; the subject's moved 90. |
| 210: only regeneration and poison at the normal rate | `haste`, `hastedis`, `slow` | 6 heals hasted and 6 slowed; the disease kept Haste's rate: 15 losses, 7–8 ticks apart. |
| 220: Slow keeps the game's halved rate | `slow`, `haste` | Slowed: 4 heals, 30 and 60 ticks apart (n1: 3, 60 apart; the phase reseeds after each heal decide which). Haste at +78: 7 heals, like `ihaste` in d1 (below). |
| 230: hasted creatures check expiry once per second | `ihaste`, `haste` | Improved Haste at +78: the buff and the regeneration were removed 12 ticks after their deadlines (+102, +192), against 4 in d1 with the same 7 heals; checks twice per second come at most 8 ticks late. Haste at +75: removed 2 late; 7 heals (below). |

What this shows:

- **Time Stop (100).** Each effect of a frozen creature kept its remaining time: the mod moved
  its deadline one tick per frozen tick, in each frozen pass before the pass checked expiry
  (the subject had a pass every tick, the sleeping T1 of area case A one every third), so
  nothing ran out in a stop, and the regeneration gave all 6 heals. Its count is one tick
  more than the 89 frozen dispatches the observer saw in the Time Stop lab (a known limit of
  the mod). An effect put on during the stop waited the rest of it (choice 2), the caster's
  own buff ran on (choice 3), and the options turned each of these around.
- **Haste and Slow (200).** Regeneration healed 6 or 7 times hasted (below), 6 slowed and 6
  with Haste ending, against 11, 3 and 10 without the mod; disease pulsed 15 ticks apart
  under Haste. Spell Revisions' Haste, which leaves the AI speed at 1, stayed native.
  Improved Haste (d1, o230) and Haste in o220 and o230 gave 7 heals, Haste in d1 6. Each was
  put on 6 ticks after a heal, and putting it on rebuilt the subject's effect list; a rebuild
  re-derives the regeneration's phase from world time (the step 3 rule). At +78 and +75,
  floor(t/15) is odd (5), so the phase gained a pulse and the next pulse healed; at +67 (d1's
  Haste, 4) it did not. Any effect put on at such a tick does the same at normal speed, where
  the phase pattern stays native (Christopher's "Native beibehalten").
- **Hasted expiry (230).** With it, the hasted subject's buff and regeneration were removed 12
  ticks after their deadlines, as at normal speed (one check per second, up to 14 ticks late);
  without it, hasted removals in these captures came at most 6 ticks late (two checks per
  second).
- **Saving.** The game refuses every save during a stop, with or without the mod: while the
  counter is set, `CGameArea::AIUpdate` keeps the area's battle music up, and
  `CGameArea::CanSaveGame` then answers "cannot save during combat"
  ([research note](../10-timestop-haste-engine-clocks.md)). What the mod moved is in the
  effects, so a game saved after a stop loads with it.

**Area cases.** Times in ticks after the stop's end; T1 and T2 are the Bounty Hunters.

| Case | Without the mod (n3, E and F n4) | With 100 and 200 (d2) |
|---|---|---|
| A: clouds exist when the stop begins | Both clouds' pulse countdowns held through the 15 s stop (44 → 43, 40 → 39). T1's sleep from the Stinking Cloud ended in the stop, 25 ticks after its deadline. | The same countdowns. T1's sleep moved 223 ticks and ended 21 after its moved deadline; both targets' `CBRTSAV` moved 223 and 224. |
| B: Stinking Cloud cast in the stop | Stayed at Imoen until the end, arrived 13 ticks after it. | The same, 15. |
| C: Magic Missile and Fireball cast in the stop | Held at Imoen. Fireball exploded +10, the missiles hit +12, +13, +20, +21. | Fireball +11, missiles +12, +13, +20, +21. |
| C2: Fireball flying when the stop begins | Stopped in the air, exploded +9. | The same, +8. |
| D: Delayed Blast Fireball and Skull Trap cast in the stop | Waited, exploded +10 and +11. | +11 and +12. |
| E: Imoen hits T1, whose contingency casts Magic Missile at her | The second round hit in the stop. The contingency fired at once; its missile waited and hit her 1–2 ticks after the end. | The same; T1's contingency effect moved 225 ticks. |
| F: instant damage, then melee | `CBRTDMG` landed at once in the stop; the second round hit in the stop. | The same. |
| G: Spell Revisions' Cloudkill exists | Its countdown held through the stop (52 → 51). | The same. |

So the engine holds every projectile and cloud the same with and without the mod, and the
mod adds what the area rule asks of durations: an existing cloud's debuff on a frozen creature
waits too (A). Hits and instant damage land at once; Magic Missile and Fireball cast in a
stop land 10 to 21 ticks after it ends, the one difference to the rule, whose hooks wait for
Christopher's decision. In sessions n3, n4 and d2, Imoen's first `AttackOneRound` hit once in
six, although with `CBRTHIT` only a natural 1 misses; every second round hit.

**Against the prototype** of the Time Stop lab (`fixstop_01`, `fixhaste_01`, `fixhaste_02`
there): both shift each deadline once per frozen tick before the expiry check, by 89 there
and 90 here. Through the stop the prototype healed +18, +33, +63, +182, +212, +242, keeping
each heal's phase across rebuilds; the mod healed +23, +38, +68, +203, +218, +248, with the
native rebuilds (the buff's removal at its moved deadline gave the 45-tick gap of `base`).
Under Haste both healed 6 times at +16, +31, +61, +91, +121, +151. The prototype corrected
one subject's two fixtures; the mod covers every creature and timed effect, Slow and the
periodic list as a whole.

## Host validation

```powershell
pwsh -NoProfile -File research/timestop-lab/Test-LabGuards.ps1
$env:CBRTS_TEST_DEPS = '%USERPROFILE%\AppData\Local\Temp\cbr-timestop-research-20260926\pylibs'
python -B -m unittest discover -s research/timestop-lab -p 'test_*.py' -v
```

Python 3.11, `lupa.luajit21`, Capstone 5.0.9, pefile 2024.8.26,
Keystone 0.9.2 and Unicorn 2.1.4 were used. The extra native-analysis libraries
are in the temporary dependency directory, not installed into the game.
For the 1.3.1 pin on 2026-10-20, the same versions were installed with
`pip install --no-deps --require-hashes --target <dir>` beside lupa 2.8 (LuaJIT 2.1):
all 14 guard groups and all 32 Python tests passed. With the smoke-test fixes above there
are 16 guard groups and 34 Python tests, all passing. The fresh-party tooling adds 23
Python tests (QA menu 12, console client 11); on 2026-10-20 all 16 guard groups and all 57
Python tests passed. The Time Stop trigger adds 3 queue-request tests that run the request
against stub bindings; on 2026-10-23 all 16 guard groups and all 60 Python tests passed.
The Haste trigger adds 2 more; after step 3 on 2026-10-23, all 16 guard groups and all 62
Python tests passed.

The correction prototype adds 36: 34 in `test_fix.py` and 2 for the `fix` request in
`test_lab_rc.py`.

- 18 run the four hook bodies in Unicorn on synthetic memory. They cover one deadline shift
  per frozen world tick, one admitted dispatch per world tick on active time, the phase
  restore across rebuilds, a reused parent address with another origin, the reseed after a
  heal and a bounded walk of a cyclic list. One test hands its state through all four hooks
  across a hasted heal and a stop.
- 7 run `Select`, `Verify`, `Disable`, `Status` and `Install` against stub bindings:
  fail-closed selection, the idle frozen hook until `Verify`, a layout mismatch, and the
  pause and main-menu preconditions.
- 4 emulate the native regeneration AIUpdate (`0x1A5CA0`) from the pinned executable, with
  the hooked epilog: a suppressed dispatch is a no-op, elapsed drives the countdown, the
  pulse rule holds, and a frozen worker leaves through the patched epilog untouched.
- 5 check the windows in the pinned executable: whole instructions without relative
  operands, no direct branch and no table or pointer into a window, the role registers, and
  no overlap with the observer's windows.

A scratch mutation check replaced 15 single guards or rules in `CBRTFix.lua`, one at a time:
among them the once-per-tick guards, the resref and opcode filters, the origin check, the
reseed formula, and fail-closed selection and verification. `test_fix.py` failed for every
mutant. After step 4 on 2026-10-23, all 16 guard groups and all 98 Python tests passed.

The [Time Clocks lab](#time-clocks-lab-2026-10-23) adds its variant, installer, requests,
driver, report and Spell Revisions staging. On 2026-10-24 all 21 guard groups passed with
`CBR_LAB_VARIANT` unset and set to `timeclocks`, and so did the 96 tests of the modules that
need no native-analysis library, under both:
`python -B -m unittest test_tc_session test_tc_requests test_lab_rc test_fixtures test_lab_variant test_decode_trace test_qa_menu test_sr_cloudkill test_tc_report`
in `research/timestop-lab`, with `PYTHONPATH` at the repository's `tests`. The dependency
directory above is no longer on this PC, so `test_observer.py` did not run.
Fixture and decoder tests use synthetic data; assembly tests use synthetic memory
and the pinned executable on disk. They do not execute the game or prove the
EEex trampoline integration works at runtime.
