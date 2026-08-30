# SCS ambient readiness live-deployment checklist

Status: **prepared only**. This document is not authorization to install component 120 or
121, launch the game, mutate `override`, touch a playthrough save, or change `WeiDU.log` /
`dialog.tlk`. Every live step below starts only after the user explicitly approves the exact
game directory, components, installer commit, and throwaway save.

The active-game reference is
`C:\Games\Baldur's Gate II Enhanced Edition modded\`. Existing WeiDU components are never
uninstalled. If a newly appended 120/121 component needs rollback, stop and obtain separate
approval for a playthrough-safe rollback plan; never edit `WeiDU.log`, compiled resources,
or source files by hand.

## 1. Authorization and clean starting state

Before doing anything live, record all of the following in the acceptance log:

- the user's exact approval message and its scope;
- `git branch --show-current`, `git rev-parse HEAD`, and an empty `git status --short`;
- successful fresh output from the TP2 parse-check and full automated suite;
- the exact game root, EET user-data root, and newly selected throwaway save;
- the installed SCS, SR, EEex, and current chriz-bg-rebalance entries from `WeiDU.log`; and
- confirmation that `Baldur.exe` and `InfinityLoader.exe` are not running.

The throwaway save must be a separately named copy/new disposable save. Never select an
active playthrough save, an `Interval-Save`, or a save that another running session can
rewrite. Record its original path and hash bundle before launch.

## 2. Before-state evidence bundle

Create one timestamped evidence directory **outside the game and save roots**. For every
entry below, preserve both the exact bytes and a manifest containing absolute source path,
UTC timestamp, byte length, and SHA-256. A missing optional file is an explicit manifest
entry, not silently omitted.

Required inputs:

- effective `SPWI611.SPL`, `SPWI708.SPL`, `SPWI808.SPL`, and `SPWI907.SPL`;
- every numeric `dw#mg*.BCS` that component 120's read-only audit identifies as a planned
  mutation target—not merely one representative script;
- an existing `override/M_CBRRDY.lua`, if present;
- `weidu_external/data/stratagems/instant_prebuff_spells.2da`;
- final loose `override/SPELL.IDS`;
- `WeiDU.log` and the effective `dialog.tlk`;
- the console-owned `override/eeex_remote_ready.json`, if the installed remote console is
  used (preserve it as a stable baseline; it is not an acceptance-run scratch file);
- the complete selected throwaway-save directory; and
- the audit JSON/text report, command transcript, installer executable hash, and exact Git
  commit being tested.

Also hash all component-120 materialized SPL roots named by its preflight and preserve the
full planned `dw#mg` target list in deterministic case-insensitive order. This makes an
unexpected extra or missing mutation visible even when its bytes were not in the four
classification spells above.

Run the read-only script audit before installation. The researched SCS 35.21 baseline is
585 common-mage scripts, 98 numeric-2808 candidate scripts, 77 first-round blocks, 80
renewal blocks, 82 Chain Contingency blocks, and zero unknown target-containing blocks. Any
different count, unknown block, changed semantic classification, missing `WIZARD_PROJECT_IMAGE`
identity/resource, or changed effective-resource hash is a **stop**, not permission to widen
the matcher.

## 3. Stage A — component 120 only

After separate approval, append component 120 and stop before installing 121.

Installation acceptance:

- WeiDU reports one successful new `cbr_scs_weapon_protection_semantics` tail entry;
- the post-install audit reports the planned first-round/renewal removals and Chain
  replacements with no unknown or out-of-allowlist mutation;
- Moment of Prescience's spell behavior, description, memorization, and `SPELL.IDS` identity
  are not redesigned;
- current SR Moment of Prescience is no longer treated as weapon immunity by the patched
  native SCS paths; and
- unrelated BCS/SPL files, `dialog.tlk`, and the throwaway save remain byte-identical unless
  a separately recorded engine save action intentionally changed the disposable save.

On the throwaway save, observe native SCS behavior separately for:

1. a first-round protection choice;
2. protection renewal after the prior protection ends; and
3. a Chain Contingency path.

Record actual selected spells, slot changes, action starts, and active effects. Queueing or
script text alone is not gameplay confirmation. Stop on any unexpected behavior; do not
uninstall or patch around it during the session.

## 4. Stage B — component 121 on the throwaway save

Only after Stage A passes and the user separately approves continuation, append component
121. Confirm that the install publishes only the backup-aware stamped
`override/M_CBRRDY.lua`; it must not alter a SPL or BCS. Record the generated manifest's
ambient rows, urgent semantic flags, EEex profile, and dynamically resolved Project Image
resref.

