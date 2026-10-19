# Party physical resistance: short immunity windows keep 100%

## Problem (2026-10-20)

Component 310 (v0.8.3) caps party slashing, crushing, piercing and missile
resistance: values above 80% count at half strength, with a 90% maximum. It
does this for every source. SCS's Divine Protection (`SPPR527`, level 5) and
Greater Divine Protection (`SPPR737`, level 7) set all four resistances to 100%
for 18 seconds. For a party member, 310 turned that into 90%, so physical hits
still did damage and interrupted casting. Enemies kept 100%. The spells'
descriptions promise immunity.

## Audit of 100% sources

Read-only scan of every SPL, ITM, EFF and CRE effect with opcodes 86-89 in
Chris's game (EET 2.7.3.0, EEex 1.2.0, SCS, SR, IWDification and the rest of the
CEBG stack) and in the reference install. Only sources that reach 100% by
themselves are listed; everything at or below 80% is untouched by 310 anyway.

| Source | Effect | Kind | v0.8.3 | Now |
| --- | --- | --- | --- | --- |
| `SPPR527` Divine Protection, `SPPR737` Greater Divine Protection (SCS) | set 100, 18 s, self | timed spell | 90 (the problem) | 100 |
| Otiluke's Resilient Sphere `SPWI413`/`SPWI853`/`SPIN853`, its subspells `SPWI413A/C/D`, the sphere trap `SPCL415A` | set 100, 42-60 s; the spheres also grant opcode 101 against damage (opcode 12) | timed spell | 90, but no damage gets through anyway | 100 |
| `CDIWDTR1` (IWDification Shades: the summoned troll's own protection) | set 100, 40 s, with regeneration | summon only | not a party member: never capped | unchanged |
| Rings `INVULNER`, `HOLDRING`, `FSSPIR`, `BAZPATRG`, `BDTROLL2`; SoD `BDMISC1B/C` | set or +100 | equipped | 90 | 90 |
| `PLYJELLY` (polymorph attack item) | piercing set 100 | equipped form item | 90 | 90 |
| Stacked bonuses (items, kit passives, buffs, forms with 75%) | several increments | mixed | capped | capped |

Where the 100% comes from:

- IWDification's Divine Protection and Greater Divine Protection grant total
  damage immunity through opcode 101 (immunity to opcode 12), not through
  resistance. SCS's `rebalance_lathander` spell tweak (`stratagems.ini`
  `rebalance_lathander=1`) rewrites them to set opcodes 86-89 to 100 for 18 s.
  Only that combination reaches 310. Without the SCS tweak the spells do not
  use these stats; without IWDification the spells do not exist.
- Spell Revisions adds no 100% physical source; its Hardiness (40%) is below the
  knee.
- SCS uses Divine Protection in its own AI (`PRIORITY_BREACH`, `PRIORITY_DISPEL`
  lists; `SHIELD_OF_LATHANDER` state). Enemy casters keep 100% because 310 skips
  everyone outside the party roster.

## Decision

Christopher chose **option A** (2026-10-20): short immunity windows stay
uncapped; stacking, equipment, passives and forms stay capped at 90%. His
condition: "Sollten nur ganz sicher testen, dass es nicht laenger oder kuerzer
dauert als gewollt" — the exception must start and end exactly with the effect.

## Design

