# Tempus Holy Power: delegated non-SR Improved Haste

## Diagnosis and captured evidence

Component 401 in v0.3.1 fails on the CEBG installation without Spell Revisions at
`C:\Users\chris\Games\ChrizEasyBG-No-SR-Test\game`. Its classifier examines only
the main Improved Haste ability effects, but this installed spell delegates its
mechanics through opcode 146. This is a classifier limitation, not evidence that
Spell Revisions is required.

Nine effective resources were copied using read-only Python file reads into
`research/originals/tempus-no-sr/`: `SPWI613.SPL`, `SPWI613A.SPL`, `DW_NEG40.SPL`,
`OHTMPS1.SPL`, `SPPR412.SPL`, `OHTEMPUS.2DA`, `SPELL.IDS`, `SPLSTATE.IDS`, and
`SPLPROT.2DA`. `manifest.json` records absolute source paths, source modification
times, byte lengths, SHA-256 hashes, and hashes of the attempt-owned evidence.
These are pre-fix effective bytes from the current stack, not pristine vanilla
game assets or a claimed reconstruction of every byte before the failed attempt.

`SPELL.IDS` resolves `WIZARD_IMPROVED_HASTE` to 2613 (`SPWI613`) and
`CLERIC_HOLY_POWER` to 1412 (`SPPR412`). The installed Holy Power `OHTMPS1` still
has 20 headers. The observed delegation is:

| Resource | Header structure | Relevant effect fields |
|---|---|---|
| `SPWI613` | Nine headers: levels 1 and 13-20; target 1; projectile 47; no casting effects | Exactly one opcode 146 per header, target 2, power 6, parameter1 0, parameter2 1, timing 1, duration 0, resistance/dispel 3, probability 100/0, resource `SPWI613A`, zero dice/save/special fields |
| `SPWI613A` | Same nine levels; target 1; projectile 1; no casting effects | Exactly one opcode 16 per header, target 2, power 6, parameter1 0, parameter2 1, timing 0, durations 90 then 96-138 seconds, resistance/dispel 3, probability 100/0, zero resource/dice/save/special fields |
| `DW_NEG40` | One header, level 1, target/projectile 0; no casting effects | Sole opcode 139, target 2, parameter1 328363, timing 1, probability 100/0; no delegated effects or APR mechanics |

The child also contains SCS protection/state infrastructure, including an opcode
326 call to `DW_NEG40` (parameter1 65536, parameter2 138). Its target contains
only display-string opcode 139, so it cannot supply competing haste/APR semantics.
The wrapper and child must not be rewritten or flattened merely to classify them.

`SETUP-CHRIZ-BG-REBALANCE.DEBUG` line 2065 reports zero recognized additive or
doubling effects in `SPWI613` header 0. The attempt directory
`.chriz/attempts/attempt-e6b6f3a5aacc11891051/steps/0106-fab86e09514d1f0a/attempt-0001`
records exit code 2. The debug log describes rollback of six files; this is
WeiDU's report, not byte-exact rollback verification. The current `OHTEMPUS.2DA`
and `SPLSTATE.IDS` lengths already differ from the failed component's logged
inputs because other requested components subsequently succeeded.

Before any production edit, the existing isolated `--nogame` classification
harness was run against these captured resources. It exited 2 with the exact
same zero-effects error and rolled its disposable output directory back to empty.
The concise transcript is retained as `baseline-classification.txt` beside the
fixtures. No WeiDU command was run inside either real installation.

## Implementation and validation boundary

The classifier retains direct additive opcode 1 and direct doubling opcode 16/317
support. A delegated header must have exactly one opcode 146, no direct APR/haste,
and the deterministic target/casting/timing fields captured above. Its child must
have one ungated timed doubling effect per header, sorted caster levels and
single-target delivery. The child may not delegate haste again. The whole graph
must agree on doubling; direct/delegated mixtures and delegated additive semantics
are rejected. The latter would require a different APR bridge implementation.

Opcode 146 parameter2 1 casts at **caster level**, so the classifier checks every
child header rather than assuming header 0. See [IESDP opcode 146](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op146).
Only explicit non-delivery auxiliary opcodes and structurally verified opcode-139-only
conditional message leaves are accepted. Unknown opcodes, hidden dispatchers,
missing dependencies, malformed slices, cycles and probability/save gates fail.
The dependency reader uses explicit fixture paths or effective game override/KEY
lookup with `BUT_ONLY`; it never publishes or edits child spells.

Recognize a proven deterministic opcode-146 delivery path and validate the actual
child haste mechanics, while retaining the existing direct additive and direct
doubling checks. Missing, malformed, cyclic, probabilistic, mixed, or ambiguous
delegation must continue to fail closed. Resolve child resources through effective
override-before-KEY lookup in a real WeiDU game and explicit fixture paths in
`--nogame` tests. Doubling classification must leave the child and wrapper bytes
unchanged and must not publish additive-only bridge resources.

### Existing non-SR Divine Power mutual exclusion

After delegated classification succeeded, the isolated full-component run exposed
a second rejected installed layout in the captured `SPPR412.SPL`. All 14 headers
(levels 1 and 8-20) contain 13 effects and begin with the same two opcode-321
records: first resource `OHTMPS1`, then self resource `SPPR412`. Both records have
target 1, power 4, parameter1/parameter2 0/0, timing 1, resistance/dispel 3,
duration 0, probability 100/0, and zero dice/save/special fields. There are no
casting effects. These are existing cross-exclusion and self-refresh effects,
not a partial CBR prefix, whose five records use parameter2 2 and resistance/dispel
2 and include the four private Strength setters.

