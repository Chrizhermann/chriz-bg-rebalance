# Potion uniqueness (330/331) and the Heroism family (332)

October 14, 2026. Design note for the installable components. The behaviour was
decided by Christopher earlier; this note only records how it is built.

## Agreed behaviour

- **330**: every temporary potion type is unique on its drinker. **331**: the same,
  but Potions of Genius keep their native stacking. 330 and 331 are exclusive.
- Different potion types may overlap. Instant healing, cures, permanent and quest
  effects behave as before.
- Drinking the same type again: potions with a timed maximum-HP bonus (Heroism,
  Power and HP potions from other mods) keep the first dose until it expires;
  every other type restarts its normal duration without stacking.
- **332**: Heroism, Greater Heroism (Bardic Wonders), their Gallant copies and the
  Potion of Heroism form one family. The first active one wins: no refresh, no
  upgrade, each recipient on its own. Song of Heroism, Aid and Potion of Power are
  not members.

## Why no runtime hook

The October 9 prototype (Codex worktree `potion-uniqueness-20261009`, never
committed) built an EEex admission hook because a private-spell rewrite changes
dispel level and duration scaling. Its native findings that still matter here:

- Removing and re-adding a timed opcode-18 bonus heals the drinker (the first
  application adds the HP gain to current HP; removal only clamps). So HP potions
  must not refresh. CON setters and regeneration do not grant HP on refresh.
- Opcode 206 never blocks item-sourced effects; opcodes 318/324 block any source
  type (IESDP agrees). Item effects are queued in two batches: effect target 1
  first, then target 2 through the item's projectile, in file order inside each.

Keeping every original effect in its original item or spell avoids the identity
problems entirely, so plain WeiDU edits are enough. No EEex, no new spells.

## Mechanism

**Refresh** (most potion types): one opcode 321 (remove effects by resource,
timed list, instant, bypass MR) per resref of the potion type, inserted at the
start of the drink ability, after any leading guard that names the potion itself
(for example Oil of Speed's haste-immunity check). The previous dose's timed
effects go, the new dose applies in full. Opcode 321 ignores the extension, so a
same-named linked spell (Item Revisions `POTNxx.SPL`) is covered too.

**Keep first** (HP potions and the Heroism family): a private SPLSTATE per potion
type (`CBR_POTION_<resref>`) or for the family (`CBR_HEROISM_FAMILY`), allocated in
SPLSTATE.IDS, plus the SPLPROT tuple "spell state is active" (0x112, -1, =),
reused when present (vanilla row 110) or appended.

- Guard: opcode 324 (immunity to resource) naming the resource itself, condition
  "state active", placed first in every delivery batch that carries a bonus
  (target 1 and/or 2). A repeat dose is then rejected as a whole with the game's
  normal "unaffected" feedback; the charge is still used.
- Marker: opcode 328 sets the state for the longest bonus duration, appended as the
  very last effect of the last batch, so the first dose's own later batch can never
  be rejected by its own marker. It copies the bonus's power and dispellability and
  always bypasses magic resistance.

Family members check the same state, so Heroism blocks Greater Heroism and the
potion, and the other way round. Bardic's leading opcode-321 "latest replaces"
controls stay in place but sit behind the guard, so they only run when no family
buff is active.

## Finding the resources (no fixed shapes)

- Potions: every category-9 item with a drink ability (ability target 5 or 7).
  A potion's payload is its drink-ability effects plus depth-1 linked spells
  (opcodes 146/148/326) whose resref names a potion item. Two potions are the same
  type when their gameplay payloads match as multisets: cosmetic effects, SPLSTATE
  markers and stacking controls that name a potion are ignored. That groups SCS's
  `DW#PTNxx` copies with their originals without reading resref patterns.
- A type is temporary when its payload has a timed gameplay effect. Keep-first
  applies when the timed payload has opcode 18.
- Anchors where the game itself has no symbol: Potion of Genius = the type holding
  `POTN29` if that type really raises Intelligence (Item Revisions turns it into
  Vocalize, which is not exempt). Potion of Heroism = the type holding `POTN09`.
  Heroism/Greater Heroism = Bardic's `C0BW202`/`C0BW502` (not in SPELL.IDS); any
  override spell with the same gameplay payload (the Gallant copies) joins too.

## Skipped on purpose (printed during install, game data unchanged)

- A potion type that already has its own lasting ward (opcode 206/318/324 naming a
  type resref, e.g. Item Revisions' linked-spell wards) keeps that native rule:
  refreshing through it could remove the old dose and then reject the new one.
- Keep-first candidates whose repeat would also have to deliver instant or
  permanent effects (damage, healing, cures), or whose bonuses use chance, saves,
  delayed timing or unusual delivery targets: one guard cannot separate those.
- Thrown potions, instant-only potions and non-drink abilities.

## Limits

- Effects already active in an existing save carry no marker: one more dose can
  stack until they expire. New doses after installation behave correctly.
- A per-effect dispel roll could remove the bonus but not the marker (or the
  reverse). Then the next dose is blocked until the marker would have expired, or
  stacks once. Both are rare.
- Only Greater Heroism's English "the more recently applied spell will remove the
  effects of the other" sentence is rewritten; other descriptions do not mention
  stacking and stay as they are.
- Bardic Wonders creates the Gallant copies itself. If that happens after 332, the
  copies carry no guard until Bardic applies the same recipe (its planned adapter):
  look up `CBR_HEROISM_FAMILY` in SPLSTATE.IDS, add the opcode-324 guard naming the
  copy itself and the opcode-328 marker, unless a guard with that state exists.

## Installed-game inventory (Chriz Easy BG, read-only)

Category-9 drink potions include SCS's `DW#PTN02` to `DW#PTN60` copies, which
group with their originals. Native self-refresh already present: Potion of
Persuasiveness (`POTN60` only; the SCS copy gets one). Oil of Speed has a leading
self-guard (op324, state 138). Bardic balance.5: `C0BW202` Heroism and `C0BW502`
Greater Heroism (op18 110%/115%, op54 THAC0, 600 s, leading op321 on both); no
Gallant copies in that install. Item Revisions/IRR sources (not installed there)
deliver potions through same-named spells; IRR adds 300 s opcode-206 wards to
Heroism, Power and Fortitude.

## Lab install (October 14, disposable copy of that game, SR/SCS/Bardic)

`--force-install-list 330 332` with WeiDU 249 succeeded in about a minute.

- 330: 46 potion types (85 files) refresh; 2 types keep their first dose:
  Potion of Heroism (`POTN09`, `DW#PTN09`) and Potion of Power (`POTN41`,
  `DW#PTN41`). `PTION41` (a Power variant that also deals 6d6 fire damage) was
  skipped with its message. Oil of Speed's own guard stays first, `POTN60` keeps
  its native refresh and gains the SCS copy's.
- 332: the Heroism potions plus `C0BW202`/`C0BW502` got the family guard and
  marker; Greater Heroism's sentence changed in the spell and its `C0BW502A`
  item (one new TLK entry).
- Spell states 240 (`CBR_POTION_POTN09`), 239 (`CBR_POTION_POTN41`) and 238
  (`CBR_HEROISM_FAMILY`); SPLPROT row 76, an existing duplicate of row 110
  ("spell state active"), was reused.
- Every changed file still holds its original effects in the original order;
  only opcodes 321/324/328 were added. Not launched in-engine.
