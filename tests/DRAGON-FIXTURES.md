# Local dragon test capture

The 110/111 installer, script and wing-buffet suites use a read-only captured SCS
35.21/EET stack, rather than accessing any live installation during a test run.
The captured CRE and full BCS assets are not published in Git or release archives.

For a maintainer with lawful access to the private reference capture, restore:

- `research/originals/dragon_wing_buffet/`: five `.cre.orig` and five `.bcs.orig`
  records plus `manifest.json` (SHA-256 and extraction metadata).
- `tests/fixtures/dragon_wing_buffet/`: matching five `.cre` records and five `.bcs`
  files containing only the captured wing-buffet blocks.

See `research/15-dragon-wing-buffet.md` for the capture contract. The unmodified
local reference remains in the a947 development worktree; never recapture from
or modify a running player's game just to run these tests.

Run from PowerShell with a Lua interpreter available (`CBR_LUA` may select it):

```powershell
python -m unittest tests.test_dragon_installer tests.test_dragon_vorpal_effects tests.test_dragon_vorpal_scripts tests.test_dragon_wing_buffet -v
```

Without the private capture, the three dependent test classes explicitly report
that prerequisite as unavailable. The fully synthetic vorpal effects/Lua tests
still run. Presence of a capture does not suppress hash or partial-file failures.
The v0.4.0 release validation used the complete capture; none of the 39 dragon
tests were skipped. Synthetic success is not native combat acceptance.
