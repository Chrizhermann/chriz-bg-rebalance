# Cleric of Tempus Holy Power redesign

Approved by the user on 2026-07-16 as an independently implementable section of the
larger Cleric of Tempus redesign.

## Scope

Add a tail-installed WeiDU component family that replaces the existing `OHTMPS1` Holy
Power innate with a short, level-scaled martial burst. The redesign must work against the
final installed resources in a heavily modded BG2EE/EET game containing Spell Revisions,
SCS, Artisan's Kitpack, and EEex.

This component does not change Chaos of Battle, remove Divination spells, add weapon-hit
riders, or alter the weapon-training component. Those remain separately selectable design
and implementation work.

The ordinary five-APR ceiling is intentional. An optional EEex-only higher-cap experiment
is deferred until separate engine research establishes that it can affect real attack
scheduling without importing true-Haste movement, timer, animation, off-hand, save/load,
or multiplayer side effects.

## Progression

For a Cleric of Tempus with the normal one APR before equipment and external buffs:

| Cleric level | Duration | Strength floor | Holy APR bonus | Holy total | With supported Improved Haste |
|---|---:|---:|---:|---:|---:|
| 1-6 | 3 rounds | 18/00 | +0 | 1 | 2 |
| 7-12 | 4 rounds | 18/00 | +1/2 | 1.5 | 3 |
| 13-18 | 5 rounds | 19 | +1 | 2 | 4 |
| 19-24 | 5 rounds | 20 | +1 | 2 | 4 |
| 25+ | 5 rounds | 21 | +1.5 | 2.5 | 5 |

Holy Power also:

- gives fighter-equivalent THAC0 for the caster's cleric level, capped at THAC0 0;
- grants temporary current and maximum HP equal to cleric level, capped at +30;
- treats the Strength entries as floors and never lowers an already higher Strength; and
- remains mutually exclusive with the installed Divine Power spell in both casting
  orders.

Durations are fixed by tier rather than one round per level. This keeps the ability a
deliberate burst throughout Shadows of Amn and Throne of Bhaal.

## Uses per rest

Grant one use at levels 1, 6, 11, 16, and 21, for a maximum of five uses per rest. Remove
only the later `GA_OHTMPS1` grants at levels 26, 31, 36, 41, and 46 from the Tempus CLAB.
Never replace `OHTEMPUS.2DA` wholesale because the live table contains domain, symbol,
memorization, and other mod-added rows.

At maximum duration this permits 25 rounds of Holy Power per rest. Retaining the current
late grants would permit 45-50 rounds and make the burst too routine.

An existing character who already owns `OHTMPS1` automatically uses the revised SPL.
Changing later CLAB grants does not retroactively remove excess uses already granted to a
high-level saved creature. The current Branwen is level 13 with the correct three uses, so
future grants at 16 and 21 naturally reach the intended cap without save surgery.

## APR implementation

Holy Power itself uses cumulative opcode 1 bonuses of `+0`, `+1/2`, `+1`, `+1`, and
`+1.5`. It does not use opcode 1 percentage modifiers. A timed percentage effect cannot
reliably express "multiply final APR after every other effect" across arbitrary casting
orders, and it would amplify equipment APR in ways not included in this balance design.

Do not enable `GETS_PROF_APR` for `OHTEMPUS`. In the target installation, True Grandmastery
would make two proficiency points provide up to +1.5 additional APR by level 13, conflating
warrior level progression with specialization and overwhelming the innate's progression.

Do not apply opcode 16 or 317 merely to raise the cap. Their true-Haste mode doubles APR
with a ten-APR cap but also changes movement, initiative, animation speed, round timing,
periodic-effect frequency, haste states and icons, and Slow interaction. Spell Revisions'
Whirlwind and Greater Whirlwind deliberately use this exceptional mechanism for a
two-round warrior-HLA burst; Holy Power must not silently become the same feature.

## Improved Haste compatibility

Resolve `WIZARD_IMPROVED_HASTE` dynamically through `SPELL.IDS`. Never assume `SPWI613`, a
Spell Revisions component number, or a mod folder. Inspect reachable, active effects in
the final resolved resource and classify all caster-level headers consistently:

- **Doubling semantics:** a timed opcode 16 or 317 with type 1, with no additive-Haste
  signature. Native doubling already produces Holy totals of 2/3/4/4/5, so no bridge or
  global spell marker is installed.
- **Additive semantics:** a timed cumulative opcode 1 granting exactly +1 APR, with no
  opcode 16/317 type-1 signature. Install the private marker and bridge described below.
- **Unknown or mixed semantics:** missing resource, inconsistent headers, conditional or
  probabilistic wrapper that cannot be resolved safely, both signatures, or neither
  signature. Fail before mutation and print actionable diagnostics.