Recognize only this exact ordered two-record legacy prefix, uniformly across all
headers and without duplicate cross/self cleanup or any private CBR cleanup.
Replace its first `OHTMPS1` record with the canonical five CBR cleanup records;
preserve the existing self-refresh record and every later effect byte-for-byte.
Malformed, reordered, duplicated, or mixed legacy/canonical prefixes must still
fail. A rerun must recognize only the canonical output and make no further change.
The self resref remains dynamically resolved through `CLERIC_HOLY_POWER`.

## Base-game inputs without SCS or Spell Revisions

`research/originals/tempus-base-game/` contains seven actual base-game resources
extracted by KEY/BIFF reads while intentionally ignoring the modded override:
`SPWI613.SPL`, `OHTMPS1.SPL`, `SPPR412.SPL`, `OHTEMPUS.2DA`, `SPELL.IDS`,
`SPLSTATE.IDS`, and `SPLPROT.2DA`. The manifest records individual resource hashes,
KEY locators, BIF offsets and source paths in `Spells.bif`, `Patch25.bif`,
`Patch2.bif`, and `Default.bif`, plus unchanged KEY/BIF hashes before and after
extraction. These are actual base-game inputs, not synthetic replacements for
spell mechanics or CLAB tables.

This `SPWI613` applies opcode 16 parameter2 1 directly in all nine headers, with
no opcode-146 delegation. Its initial duration is also 90 seconds. Base-game
`SPPR412` contains the same two-record legacy cross/self cleanup prefix. The full
component installs successfully against these resources in a disposable game and
is byte-exactly idempotent through the `--nogame` harness.

## Isolated integration verification

Final verification on 2026-09-07: `python -m unittest discover -s tests -p
'test_*.py'` passed all **281 tests** in 334.600 seconds with WeiDU 24900.
The 18 new delegation tests include direct SR/additive and non-SR/doubling with
and without synthetic SCS metadata, opcode 317, forced-mode consistency, invalid
graphs and dispatchers, probability/save gates and exact failure restoration.
The real base-game and captured SCS/no-SR profiles below provide full installation
evidence; this is not a claim of four live-engine acceptance runs.

All 16 staged resource blobs match their manifest SHA-256 values. `.gitattributes`
marks these SPL/IDS/2DA fixtures binary so Git cannot change their line endings.

`python -m unittest tests.test_tempus_delegated_haste_installer -v` covers nine
tests using the real WeiDU 24900 executable:

- All captured resource hashes and the actual nine-header delegated structure.
- Full transformation and byte-exact second-run idempotence for the captured
  SCS/no-SR resources and the actual no-SCS/no-SR base-game resources.
- Public component 401 installation with an override child, a KEY-only child,
  and a valid override child shadowing a malformed KEY child.
- Atomic rejection when an invalid override shadows a valid KEY child, and ten
  malformed legacy Divine cleanup layouts (fields, ordering, duplicates, mixed
  headers, partial private cleanup, and corrupt self cleanup).
- Byte-exact synthetic-game uninstall restoration, unchanged KEY/BIF/TLK inputs,
  no publication of the read-only child or additive bridge, and unchanged
  wrapper/child/notification bytes.
- Exact replacement of the legacy Divine cross-cleanup by five canonical CBR
  records, preserving its original self-cleanup and every later effect byte-for-byte.

After the isolated runs, all 20 recorded live-source resources and evidence files
(nine captured resources, setup DEBUG, WeiDU.log, and nine attempt-owned files)
still match their recorded SHA-256 hashes. This verifies the read-only boundary
for these observed files; it does not certify the earlier failed installer
attempt's entire rollback or constitute live engine acceptance.

All verification here uses captured fixtures or disposable synthetic games.
Installing/recovering component 401 in CEBG, reconciling frozen receipts/logs, and
finishing the remaining collection stack belong to the collection task. A fixed
release and collection artifact/checksum pin are required before that recovery.

## Release and collection handoff

This work is based on the installed v0.3.1 commit `d31fda2` and is an unreleased
fix on `codex/tempus-delegated-haste`. Before collection recovery:

1. Integrate the fix into the release branch, bump `VERSION` in
   `setup-chriz-bg-rebalance.tp2`, and publish a new immutable release/tag (next
   patch candidate: v0.3.2). Do not replace the existing v0.3.1 archive.
2. Verify the published package contains this library and record its exact URL,
   version/ref and SHA-256. Update the collection source pin through its normal
   lock/freeze workflow; local working-tree files are not a reproducible pin.
3. Reconcile the frozen records for attempt `attempt-e6b6f3a5aacc11891051`, step
   `0106-fab86e09514d1f0a`, attempt `0001`. Requested components were
   `101 121 400 401 404 405 407 408`; only 401 failed. Preserve the recorded
   successful appends and determine the supported controlled recovery action.
4. Confirm the earlier failed attempt's rollback against its owned evidence;
   these fixture tests do not establish byte-exact restoration of that install.
   The collection task owns recovery and the remaining BG Modpack, final CDTweaks
   2312 and BuffBot steps. This fix does not manually install 401, alter receipts
   or logs, uninstall later components, or restart the stack.