### 4.1 Urgent first-contact matrix

For every case, record first `See([PC])`, current/queued action IDs, queued `SpellRES`, exact
started-action callback, slot count, aura/casting time, interruption result, and resulting
effect. A queued response without a matching start is not success.

- hostile fast rush: safe passive caster starts a valid protection within one AI tick;
- neutral-to-hostile transition: readiness begins only after hostile contact;
- already casting: existing cast is never cleared;
- attack and tactical queues: neither current nor queued work is displaced;
- dialogue and cutscene: no accelerated action occurs;
- Project Image: both clone and owner/uncertain ownership skip, using the stamped installed
  identity rather than a stock `SPWI703` assumption;
- interruption: once the cast starts, the episode is spent even if the spell is disrupted;
- bait/re-engagement: continuous sight never retriggers, while one full round without sight
  rearms exactly once; and
- never-started queue: at most one bounded retry occurs, then the episode closes.

The chosen spell must follow installed semantic order: Absolute Immunity, genuine Improved
Mantle if present, Mantle, then PfMW. Current SR Moment of Prescience must never be selected.

### 4.2 Ambient one-slot-per-reset matrix

Exercise every baseline row actually stamped by the install (currently Armor, Non-Detection,
Stoneskin, Mind Blank, Ironskins, and Impervious Sanctity of Mind) on a caster that truly has
an available memorized copy. For each row, verify and record:

1. the first confirmed ambient application consumes exactly one correct memorized record;
2. SCS's later initial prebuff pair does not produce a second net debit;
3. natural expiry refreshes only out of combat with no party member visible and spends no
   additional copy;
4. early dispel/removal suppresses free maintenance through save/load;
5. save/load preserves the ledger and does not charge or apply a second first-use copy; and
6. a genuine engine spellbook refresh/rest clears the cycle, after which the next successful
   application consumes exactly one newly available copy.

Do not infer execution from a successful EEex call. Wait for engine ticks and independently
check the memorized record, quick-list count, ledger, and active effect. Never repeat a
slot-mutating experiment on the same disposable actor unless its exact state was independently
restored or the throwaway save was reloaded.

### 4.3 Retirement and ownership controls

In session-scoped tests, prove each control independently and restore it after observation:

- `CBR_RDY_AMBIENT_ENABLED = 0` retires ambient only;
- `CBR_RDY_URGENT_ENABLED = 0` retires urgent only;
- external-owner bit 1 retires ambient only;
- external-owner bit 2 retires urgent only; and
- external-owner value 3 retires both.

Also capture one controlled unsupported/fault case per layer if the approved test method can
do so safely. The affected layer must become inert and log at most one diagnostic/traceback;
the sibling layer must continue. Do not inject faults into the active playthrough.

## 5. After-state comparison and cleanup

At the end of each stage, create a new timestamped after-manifest with the same scope as the
before bundle and produce a path-by-path hash diff. Distinguish expected installer changes,
intentional disposable-save changes, and unexpected drift. Preserve raw engine observations
separately from automated-test output.

Before declaring the session closed:

1. neutralize/teardown any session probe or remote-console watcher used by the approved
   procedure;
2. after preserving their bytes, remove only the exact transient command/request, result/
   response, run, or temporary files created for this acceptance run; do not delete the
   installed console's stable `eeex_remote_ready.json` marker;
3. exit the game normally, close InfinityLoader, and wait for both processes to terminate;
4. verify no `Baldur.exe` or `InfinityLoader.exe` process remains;
5. confirm no request is still queued and no disposable save is still being written;
6. preserve the throwaway save and its final hash bundle outside the live save rotation; and
7. re-hash `WeiDU.log`, `dialog.tlk`, all planned resources, `M_CBRRDY.lua`, and the stable
   remote-console ready marker when present.

Do not delete evidence or an unexpected changed file to make the comparison clean. If any
target differs outside the approved mutation set, stop and report it with hashes. No rollback,
uninstall, real-save repair, branch merge, or release follows implicitly from this checklist.

## 6. Pass report and deployment boundary

The acceptance report must name the exact commit and include:

- component 120 install/audit counts and native SCS observations;
- component 121 stamped manifest and urgent/ambient matrices;
- every before/after hash difference with its reason;
- process and transient-IPC cleanup evidence;
- unresolved failures or untested cases stated literally; and
- whether the active playthrough remained untouched.

Completion of this document means only that the offline branch is ready for a future explicit
approval checkpoint. Until that approval is given, components 120 and 121 remain uninstalled
in the live game.
