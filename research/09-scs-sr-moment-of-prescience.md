# 09 — SCS / Spell Revisions weapon-protection semantic mismatch

- Date verified: **2026-08-29**
- Target: BG2:EE + EET active install, read-only
- Planned repair: component **120**, label `cbr_scs_sr_weapon_protection_semantics`

## Finding

The current Spell Revisions resource at `SPWI808` is **Moment of Prescience**, a level-eight
Divination self-buff that improves AC and saves. It has no weapon-immunity opcode. The same
install nevertheless exposes both `WIZARD_IMPROVED_MANTLE` and
`WIZARD_MOMENT_OF_PRESCIENCE` as spell number 2808, retains SCS/SR metadata that marks the
spell as weapon protection, and has SCS common-mage scripts that select it wherever weapon
immunity is expected.

This is a compatibility bug, not a reason to redesign Moment of Prescience here. Component
120 should correct the false metadata and only the three proven SCS script contexts. A
separate SR balance project may later replace or redesign the spell itself.

## Provenance and installed-mod facts

- Active game root: `C:\Games\Baldur's Gate II Enhanced Edition modded`
- `weidu.conf`: `lang_dir = en_us`; the TLK used below is
  `lang\en_US\dialog.tlk`.
- `WeiDU.log` records SCS 35.21 component 5900 (AI initialization) and component 6030
  (Smarter Mages), among the installed SCS components.
- Audit/decompile executable: repo-owned WeiDU 24900,
  SHA-256 `ad70f5897a6d0ba4b0d226f845a9b14cf345f56cc9697ca8d05cac9fe4932c1a`.
- Earlier ambient-readiness context came from
  `C:\src\private\chriz-bg-rebalance\research\08-ambient-readiness.md`, 22,651 bytes,
  modified `2026-08-24T19:44:44Z`. It was rechecked against the effective resources rather
  than treated as current authority.

The effective `override\spell.ids` (SHA-256
`ec61787577644d662885489d2e72293e9306c24c63b9fbf8a0e6330a0a003fdf`) contains:

```text
2611 WIZARD_PROTECTION_FROM_MAGIC_WEAPONS
2708 WIZARD_MANTLE
2808 WIZARD_IMPROVED_MANTLE
2808 WIZARD_MOMENT_OF_PRESCIENCE
2907 WIZARD_ABSOLUTE_IMMUNITY
```

WeiDU decompiles the installed numeric 2808 references through the later, truthful alias
`WIZARD_MOMENT_OF_PRESCIENCE`. The duplicate old alias still explains why code that resolves
`WIZARD_IMPROVED_MANTLE` reaches `SPWI808`; production code must resolve symbols dynamically
and then validate the resulting SPL semantics.

## Effective SPL evidence

Exact installed resources are preserved under `research/originals`; hashes, sizes, source
paths, and source modification times are in
`research/originals/scs-ambient-readiness-sha256.txt`.

`SPWI808.spl` is 1,066 bytes, SHA-256
`993d5d598b24fffda5ca65ace27f6b7376c759b0a1aa6eeaf42bee6f2f98ad28`. Its live English
name and description identify **Moment of Prescience**, level 8, school Divination, personal
range, four-round duration, casting time 1, with +20 AC / save effects. Its sole ability has
19 effects:

- opcode 321 self-removal, five opcode-0 AC modifiers, and opcodes 33–37 save modifiers;
- **no opcode 120 weapon-immunity effect**;
- opcode 233 with parameter 1 = 2 and parameter 2 = 128 — the false tier-2 weapon-defense
  marker;
- opcode 328 state 64 (`BUFF_PRO_WEAPONS`) — the false active weapon-protection marker;
- opcode 328 states 187 and 188 — generic Breach/Dispel priority metadata; and
- cosmetic/display effects 142, 215, 50, and 174.

The comparison resources demonstrate the semantic distinction:

