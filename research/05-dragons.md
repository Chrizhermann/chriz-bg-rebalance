# Component 110 (proposed) — Apex Dragons: BG2 dragons stronger on high difficulties

**Status:** research complete 2026-07-20; design levers pending user decisions (asked
in-session). No code. Triage context: `docs/plans/2026-07-20-community-ideas-triage.md` §5.
All game-dir reads below were read-only per the standing directive.

## 1. Intent and constraints (Discord, 2026-07-13 → 07-20)

User: dragons "too weak", wants them stronger on high difficulties, "not sure how to buff
them"; meta-rule "we don't want a grind fest — more fun, maybe more replayable".
Community constraints the user endorsed: **no spammable wing buffet** (hard veto — "very
unfun"), **vorpal chance acceptable**, aura/save-shred direction OK but −50 resist / −4
saves needs taming, escorts idea deferred, **drops unchanged** (Carsomyr stays on
Firkraag), everything optional except Abazigal ⇒ Abazigal needs a fairness carve-out.

## 2. Verified installed baseline (2026-07-20)

`research/scripts/parse_cre.py` (new; offsets from the bg-modding skill CRE reference,
**self-checked** against `bdmorent.cre` = exactly the comp250-documented 112 HP / AC −1 /
THAC0 2 / APR 3 / saves 5,7,6,5,8 / MR 15 — parser trusted).

Post-SCS/cdtweaks override state (`HP  AC  THAC0  APR  saves(d/w/p/b/s)  MR  lvl`):

| Dragon | CRE | HP | AC | TH | APR | saves | MR | resists | lvl | XP |
|---|---|---|---|---|---|---|---|---|---|---|
| Firkraag (red) | firkra02 | 184 | −11 | 0 | 3 | 3/5/4/4/6 | 65 | fire 100 | 23 | 64k |
| generic red (Brimstone donor) | dragred | 184 | −11 | 0 | 3 | same | 65 | fire 100 | 23 | 24k |
| Saladrex (red, WK L5) | gorsal | 244 | −12 | 0 | 3 | 3/4/3/3/5 | 65 | fire 100 | 26 | 64k |
| WK guardian (green) | fsdragon | 234 | −10 | 0 | 3 | 3/5/4/4/6 | 55 | acid 50 | 24 | 62k |
| Fll'Yissetat (green) | bazdra03 | 280 | −8 | 0 | **5** | 2/2/2/2/4 | 55 | acid 100 | 24 | 60k |
| Draconis (brown) | bazdra02 | 190 | −10 | **14** | 3 | 3/3/4/4/4 | 55 | fire 50, acid 100 | 30 | 61k |
| Nizidramanii'yt (black) | dragblac | 200 | −12 | 0 | 4 | 3/5/4/4/6 | 45 | acid 100, F/C/E 20 | 23 | 52k |
| Hell dragon ×2 | hdragred/hdragsil | 184 | −12 | 0 | 4 | 3/5/4/4/6 | 60 | acid 100 | 23 | 22k |
| Adalon (silver) | udsilver | 254 | −11 | 0 | 3 | 3/5/4/4/6 | 60 | cold 100 | 23 | 54k |
| Thaxll'ssillyia (shadow) | shadra01 | 184 | −12 | 0 | 3 | 3/5/4/4/6 | 60 | cold 100 | 23 | 45k |
| Abazigal (blue, Ascension) | dragblue | **500** | −12 | 0 | 3 | 3/5/4/4/6 | 65 | elec 100, F/C/A 50 | 32 | 78k |
| Tamah (Ascension, psionic) | abazdg02 | 265 | −10 | 0 | 3 | 3/5/4/4/6 | 50 | all 50 | 25 | 29k |

Anomalies worth a look during implementation: **Draconis THAC0 14** (everyone else 0) and
class byte 1 (MAGE) — possibly deliberate SCS caster-form design, possibly a gap; verify
against SCS intent before "fixing". `dragred` is cloned by SCS's Fire Giants component into
Brimstone — script-level buffs on `dragred.bcs` propagate there; decide whether that's
wanted.

## 3. The SCS layer (what #6540 already does)

Source: `stratagems/dragon/dragon.tpa` + `ssl/` (game-dir copy, SCS 35.21).

- **Caster levels** (`level_all`): Firkraag 23, Saladrex 26, greens 24, blacks 23, Adalon
  23, Thax 23, Draconis 30, Abazigal 32. Full per-color spell kits (`add_spells=>...`),
  sequencers/triggers from `dragon/dragon_triggers.2da`, elemental immunity packages,
  anti-insect/poison for green/black.
- **Scripts**: `ssl_to_bcs` → installed `dragred/dragblac/draggre2/draggree/dragshad(→shadra01)/
  dragblac(→draghell)/gorsal/dragsilv` (+ `abazdrag`/`abazdg02` via
  `ascension/abazigal_dragon.tpa` since Ascension is present). Ascension path also defines
  Tamah (L25, psionics) and passes **`NoHitPointBoost=True` for Abazigal's script**.
- **Runtime difficulty ladder** (`ssl/dragonsetup.ssl`):
  - CorePlus: `ApplySpellRES("dw#innat")` — innate-casting package. Parsed
    (`parse_spl.py`): op221 stack-cleaner + **op101 immunity to opcodes 38/60/80** (silence
    / casting-failure family) + **op189 casting time −10**. Removed via `dw#inrem` below.
  - HardPlus: `ApplySpellRES("dw#drahp")` (LOCALS `staying_power` flag) — parsed: op221 +
    **op18 p1=300 p2=2 ⇒ max HP SET to 300% of base** + op146 delayed self-recast
    (refresh). Removed via `dw#hprem` on CoreMinus. Exemptions: IWD mode, Abazigal.
  - Insane: `BreathAccelerator` — zeroes the 12s `dragonbreath` cooldown each pass (50%
    per round), i.e. breath nearly every round.
- **Wing buffet** (`ssl/wingbuffet.ssl`): two blocks, shared LOCALS timer **"Buffet" = 6
  seconds (1 round)**: (a) cast whenever the party drops cloud spells; (b) whenever a
  second enemy stands within 12 ft — 50% per eligible round (double RESPONSE #100).
  In a melee party this is the every-other-round knockdown the Discord thread calls toxic.
  The compiled literal is directly visible in `override/dragred.bcs`
  (`6 0 0 0 0"LOCALSBuffet"`) — patchable per installed script via `REPLACE_TEXTUALLY`,
  no .baf sources involved.
- **Difficulty variable**: compiled scripts check GLOBAL **`DMWW_dragon_difficulty`**
  (observed comparisons 0–7; 0 = "follow the game slider" via `DifficultyGT` fallback,
  ≥1 = explicit per-category override from SCS's in-game menu).

## 4. The decisive install fact: the user already plays with the boosts ON

`Baldur.lua` (EET userdir, read-only 2026-07-20): game `Difficulty Level = 5`,
`Suppress Extra Difficulty Damage = 0`, and explicit SCS overrides including
**`DMWW_dragon_difficulty = 5`** (mage 4, fiends 5, spawns 7, …).

**SCS tier value mapping (verified 2026-07-20):** the per-category in-game fine-tune
panel uses Basic=1, Improved=2, Tactical=3, **Hardcore=5**, **Insane=7** (4/6 =
intermediate positions). Evidence: `lang/english/difficulty.tra` @1100–@1104 tier names;
@1113 ("a small number receive a boost to hit points") is the **Hardcore** description and
matches the compiled `dw#drahp` trigger set {5,6,7}; EasyMinus compiles to {1,2}, CorePlus
to {3..7} (`override/dragred.bcs`). Terminology note: SCS's script-side block names
(HardPlus etc.) do NOT match the player-facing tier names — always speak "Hardcore/Insane"
to the user, and mirror the compiled trigger sets verbatim rather than reasoning from
block names.

⇒ The user's dragons run at **Hardcore**: they already fight with **×3 max HP** (dw#drahp
active at 5) and the innate-casting package — and the user *still* reports them too weak. The
deficit is therefore **lethality and action-economy pressure, not HP**: THAC0 0 / APR 3 /
AC −8…−12 stop threatening endgame parties (AC −11 is trivially hit late; 3 attacks are
tank-able; the only pressure spikes are breath, buffet, and casting — and SCS's own
casting is already good). Design consequence: **buff offense/pressure, not sponge.**
More HP is the one lever SCS has already pulled hard.

## 5. Proposed design (levers for the design session)

**Delivery — comp250 pattern, adapted (recommended):** `EXTEND_TOP` each installed dragon
BCS with once-per-tier LOCALS-flagged blocks that `ApplySpellRES` our tier spells
(timing 1, dispel byte 2 — represents the dragon being tougher, not a strippable buff) and
`Continue()`. Trigger conditions **mirror SCS's own compiled `DMWW_dragon_difficulty`
semantics** (variable override with slider fallback) rather than raw `DifficultyGT` —
the user demonstrably tunes SCS per-category, and this keeps one knob governing both
layers. Properties: reaches **already-spawned dragons in the active playthrough** (scripts
re-resolve from override on load; CRE stat edits would not), zero interference with SCS AI
(orthogonal blocks, `Continue()`), no EEex dependency, idempotent via marker-comment
scan before extending, uninstallable by WeiDU backup. De-buff blocks (tier removal when
difficulty is lowered mid-game, mirroring `dw#hprem`) included for parity.

**Tier spells (numbers = starting proposal, to be tuned with the user):**

- **Tier 1 — SCS "Hardcore" (5) and up** (`cbrdrg1`): +1 APR (op1 cumulative), AC −2
  (op0), all saves +2 (op33–37), THAC0 left alone (already 0).
- **Tier 2 — SCS "Insane" (7), stacks** (`cbrdrg2`): +1 APR more (Firkraag ⇒ 5, Fll'Yissetat ⇒
  7), AC −2 more, saves +2 more, MR +10, and the two signature riders:
  - **Vorpal claws:** on-melee-hit rider (op248 → subspell), ~5% probability window,
    kill effect behind a **save vs. death** (bonus TBD, likely −0…−2), explicitly subject
    to Death Ward / death-immunity (verify kill opcode choice 13 vs 55 against IESDP at
    implementation; add a floating string so deaths read as deliberate).
  - **Presence aura:** repeating pulse each round on party members in ~30 ft; shape per
    user decision — saves-shred (−2 Hard / −4 Insane) vs. elemental-resist shred
    (IAIWE's original, tamed to −25) vs. both/none. Per-pulse save to resist, short
    duration so leaving the radius decays it. Must respect the existing stack: cdtweaks
    #2312 already penalizes saves vs. high-level casters; SR changes resist math.
- **HP:** none in T1/T2 by default (SCS ×3 active; grind-fest veto). Optional Insane-only
  +25% *flat* rider if the user wants it — implementation note: use op18 **p2=0 cumulative**,
  never a second p2=2 percentage-SET, to avoid last-writer-wins interaction with
  dw#drahp's refresh loop; live-verify stacking order regardless.
- **111 (separate optional component) — Wing-buffet cadence relief:** patch the compiled
  `SetGlobalTimer("Buffet","LOCALS",6)` literal → 18 (once per 3 rounds; or 12) in the
  installed dragon BCS files. Pure de-toxifier, independent of 110 so purists can skip.
  (SPPR695 itself is biffed — extract and read its save/knockback behavior during
  implementation before deciding whether spell-side softening is also warranted.)
- **Deferred:** escorts/adds (encounter design, overlaps SCS lair components), drop/XP
  rebalance (thread explicitly deferred), Draconis THAC0 anomaly (investigate separately).

**Abazigal & Tamah:** default proposal = Tier 1 only, no vorpal/aura (mandatory fight,
already Ascension+SCS-toughened at 500 HP, and SCS itself exempts him from the HP boost).
User decides: light tier / full treatment / excluded.

**Scope list v1:** firkra02, dragred(+Brimstone side effect), gorsal, fsdragon, bazdra03,
bazdra02, dragblac, hdragred, hdragsil, shadra01, udsilver (fights only if provoked —
buffing is pure flavor consistency), + per decision dragblue/abazdg02, + `dw#ab*`/`dw#ysdra`
escort dragons if present (SCS adds them in Ascension fights; `allow_missing` handling).
SoD's Morentherene stays in chriz-sod-remix (already done there).

## 6. Compatibility matrix

- **SCS:** layered via mirrored `DMWW_dragon_difficulty` gating; never edits dw# script
  content except the optional, clearly-scoped 111 timer literal; tier spells are additive
  effects, no `remove_spells`/AI changes. Re-running SCS would rebuild BCS and drop our
  extensions ⇒ standing "tail-install, never reinstall SCS" rule already covers this.
- **Ascension:** Abazigal/Tamah path detected via `abazdg02.cre` presence (same predicate
  SCS uses); component works with or without.
- **cdtweaks:** #3010 (max HP) is the base of dw#drahp's percentage — no interaction with
  our flat adds; #2312 factored into aura numbers.
- **SR:** spell kits unaffected; aura resist-shred option must be sanity-checked against
  SR resist stacking.
- **Item Randomiser:** untouched (no drop changes).
- **EEex:** not required (pure WeiDU/BCS/SPL component — works even if EEex is removed).
- **Idempotency/predicates:** `REQUIRE_PREDICATE` on SCS #6540 markers (e.g.
  `dragred.bcs` present + `dw#drahp.spl` present), per-dragon `allow_missing`-style
  skips, marker-string idempotency scan before each `EXTEND_TOP`.

## 7. Verification plan (implementation phase)

1. `--nogame` parse-check + synthetic-fixture install/uninstall byte-exact tests
   (repo `tests/` harness patterns).
2. Binary re-dump of tier SPLs with `parse_spl.py` (op18 modes, probability windows,
   save bits — the savetype≠0 rule from CLAUDE.md applies to the vorpal save).
3. Live (user-approved install only): console-spawn `firkra02` at DMWW 0/3/5/7,
   verify tier application order, APR via stat 8 double-sample (halves alternate),
   aura pulse on a party member, vorpal string on kill, buff removal when difficulty
   drops, and dw#drahp coexistence (HP reads ~552 not 300%+adds-lost).
4. Confirm already-spawned-dragon retrofit: load a save in a visited dragon area.