A *window* is one effect in the creature's timed effect list that by itself
reaches 100% for its damage type: opcode 86-89, increment (mode 0) or set
(mode 1), amount at least 100, applied limited duration (`m_durationType` 4096,
the engine's absolute-expiry form) and not finished (`m_done` 0). While such an
effect exists, that damage type keeps its native value; the other three types
are still capped.

- The window is read from the effect list at every stats rebuild, inside the
  existing ListsResolved listener. It has no timer and compares no time, so it
  cannot outlast or undercut the effect: the engine decides when the effect
  starts, expires, is dispelled or is restored from a save.
- The list is only scanned when the curve would lower a value, and the scan
  stops once all four types have a window.
- Equipped effects (timing 2), permanent ones (1, 9), still-delayed ones (4)
  and percentage changes (mode 2) never qualify. A window delivered through an
  opcode-177 EFF wrapper is not inspected and stays capped; none is known.
- Native value means the engine's own total, including later penalties; a
  window does not raise anything above what the engine computed.
- Missing or malformed fields disable the module before any write, as before.

Component 310's tp2 wording and README/CHANGELOG describe the exception. No
spell, item or save is changed.

## Live game update path

Chris's game has the private adapter `CBR_PHYSICAL_CAP` component 0 in the
middle of its log (line 441 of 452). It must not be uninstalled. The adapter now
has component 1: a new tail entry that requires component 0 and its existing
`CBR_PHYSICAL_SOFTCAP` marker, and replaces only `override/M_CBRRES.lua`.
WeiDU keeps the replaced runtime in `backup/1`, so uninstalling component 1
restores it. The adapter tests cover the update, the missing component 0 and a
missing marker.

## Verification

### Automated

- `tests/test_physical_resistance.py`: Lua simulator with mock EEex for window
  start/end, partial windows, every non-window kind (set 99, increment 99,
  percentage, two increments of 50, each timing, finished effects, opcode 177,
  other resistances), equipped lists, later penalties, scan scope, the
  registered callback, the reserved 95% curve, invalid lists and a missing
  iterator.
- `tests/test_physical_resistance_live_adapter.py`: real WeiDU in disposable
  games: public/private parity, the in-place update (only the runtime changes;
  the log gains one row and only row 0's comment is refreshed), the
  prerequisite and marker guards.

### Lab 1: BG2EE 2.7.3.0, EEex 1.3.1 (target engine)

A disposable copy of a bare 2.7.3.0 game with EEex 1.3.1 and LuaJIT, component
310 installed from this branch, run through `bg_lab_slots.py` (quiet, hidden).
Chris's `SPPR527`/`SPPR737` were copied in byte for byte. Party member 0 and a
neutral control creature (copy of `AMNG1`, base physical resistance 0, outside
the party, so never capped) both received a +90 stacking source; a probe
listener registered after 310's recorded every pass. Ticks are game ticks
(15 per second); "expiry" is the effect's own absolute expiry tick.

| Scenario | Party: 100% from - to | Control: 100% from - to | Effect expiry |
| --- | --- | --- | --- |
| DP | 33303 - 33578 (then 85) | 33302 - 33582 (then 90) | 33572 / 33571 |
| GDP | 33631 - 33908 | 33631 - 33912 | 33900 |
| DP removed by opcode 321 at 34068 | 33960 - 34070 | 33959 - 34069 | (34229) |
| DP recast at 34271 | 34127 - 34553 | 34127 - 34542 | 34396, then 34542 |
| DP without stacking source | 34645 - 34928 (0 / 100 / 0) | 34644 - 34917 | 34914 / 34913 |
| DP, save and reload at 37431 | 37310 - 37585 | 37310 - 37590 | 37579 |

### Lab 2: copy of Chris's game, EEex 1.2.0 (deployment target)

A fresh copy of `%USERPROFILE%\Games\Chriz Easy BG\game` (only read), the live
update installed there exactly as planned for the real game, one of his saves
copied in (party of six, Waukeen's Promenade). Same probe and control. His
protagonist also had a +25 buff (`C0DC03`), so outside a window the party value
was 90 (115 capped) and later 85.

| Scenario | Party: 100% from - to | Control: 100% from - to | Effect expiry |
| --- | --- | --- | --- |
| DP | 31732182 - 31732455 | 31732182 - 31732453 | 31732451 |
| GDP | 31732510 - 31732785 | 31732510 - 31732783 | 31732779 |
| DP removed at 31732941; `C0DC03` expired inside the window | 31732838 - 31732942 | 31732839 - 31732943 | (31733107) |
| DP recast at 31733136 | 31732999 - 31733415 | 31733000 - 31733413 | 31733268, then 31733406 |
| DP without stacking source | 31733509 - 31733779 | 31733510 - 31733788 | 31733778 / 31733779 |
| DP, script save, new game process, load | 31732180 - 31732455 | 31732181 - 31732455 | 31732449 |

Findings in both labs:

- In every row the party's value changed in the same pass as the effect entered
  or left its timed list. No pass showed the effect present with a capped value
  or a 100% value without the effect.
- The engine removes an expired effect in the creature's next effect pass, 0-15
  ticks after the expiry tick. The party window always ends in that pass, like
  the uncapped control's own 100%. Party and control differ only by each
  creature's pass phase. After a reload the window resumed with the saved
  absolute expiry.
- A second stacking source expiring inside a window, the first of two copies
  expiring, and removal through the spell's resource all behaved as the engine
  does for the control.
- `m_done` is a number on EEex 1.2.0 and 1.3.1; applied timed effects carry
  `m_durationType` 4096 on both. ListsResolved fired once per tick per creature.

### Live update rehearsal

On the same fresh copy, before any game launch: component 1 installed with
WeiDU 24900 (as on October 6). Exit 0; the log gained one row
(`~CBR_PHYSICAL_CAP/SETUP-CBR_PHYSICAL_CAP.TP2~ #0 #1`); the only other log
change is WeiDU's refreshed comment on row 441 (version label
`private-oct06-90pct` becomes `private-oct20-immunity-windows`). Of 40,925
override files only `M_CBRRES.lua` changed, and it equals the tested runtime
with marker 241. `SPLSTATE.IDS`, `UI.MENU`, `dialog.tlk`, `chitin.key`,
`engine.lua` and `weidu.conf` were unchanged. Uninstalling component 1 restored
the October 6 runtime byte for byte.

### Not covered

- Dispel Magic itself (a random level check) was not cast; removal through the
  spell's own resource exercises the same list change.
- In the copy of Chris's game, the lab automation's click on Options ends the
  game process even with 310 and the probe switched off, so the in-process save
  and reload ran only in lab 1; lab 2 used a script save and a new process.
- No window from an opcode-177 EFF wrapper exists to test.