| Resource | Live name | Reachable weapon-immunity evidence | SCS weapon state |
|---|---|---|---|
| `SPWI611` | Protection from Magical Weapons | six opcode-120 effects, weapon categories 1–6 | opcode-328 state 64 |
| `SPWI708` | Prismatic Mantle | opcode 120 for enchantment/category restrictions | opcode-328 state 64 |
| `SPWI808` | Moment of Prescience | **none** | opcode-328 state 64 (false) |
| `SPWI907` | Absolute Immunity | opcode 120 for enchantment/category restrictions | opcode-328 state 64 |

The exact false opcode-233 tier marker and opcode-328 state 64 are therefore candidates for
surgical removal when the mismatch predicate is true. States 187/188 are a separate fact:
they describe generic counter priority, not weapon immunity, and must be decided from the
installed counter graph rather than removed as a class.

### Breach / Dispel counter audit (2026-08-29)

The isolated installed-resource audit resolves those two states differently:

- `SPLSTATE.IDS` names 187 `PRIORITY_BREACH` and 188 `PRIORITY_DISPEL`.
- `WIZARD_BREACH` resolves to `SPWI513`. Its two opcode-146 children reach `SPWI513B/C`;
  `SPWI513B` contains opcode 221 with parameter 1 = 9 and parameter 2 = 7. The effective
  `SPWI808` header has secondary type / MSECTYPE 7, so the installed Breach graph can remove
  Moment of Prescience. **State 187 is truthful and remains.**
- `WIZARD_DISPEL_MAGIC` resolves to `SPWI302`, whose reachable opcode 58 uses caster-level
  dispelling (`parameter2 = 0x20001`). Every one of `SPWI808`'s 19 effects has embedded SPL
  `resist_dispel = 0`, so none is eligible for that dispel. **State 188 is false on this
  install and is removed.**

Counter-resource provenance: `SPWI302` SHA-256
`8576d05013fc2e413e2f7fe59d6e5af1897264edcb3fac90653c98ab9cd6e19f` (538 bytes),
`SPWI513` `7e0f1326f2410aac9046b2050d49c343da48f3bda28f01786de2c66230cff196`
(346 bytes), `SPWI513B`
`2ec4562b5972e27f82cfc302d5800b0611426278abb0d75f4067d250fec00785` (490 bytes), and
`SPWI513C` `82f6b325750cb19cc438eed584094ad3a89911222d7151aed0647620778f7c46`
(298 bytes), all from the effective override read-only. Tests model both outcomes: a future
dispellable target keeps 188, while a counter graph proven not to reach the target's
secondary type does not keep 187.

## Reproducible common-mage audit

`research/scripts/audit_scs_weapon_semantics.py` accepts explicit game, override, WeiDU,
spell-ID, and output paths. It enumerates only `^dw#mg[0-9]+\.bcs$`, prefilters the binary
bytes for decimal spell ID 2808, decompiles each candidate in a separate
`TemporaryDirectory`, and classifies complete trigger/action shapes. Output paths inside the
game root are rejected.

Command used (the JSON/report destination was a generated path under the user's OS temp
directory, outside the game):

```powershell
python research\scripts\audit_scs_weapon_semantics.py `
  --game "C:\Games\Baldur's Gate II Enhanced Edition modded" `
  --override "C:\Games\Baldur's Gate II Enhanced Edition modded\override" `
  --weidu .\weidu.exe --spell-id 2808 `
  --output "$env:TEMP\cbr-scs-audit-<unique>.json"
```

Observed totals:

| Measure | Count |
|---|---:|
| Installed common-mage scripts | 585 |
| Decimal-2808 prefilter candidates / decompiled scripts | 98 / 98 |
| Recognized first-round blocks | 77 |
| Recognized renewal blocks | 80 |
| Recognized chain-contingency blocks | 82 |
| Recognized blocks, total | 239 |
| Unknown target-containing blocks | **0** |

Every candidate contained at least one recognized context. These counts describe this
installation and are evidence, not future installer predicates.

The final matcher allowlists complete canonical families rather than a bag of identifying
substrings: plain, difficulty-gated, and chapter/range-gated first-round blocks; the one
renewal shape; and low-prep, high-prep, and ordinary-difficulty Chain Contingency blocks.
Difficulty-variable variants are explicit, while each generated numeric `dw#cc*` helper is
validated and left unchanged. Adversarial fixtures with an added action or a
different actual cast are reported as unknown and remain untouched. A 2026-08-30
production-on-copies pass over all 98 candidates reproduced `77 / 80 / 82 / 0`; the live
candidate aggregate hash was identical before and after.

