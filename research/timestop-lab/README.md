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
On 2026-10-25, step 5 tested the revised correction with the other Haste kinds, Slow, pauses,
stops with removal or application in them, caster and immune subjects, attacks, movement and
save/load ([below](#lab-run-of-2026-10-25-step-5)). On 2026-10-26, step 6 tested
`CBRTCor.lua`, the correction for every creature, every timed effect and all four periodic
families, with Haste, Slow, stops, pauses, a maintained group, time compression and save/load
([below](#lab-run-of-2026-10-26-step-6)). A cloud's lifetime through a stop, area transitions
and saving during a stop are still open.

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

Install, staging and the preflight refuse while any `Baldur.exe` or `InfinityLoader.exe`
runs, another agent's lab included. Steps 1 to 5 also ran the game alone: take the exclusive
`bg-game-install.lock` of the shared lab coordination folder, wait until no BG game runs, then
run `python -I lab_quiet_run.py run <lab> <profile> <out.json> 600`, and release the lock by
renaming it only after no process runs from the lab. Step 6 staged while no BG game ran and
then started the game in a parallel lab slot:
`python -I bg_lab_slots.py run <lab> <profile> <out.json> 3600 --owner … --purpose …`. It
waits only for this lab's own processes, the exclusive lock and streaming software, runs the
same quiet runner, and releases the slot when the game exits. Either way the run ends at its
time limit, on a message box, or when the game exits; `<out.json>` records the guards' result.

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
  lab-only copy. It names 20 stock items (`CBRTSQA_*`): the SoA logo, Single Player, New
  Game, the character-creation buttons, Import's Character File, the Done buttons, the
  difficulty and the dialogue confirm button; and for one save and reload, the left sidebar's
  quick-save and options buttons, the options screen's Load Game, the two-button popup's
  confirm and the load screen's Load button. Each name is added only where exactly one item
  with the stock action exists. It also adds an inert START label (2.7.3 reopens START after
  the campaign choice only on the next mouse event) and a 1×1 polling widget to the 15 menus
  that cover START or the world during character creation, dialogue and the reload. The
  builder is idempotent and refuses unknown actions, ambiguous or missing items and name
  collisions.
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
  `status`, `subject`, `nearby`, `creature`. Changing: `watchdog`, `install`, `arm`, `stop`,
  `export`, `start-soa`, `click`, `pick-character`, `set-name`, `dialog`, `pause`, `queue`,
  `quit`, `fix` for the [correction prototype](#correction-prototype-cbrtfixlua), `activity`
  for the [activity recorder](#activity-recorder-and-weapon-hit-dummy) and `save` for the load
  screen's list. `fix op=status`, `activity op=read` and `save op=list` only read. `save
  op=select` takes the save's exact folder (`file`) or the start of its name (`prefix`). The
  list shows the name from `slotName`; `sName` is the party leader's name. The engine rotates
  quick saves through `Quick-Save`, `Quick-Save-2` and `Quick-Save-3`, so a prefix can match
  several. Each changing
  request checks its precondition first (menu on the stack, no transition, paused game, armed
  or disarmed capture, the subject's name). `lab_rc.py` refuses Lua reserved words as argument
  names, because `{then = …}` would not compile.
- **Time Stop trigger and clocks.** `queue what=timestop` makes the controller in portrait 1
  wait `SmallWait(N)` AI updates and then apply `CBRTSTP` to itself, so it is the caster
  and the subject is frozen. It refuses without an armed capture, without exactly one of
  each fixture on the subject, while a stop runs, with a busy controller, or with the subject
  as controller. `caster=subject` lets the subject cast its own stop instead. With the
  controller as caster, `step` adds one action `step_wait` AI updates after the stop, while
  the subject is frozen: a second stop (`stop`), `CBRTRMR` on `Player1` (`remove`),
  `CBRTRMR` and then `CBRTREG` (`refresh`), or `CBRTREG` alone (`apply`, only with `CBRTBUF`
  alone on the subject before, because the correction verifies its list walk on a timed
  effect). The request first checks that `Player1` resolves to the subject.
  `queue what=fixtures` refuses while a fixture from an earlier case is still on the subject;
  `only=CBRTBUF` or `only=CBRTREG` applies just one of them. `queue what=immunity` applies
  `CBRTTSI` before the fixtures, and `queue what=remove` applies `CBRTRMR` or `CBRTRMB` after
  `SmallWait(N)`, optionally reapplying the removed fixture `reapply_wait` updates later.
  `subject` also reports every lab fixture (`CBRT*`), each actor's current action and state
  flags, and the raw counters behind native effect timing on 2.7.3.0:
  - `+0x3A0`: the full effect check runs only when this value mod 15 equals the actor ID
    mod 15 (`0x3ABB7C–0x3ABBC5`).
  - `+0x1A08+0x38`: the regenerated periodic list's counter, which the dispatcher copies into
    each worker (`0x22653D`).
  - `+0x520C`: the frozen-actor marker (`0x3ABA9D`).
  - `+0x4BA4`: `m_newEffect`, which is set when a stop ends (`0x3ABACE`).
- **Speed trigger.** `queue what=speed` (until 2026-10-24 `what=haste`) makes the subject wait
  `SmallWait(N)` AI updates and then apply `CBRTHST` (Haste), `CBRTIHS` (Improved Haste),
  `CBRTWHS` (Weak Haste), `CBRTSRH` (SR-shaped Haste) or `CBRTSLW` (Slow) to itself. It
  refuses without an armed capture, with a busy subject, with a speed fixture already on it,
  with a partial or doubled fixture set, or while a stop runs. `subject` lists the speed
  fixtures with their deadlines. Its `ai_speed` is `m_AISpeed` (`+0x58`): 1 at normal speed,
  0 while hasted and 3 while slowed.

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
| `CBRTWHS` | op16, p2=2, twenty seconds | Weak Haste: speed without attack bonus |
| `CBRTSRH` | op176 p1=6, op1 p1=6, op142 icon 38; twenty seconds | SR-shaped Haste: Spell Revisions 4.19 builds its Haste (`SPWI305`) from movement rate and attacks per round, without op16 |
| `CBRTSLW` | op40, twenty seconds | Native Slow |
| `CBRTTSI` | op310, p2=1, forty seconds | Time Stop immunity |
| `CBRTRMB`, `CBRTRMR` | op321 type 0, instant, resource `CBRTBUF` or `CBRTREG` | Explicit removal of one fixture |
| `CBRTDUM` | op208 p1=1 and op175 p1=0 p2=2 (any creature), 900 seconds | Keeps the weapon-hit dummy alive and helpless, so every swing at it hits |

The engine must confirm actual durations. These resources have one single-target
ability, no TLK or secondary-resource dependency, and no area effect. All but `CBRTSRH`
and `CBRTDUM` carry one effect. Fixtures ignore MR and are nondispellable; removal tests use
explicit source removal (`CBRTRMB`, `CBRTRMR`), not a dispel check that cannot affect them.
The removal fixtures name only lab fixtures, since op321 with an empty resource would strip
every effect without a parent resource. The first five keep the bytes of the captures up to
step 4; `test_fixtures.py` pins their hashes.

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
5. Repeat with the revised correction and add Improved, Weak and SR-shaped Haste, Slow, pauses,
   consecutive stops, removal, refresh and application during a stop, explicit removal, caster
   and immune subjects, attacks and movement, and save/load. **Done on 2026-10-25**
   ([results](#lab-run-of-2026-10-25-step-5)).

Steps 1 to 3 resolved the disputed engine paths, step 4 tested the first actor/effect-scoped
correction against them, and step 5 the robustness cases. Saving during a stop, time
compression and rest, area transition, area effects, SR/SCS maintenance graphs, other periodic
opcodes and party/enemy symmetry remain explicit later gates; component absence was dropped on
2026-10-25 ([decisions](../10-timestop-haste-engine-clocks.md#compatibility-and-unresolved-design-decisions)).
This lab has no current-save safety claim.

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

`CBRTFix.lua` is the first clock correction, made for step 4 and revised on 2026-10-25. It
acts on one selected subject and on two effects: `CBRTBUF`, and `CBRTREG` (op98 p2=3, a
regeneration worker that counts its phase up to the period and then heals). Both must have
absolute timing (`0x1000`). No other effect, opcode or actor is touched. At normal speed it
keeps the native heal pattern, including the 15-tick second interval after the first heal; it
only removes the influence of Time Stop, Haste and Slow. Christopher chose the native pattern
on 2026-10-23, and on 2026-10-25 that periodic effects run in world time under Slow too, while
movement and attacks stay slowed.

Five hooks do the work. Their windows were decoded from the pinned executable like the
observer's, and none overlaps an observer window.

| Hook | Site | What it does |
|---|---|---|
| Frozen | `0x3ABA9D`, after the engine marks a frozen noncaster | In each world tick in which the subject is frozen, once: moves each selected parent's deadline one tick later, and the regeneration's origin (`+0x6C`) with it. This happens before that pass checks for expiry. An immune subject or the caster never reaches this site (`0x3ABA67–0x3ABA9B`). |
| Dispatch entry | `0x226513`, at the start of the periodic-list dispatch | For the subject, records `+0x3A0` of its current `ProcessEffectList` call (raised at the start of every call) and the highest world tick whose dispatch ran. The construct hook uses both to tell whether a new regeneration's first tick was already processed. The dispatcher has two direct callers, both checked: `0x39D5DD` (time compression) and `0x3ADFF7`. |
| Dispatch | `0x226543`, after the list counter is copied into the worker | Runs the tracked worker on the subject's active time T: world time minus its frozen ticks, plus one for the frozen tick that a pause repeats. The first admitted dispatch waits for the parent's first active tick and keeps the native grid through an offset from the list counter recorded at construction. After that, one dispatch per active tick is admitted; a repeated tick or a second hasted dispatch runs as a no-op (counter 0, elapsed 0). Elapsed is the number of active ticks since the last admitted dispatch, so the worker counts down once per world tick. When a slowed subject skips ticks, the hook scans them for a pulse boundary and delivers it, capped at the parent's last tick; gaps of 15 or more pay whole periods. Any other regeneration worker of the subject stays native and is counted as unmatched. |
| Construct | `0x1BEDD2`, after the regeneration seeds its worker | A rebuilt worker of the tracked parent gets the kept phase back, if the parent's origin moved by exactly the frozen ticks counted since; its countdown resumes on the next active tick. Another `CBRTREG` parent, or one whose origin does not fit, becomes the new tracked entry with the native seed. Its first tick is the construction's active tick, or the next one when the tick was already processed: an application outside the subject's call after its dispatch, one while paused, or one in a counted frozen tick. |
| Worker exit | `0x1A5F19`, the regeneration AIUpdate epilog | Records the worker's phase. After a heal it records the phase that a native rebuild on the next un-hasted tick would seed: floor((active time + 1 − active origin)/15) mod period. |

The 2026-10-25 revision fixed both one-tick residuals of step 4 and normalized Slow:

- **R7, grid anchor.** A regeneration applied while paused to a hasted subject took its offset
  from the extra hasted update at the paused world value. The first tick now comes from the
  construction, so that update is held (`held_first`) and the grid matches an un-hasted
  subject's.
- **R8, worker end.** A rebuild in the second hasted update of a tick reseeded remaining =
  deadline − world after the tick's admitted dispatch. The countdown now resumes on the next
  active tick, and every hasted elapsed of the corrected worker covers the active ticks since
  the last admitted dispatch (`stretched` counts the ones above 1).
- **Slow.** A dispatch hook that could only drop dispatches kept a slowed subject on its slower
  native cadence. Elapsed now covers the skipped ticks, and the boundary scan delivers their
  pulse.

Remaining limits, all covered by host tests:

- An application while paused during a stop misses the shift for the frozen tick that the
  pause repeats, so it behaves as applied one active tick earlier.
- A stop that starts between a hasted subject's two updates of a tick counts that tick as
  frozen.
- A regeneration first built inside a slowed subject's own update can anchor one tick late;
  slowed heals land within one tick of an un-slowed subject's.
- Gaps of 15 ticks or more give the exact pulse count, but the heal phase only approximately.
- Native pauses shift the native grid one tick each; the corrected grid stays locked to active
  time.
- Native Slow also slows the subject's expiry checks, which the correction leaves alone.
- The design assumes that `ProcessEffectList` reaches its dispatch in every call that raised
  `+0x3A0`; an early exit would leave the recorded call behind.

Controls, also available as the Remote Console request `fix` (`op=install`, `select`,
`verify`, `status`, `disable`):

1. `CBRTF.Install()` at the fresh main menu. It first runs `CBRTF.Inspect()`, which checks
   the lab, the image base and timestamp, the regeneration vtable and all five windows.
   Then it compiles the bodies and installs the hooks, disabled.
2. `CBRTF.Select(0)` while paused, **before** the fixtures, so that the regeneration's first
   construction is tracked. It disables the correction first, so a refused selection leaves
   it off. It clears the counters and the tracked entry and stores the subject's pointer, ID
   and timed-list offset. Paused, world time stands one tick behind the last processed tick,
   so it records that tick and the subject's current `+0x3A0` for the construct hook. The
   frozen hook walks the timed list natively. It stays idle until the walk is proven on the
   subject's own effects; an empty list proves nothing.
3. Apply the fixtures, then call `CBRTF.Verify(0)` while paused. It requires the selected
   subject, at least one timed effect, and a native walk that matches the EEex iterator. A
   mismatch disables the correction.
4. `CBRTF.Status()` reports the counters (frozen ticks, deadline shifts, admitted, suppressed
   and unmatched dispatches, restored phases, new parents, heal reseeds, held first
   dispatches, stretched elapsed values, long gaps) and the tracked entry.
5. `CBRTF.Disable()` needs no pause. One aligned store turns it off, and every later pass is
   native. Destroying the game session disables it too.

The request refuses `select` and `verify` unless the game is paused and portrait 0 carries
the subject's name.

## Activity recorder and weapon-hit dummy

Attack and movement checks need records that the effect observer does not keep.

- **Recorder.** The request `activity` keeps its state in the global `CBRTA`. `op=install`
  registers two EEex listeners once per game process: every action the armed subject starts
  (world time, action ID, position), and every weapon swing of the armed subject that hits
  (world time, target ID). Both listeners return nothing, so they never block a hit or change
  an action. `op=arm` starts recording for portrait 0 and clears earlier records; `op=read` and
  `op=disarm` return them. More than 500 records of either kind end the recording with
  `overflow`.
- **Dummy.** EEex calls the weapon-hit listener after a hit roll succeeds, never on a miss. So
  the target is a creature that every swing hits: `queue what=dummy` lets the controller create
  `BATIN01` (a neutral bat without scripts, 8 HP), and `queue what=hold` makes it apply
  `CBRTDUM` to itself. A held creature is helpless, which the engine's hit roll turns into an
  automatic hit, and the minimum of 1 HP keeps it alive. `creature` reads the dummy's effects.
- **Walk and attack.** `queue what=activity` stores the dummy as the subject's EEex scripting
  target and queues `MoveToPoint` to a given point, then `Attack(EEex_Target("CBRTDummy"))`.
  The movement time is the gap between the starts of the two actions.
- **Back to the start.** The attack on the dummy never ends by itself, and the subject's own
  `ClearActions` empties its queue but leaves the current action running. `queue what=halt`
  therefore lets the controller run `ClearActions(Player1)`, which ends it. `queue what=walk`
  then drops the subject's queued actions and walks it back.

The walk runs along a straight row of free search-map cells in AR0602, west from (3704, 2850)
to (3512, 2850), with the dummy at (3480, 2850). Those points come from the area's own search
map (`AR0602SR.BMP` in the lab's BIF) around the party's position after the opening.

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
went into the next lab run, step 5 ([below](#lab-run-of-2026-10-25-step-5)).

## Lab run of 2026-10-25 (step 5)

Step 5 tested the 2026-10-25 revision of `CBRTFix.lua` (R7, R8, Slow) and the items that step 4
left open: the other Haste kinds, Slow, pauses, stops with a step in them, explicit removal,
caster and immune subjects, attacks and movement, and save/load.

- **Run.** One quiet run through `lab_quiet_run.py run … 3600`, holding the exclusive lock, after
  a `-Refresh` restage with the twelve fixtures. At the fresh main menu, `CBRTS.Install()`
  installed its 8 sites, `CBRTF.Install()` its 5, disabled, and `activity op=install` its two
  listeners. The party came from the [fresh-party sequence](#fresh-test-party-in-the-hidden-game).
  Between cases, the correction was disabled, a disarmed run let every lab fixture run out, and
  `ApplyDamage` restored at least 6 missing HP. `rc/quit.lua` ended the run after 2,684 s, and the
  lock was released right after. No guard tripped: audio peak 0.0, pointer clip unchanged,
  nothing left in the job.
- **Trigger.** As in step 4, each case started paused: `Arm(0)`, `fix op=select` in corrected
  cases, the fixtures, `fix op=verify`, a `subject` probe, then the case's own event.
- **Decoding.** `decode_trace.py` exited 0 for 27 of the 29 traces: complete, no issues. The two
  captures armed after a load exited 1, as they should: the subject's worker was built during the
  load, before the capture, so its events lack a construct (`unmatched_selected_worker`). The
  files stay in the lab with their decoded JSON/CSV, the request log, and each case's plan and
  correction status.

Times are world ticks; +n counts from the fixtures' application. "Prediction" applies the native
un-hasted rules from step 3 to the case's own probe counters, in active time.

### Speed effects and pauses

| Case | Event | Heals against the prediction | Worker end | Correction |
|---|---|---|---|---|
| `fixctl_11` | None. | Same 6 ticks. | Deadline − 1. | 179 admitted. |
| `fixhaste_11` | Haste from +74. | Same 6 ticks. | Deadline − 1 (step 4: the deadline). | 105 suppressed, 4 stretched. |
| `fixhaste_12` | Haste first; the fixtures while hasted; Haste off at +78. | Same 6 ticks (step 4: one tick early each). | Deadline − 1. | 1 held first dispatch. |
| `fixihaste_11` | Improved Haste from +80. | Same 6 ticks. | Deadline − 1. | 99 suppressed. |
| `fixihaste_12` | Improved Haste first; off at +75. | Same 6 ticks. | Deadline − 1. | 75 suppressed. |
| `fixwhaste_11` | Weak Haste (op16 type 2) from +80. | Same 6 ticks. | Deadline − 1. | 99 suppressed. |
| `fixsrhaste_11` | SR-shaped Haste queued for +74. | Same 6 ticks. | Deadline − 1. | None suppressed. |
| `natslow_11` | Native Slow first, not corrected. | 3 heals, 60 ticks apart. | Deadline + 19. | — |
| `fixslow_11` | Slow first. | 6 heals; 3 of them one tick late. | Deadline. | 83 stretched. |
| `fixslow_12` | Slow from +68. | 6 heals; 3 of them one tick late. | Deadline. | 53 stretched. |
| `fixpause_11` | 9 pauses of 1.4 s. | Same 6 ticks. | Deadline − 1. | 4 repeated ticks suppressed. |
| `fixpause_12` | Haste first, then 9 pauses. | Same 6 ticks. | Deadline − 1. | 184 suppressed. |

Haste, Improved Haste, Weak Haste and Slow began on their planned ticks. The hasted subject got
two dispatches per world tick (`m_AISpeed` 0), the slowed one a dispatch every second tick
(`m_AISpeed` 3, `STATE_SLOWED`). SR-shaped Haste set no state flag and left one dispatch per tick.

### Stops, removal and refresh

| Case | Event | Heals | Buff | Regeneration | Correction |
|---|---|---|---|---|---|
| `fixstop_11` | Two stops of 89 frozen ticks, +74 to +162 and +179 to +267. | +23, +38, +68, then +276, +306, +336: the prediction in active time. None inside a stop. | 16 ticks left when the first stop began, all used between the stops. Removed at its shifted deadline, the first free tick after the second stop. | Removed 2 ticks after its shifted deadline; worker end deadline − 1. | 178 frozen ticks, 356 shifts. |
| `fixstop_12` | Stop from +70; 30 ticks in, `CBRTRMR` removes the regeneration. | +19, +34, +64 before the stop, none after. | 20 ticks left at the stop. Survived it; removed 12 ticks after its shifted deadline. | Removed in the stop's 31st tick, its workers destroyed. | 89 frozen ticks; 119 shifts (89 buff, 30 regeneration). |
| `fixstop_13` | The buff alone; stop from +41; 30 ticks in, `CBRTREG` applied. | 6 in the native pattern, the first 24 ticks after the stop. | 49 ticks left at the stop; removed 13 ticks after its shifted deadline. | Deadline moved by the 59 frozen ticks after the application; removed 3 ticks after it. | 89 frozen ticks, 59 held first dispatches. |
| `fixstop_14` | Stop from +66; 30 ticks in, `CBRTRMR` and then `CBRTREG` (refresh). | +27, +42 from the first parent, then 6 from the new one in the native pattern, the first 21 ticks after the stop: 8 in all. | 24 ticks left at the stop; removed 5 ticks after its shifted deadline. | The new parent's deadline moved by the 59 frozen ticks after it; removed at that deadline. | 89 frozen ticks, 2 new parents, 59 held. |
| `fixremove_11` | No stop; `CBRTRMR` at +50, `CBRTREG` again at +80. | +17, +32, then 6 from the new parent in the native pattern: 8 in all. | Native. | First parent's workers destroyed at +50; the new parent removed 4 ticks after its deadline. | 2 new parents. |
| `fixcaster_11` | The subject casts a stop at +70. | The 6 predicted ticks, 3 during the stop. | Removed inside the stop, 5 ticks after its deadline. | Native. | 0 frozen ticks. |
| `fiximmune_11` | `CBRTTSI` (op310) on the subject; the controller's stop at +70. | The 6 predicted ticks, 3 during the stop. | Removed inside the stop, 2 ticks after its deadline. | Native. | 0 frozen ticks. |

The observer's removal site does not see op321 removals: `fixstop_12`, `fixstop_14` and
`fixremove_11` show them only as destroyed workers and missing dispatches.

### Attacks and movement

The subject walked 192 pixels from (3704, 2850) to (3512, 2850) and then attacked the held
dummy; each recording lasted 253 to 256 ticks.

| Case | Speed, correction | Walk | Hits | Heals |
|---|---|---|---|---|
| `act_nrm_11` | Normal; native; party AI on. | 22 ticks. | 4 (gaps 40, 70, 90). | 6; the 4th one pulse late (below). |
| `act_nrm_12` | Normal; native. | 22 ticks. | 4 (gaps 40, 50, 100). | 6, the prediction. |
| `act_hst_11` | Haste; native. | 11 ticks. | 5 (gaps 45, 59, 46, 45). | 14; worker end 12 ticks early. |
| `act_hstfix_11` | Haste; corrected. | 11 ticks. | 5 (gaps 55, 45, 50, 50). | 6, the prediction; worker end deadline − 1. |

After `act_nrm_11` the subject kept attacking, and the walk back failed: its own
`ClearActions` leaves the current action running. The controller's `ClearActions(Player1)`
ended it, which became `queue what=halt`. Before `act_nrm_12`, `game:ToggleAI()` turned the
party AI off, so the last three cases ran only the queued actions. In `act_nrm_11` the buff's
removal at +91 rebuilt the list between two pulses and reseeded phase 0, so the 4th heal came
15 ticks late. The correction keeps the phase across such a rebuild.

### Save and reload

Three tries; the third gave the full answer.

- **`fixsave_11`.** A corrected stop from +70; all 6 heals came on the predicted ticks before the
  quick save at +249. The regeneration's deadline stood at 41797 instead of 41708 and its origin
  at 41617 instead of 41528, both shifted by the 89 frozen ticks. The reloaded game ran 46 ticks
  before the first pause, enough for the regeneration's last 20 ticks to run out. Then the
  selection failed: `save.lua` compared the prefix with `sName`, the party leader's name, while
  the load screen shows `slotName`.
- **`fixsave_12`.** With `slotName` fixed, the first request the game claimed after the load
  paused it, 10 ticks after the load. But the quick save, taken 28 ticks after a stop's end,
  had written nothing, so this loaded `fixsave_11`'s save. The stop's op231 effect lasts 180
  ticks on its caster and was most likely still running; the cause is not isolated. The
  regeneration came back with the shifted deadline 41797 and origin 41617 and was removed at that
  deadline (`fixload_12`), with no heal after the load.
- **`fixsave_13`.** A stop from +6 and the quick save at +207, after the caster's op231 effect had
  run out; the click wrote at once. Before it, 4 heals on the predicted ticks. The engine rotates
  quick saves through `Quick-Save`, `Quick-Save-2` and `Quick-Save-3`, so the reload named the
  folder exactly. The regeneration came back with the same deadline (42174) and origin. The
  correction's own state is not saved, so it ran natively after the load. The remaining two heals
  came, 6 in all, at 42118 (inferred from HP and the list grid) and 42148, against 42116 and 42146
  on the corrected grid: the load restarted the subject's list counter. The worker ended at
  deadline − 1.

### What this shows

- **R7 and R8 are fixed.** Every Haste case, normal, Improved and Weak, entering and ending,
  healed on the un-hasted ticks with the worker ending at deadline − 1, like the control.
- **SR-shaped Haste needs no correction.** Without op16 the subject keeps one update per tick, so
  the fixture behaves like the control.
- **Slow is normalized.** 6 heals instead of 3. A slowed subject updates only every second tick,
  so a heal that falls on the other tick comes one tick late, and so does the worker's end. That
  is as close as a dispatch-side correction can get.
- **Pauses leave the corrected grid alone.** With and without Haste, 9 pauses changed nothing:
  each repeated tick was suppressed.
- **Stops count each frozen tick once, and removal stays removal.** Two stops in a row shifted
  the deadlines by 178. An effect removed during a stop stayed removed. An effect applied or
  refreshed during a stop got no credit for the frozen time: its first tick was the first free
  tick, and its whole duration ran after the stop. Removal and reapplication without a stop
  behaved the same.
- **Caster and immune subjects stay native.** The engine does not freeze them, the correction
  counted no frozen tick, and their buff expired inside the stop.
- **Attacks and movement keep their native acceleration.** Corrected Haste walked as fast and hit
  as often as native Haste while the regeneration kept world time.
- **Shifted deadlines survive save/load; the phase does not.** Deadlines and the regeneration's
  origin are native effect fields, saved and loaded unchanged. After a load the correction must
  be selected again; the native grid restarts, here 2 ticks off, with the heal count unchanged.
- **Expiry timing stays native.** Removals still wait for the subject's next full pass: up to 14
  ticks late at normal speed, about 7 hasted, and 21 for the natively slowed regeneration.

Not covered yet: saving during a stop, time compression and rest, area transition, area
effects, SR/SCS maintenance graphs, other periodic opcodes (poison, disease), party/enemy
symmetry, component absence and a clean process restart. The quick save after the stop that
wrote nothing is unexplained. Christopher decided afterwards that poison, disease and repeated
effects get the regeneration handling, that area effects stop with the stop, and that component
absence needs no test
([decisions](../10-timestop-haste-engine-clocks.md#compatibility-and-unresolved-design-decisions)).

## Correction for every creature `CBRTCor.lua`

`CBRTCor.lua` replaces the one-subject prototype for step 6. It corrects every creature, party
or not, and every effect with an absolute deadline, a delayed start or a periodic time origin,
timed or equipped, across all four periodic families: regeneration (op98), poison (op25),
disease (op78) and repeated EFF (op272). It follows Christopher's rule: in a Time Stop
everything but the caster and Time-Stop-immune creatures stops, periodic effects included;
Haste and Slow change actions and movement only, and periodic effects keep world time; at
normal speed the native pattern stays. `CBRTFix.lua` stays as the record of steps 4 and 5;
`Install()` refuses a process in which it is installed.

The bookkeeping is Lua. Eight thin assembly gates call it through `EEex_GenLuaCall`; their
windows were decoded from the pinned executable like the prototype's (whole instructions, no
relative operand, no branch target past the first byte).

| Gate | Site | What it does |
|---|---|---|
| Frozen | `0x3ABA9D`, after the engine marks a frozen noncaster | Once per world tick and creature, before that pass checks for expiry: moves every timed effect with an absolute deadline (`0x1000`) or a delayed start (timings 6, 7, 8) one tick later, and the time origin (`+0x6C`) of op25, op78, op98 and op272, timed or equipped. A slowed creature counts the ticks it skipped from its own previous frozen pass. Its first frozen pass counts every tick since its last update that the stop held: also a skipped tick the stop began on, and, when the stop began in the tick of its last update but after it, the tick that followed. A tick in which its own update ran before the stop began (a hasted creature's first update) counts nothing. |
| Entry | `0x226513`, the periodic dispatcher's start | Decides once per creature and pass, so every worker of it sees the same decision. One delivery per active tick (world time minus the creature's frozen ticks); a second hasted update, a frozen update and the tick a pause repeats are suppressed. The native workers ignore every frozen update, so active ticks a slowed creature skipped before a stop stay due for its first update after it; after more than 14 ticks without a pass the creature restarts on the native list counter. Time compression (elapsed above 1) passes natively and re-anchors the counter; during a stop it moves a frozen creature's effects by the span. A stop that ended on a tick a slowed creature skipped is caught up from the other frozen creatures' marks. |
| Dispatch | `0x226543`, after the list counter is copied into the worker | Only the four worker classes reach Lua. The worker's counter becomes the creature's fixed offset plus active time, which at normal speed is the native list counter, and elapsed the active ticks since its last countdown. A suppressed call is a no-op (counter 0, elapsed 0). A slowed creature's gap is scanned for the latest pulse boundary with the family's step (poison 2, the others 1), never before the effect existed and never past its last tick. |
| Construct (5) | after the phase seed, before `CObList::AddTail`: regeneration `0x1BEDD6`, poison `0x1BBB09`, disease `0x1B1894` and `0x1B1AC1`, repeated EFF `0x1BFEC8` | Keeps the native reseed, taken at the active tick a creature without Haste, Slow, pauses or stops would have rebuilt. A worker built after its creature's delivery in this tick seeds and counts down as of the next active tick (rule 1, "ahead"); one rebuilt after a slowed pass that delivered a pulse, as of the tick after that pulse (rule 3, "behind"). The rebuild that a stop's end forces keeps each worker's phase (rule 2, "carried"). A parent is known by its address and its origin, moved only by the frozen ticks counted since; a new one pulses only after the tick it was applied. |

- **State.** Per creature, keyed by the sprite pointer; another object ID at the same address
  starts over. Creatures unseen and parents not rebuilt for 9,000 ticks are forgotten.
- **Fail closed.** A Lua error in a gate clears the shared enabled flag: every gate is off and
  the game runs natively.
- **Load.** Nothing of the correction is saved. EEex's destroyed-session listener (quit, load)
  clears the per-creature state and counts `sessions`; the correction stays enabled, and each
  creature's clock restarts at its first update. An effect applied before that update counts
  natively.

Controls, also as the Remote Console request `cor` (`op=install`, `status`, `disable`,
`record`; while paused `enable`, `observe`, `watch`, `export`):

1. `CBRTC.Install()` at the fresh main menu checks the lab, the image base and timestamp, the
   four worker vtables and all eight windows, then installs the gates, off.
2. `CBRTC.Enable(0)` while paused: portrait 0's timed and equipped lists must match the EEex
   iterator. Then every creature is corrected.
3. `CBRTC.Observe()` runs the gates with nothing but the recorder, changing no effect or
   worker, so native controls use the same measurement.
4. The recorder follows creatures chosen by object ID (`Watch`) and logs frozen passes,
   dispatcher entries, dispatches and constructions, with the native value next to each
   corrected one. `Record` starts and stops a record, at most 400,000 events;
   `ExportRecord(name)` writes `cbr-timestop-output/NAME.jsonl` and refuses an existing file.
   `decode_cor.py` turns a record into per-creature passes, modes and dispatch checks and
   per-effect units, intervals, deadline shifts and construction rules; it shares the native
   worker rules in `periodic_model.py` with the host tests.
5. `CBRTC.Status()` reports the counters; `CBRTC.Disable()` turns everything off with one
   aligned store.

Step 6 added fixtures on `CBRTREG`'s schedule (once every 2 seconds for 12 seconds): `CBRTPSN`
(op25), `CBRTDIS` (op78) and `CBRTRPT` (op272 with `CBRTRPE`, one crushing damage). `CBRTVIT`
(+200 maximum HP, never below 1 HP) and `CBRTHEL` (60 HP healed) give any creature room for
heals and damage. `CBRTHPG` is a group like Tempus' Holy Power: an op272 upkeep every second
that applies `CBRTHPE` (AC +1 for 31 ticks), an op44 child for 14 seconds and an op321 cleanup
of the whole group delayed by 12 seconds. The request `apply` queues lab fixture applications
on any creature; `effects` lists effect clocks by object ID.

Remaining limits, all covered by host tests:

- A slowed creature updates every second tick: each family's units land within one tick of an
  un-slowed creature's. A pulse due on the skipped tick right before a stop comes with its first
  update after the stop, up to two active ticks late. With several families, a unit of one family
  on a skipped tick reseeds the others in the same call, so a phase can move by one pulse; the
  counts stay, except that an effect's last pulse on its last, skipped tick can be lost: it would
  come with the next update, and that update removes the expired effect first when it runs the
  full effect pass, as it does right after another family's unit.
- A slowed creature that is the only frozen one can be one tick off at each end of a stop.
- An application in a pause during a stop is stamped one tick earlier, as natively.
- After a load, effects run on the native grid until their own end; the restarted list counter
  can move their remaining units by a pulse (step 5).

## Lab run of 2026-10-26 (step 6)

Step 6 tested [`CBRTCor.lua`](#correction-for-every-creature-cbrtcorlua) on every creature and
all four periodic families. It took four runs on a fresh party each; every run found the code of
the run before it wanting, and each fix came with host tests first:

1. The first run stopped after its two controls: an effect applied while paused right after
   Enable stretched its creature's first dispatch to two ticks. The clock now starts at the
   creature's first update.
2. The second run (18 records) froze a hasted creature 90 ticks in an 89-tick stop: its first
   update of the stop's first tick ran before the stop began, and the tick was counted again.
3. The third run (commit `fff6c37`, 18 records) is the one reported below. It found a slowed
   creature losing a pulse at a stop's start; reading that code turned up a second slowed case.
4. The fourth run (commit `bbbcc46`, 6 records) aimed stops at that slowed case and confirmed
   both fixes ([below](#fourth-run-stops-aimed-at-a-slowed-creature)).

- **Run.** Each run was one quiet run in a parallel lab slot (`bg_lab_slots.py run … 3600`) after
  a `-Refresh` restage while no BG game ran. The third lasted 1,223 s and the fourth 737 s; no
  guard tripped (audio peak 0.0, pointer clip unchanged, nothing left in the job), and the slot
  was released when the game exited. At the fresh main menu, `cor op=install` installed the 8
  gates, off. The protagonist P0 and Imoen P1 came from the
  [fresh-party sequence](#fresh-test-party-in-the-hidden-game) in AR0602. Setup turned the
  party AI off, let Imoen create three neutral `BATIN01` dummies D1 to D3 next to P0, took the
  nearest hostile, a smoke mephit, as E, and gave everyone `CBRTVIT` and `CBRTHEL`.
- **Cases.** Each case began paused: `cor op=enable` (`observe` for a native control), `watch`
  for the party, the dummies and E, a new record, then one second of play, so that the
  correction had seen every creature update before the applications (`fix_fresh` skipped it).
  P0 got all four families, D1 regeneration and poison, D2 disease and the repeated EFF, and E a
  regeneration from Imoen; Haste or Slow came first where a case says so. In the stop cases
  Imoen gave herself a regeneration and stopped time 45 of her updates after the applications,
  and D3 got op310 immunity (`CBRTTSI`) and a regeneration. Between cases the gates went off,
  every case effect ran out, and creatures below 90 HP were healed.
- **Decoding.** `decode_cor.py` decoded all 18 records of the third run with no issue and no
  mismatch: every worker field the recorder saw agreed with the native worker rules replayed
  from the record. The correction covered the 39 creatures in the area; the recorder followed 6.

Times are world ticks; +n counts from an effect's application. A unit is one heal, one damage or
one application of the repeated EFF. The fixtures last 12 seconds on a 2-second schedule: 6
units, or 5 when the first comes at +30 or later. That is the native pulse grid: the first unit
waits for the second 15-tick boundary of the creature's own counter after the application, and
another family's unit just before a pulse rebuilds the list and reseeds the phase (step 3). The
corrected creature has them where an unhasted, unstopped creature with the same grid and the
same events has them; the host tests compare exactly that.

### Controls, Haste and Slow

| Case | Event | Units | Correction |
|---|---|---|---|
| `nat_ctl` | None; observer only. | 6 each; E 5, the first at +34. | — |
| `fix_ctl` | None. | 6 each. | 2,016 deliveries; 10 suppressed (the ticks pauses repeat). |
| `fix_fresh` | Applied right after Enable. | 6 each; every dispatch native. | Clocks started at the first updates. |
| `nat_hst` | Native Haste on P0, D1 and E. | P0 and D1 11 per family, E 15, 7 to 23 ticks apart; workers ended 10 ticks before the deadline. | — |
| `fix_hst` | Haste on P0, D1 and E. | 6 each, 30 ticks apart; P0's regeneration, disease and repeated EFF 5 (below). | 1,557 second hasted updates suppressed. |
| `nat_slw` | Native Slow on P0, D1 and E. | P0 and D1 2 per family, 90 ticks apart; E 3, 60 apart, the last 5 ticks after its deadline. | — |
| `fix_slw` | Slow on P0, D1 and E. | 6 each, 30 ticks apart; the slowed creatures' first interval 14 or 16 instead of 15. | 776 stretched elapsed values, 105 boundaries found in skipped ticks. |

In `fix_hst`, P0's poison hit at +29; its rebuild reseeded the other three families one tick
before their pulse, as the rebuild of an unhasted creature in the next tick does, and their first
unit came at +45.

### Stops

The engine froze P0 and D2 for 89 ticks and D1 and E for 90: those two are updated after Imoen,
so the stop's first tick froze them already (natively too).

| Case | Event | Units | Effect clocks |
|---|---|---|---|
| `nat_stp` | Native stop. | P0 3 or 4 per family, D1 3 and 4, D2 4, E 4; immune D3 6, caster P1 7. | Unchanged; every effect ended at +179. |
| `fix_stp` | Stop. | 6 for every frozen creature, the interval across the stop 30 plus its frozen ticks (119 or 120); D3 6 and P1 7, as natively. | Deadlines and origins moved by each creature's own frozen ticks; ended at the moved deadline − 1. |
| `fix_stp_spd` | Stop over hasted P0 and slowed D1. | P0 6 per family, frozen 89: its first update in the stop's first tick was still active. D1 poison 6, regeneration 4 (below). E 5, the first at +37. | As `fix_stp`. |
| `fix_steps` | 30 of Imoen's updates into the stop, a regeneration onto frozen D2 and `CBRTRMR` on P0. | P0's regeneration 1, before the stop; its workers gone. D2's new regeneration 5, the first 41 active ticks after the stop. D2's disease and repeated EFF 7: the application rebuilt D2's list, and the native reseed added a unit. | The new regeneration's deadline moved by the 59 frozen ticks after its application only. |

**D1's regeneration in `fix_stp_spd`.** Slowed D1 skipped the tick before the stop, an active
tick that held a 15-tick boundary of its regeneration. D1's next update was its first frozen one,
and the correction delivered the skipped tick there; the native worker ignores every update while
frozen, so the boundary was lost, and with it the pulse after the stop (+149). The last pulse was
lost to the effect's end, as in the fourth run's `tgt_reg` (below): 4 units. The fix lets a frozen
update deliver nothing and keeps the skipped active ticks due: they come with the first update
after the stop, one active tick late for D1, two for a slowed creature frozen 89 ticks, whose
first active tick after the stop is one it skips too. The same reading found a slowed creature
updated before the caster in the stop's first tick missing the frozen tick it skipped next; it
now counts every tick since its last update that the stop held. Both are covered by host tests
at every grid position, and the fourth run confirmed both.

### Group, pauses, time compression, save and load

| Case | Event | Result |
|---|---|---|
| `nat_grp` | The Holy-Power-like group on P0 and D1; native stop 45 updates later. | Upkeep, child and delayed cleanup kept their times; 7 upkeep applications on each, the cleanup removing the group 12 s after its application. |
| `fix_grp` | The same, corrected. | All three parts moved together, by 89 (P0) and 90 (D1): 13 upkeep applications on each before the cleanup. |
| `fix_pause` | Haste on D1; nine pauses of 1.4 s. | 6 each; E 5, the first at +30. 420 repeated or second hasted updates suppressed. |
| `fix_cmp` | The families for 4 s, then `DayNight` to the next full hour: 4,824 ticks. | Every creature got one dispatch with the whole span, as natively; the running effects ended in it without another unit. New effects afterwards: 6 each, D1's regeneration 5; the correction continued on the native list counters (39 compressions). |
| `fix_save` | A corrected stop over P0's four families and D1's two; quick save at once after the caster's op231 ran out. | The first click wrote `000000001-Quick-Save`. P0's effects saved with deadline and origin moved by 89, D1's by 90. |
| `fix_load` | Reload; the gates stayed on. | `sessions` 1: the destroyed-session listener had cleared the correction's state. The effects came back with the moved deadlines and ended at deadline − 1. Before the save they gave 3 or 4 units, after it 2 or 1: 5 instead of 6, since the load restarted the creatures' list counters and reseeded the workers on a new grid (step 5). Object IDs changed, and kept creatures' resrefs begin with `*`. |
| `fix_hst_load` | Haste on P0, D1 and E in the loaded game. | 6 each; E 5 and P0 5 per family, the first at +30 or +46. |

### Fourth run: stops aimed at a slowed creature

The fourth run (commit `bbbcc46`) aimed three stops at the case the third run met by chance. In
`tgt_reg`, `tgt_reg2` and `tgt_psn`, P0 was hasted, D1 and D2 slowed, and D3 immune. While
paused before the applications, the drive read D1's counter offset from the correction
(`CBRTC.ActorState`). After Slow at the paused world X, a slowed creature updates at X + 1,
X + 3, …, and Imoen's stop begins at X + wait (runs 2 and 3). The drive therefore chose an odd
wait that put a boundary of D1's regeneration (twice) or poison on the tick D1 skips right before
the stop. The third run's `fix_stp_spd` fits the same rule: its wait of 45 was the aimed one by
chance, and the second run's needed 49.

| Case | Wait, stop | D1, updated after the caster | D2, updated before the caster |
|---|---|---|---|
| `tgt_reg` | 45, began at 33163 as aimed | Skipped 33162, a regeneration boundary, and was frozen at its update in 33163. The pulse after the stop came on time at +149, where the third run lost it. Regeneration 5, poison 6: the last pulse fell on the effect's last tick, which D1 skipped (below). | Updated in 33163 before the stop began; 2 ticks at its first frozen pass, 89 in all (deadlines +89). Disease and repeated EFF 6. |
| `tgt_reg2` | 55, at 34501 | The same with another grid: regeneration and poison 6, the pulse after the stop on time. | The same; 6 each. |
| `tgt_psn` | 41, at 33832 | The poison unit due on the skipped tick came with D1's first update after the stop, one active tick late. Regeneration and poison 6. | The same; 6 each. |

D1's last regeneration in `tgt_reg` is the slowed creature's remaining limit, not the stop: its
pulse on the effect's last tick would have come with D1's next update, but D1's last poison unit
had just forced a full effect pass, and that update removed the expired effect first: neither
worker was dispatched in it.

The repeated cases matched the third run: `fix_stp_spd` 6 per family for P0 and D1 (D1's
regeneration one pulse later across the stop, after a poison unit one tick before its pulse
reseeded it, as natively) and E 5, its first unit at +31; `fix_stp` 6 for every frozen creature,
deadlines moved by 89 or 90, D3 6 and Imoen 7; `fix_slw` 6 for the slowed P0, D1 and E, the
first interval 14 or 16, with 782 stretched elapsed values and 105 boundaries found in skipped
ticks. All six records decoded with no issue and no mismatch.

### What this shows

- **Every creature and all four families.** Party, dummies and the hostile mephit alike, poison,
  disease and repeated EFF behave like regeneration: no unit inside a stop, deadlines and
  origins moved by each creature's own frozen ticks, phases kept across the stop, Haste and Slow
  on world time.
- **Normal speed stays native.** Without Haste, Slow, pauses or stops the corrected creatures
  matched the native ones, and `fix_fresh` was native dispatch by dispatch.
- **Haste and Slow are normalized.** Hasted creatures fell from 11 to 15 units to 6, slowed ones
  rose from 2 or 3 to 6, a slowed creature's units at most one tick late (two are possible right
  after a stop, host tests). D1's regeneration lost its last unit twice to the slowed creature's
  remaining limit (`fix_stp_spd` in the third run, `tgt_reg`).
- **Each creature's own stop.** A creature updated after the caster loses the stop's first tick
  too; one updated before keeps it, a hasted one updated on both sides keeps its first update, and
  a slowed one updated before counts the skipped tick after it. The correction counted 89 or 90
  for each, as the engine froze it.
- **Groups stay together.** Upkeep, child and delayed cleanup of a maintained group moved by the
  same frozen ticks, so the group kept its shape.
- **Time compression and loads stay native.** A rest-like jump passes through untouched. A load
  keeps the moved deadlines and origins; the correction restarts its own state.
- **Removal and new effects in a stop.** Removal stays removal; an effect applied in a stop gets
  no credit for the frozen time before it.

Not covered by the lab: area effects (a cloud's lifetime through a stop, read from the code only),
area transitions, saving during a stop, dispel, cure and death, and a stop ending between a hasted
creature's two updates (host tests only). Christopher, 2026-10-26: area transitions need no test;
saving during a stop, dispel, cure and death come later; the slowed creature's lost last unit is
not urgent and goes on the agenda.

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

The 2026-10-25 revision and step 5 bring the total to 145 Python tests: `test_fix.py` 61,
`test_lab_rc.py` 36, `test_decode_trace.py` 17, `test_qa_menu.py` 12, `test_observer.py` 11
and `test_fixtures.py` 8. `test_fix.py` adds the R7 and R8 cases, slowed dispatches, the
boundary scan and the pause and stop limits. `test_lab_rc.py` adds the new `queue` variants,
the activity recorder, the save list (with the rotated quick saves and the leader name in
`sName`), `halt`, and the refusal of Lua reserved words as argument names. `test_fixtures.py`
pins the first five fixtures' bytes and keeps the removal fixtures on lab resources. The
mutation check now has 34 mutants, and `test_fix.py` fails for each. After step 5, all 16
guard groups and all 145 Python tests passed.

Step 6 on 2026-10-26 brings the total to 233 Python tests: `test_cor.py` 81 (new),
`test_fix.py` 61, `test_lab_rc.py` 41, `test_decode_trace.py` 17, `test_qa_menu.py` 12,
`test_observer.py` 11 and `test_fixtures.py` 10. `test_cor.py` runs `CBRTCor.lua` in LuaJIT on
synthetic memory, with the native worker rules of `periodic_model.py`:

- 18 call the gate targets directly: once per tick and creature, slowed gaps and the boundary
  scan, the construction rules, parent identity, time compression and the state sweep.
- 28 scenarios compare a corrected creature, unit by unit in active time, with a native one that
  is never hasted, slowed, paused or stopped but has the same list counter grid and the same
  applications. They cover every family at normal speed, Haste, Slow, stops (also beginning or
  ending between a hasted creature's two updates, and over a slowed creature at every grid
  position and update order), pauses, applications and removal in a stop, rest, an area left
  alone, the caster and immune creatures, a maintained group and two creatures side by side.
- 5 check the recorder, 4 the decoder, and 8 run `Install`, `Enable`, `Observe`,
  `ExportRecord`, the session listener, `Disable` and `Status` against stub bindings.
- 6 run the eight assembly gates in Unicorn: registers passed in order and restored, the
  dispatch result, the off switch, the class filter, fail closed on a Lua error and EEex's stack
  bookkeeping. 4 emulate the native workers from the pinned executable, and 8 check the eight
  windows in it as for the prototype.

`test_lab_rc.py` adds the `cor`, `apply` and `effects` requests, `test_fixtures.py` the new
fixtures' bytes. A scratch mutation check replaced 50 single guards or rules in `CBRTCor.lua`,
one at a time; `test_cor.py` failed for each. After step 6, all 16 guard groups and all 233
Python tests passed.

Fixture and decoder tests use synthetic data; assembly tests use synthetic memory
and the pinned executable on disk. They do not execute the game or prove the
EEex trampoline integration works at runtime.
