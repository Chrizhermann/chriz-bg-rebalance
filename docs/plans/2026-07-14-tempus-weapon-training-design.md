# Cleric of Tempus weapon training — design (approved 2026-07-14)

Approved by the user in the 2026-07-14 brainstorming session.

## Goal and priority

Add a durable, tail-installed WeiDU component that makes the existing `OHTEMPUS` kit a
more capable martial cleric without disturbing the rest of the heavily modded EET install.
The first release is intentionally limited to weapon access and proficiency rules:

- Clerics of Tempus may use axes, longswords, and crossbows in addition to every weapon
  available to a normal cleric in the installed game.
- They may place two proficiency points in every weapon they can use.
- They may place two points in every weapon style: two-handed, sword and shield,
  single-weapon, and two-weapon style.
- New Clerics of Tempus receive one starting point in axe, longsword, and crossbow.
- The already-joined Branwen in the current playthrough receives the same missing access
  and starter points through a separate, one-shot migration.

Tempus spell-domain drawbacks and stronger innate abilities are deliberately deferred.
They need their own balance pass and must not delay the live-playthrough fix.

## Current-install evidence

The design is based on the live EET installation, its installed Artisan's Kitpack
resources, the reference balance-patch repository, and the current save. The important
facts are:

- The kit symbol is `OHTEMPUS`; its installed CLAB is `OHTEMPUS.2DA`.
- `OHTEMPUS.2DA` applies the shared cleric permission spell `C0PR#CL` and the
  Tempus-specific spell `C0PR#C4` at level 1.
- Artisan's EEex proficiency system gates fighter-usable weapons with custom-stat checks.
  `C0PR#CL` grants normal cleric permissions, including crossbows. `C0PR#C4` currently
  grants axe permission and one axe proficiency point. No corresponding Tempus grant
  exists for longswords.
- The installed `WEAPPROF.2DA` caps the normal Tempus cleric weapons and all four styles at
  one point, while axe, longsword, and crossbow are capped at zero.
- The current joined Branwen is a level-13 `OHTEMPUS` cleric in the latest save. Her saved
  creature already has the normal cleric permissions, crossbow permission, and one axe
  point, but no longsword or crossbow proficiency points.
- Spell Revisions, SCS, EET, EEex, and Artisan's Kitpack are all part of the compatibility
  environment. This component must patch the final installed state rather than replace
  source-owned resources wholesale.

The target save discovered during the design audit is:

`C:\Users\chris\OneDrive\Documents\Baldur's Gate - Enhanced Edition Trilogy\save\000000437-chat is mean dot jpg`

That path is deployment evidence, not an installer default. The installer must never
search for or edit a user's saves.

## Chosen approach

Use a formal component plus an explicit in-game migration:

1. Add component 400 to `chriz-bg-rebalance` and install it at the tail of the current
   WeiDU stack.
2. Patch only the live `OHTEMPUS` column in `WEAPPROF.2DA` and the existing
   Tempus-specific Artisan spell `C0PR#C4.SPL`.
3. Include a small, idempotent helper spell for migrating an already-joined Tempus cleric.
4. Invoke that helper once on Branwen after loading the original save, verify the result,
   and save into a new manual slot.

This was selected over two alternatives:

- A direct override-only hotfix would solve the immediate game but create undocumented
  drift with fragile manual rollback.
- Editing `BALDUR.GAM` or the embedded saved creature directly would depend on binary
  offsets and OneDrive timing and is unnecessary when the engine can apply the same
  effects safely in-game.

## Repository placement and component identity

The repository currently uses 1xx for SCS, 2xx for Spell Revisions, and 3xx for
cross-cutting adjustments. Add a 4xx family for class and kit rebalances:

- `400`: Cleric of Tempus — weapon training
- `401+`: reserved for the later Tempus innate/domain/downside redesign and other
  independently selectable Tempus changes

The component label is `cbr_cleric_tempus_weapon_training`. It must remain independently
installable and must not silently bundle later spell or innate changes.