### Representative installed decompilations

`dw#mg14.bcs` contains two chain-contingency variants (helpers `dw#cc23` and `dw#cc15`) and
one renewal block. One chain variant is:

```baf
IF
  Global("ChainContingencyFired","LOCALS",0)
  Allegiance(Myself,ENEMY)
  OR(7)
    Detect(NearestEnemyOf(Myself))
    Range(Player1,20)
    Range(Player2,20)
    Range(Player3,20)
    Range(Player4,20)
    Range(Player5,20)
    Range(Player6,20)
  !StateCheck(Myself,STATE_REALLY_DEAD)
  OR(4)
    INI("DMWW_mage_prep_difficulty",0)
    INI("DMWW_mage_prep_difficulty",1)
    INI("DMWW_mage_prep_difficulty",2)
    INI("DMWW_mage_prep_difficulty",3)
  OR(2)
    !INI("DMWW_mage_prep_difficulty",0)
    DifficultyLT(HARD)
  OR(4)
    INI("DMWW_mage_prep_difficulty",0)
    INI("DMWW_mage_prep_difficulty",1)
    INI("DMWW_mage_prep_difficulty",2)
    Global("created_out_of_sight","LOCALS",1)
  OR(3)
    !INI("DMWW_mage_prep_difficulty",0)
    DifficultyLT(NORMAL)
    Global("created_out_of_sight","LOCALS",1)
  !GlobalGT("Chapter","GLOBAL",19)
THEN
  RESPONSE #100
    SetGlobal("ChainContingencyFired","LOCALS",1)
    ReallyForceSpellRES("dw#cc23",Myself)
    ReallyForceSpell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)
    Continue()
END
```

`dw#mg144.bcs` contains the canonical first-round shape:

```baf
IF
  !GlobalTimerNotExpired("castspell","LOCALS")
  HaveSpell(WIZARD_MOMENT_OF_PRESCIENCE)
  CheckStatLT(Myself,60,SPELLFAILUREMAGE)
  Global("instantprep","LOCALS",0)
  See(NearestEnemyOf(Myself))
THEN
  RESPONSE #100
    SetGlobalTimer("castspell","LOCALS",ONE_ROUND)
    Spell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)
    SetGlobal("instantprep","LOCALS",1)
    SetGlobalTimer("redefend","LOCALS",7)
END
```

`dw#mg148.bcs` contains the canonical renewal shape:

```baf
IF
  !GlobalTimerNotExpired("castspell","LOCALS")
  HaveSpell(WIZARD_MOMENT_OF_PRESCIENCE)
  CheckStatLT(Myself,60,SPELLFAILUREMAGE)
  !CheckStatGT(Myself,0,WIZARD_PROTECTION_FROM_MAGIC_WEAPONS)
  !CheckSpellState(Myself,TIME_STOP)
  !StateCheck(Myself,STATE_INVISIBLE)
  See(NearestEnemyOf(Myself))
  !GlobalTimerNotExpired("justdonepmw","LOCALS")
  Global("instantprep","LOCALS",1)
THEN
  RESPONSE #100
    SetGlobalTimer("castspell","LOCALS",ONE_ROUND)
    Spell(Myself,WIZARD_MOMENT_OF_PRESCIENCE)
    SetGlobalTimer("redefend","LOCALS",7)
    SetGlobalTimer("justdonepmw","LOCALS",7)
END
```

The first-round and renewal blocks spend the caster's normal cast on a spell that does not
satisfy the physical-defense condition. The chain blocks apply their generated contingency
helper and then force the same false protection. Component 120 will only transform these
proven complete shapes; any future unknown shape must be reported and left byte-identical.

## Read-only proof

SHA-256, size, and modification time were captured immediately before the live audit and
again after audit plus evidence copying. All ten compared inputs were identical:

