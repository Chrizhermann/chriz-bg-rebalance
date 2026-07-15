# Research 04 — installed Cleric of Tempus Holy Power resources

**Date:** 2026-07-16 · **Status:** exact pre-component evidence captured · **Live game:**
read-only

This records the final effective resources that components 401–403 must patch. The active
installation was used only as a read source. No live WeiDU command was run and nothing was
written to the game directory.

## Preserved artifacts

The source root for this snapshot is
`C:\Games\Baldur's Gate II Enhanced Edition modded`. Modification times are UTC snapshot
evidence, not future install predicates or test requirements. For the biffed resource, the
time is the containing BIF's time because a BIF member has no independent filesystem time.

| Captured file | Effective source | Source modified (UTC) | Resource size | SHA-256 |
|---|---|---:|---:|---|
| `originals/OHTMPS1.spl.orig` | `chitin.key` → `DATA/PATCH25.BIF` | `2026-02-07T16:15:58.6008646Z` | 13,394 | `abd47abfa923196f7c25332a5bc9518ceb08458b0a0bfa25a85fa3be1e1d70ef` |
| `originals/OHTEMPUS.2da.orig` | `override/OHTEMPUS.2da` | `2026-02-11T17:04:31.5987630Z` | 40,401 | `84fc365814c45d323220ad9760b6bbf45f0d9072f583899ab879ba06f2600d98` |
| `originals/SPPR412.spl.orig` | `override/SPPR412.spl` | `2026-02-12T16:05:39.3953026Z` | 10,754 | `c2db73888707428cb8f0abb68faa1f6393b98ec37fa0ac814a36428a72cf7062` |
| `originals/SPWI613.spl.orig` | `override/SPWI613.spl` | `2026-02-11T16:56:47.4423217Z` | 1,210 | `67443841399a7e67020cc5e02fb87d198caa582ea88dc23dca6f60fe2e07e028` |

`OHTMPS1` was extracted with the repository-owned
`research/scripts/extract_key_resource.py`; the three effective override files were copied
with `Copy-Item` directly to the paths above. The copied files re-hash to the values in the
table.

## KEY/BIFF resolution for OHTMPS1

The extractor independently resolved and validated this chain:

- `chitin.key`: KEY V1, 1,184,486 bytes, modified
  `2026-02-11T17:19:03.4564497Z`, SHA-256
  `573383bc152c1b0357e25ae3a49058ea5e6b7a465354e46d1684758c0757a734`;
- KEY resource entry **33414**: `OHTMPS1`, type 1006 (`SPL`), locator
  **`0x01000035`**;
- the locator high bits, `0x01000035 >> 20`, select BIF index **16**;
- the locator low 20 bits, `0x01000035 & 0xFFFFF`, select variable resource
  index **`0x35`**;
- KEY BIF entry 16 names `data\Patch25.bif` (`DATA/PATCH25.BIF` on this
  case-insensitive installation);
- `PATCH25.BIF`: BIFF V1, 111 variable resources, no fixed resources, 17,396,564
  bytes, modified `2026-02-07T16:15:58.6008646Z`, SHA-256
  `eb4340f6d0628a761ff16c5383c49e36d87b4c071e81fd9ac5ccadb9518b6d6e`;
- its variable entry stores the low locator **`0x35`**, not the full KEY locator;
- the payload begins at **`0x5EAA08`**, is **13,394** bytes, and hashes to
  **`abd47abfa923196f7c25332a5bc9518ceb08458b0a0bfa25a85fa3be1e1d70ef`**.

The extractor requires explicit `--key`, `--game-root`, `--resref`, `--type`, and
`--output` arguments. It does not synthesize an output name. Existing output is refused
unless `--expected-sha256` matches the payload that would be written.

## Symbolic spell resolution

The final `override/SPELL.IDS` contains:

| IDS value | Symbol | Effective resref | Displayed spell |
|---:|---|---|---|
| 1412 | `CLERIC_HOLY_POWER` | `SPPR412` | Divine Power |
| 2613 | `WIZARD_IMPROVED_HASTE` | `SPWI613` | Improved Haste |

Spell Revisions exposes **Divine Power through `CLERIC_HOLY_POWER`**. There is no
`CLERIC_DIVINE_POWER` entry in the final `SPELL.IDS`; code must not look for that
nonexistent symbol. `OHTEMPUS.2DA` grants the kit innate directly as `GA_OHTMPS1`.

## Parsed live layout

All SPL summaries below use the empirical SPL V1 ability offsets `nFx @ 0x1E` and
`firstFxIdx @ 0x20`.

### OHTMPS1 — current Tempus Holy Power

- SPL V1, ability table `0x72`, effect table `0x392`, no casting features.
- Exactly 20 self-targeted headers, minimum levels 1 through 20. Every header uses
  projectile 255 and owns 13 effects.
- Each header starts with instant opcode 321 removals of `OHTMPS1` and `SPPR412`.
- For header level `L`, timed opcode 54 flat-sets THAC0 to `21 - L`; opcode 18 grants
  `L` maximum/current temporary HP cumulatively; opcodes 44 and 97 flat-set Strength to
  18 and the exceptional bonus to 100, i.e. 18/00 even when that lowers an existing
  score.