## `WEAPPROF.2DA` transformation

Resolve both the `CLERIC` and `OHTEMPUS` columns by header name. Do not assume a kit-list
row, kit numeric value, or a fixed column number. WeiDU's 2DA data rows contain an
unlabelled row-name field before the declared header fields, so a header index maps to
data index `header_index + 1`; tests must protect this easy off-by-one failure.

For the resolved `OHTEMPUS` column:

1. For each actual weapon proficiency row whose installed `CLERIC` or `OHTEMPUS` value is
   greater than zero, set the Tempus maximum to 2. This inherits modded normal-cleric
   weapon availability and preserves any pre-existing Tempus-only access instead of
   freezing a vanilla weapon list.
2. Set `LONGSWORD`, `AXE`, and `CROSSBOW` to 2 even though their normal cleric values are
   zero.
3. Set `2HANDED`, `SWORDANDSHIELD`, `SINGLEWEAPON`, and `2WEAPON` to 2 explicitly.
4. Leave `EXTRA2` through `EXTRA20` and every unrelated kit column untouched.

The normal-cleric inheritance rule must not accidentally treat metadata, placeholder, or
future custom-stat rows as weapons. The implementation should classify the standard
weapon and style row range by symbolic boundary or an explicit validated row set, then
apply the positive-`CLERIC` rule only within that range.

The legacy BG1 composite rows require an explicit compatibility decision in the
implementation tests. In BG2EE/EET, the authoritative grants are the individual
`LONGSWORD`, `AXE`, and `CROSSBOW` rows. `LARGE_SWORD_BG1` and `AXE_BG1` can mirror the
first two without ambiguity if the installed rules use them. A BG1 composite bow row
cannot express crossbow-only access without also broadening bows; it must not be changed
silently. Component 400 targets BG2EE/EET and should document or reject any unsupported
legacy-only layout rather than guess.

The patch is idempotent: applying it twice produces the same table bytes and values as
applying it once.

## Artisan proficiency integration

Patch `C0PR#C4.SPL`, the Tempus-specific level-1 grant, rather than the shared `C0PR#CL`
dispatcher or every weapon item. This keeps all new permissions and starter points scoped
to Clerics of Tempus.

The combined level-1 grants (`C0PR#CL` plus the patched `C0PR#C4`) must leave exactly one
effective permission and one Tempus starter point for each of:

- longsword (`C0PR#90`) and one longsword proficiency point;
- axe (`C0PR#92`) and one axe proficiency point; and
- crossbow (`C0PR#103`) and one crossbow proficiency point.

The installer must inspect both grant spells before changing `C0PR#C4`. It should
recognize and preserve the installed Artisan effect structure, retain the existing axe
permission and axe opcode-233 point when they are already correct, and add one opcode-233
starter point each for longsword and crossbow. The current `C0PR#CL` already supplies
`C0PR#103`; `C0PR#C4` must not duplicate that permission. If a supported future Artisan
layout moves the permission out of the shared spell, the Tempus spell may supply the one
missing permission after capability validation. Reinstalling component 400 must not add
another copy of any permission or proficiency effect.

The component must not:

- patch `C0PR#CL` for all clerics;
- globally rewrite Artisan's item usability gates;
- replace `OHTEMPUS.2DA` or any SPL wholesale;
- depend on Artisan's mutable WeiDU component number; or
- touch Spell Revisions or SCS spell resources.

Compatibility is detected by required resources and the expected custom-stat/effect
structure. If the installed Artisan mechanism is absent or materially different, the
component exits before writing anything and explains which prerequisite was not found.

## Existing-save migration

`WEAPPROF.2DA` changes future caps and character-generation choices, but the joined
Branwen stored in `BALDUR.GAM` has already received her level-1 CLAB effects. Component
400 therefore ships an eight-character-or-shorter helper SPL, provisionally `CBRTMIG`,
for manual, one-time use after loading the save.

The helper is scoped to a target creature and is idempotent. For Branwen it must:

