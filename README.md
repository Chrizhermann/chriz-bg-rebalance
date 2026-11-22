# BG Rebalance (`chriz-bg-rebalance`)

Gameplay balance adjustments, spell and item fixes, True Time Stop, Round Clock, and
class/kit revisions for **BG2:EE**, **EET**, **BG:EE/SoD**, and **IWD:EE** (**v0.8.12**).
Part of **[Chriz Easy BG](https://bg.chrizfader.org/collection)**.

**[Rules & Balance](https://bg.chrizfader.org/rules)** · **[Chriz Easy BG](https://bg.chrizfader.org/collection)** · **[Latest Release](https://github.com/Chrizhermann/chriz-bg-rebalance/releases/latest)**

---

## Part 1 — For Players

*BG Rebalance* refines rough edges on top of **Sword Coast Stratagems (SCS)** and
**Spell Revisions (SR)** while keeping their overall vision intact.

### Highlights

- **True Time Stop – fair Haste & Slow (`360`, EEex 2.7.3.0):**
  During Time Stop, frozen creatures' spell durations, poison, regeneration, and
  repeated effects pause and resume afterward with the time they had left. Engine
  Haste and Slow affect only actions, attacks, and movement — no faster poison or
  regeneration ticks. Also available standalone as `CBR_TRUE_TIMESTOP-v<version>-windows.zip`.
- **Round Clock (`361`, EEex 2.7.3.0 — BG:EE/SoD, BG2:EE/EET, IWD:EE):**
  Credits world-clock advances (map travel, rest, scripted jumps) toward spent
  spell/item aura, attack-round recovery, Hide in Shadows lockout, and contingency
  checks. A thief whose lockout expires can Stealth on the first paused frame.
  Also available standalone as `CBR_ROUND_CLOCK-v<version>-windows.zip`.
- **Spell & item balance (`200`–`340`):**
  - **Flail of the Ages (`302`):** Adds a save vs. breath against on-hit Slow (-2/-4/-6)
    and lets the +5 flail keep Free Action while allowing Haste and Improved Haste.
  - **Potion & Heroism uniqueness (`330`–`332`):** Caps temporary potion types to one
    active dose at a time (`331` exempts Potions of Genius) and keeps Heroism, Greater
    Heroism, and Potion of Heroism mutually exclusive.
  - **90% physical resistance cap (`310`, EEex):** Party physical resistance above 80%
    counts at half strength up to 90% (short 100% immunity spells stay at 100%).
  - **Damageable combat clouds (`320`):** Lowers cloud-form invulnerability to 75% resistance.
  - **SR anti-magic & Hardiness (`200`–`211`):** Restores vanilla 40%/30% physical-only
    Hardiness (`200`/`201`, optional +20% elemental `202`), bounds Pierce Magic MR reduction
    to 10–40 points for 5 rounds (`210`), and changes Spellstrike to 15% spell failure for 2 rounds (`211`).
  - **Chris Revisions (`340`) & Emotions (`301`):** Aid grants HP only, Luck 90s, Bless 30s + 1 rd/level
    (open to druids), Chaotic Commands open to druids, Prayer/Recitation non-stacking;
    Emotion Courage/Hope mutually exclusive (`301`).
  - **Bracers of Blinding Strike (`220`) & EET arrows (`130`):** Self-only SR Improved Haste
    on bracers; BG2-strength elemental arrows in EET.
- **SCS refinements & Apex Dragons (`100`–`121`):**
  Fixes Telekinetic Storm's missing save-for-half (`100`), restores five Adventurer's Mart
  Freedom scrolls (`101`), repairs false SR Improved Mantle script markers (`120`), adds
  honest EEex ambient caster readiness (`121`), and offers optional **Apex Dragons**
  with lethal claws/bites (`110`, chunking risk) and an 18s wing-buffet cooldown (`111`).
- **Class & kit revisions (`400`–`421`):**
  Druids gain axes & short bows (fighter/druids also long bows, `410`); Yeslick's Alaghor
  uses cleric weapons + axes with fighter/cleric limits (`411`, Artisan's Kitpack + EEex);
  EEex kit-specific bard spell progressions (`420`/`421`); and full **Cleric of Tempus**
  revisions (`400`–`409`).

### Standalone Downloads (`360` & `361`)

Don't need the full balance overhaul? Two standalone installers ship in
[Latest Release](https://github.com/Chrizhermann/chriz-bg-rebalance/releases/latest)
for games with **EEex (`2.7.3.0`)**:

- **`CBR_TRUE_TIMESTOP-v<version>-windows.zip`** — Standalone component `360`
  (True Time Stop – fair Haste & Slow for BG2:EE / EET).
- **`CBR_ROUND_CLOCK-v<version>-windows.zip`** — Standalone component `361`
  (Round Clock for BG:EE / SoD, BG2:EE / EET, and IWD:EE).

Install either standalone package *or* the matching component in the full installer
(each refuses while the other is installed).

### Quick Install

1. Close the game and any mod manager using the game directory.
2. Download the full `chriz-bg-rebalance` ZIP (or standalone `CBR_TRUE_TIMESTOP` /
   `CBR_ROUND_CLOCK` ZIP) from [Latest Release](https://github.com/Chrizhermann/chriz-bg-rebalance/releases/latest)
   and extract it into your modded game folder containing `chitin.key`.
3. Run `Setup-chriz-bg-rebalance.exe` (or use the standalone setup EXE), or run via CLI:
   ```text
   ./Setup-chriz-bg-rebalance.exe --force-install-list 401 301 --language 0 --no-exit-pause
   ```
4. Launch through `InfinityLoader.exe` when EEex components are installed.

---

## Part 2 — Component Reference, Load Order & Technical Details

### Component Table (`100`–`421`)

| # | Group | Component |
|---|---|---|
| 100 | SCS adjustments | Telekinetic Storm: restore save vs. spell for half damage (+ bypass Mirror Image) |
| 101 | SCS adjustments | Restore five Freedom scrolls to the Adventurer's Mart (`ribald.sto`) |
| 110 | SCS adjustments | EEex Apex Dragons: lethal claws and bites (can cause permanent death) |
| 111 | SCS adjustments | Five dragon encounters: 18-second wing-buffet cooldown |
| 120 | SCS adjustments | Repair false SCS / SR Improved Mantle weapon-protection semantics |
| 121 | SCS adjustments | EEex ambient caster readiness + one honest first-contact defense |
| 130 | SCS adjustments | EET elemental arrows: BG2-strength acid, cold, and fire damage |
| 200 / 201 | SR adjustments | Hardiness: 40% (recommended) / 30% physical resistance only |
| 202 | SR adjustments | Hardiness: optional extra 20% elemental & magic damage resistance (requires `200`/`201`) |
| 210 | SR adjustments | EEex Pierce Magic: halve MR, bounded 10–40 points, for five rounds |
| 211 | SR adjustments | Spellstrike: 15% arcane/divine spell failure for two rounds |
| 220 | SR adjustments | Bracers of Blinding Strike: self-only SR Improved Haste |
| 301 | Cross-cutting | Emotion, Courage / Emotion, Hope — mutually exclusive beneficial emotions |
| 302 | Cross-cutting | Flail of the Ages: save vs. breath against Slow; +5 allows Haste |
| 310 | Cross-cutting | EEex party physical resistance: half above 80%, 90% max (short immunities stay 100%) |
| 320 | Cross-cutting | Combat clouds: 75% damage resistance instead of invulnerability |
| 330 / 331 | Cross-cutting | Potion uniqueness: one active dose per type (`331` exempts Potions of Genius) |
| 332 | Cross-cutting | Heroism family: Heroism, Greater Heroism, and Potion of Heroism do not combine |
| 340 | Cross-cutting | Chris Revisions: Aid, Luck, Bless, Chaotic Commands, Prayer & Recitation |
| 360 | Cross-cutting | EEex True Time Stop – fair Haste & Slow (2.7.3.0; standalone ZIP available) |
| 361 | Cross-cutting | EEex Round Clock: credit world-time jumps toward personal cooldowns (standalone ZIP available) |
| 400–409 | Class & kit | Cleric of Tempus: weapon training (`400`), Holy Power (`401`–`403`), Chaos of Battle (`404`), Divination toll (`405`), specialization APR (`406`/`407`/`409`), descriptions (`408`) |
| 410 | Class & kit | Druids: axes & short bows; fighter/druids also long bows |
| 411 | Class & kit | Alaghor of Clangeddin (Yeslick): cleric weapons + axes (Artisan's Kitpack + EEex) |
| 420 / 421 | Class & kit | EEex kit spell-progression provider (`420`) & Bard IWD7 / Blade & Skald vanilla6 (`421`) |

> Tail patches for existing stacks also live under `live-patch/` (`CBR_SR_HARDINESS`,
> `CBR_SR_ANTIMAGIC` incl. texts-only `212`/`213`, `CBR_TRUE_TIMESTOP`, `CBR_ROUND_CLOCK`).

### Load Order, Uninstall & We Overwrite Policy

- **Install order:** Install as a **tail mod** after SCS, Spell Revisions, IWDification,
  Artisan's Kitpack, Yeslick NPC, and other spell/item/kit mods. Place `120` before `121`,
  and `420` → `421` → Bardic Wonders Balance Patch `3010`.
- **Uninstall:** Normal WeiDU uninstall works cleanly (remove tail components cleanly via
  `Setup-chriz-bg-rebalance.exe`, which restores files from `weidu_external/backup/chriz-bg-rebalance`).
  Avoid adding or removing runtime hooks (`360`) mid-playthrough.
- **We Overwrite:** Every component writes its decided result directly over edited values,
  descriptions, effect counts, or other mods' changes (`AGENTS.md`). SCS and SR are optional
  unless a feature truly requires them; missing optional targets are logged individually.

### Detailed Reference & Research

- **[Detailed Component & Engine Reference](docs/components-reference.md)** — full per-component mechanics, standalone packages, and validation boundaries
- **[Project Scope](docs/00-project-scope.md)** · **[Research Notes](research/)** · **[Changelog](CHANGELOG.md)**

### Credits

- **[Sword Coast Stratagems (SCS)](https://github.com/Gibberlings3/SwordCoastStratagems)** by DavidW — AI, dragon, and spell baseline
- **[Spell Revisions (SR)](https://github.com/Gibberlings3/SpellRevisions)** by Demivrgvs & Gibberlings3 — spell system foundation
- **[EEex](https://github.com/Bubb13/EEex)** by Bubb — 64-bit engine hooks and runtime extensions
- **[IWDification](https://github.com/Gibberlings3/iwdification)** by CamDawg & contributors — Emotion spell and scroll design precedent

## License

First-party code, WeiDU libraries, and documentation are licensed under the **[MIT License](LICENSE)**
(`Copyright (c) 2026 Christopher Hermann`). Third-party mods are **not** bundled. The included
**WeiDU 249.00** installer is distributed under GNU GPL v2 (see [WEIDU-LICENSE.txt](WEIDU-LICENSE.txt)
and [WeiDU source](https://github.com/WeiDUorg/weidu/tree/v249.00)).
