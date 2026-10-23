# Dragon physical-vorpal delivery

2026-09-07. Research before implementation; all game access was read-only. No
gameplay acceptance is claimed. Scope and actor identities are in
[research 14](14-dragon-runtime-scope.md).

## Delivery decision

Use an actor-owned opcode-248 melee rider referencing an EFF V2 opcode 402.
The EFF owns the probability and death save. Its Lua callback constructs one
opcode-13 effect, death type 8, using EEex's public `noSave=1` application option.
There is no second chance/save, damage prerequisite, immunity removal, creature
replacement, or persistent Lua listener. This requires EEex at runtime while
still installing only override resources.

The [IESDP opcode reference](https://gibberlings3.github.io/iesdp/opcodes/bgee.htm#op248)
describes 248 as applying an EFF on successful melee attacks, after base weapon
damage. It is not an HP-loss event. Opcode 120 weapon immunity prevents this
rider too; `HitBy` alone would not provide that protection. Opcode 101 can block
the delivered EFF, so direct opcode 13 would still lose to Death Ward.
EFF resistance/dispel flag bit 2 concerns spell deflection/turning, not opcode-101
immunity; setting it cannot solve this requirement. See
[EFF V2](https://gibberlings3.github.io/iesdp/file_formats/ie_formats/eff_v2.htm).

The chosen profiles are 15% / death save -4, 10% / -2, and 5% / -2. Store inclusive
probability windows 0..14, 0..9, and 0..4 respectively for the engine's 0..99 roll.
The installed EE Fixpack's corresponding 25-to-24 and 10-to-9 weapon corrections
are consistent with these windows. No ordinary attack-damage roll is added.

## EEex API evidence

The reference tree's `EEex/EEex.tp2:3` and `WeiDU.log:8-15` identify v0.11.0-alpha.
In `override/EEex_GameObject.lua`, line 223 documents `noSave` as bypassing
immunities to application; lines 257-324 implement `EEex_GameObject_ApplyEffect`.
Line 298 constructs a native effect through `CGameEffect.DecodeEffect`; line
322 calls `virtual_AddEffect(effect, effectList, noSave, immediateResolve)`.
The same public API and argument names are present in the
[official v1.2.0 source](https://github.com/Bubb13/EEex/blob/v1.2.0/EEex/copy/EEex_scripts/EEex_GameObject.lua#L330)
(documentation line 330; native forwarding line 424).

SHA-256 of the read reference files:

| File under reference `override/` | SHA-256 |
|---|---|
| `EEex_GameObject.lua` | `55eb80fc6d2cb6f9d7f5d50e2c8f844cc87365552ca0f91a5cd8ab9669bab650` |
| `EEex_Opcode_Patch.lua` | `b4bdadfdfb0cfb17ad96e92ac09328aee365642f720d750dfe6e2116c7e047b3` |
| `EEex_Sprite.lua` | `b4c3650979b0163b0bac9c859b4d3100a9e94f956b3aa3ac536ee34ecbd0a589` |

The correct parameter-2 key is `dwFlags`, not `parameter2` or `m_dWFlags`.
The latter is the native effect field used when reading an existing effect.
`sourceID` represents `m_sourceId`; `sourceTarget`, `m_sourceRes`,
`m_sourceType`, and `m_sourceFlags` are supported arguments. Preserve source
identity when constructing the lethal effect. The inner effect uses
`savingThrow=0`, `saveMod=0`, `probabilityUpper=100`, `probabilityLower=0`,
`m_flags=2`, and `durationType=1`; permanence is selected by `dwFlags=8`.

`override/EEex_Opcode_Patch.lua:741-748` documents opcode 402 as invoking an
uppercase global function of at most eight characters with arguments
`(effect: CGameEffect, target: CGameSprite)`. Lines 771-773 bind those arguments.
The callback is immediate and does not retain either userdata.

`override/EEex_Sprite.lua:582-585` implements the public
`EEex_Sprite_GetStat(sprite, statID)` through active derived stats;
`override/STATS.IDS:84` defines `83 MINHITPOINTS`. The callback must explicitly
decline death for positive minimum HP, preserving plot immortality despite the
application-immunity bypass. Missing APIs or unreadable guard data fail closed
with a component-labelled diagnostic. Ordinary death immunity is not this guard.

## Native engine limits and rejected route

A separate read-only disassembly audit identified the reference `Baldur.exe`
as 2.6.6.0, SHA-256
`fc821a4806a0305b84fd85f1aad2bd472c8db642ed34b4494ae62351cae1c580`.
The native `AddEffect` path at `0x140386dc6-0x140386e38` continues after a failed
application check when its override argument is set. This supports the public
EEex `noSave` contract rather than requiring temporary protection edits.

Native opcode 13 can downgrade death type 8 to normal death internally at
`0x1401af080-0x1401af17b`. Gore disabled, party safety/difficulty rules, and
derived `m_bNoPermanentDeath` can affect that decision. The component preserves
these native settings and must describe its effect as the native permanent-death
type, not promise to defeat every engine anti-chunking option.

Opcode 151 was rejected. Its resource check at `0x1401bff1e` rejects an empty or
invalid CRE before death (`0x1401bff27`). A valid resource internally applies
death with the override argument (`0x1401c00d6-0x1401c00f5`), but unconditionally
creates the replacement creature afterwards (`0x1401c0453` onward), with extra
death-type branches. An invisible helper would introduce replacement and
lifecycle behavior unrelated to a weapon rider. This is not implemented.

## Resource and validation contract

Profiles use `CBRDV15/CBRDV10/CBRDV05.SPL`, their EFFs use
`CBRDVE15/CBRDVE10/CBRDVE05.EFF`, removal uses `CBRDVREM.SPL`, and the callback
is installed as `M_CBRDVG.lua`. Each profile first removes only those three
owned spell resources and then adds its permanent opcode-248 rider. Removal
likewise targets only the owned profiles. No shared dragon weapon is patched.
The profile's own removal is always first, as required for opcode-321 stacking
prevention. Because 321 matches item and spell source resrefs, same-name
`CBRDV15/CBRDV10/CBRDV05.ITM` resources are also rejected during preflight.

Generate all binary buffers in memory and compare every reserved existing file
against the exact canonical bytes before publishing any output. An unknown,
modified, or truncated file is a collision. The public installer must complete
script and resource preflight before either mutation phase. The runtime module
is also included in resource collision checking.

Hermetic tests must exercise actual WeiDU generation, whole-output idempotence,
late collisions with no earlier writes, probability windows, a single death
save on the delivered 402, removal scope, and the Lua guard/bypass call. These
tests do not prove engine gameplay. Separate authorized acceptance remains for
landed hits, Stoneskin, 100% physical resistance, Death Ward, successful and
failed saves, weapon immunity, plot minimum HP, native anti-chunking settings,
save/load, and changing the difficulty gate.

Implementation verification on 2026-09-07: `python -m pytest -q
tests/test_dragon_vorpal_effects.py -p no:cacheprovider` passed **13 tests**.
The binary harness uses WeiDU 249 in temporary directories. Failure cases
assert both unchanged resource bytes and zero WeiDU rollback files, so an
earlier write followed by restoration cannot masquerade as successful
preflight. Lua runs with mocked EEex functions in a temporary directory; no
game state, settings, creature, or effect list was used or modified.
