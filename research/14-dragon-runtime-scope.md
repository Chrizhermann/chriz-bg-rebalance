# Dragon runtime scope and difficulty gates

2026-09-07. Read-only inspection of the installed SCS 35.21 resources, before implementation. Captured CRE/BCS bytes and SHA-256 provenance are in `originals/dragon_wing_buffet/manifest.json`.

The first implementation covers five encounters. No HP or aura change is included. Current implementation defaults are Hardcore/Insane activation, 15%/-4 for Firkraag, 10%/-2 for Nizidramanii'yt and Saladrex, and 5%/-2 for Thaxll'ssillyia and the Watcher's Keep guardian. The latter allocations and activation are conservative implementation choices following the request to proceed, rather than earlier explicit per-dragon decisions.

| CRE | Death variable at 0x280 (32 bytes) | Existing combat script and slot |
|---|---|---|
| FIRKRA02 | firkra02 | DRAGRED, class 0x250 |
| SHADRA01 | ShaDra01 | SHADRA01, override 0x248 |
| DRAGBLAC | Dragblac | DRAGBLAC, class 0x250 |
| GORSAL | GorSal | GORSAL, default 0x268 |
| FSDRAGON | FSdragon | DRAGGREE, class 0x250 |

The weapons are shared with other dragons and cannot be patched globally. DRAGRED.BCS is shared with generic/ToB dragons too. Prefix each relevant combat script with blocks gated by the exact actor death variable (`Name(...,Myself)`) and a private LOCALS flag. Validate the CRE signature, identity and expected script assignment before touching any resource. Preserve all existing script bytes after the prefix.

**Correction to the July research:** the inspected SCS runtime reads `DMWW_dragon_difficulty` using **INI**, not a saved GLOBAL. Its compiled trigger is 16621 (`0x40ED`), as identified by the final `TRIGGER.IDS`; do not substitute `Global()` simply because the setting's name looks like a variable. The [engine's INI trigger](https://gibberlings3.github.io/iesdp/scripting/triggers/bgeetriggers.htm#0x40ED) reads the configuration setting. Value 0 follows the game slider; values 5/6/7 include the player-facing Hardcore and Insane settings. The new first-pass gate deliberately begins at 5, not the SCS HP block's broader 4/5/6/7 group. The installed `DIFFLEV.IDS` maps EASIEST=1, EASY=2, NORMAL=3, HARD=4, HARDEST=5; fallback therefore activates at game difficulty 4 or 5. Unknown category values fail closed. Lowering the setting removes only this component's own on-hit package, without resetting unrelated effects or AI timers.

Application/removal uses ordinary `ApplySpellRES` followed by a LOCALS update and `Continue()`, matching the installed SCS setup pattern. Script replacement can reach already-spawned actors once their script runs, but save/load and in-combat timing remain gameplay acceptance items. No active installation was modified or launched for this research.

The physical immunity-bypass mechanism is researched separately. No direct opcode-13 immunity stripping is permitted. An opcode-151 workaround was rejected because the engine requires and creates a replacement creature and has additional death-type branches; it is not a narrow physical-death implementation.

## Automated verification (2026-09-07)

`python -m unittest discover -s tests -q` passed **293 tests** in 264.609 seconds,
including 39 dragon-specific checks. The public TP2 and all three dragon TPA files
passed WeiDU 24900 parse checks individually. Coverage includes compiled activation/
removal conditions across actor identities and difficulty values, unchanged original
script bytes, actual generated effects, callback failure handling, complete collision
preflight, both component installation orders, a pre-applied hotfix, and exact synthetic
game restoration. No game process was launched. Combat, kill attribution, save/load,
Stoneskin/weapon-immunity delivery and native permanent-death outcomes remain separate
acceptance items.