- The remaining installed package is the visual/icon and compatibility material:
  opcodes 141 and 50, portrait icon opcode 142 with icon 60, opcode 328 states 68 and 9,
  opcode 282 (`p1=3`, `p2=5`), and delayed opcode 174 using `EFF_E03`.
- Timed effects last `6 * L` seconds. Level 1 therefore lasts 6 seconds and level 20
  lasts 120 seconds.
- The embedded SPL effects, including both opcode 321 removals, use
  `resist_dispel=3`.
- Above level 20 the engine continues selecting the level-20 header. THAC0, temporary
  HP, and duration therefore freeze at 1, 20, and 120 seconds respectively.

The current exclusion is one-way: casting `OHTMPS1` removes `SPPR412`, but the preserved
final `SPPR412` described next removes only itself.

### SPPR412 — final Spell Revisions Divine Power

- SPL V1, ability table `0x72`, effect table `0x2A2`, no casting features.
- Fourteen self-targeted, projectile-255 headers with minimum levels
  `[1, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]`; each has 15 effects.
  The minimum-level-1 header carries the level-7 mechanic values and serves levels 1–7.
- Each header begins with opcode 321 removing `SPPR412`; that administrative removal uses
  `resist_dispel=0`, while the timed mechanics use `resist_dispel=3`. **No header removes
  `OHTMPS1`**, which is the live Divine-Power-after-Holy-Power stacking hole.
- The timed mechanics retain fighter THAC0 (opcode 54), temporary HP (18), flat 18/00
  Strength (44/97), the installed VFX/icon package (141/50/142/174), states 9 and 68
  (328), and opcode 282. The mechanics run from 42 seconds at the first header to 120
  seconds at level 20; opcode 50 is a separate two-second visual.
- Every header ends with three conditional opcode 177 applications. Levels through 12
  reference `SPPR412A`; level 13 onward references `SPPR412B`. These final compatibility
  effects are part of the post-mod resource and must be preserved.

`SPPR412A.EFF` and `SPPR412B.EFF` are standalone EFF V2 resources. EFF V2 does **not**
have the SPL V1 `resist_dispel` byte at offset `0x5C`; therefore this audit deliberately
makes no `dr0` claim about either EFF. The `resist_dispel` observations above apply only
to the effects embedded in the captured SPL V1 file.

### SPWI613 — final Spell Revisions Improved Haste

- SPL V1, one header at minimum level 1, area target 4, projectile 158, 22 effects,
  and a 60-second timed package.
- Its APR mechanic is timed opcode 1, `p1=1`, `p2=0`: one cumulative attack per round.
- It has **no opcode 16 or 317** and therefore is additive, not true-Haste doubling, in
  this installed layout.
- A later compatibility addition is present as instant opcode 221 (`p1=9`, `p2=21`).
- The final file also retains movement opcode 176, +2 THAC0/AC/breath-save effects,
  VFX/icon effects, opcode 101, and ten opcode 206 protections including `SPWI613`
  itself. This exact post-mod file—not a Spell Revisions source copy—is the fixture to
  preserve and patch surgically.

### OHTEMPUS.2DA — final Tempus CLAB

The captured table has 50 level columns and 65 data rows, including domain/spell grants,
proficiency rows, and other mod-added material. Its exact `ABILITY1` cells are:

- `GA_OHTMPS1` at levels **1, 6, 11, 16, 21, 26, 31, 36, 41, and 46**;
- unrelated `AP_CDHLYSYM` at level **25**; and
- `****` in the other `ABILITY1` cells.

Later implementation must remove only the five `GA_OHTMPS1` cells at levels 26, 31, 36,
41, and 46. It must preserve the first five grants, level-25 `AP_CDHLYSYM`, every other
row, and all unrelated cells rather than replacing the table wholesale.

## Read-only capture proof

These files were hashed immediately before and after extraction/copy. Every pair is
byte-identical; modification time and size were also unchanged. The effective language
for this install is `en_US`, so that is the `dialog.tlk` checked here.

| Live file | SHA-256 before | SHA-256 after | Equal |
|---|---|---|:---:|
| `lang/en_US/dialog.tlk` | `ccce159174614a41d8bd845496e590c061e1e7f5d43e683ff2d472109ca25089` | `ccce159174614a41d8bd845496e590c061e1e7f5d43e683ff2d472109ca25089` | yes |
| `WeiDU.log` | `bcea63fa0ca8883ba015fd674819c561ae28dcb41a054d9a2ab2992fdca3939f` | `bcea63fa0ca8883ba015fd674819c561ae28dcb41a054d9a2ab2992fdca3939f` | yes |
| `override/OHTEMPUS.2da` | `84fc365814c45d323220ad9760b6bbf45f0d9072f583899ab879ba06f2600d98` | `84fc365814c45d323220ad9760b6bbf45f0d9072f583899ab879ba06f2600d98` | yes |
| `override/SPPR412.spl` | `c2db73888707428cb8f0abb68faa1f6393b98ec37fa0ac814a36428a72cf7062` | `c2db73888707428cb8f0abb68faa1f6393b98ec37fa0ac814a36428a72cf7062` | yes |
| `override/SPWI613.spl` | `67443841399a7e67020cc5e02fb87d198caa582ea88dc23dca6f60fe2e07e028` | `67443841399a7e67020cc5e02fb87d198caa582ea88dc23dca6f60fe2e07e028` | yes |

No live save, override file, KEY/BIF, TLK, or WeiDU state was changed during capture.