- ensure the three Tempus weapon permissions are present, adding only missing ones;
- preserve her existing axe proficiency point;
- add one longsword point only if she has none;
- add one crossbow point only if she has none;
- never reduce, overwrite, or duplicate an existing proficiency; and
- remove or mark its own migration state so accidental reapplication is harmless.

The migration is invoked through an engine action such as `ReallyForceSpellRES` while the
user controls the loaded game. The final implementation plan must supply the exact tested
console command and targeting procedure. It must not automatically scan party members or
rewrite save files during WeiDU installation.

## Failure handling and transactional safety

Before component 400 writes any resource, it validates all prerequisites:

- an Enhanced Edition BG2/EET game;
- `WEAPPROF.2DA` with named `CLERIC` and `OHTEMPUS` columns;
- required symbolic proficiency rows;
- `OHTEMPUS.2DA` applying the expected Artisan grants; and
- `C0PR#C4.SPL` and the required Artisan custom-stat mechanism in a recognized form.

Validation happens before mutation. Missing or unexpected structures are hard failures
with actionable messages; there is no broad fallback patch.

Component 400 is TLK-neutral. It adds no kit description, `STRING_SET`, game-facing
string, or dialog change. Setup/TRA component labels are installer UI only. A live install
must leave `dialog.tlk` byte-for-byte unchanged.

## Live deployment procedure

The live playthrough is protected as follows:

1. Develop and test against copied fixture resources, including a second application for
   idempotency, before touching the game directory.
2. Fully close both `Baldur.exe` and `InfinityLoader.exe`.
3. Make a complete timestamped copy of the latest save directory. Never move or delete
   the original.
4. Record hashes for `dialog.tlk`, the target save files, `WEAPPROF.2DA`, `C0PR#C4.SPL`,
   and any existing resource that the migration helper will replace.
5. Tail-install component 400 only. Never uninstall or reinstall an earlier component in
   the middle of the current WeiDU stack.
6. Verify the installed resources and confirm that `dialog.tlk` is byte-identical.
7. Restart the game so the 2DA changes are loaded.
8. Load the unmodified source save, apply the migration once to Branwen, and test her
   proficiencies, weapon equipping, and two-point caps.
9. Save the migrated playthrough to a new manual save slot, retaining both the original
   save and its timestamped backup.

If correction is required, use the captured original resources or a new tail patch. Do
not uninstall through the middle of the mod stack.

The generated Claude project memory consulted during design was last modified
2026-07-09T12:34:44Z and is treated only as historical safety context; current files and
the user's explicit authorization govern this deployment.

## Verification and acceptance criteria

Automated fixture checks must show:

- prerequisite validation fails before writes for every missing or malformed dependency;
- only the `OHTEMPUS` cells intended by this design change in `WEAPPROF.2DA`;
- all inherited normal-cleric weapons, the three new weapons, and all four styles cap at 2;
- `EXTRA2`–`EXTRA20` and unrelated kit columns are byte/value identical;
- the Tempus grant contains one effective starter grant for longsword, axe, and crossbow;
- a second installation is a no-op at the semantic and resource level;
- the migration adds only missing permissions/points and is harmless when repeated; and
- no component operation changes `dialog.tlk`.

Live acceptance requires all of the following in the copied/new save state:

- Branwen has exactly one initial point in axe, longsword, and crossbow unless the source
  save already had a higher legitimate value;
- she can equip representative axes, longswords, and crossbows that Artisan's gates
  previously blocked;
- the level-up UI permits two points, but not three, in every usable weapon and each of
  the four styles;
- representative normal cleric weapons remain usable;
- unrelated party members, spells, and kit abilities are unchanged; and
- the original save, backup, and pre-install `dialog.tlk` hash remain intact.

## Deferred Tempus balance work

Component 401 or later will separately design stronger Tempus innate abilities and a
meaningful spell-domain or school drawback. That work requires inspecting Spell
Revisions' final divine spell taxonomy and testing SCS interactions. It must not be
smuggled into component 400 or used as a reason to postpone the playthrough-safe weapon
fix.
