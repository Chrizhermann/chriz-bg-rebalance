# Apex Dragons (components 110 + 111) — design draft

**Status:** 2026-07-20 — lever decisions taken by the user in-session; §6 points resolved
same session (WK in; tier gating clarified against SCS's real tier ladder). Ready for an
implementation plan once the user green-lights the build. Research/evidence base:
`research/05-dragons.md`.

**Difficulty terminology (binding for all tier language below):** tiers refer to SCS's
**in-game per-category fine-tune panel** for Dragons — the `DMWW_dragon_difficulty`
GLOBAL — with the verified value map Basic=1 / Improved=2 / Tactical=3 / **Hardcore=5** /
**Insane=7** (see research/05 §4). Nothing here is an install-time choice: everything
installs; tiers activate and deactivate from the player's in-game setting, changeable
mid-game. The user currently plays Dragons at Hardcore ⇒ aura + component 111 are live
for the current playthrough; vorpal + HP arm when the Dragons category is flipped to
Insane in the SCS panel.

## 1. Decisions taken (user, 2026-07-20)

- **In:** vorpal claws (Insane tier), +25% flat HP (Insane tier), presence aura with
  **both** shreds (saves + elemental resistances), wing-buffet cadence relief
  (6s → 18s, separate component 111).
- **Explicitly not in v1:** APR ladder, AC/saves/MR tightening. The chosen profile makes
  dragons deadlier through magic pressure, breath, and fear-of-contact (vorpal) while
  staying killable — not through stat inflation. Revisit-able after the first Discord
  feedback round.
- **Deferred (user: "ToB content is already hard enough… discuss it more on Discord"):**
  Abazigal (`dragblue`), Tamah (`abazdg02`), and with them the Abazigal-lair dragons —
  Draconis (`bazdra02`), Fll'Yissetat (`bazdra03`) — plus SCS's `dw#ab*`/`dw#ysdra`
  escort dragons. Drop/XP changes stay untouched per the earlier thread decision.

## 2. Scope v1 (pending §6.2 confirmation)

SoA-reachable dragons: Firkraag (`firkra02`), generic red (`dragred` — note: SCS clones it
into Brimstone for the Fire Giant temple, ToB; script-level buffs propagate there),
Thaxll'ssillyia (`shadra01`), Nizidramanii'yt (`dragblac`), Hell dragons
(`hdragred`/`hdragsil`), Adalon (`udsilver`, flavor consistency — she fights only if
provoked), and the Watcher's Keep pair Saladrex (`gorsal`) + WK guardian (`fsdragon`).
WK straddles campaigns — flagged in §6.2.

## 3. Mechanism

Per `research/05-dragons.md` §5: `EXTEND_TOP` each installed dragon BCS with
once-per-tier, LOCALS-flagged blocks that `ApplySpellRES` the tier packages and
`Continue()`. Triggers mirror SCS's compiled **`DMWW_dragon_difficulty`** semantics
(explicit per-category value, game-slider fallback at 0) so the user's existing SCS
difficulty knob governs both layers. De-buff blocks mirror `dw#hprem` for mid-game
difficulty lowering. Retro-applies to already-spawned dragons on next load; no EEex; no
CRE stat writes; no edits to SCS AI logic (111's timer literal is the sole, clearly-scoped
exception).

### Tier packages

- **`cbrdrga` — presence aura (Hardcore and up):** script-driven pulse each round while
  hostile and in combat: hostile AoE (~30 ft) applying, per pulse, **save vs. breath or**
  −2 all saves and −25% fire/cold/electricity/acid resistances for 1 round (refreshing
  while you stay close; decays when you leave). Insane pulses upgrade to −4 saves /
  −40% resists. Magic resistance untouched (SR/SCS balance). Tuning check vs. cdtweaks
  #2312's existing high-level-caster save penalties in live testing.
- **`cbrdrgv` — vorpal claws (Insane):** melee-hit rider (op248 → subspell): ~5%
  probability window, kill effect behind a **save vs. death**, honoring Death Ward /
  death immunities (verify kill opcode 13 vs 55 semantics against IESDP at
  implementation). Floating text on trigger so deaths read as deliberate. Applies to the
  claw/bite weapon path used by the SCS-edited dragon weapons (`dragred1` etc.).
- **`cbrdrgh` — staying power (Insane):** +25% max HP **on top of** SCS's
  `dw#drahp` (which SETs 300% of base). Implementation constraint: dw#drahp's refresh
  loop re-applies a percentage-SET, so a naive flat add can be clobbered on refresh, and
  our spell must NOT share dw#drahp's cleanup MSECTYPE or its op221 sweep strips us.
  Candidate mechanisms (decide at implementation, live-verify either way): per-dragon
  install-time-computed flat adds re-asserted by the script block, or mirroring SCS's own
  op146 self-refresh idiom with a percentage-SET of 375%. Test: Firkraag on Insane reads
  ~690, not 552, after a difficulty flip-flop.

### Component 111 — wing-buffet cadence

`REPLACE_TEXTUALLY` on the installed dragon BCS files only, targeting the compiled
SetGlobalTimer **action** literal (`6 0 0 0 0"LOCALSBuffet"` in action context) → 18
seconds. The GlobalTimerNotExpired trigger lines have a different compiled shape and are
left alone. Optional and independent of 110; also read extracted `SPPR695` before deciding
whether spell-side softening (save/knockback) is warranted at all — frequency may suffice.

## 4. Compatibility & guardrails

As researched (`research/05` §6): SCS-layered via mirrored difficulty gating; Ascension
path irrelevant in v1 (deferred dragons); cdtweaks #3010 base-HP interaction handled by
the cbrdrgh mechanism choice; SR untouched except aura-resist sanity check; Randomiser
untouched; idempotent (marker-scan before EXTEND_TOP); `REQUIRE_PREDICATE` on SCS #6540
artifacts; tail-install after current log tail (408); live install only with explicit
user sign-off (active playthrough — buffs land on next load).

## 5. Testing

Per `research/05-dragons.md` §7: parse-check + synthetic-fixture install/uninstall
byte-exact tests; `parse_spl.py` re-dump of all tier spells (savetype non-zero wherever a
save is promised — repo rule); live protocol: spawn firkra02 at DMWW 0/3/5/7, verify tier
application/removal, aura pulse + per-pulse save, vorpal string + Death Ward immunity,
HP figure after difficulty flip-flop, retrofit on a save with a visited dragon area.

## 6. Resolved points (2026-07-20, same session)

1. **Tier gating:** stands as picked — vorpal + HP at Insane (7). The initial framing of
   this question confused SCS's script-block names with its player-facing tiers; after
   verifying the ladder (Hardcore=5 / Insane=7, research/05 §4) the picked gating is
   coherent: the user's current Hardcore game gets aura + buffet relief immediately, and
   flipping the Dragons category to Insane in SCS's in-game fine-tune panel arms
   vorpal + HP at any time, mid-game. A Hardcore-scaled vorpal (e.g. 3%) stays available
   as a Discord follow-up tweak, not a blocker.
2. **Watcher's Keep pair:** IN for v1 (user decision) — optional-superdungeon content,
   same "can be wild" category as Firkraag.
