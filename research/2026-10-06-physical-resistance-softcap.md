# Party physical resistance: diminishing returns above 80%

## Approved behavior (2026-10-06)

Christopher requested a separate component for player characters: physical
resistance above 80% has diminishing returns, with a default maximum of 90%
and an optional 95% maximum. He explicitly approved half effectiveness above
80%: `min(cap, 80 + floor((resistance - 80) / 2))`. Values at or below 80%,
including negative resistance, remain unchanged. Integer results round down.

| Original total | 90% maximum | 95% maximum |
| --- | --- | --- |
| 80 | 80 | 80 |
| 90 | 85 | 85 |
| 100 | 90 | 90 |
| 110 | 90 | 95 |

Apply independently to slashing, crushing, piercing and missile resistance
for party-roster members, including recruited NPCs. Do not affect enemies,
neutral NPCs, summons or elemental/magic resistance. Do not remove Stoneskin,
weapon-immunity spells, or other protections unrelated to these four stats.
Do not rewrite CRE base stats, spell/item sources, active effects or saves.

This supersedes the old 60% knee / 80-or-90 cap sketch in the untracked
owner-main `research/06-sr-hardiness.md`. That sketch's proposed component 301
is now occupied by Emotion non-stacking; reserve new choices **310 / 311**.
Hardiness 40%/30% is independent work in `.worktrees/sr-hardiness`.

## Verified source and engine constraints

- Installed EEex `EEex_Fix.lua` maps signed derived stats 21-24 to
  `m_nResistSlashing`, `m_nResistCrushing`, `m_nResistPiercing`,
  `m_nResistMissile`. These are the existing engine stats, not mod resources.
- `EEex_Sprite_GetPortraitIndex` searches the party roster by object ID;
  unlike enemy/ally allegiance it does not include ordinary allied summons.
- Existing Tempus code and `research/07-spec-apr-listener-runaway.md` prove
  that ListsResolved is per pass, not per rebuild. Reapplying the curve on
  every pass would incorrectly decay 100 -> 90 -> 85 -> 82 -> 81 -> 80.
  A private marker in the same derived-stat block must prevent this.
- The installed BG2EE 2.7.3.0 executable's `CDerivedStats::CheckLimits`
  (function-name map address `0x1401514B0`) clamps the four physical stats
  at 100. Read-only disassembly independently reproduced on 2026-10-06:
  SHA256 `b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
  At `0x1401516EA`, the limit is set to 0x64; the four signed-short fields
  at offsets 0x2C/0x2E/0x30/0x32 are capped through `0x140151750`.
- `ProcessEffectList` calls `CDerivedStats::operator+=` at `0x1403AC5BC`,
  merging derived and bonus stats; it calls `CheckLimits` at `0x140150BF7`.
  The immediate ListsResolved hook runs at the exit after the effects
  processing flag is restored (`0x1403ADFFC`, hook boundary `0x1403AE017`).
  Native `GetResistance` (`0x14039CFC0`) reads the previous `m_tempStats`
  during processing and the new `m_derivedStats` afterwards. The component
  must write `m_derivedStats` directly, not `getActiveStats()`.
- There are earlier per-opcode clamps as well: e.g. slashing-resistance
  ApplyEffect adds to its bonus at `0x1401C1B38`, compares against 100 at
  `0x1401C1B3F`, and caps it at `0x1401C1B4E`. The review also identified
  equivalent crushing/missile/piercing limits. A before-final-merge hook
  alone cannot recover those lost values.
- Therefore 310 applies the curve to the **native effective stat**, retaining
  native effect-stacking order/truncation; it does not reconstruct an
  arbitrary sum of all resistance sources. This supports the 90% ceiling.
  The 95% variant requires separately scoped native changes, not a different
  Lua constant. No such changes or global cap increases are implemented.

## Implementation status

- Unreleased component **310**: BG2EE/EET + EEex; allocated private
  `CBR_PHYSICAL_SOFTCAP` bit; one immediate listener with per-rebuild marker,
  guarded module reload, one-error shutdown and defensive write rollback.
- Component **311 is reserved only**. It is not shown in WeiDU or CEBG.
  Christopher was asked whether to defer it or authorize the deeper work;
  that answer is still pending. The approved curve itself is unchanged.
- Core simulations exercise 95% on untruncated input only, explicitly as a
  future mathematical contract, not proof of a working 95% game component.

## Boundaries and remaining acceptance

Work is isolated on `codex/physical-resistance-softcap`; no game modification,
live probe, publication or collection pin change is authorized by this work.
Automated curve/EEex-surface simulations do not prove native hook operation.
Every implemented menu choice must be exercised in disposable WeiDU fixtures;
the default setup needs a short later in-game resistance/damage check.
Do not expose a 95% installer option that cannot actually reach 95%.

## Automated evidence (2026-10-06)

- `python -B -m unittest tests.test_physical_resistance tests.test_physical_resistance_installer -v`:
  **28 tests passed**, covering the curve, four independent damage types,
  party membership including charm/dismissal/rejoin, per-rebuild idempotence,
  callback/reload behavior, invalid bindings, partial-write recovery and
  real WeiDU installation in disposable games. The fixtures confirm marker
  fallback/reuse/collision/exhaustion and no changes to unrelated resources,
  KEY/BIF data or dialog.tlk. Repeat-helper execution is byte-stable without
  reinstalling an existing component.
- `python -B -m unittest discover -s tests -t .`: **423 tests run, 422 passed,
  1 skipped**, exit 0, 402.922 seconds. The pre-existing optional dragon-stack
  test was skipped because `CBR_DRAGON_STACK_CAPTURE` was not supplied. No
  failing tests were ignored. Expected negative-case bard diagnostics in the
  output are from passing tests, not a new runtime failure.
- Independent review found no blocker for component 310. The reviewed engine
  evidence and tests do not substitute for a first live damage/resistance check.
- No source release, CEBG preset/pin update, live game install, save modification
  or publication was performed. Integrate the released owner component into
  CEBG later; the optional 95% variant remains a separate open item.