| Live input | SHA-256 before and after | Equal |
|---|---|---:|
| `WeiDU.log` | `ac8f36cd73a444be0311f4979d343ab9bbed589b80a1203c785ba310469ea75f` | yes |
| `lang\en_US\dialog.tlk` | `2daba5da0ac6810149e037c2f6d9cea8b72c8ad3ed0fa2e98c205bc749a67d51` | yes |
| `override\spell.ids` | `ec61787577644d662885489d2e72293e9306c24c63b9fbf8a0e6330a0a003fdf` | yes |
| `override\SPWI611.spl` | `a230b85a361f8d3c2f6e4eb0717cfa43f275ad15f8ed629182663ca790c3521c` | yes |
| `override\SPWI708.spl` | `e1888af2c41368389ee388bbf3b3c20e73559f00eb978ec913a71fc0eb09d5d3` | yes |
| `override\SPWI808.spl` | `993d5d598b24fffda5ca65ace27f6b7376c759b0a1aa6eeaf42bee6f2f98ad28` | yes |
| `override\SPWI907.spl` | `024c77beafed4cd7b8d7e3188c1bd719426695a99f1d0f2bdfc27dc2d18a347f` | yes |
| `override\dw#mg14.bcs` | `993417a24d3a216f81ecb97c19f03ecf6b471b1c06fa94e7f2042d7231e9f43e` | yes |
| `override\dw#mg144.bcs` | `4dc0a804eb96e2bf5f81ed9ab954cbd205b01bdb1fc6b03bf0e60679416f4505` | yes |
| `override\dw#mg148.bcs` | `faed6ac12dcae02128ee3b9d0aab41fb8414220f32682cf5fd9b34cb297e7e2d` | yes |

No file was created or changed in the active game. The only persistent copies are the seven
explicit evidence files in this repository; audit reports were written outside the game.

## Repair boundary carried into implementation

1. Resolve all four relevant spell symbols through the install's `spell.ids`; never hardcode
   `SPWI808` or 2808 in production.
2. Classify genuine weapon protection from reachable, self-applicable opcode-120 effects,
   never from the name or detectable-state marker.
3. Preflight the full SPL/script plan before any mutation.
4. If the mapped Improved Mantle is already a genuine protection in a future SR version,
   component 120 is a no-op.
5. Preserve Moment of Prescience's gameplay effects, level, school, text, and unrelated
   metadata. Priority states are retained or removed only from the separately proven
   installed counter semantics; false weapon metadata and allowlisted SCS contexts remain
   the sole repair scope.
6. Keep dragons and broader SCS AI redesign out of this component.

## Implemented component 120

The public WeiDU component is designated **120** with label
`cbr_scs_sr_weapon_protection_semantics`. It requires BG2:EE/EET, SCS Smarter Mages 6030,
the final loose SCS `SPELL.IDS`, every required symbolic mapping, and the installed SR alias
where Improved Mantle and Moment of Prescience share a spell number. Missing target mods
therefore `REQUIRE_PREDICATE`-skip; malformed mapped resources fail before mutation.

The alias predicate deliberately does not pretend to prove spell mechanics. The shared
semantic classifier remains authoritative: if the aliased spell has gained a genuine,
deterministic self-applied opcode-120 protection in a future SR version, installation is a
byte-no-op and reports zero changes.

For the current proven mismatch, the component prints one summary containing exact metadata,
first-round, renewal, chain-contingency, unknown-shape, and replacement counts. Its public
synthetic-game tests cover the current SCS/SR combination, absent SCS, absent SR aliasing, a
future restored Improved Mantle, an unknown target-like SCS block, reinstall byte stability,
and complete WeiDU uninstall restoration. Non-common-mage scripts such as `bheye.bcs` remain
outside the allowlist.

The compiled-block isolation technique is a minimal namespaced adaptation of DavidW's SCS
v35.21 `stratagems/sfo2e/alter_script.tph`; it is vendored so this tail component never loads
another installed mod's implementation at runtime. Spell Revisions and Moment of Prescience
are credited to Demivrgvs and the Gibberlings3 team. No active-game write or installation was
performed while implementing component 120.