The default component uses automatic semantic detection. Two advanced mutually exclusive
subcomponents may force doubling or additive treatment for supported but unrecognized
layouts. Force mode selects compatibility behavior; it must not replace or rebalance the
user's Improved Haste spell, and it still fails if the minimum resource structure required
for safe patching is absent.

### Additive-Haste bridge

For the additive case, allocate private spell states dynamically rather than hardcoding
numbers that may collide with SCS or another mod.

1. Add an inert marker to the final Improved Haste resource. Its target, power, timing,
   duration, dispel/resistance, caster level, and probability must match the detected +1
   APR effect.
2. Mark the active Holy Power APR tier (`+1/2`, `+1`, or `+1.5`) with separate private
   states. The level-1 `+0` tier requires no bridge.
3. When Holy Power is cast second, an immediate conditional check sees the Improved Haste
   marker and applies a second copy of Holy Power's own APR bonus.
4. When Improved Haste is cast second, conditional kick effects see the active Holy tier
   and apply the same bonus immediately.
5. While Holy Power remains active, a tier-specific opcode 272 heartbeat checks the
   Improved Haste marker. Its helper removes its previous helper effect by resource before
   applying a one-second cumulative APR effect, preventing accelerated pulses or reloads
   from stacking copies.
6. When either parent buff ends or is dispelled, the helper expires within at most one
   engine tick. Truly zero-lag expiry would require EEex and is not required for this
   portable component.

For the normal one-APR cleric baseline, steady-state overlap is:

`1 base + Holy bonus + 1 SR APR + repeated Holy bonus = 2/3/4/4/5 APR`.

The bridge deliberately duplicates only Holy Power's bonus. It does not multiply APR from
weapons, items, proficiencies, or unrelated mods. The normal five-APR ceiling therefore
remains the safety boundary.

## Divine Power exclusion

Resolve the installed Divine Power spell symbolically. Holy Power must remove timed Divine
Power effects before applying itself, and Divine Power must reciprocally remove timed
`OHTMPS1` effects before applying itself. Preserve every other effect, header, description,
and mod-added behavior in Divine Power. This closes the current one-way stacking hole in
which casting Divine Power after Holy Power can retain both APR progressions.

If the final Divine Power resource cannot be resolved or patched in a recognized form,
fail before changing either spell.

## Component identity

Use the 4xx class/kit family introduced by the approved Tempus weapon-training design:

- `401`: Holy Power compatibility - automatic semantic detection (recommended)
- `402`: Holy Power compatibility - force true-doubling treatment
- `403`: Holy Power compatibility - force additive treatment

The three entries form one mutually exclusive WeiDU subcomponent group. Suggested labels:

- `cbr_cleric_tempus_holy_power_auto`
- `cbr_cleric_tempus_holy_power_force_double`
- `cbr_cleric_tempus_holy_power_force_additive`

Chaos of Battle and the Divination drawback receive later component numbers and remain
independently selectable until the complete kit package is approved.

## Compatibility and failure handling

Before any mutation, validate:

- BG2EE or EET;
- `OHTEMPUS.2DA` and an exact `ABILITY1` row containing the expected current grant shape;
- the existing `OHTMPS1` resource and supported SPL V1 layout;
- dynamically resolved Divine Power and Improved Haste resources;
- internally consistent Improved Haste semantics for the selected mode; and
- availability of collision-free spell-state and SPLPROT entries for the additive bridge.

Patch final resources surgically and idempotently. Do not replace source-owned SPLs or
2DAs wholesale, hardcode mutable mod component numbers, change `CLSWPBON.2DA`, or modify
unrelated kit rows. A second installation must produce the same semantic resources, not
duplicate effects, states, helpers, or CLAB changes.

All new engine resources use the `CBR` prefix and eight-character-or-shorter resrefs. The
component adds no game-facing strings and should leave `dialog.tlk` byte-identical.

## Testing and deployment boundary

Automated tests use copied/synthetic SPL and 2DA fixtures, never the active game directory.
They must cover:

- exact level progression, duration, Strength floors, THAC0 cap, HP cap, and APR keys;
- the five-use CLAB cap while preserving every unrelated row and cell;
- additive, doubling, mixed, missing, and inconsistent Improved Haste layouts;
- both buff casting orders and bridge non-stacking at the resource-graph level;
- reciprocal Divine Power exclusion;
- dynamic state allocation without collisions;
- idempotent second application; and
- no dialog/TLK operation in the component.

Before live deployment, perform a controlled in-engine matrix for both casting orders,
expiry, dispel, save/reload, Slow, APR equipment, and Divine Power. The current game is an
active-playthrough reference installation and remains read-only until the tested component
and a timestamped rollback bundle are ready.
