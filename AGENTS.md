# chriz-bg-rebalance

SCS- and SR-adjacent balance adjustments + spell-behavior fixes for a heavily-modded
**BG2:EE + EET** install. Research/design-first; components ship as tail-install WeiDU mods.

## Scope boundaries (respect them)

- **This repo:** SCS adjustments (1xx), SR adjustments (2xx), cross-cutting spell audits (3xx),
  **class/kit revisions of base-game and SoD kits (4xx — e.g. the Cleric of Tempus rework 400–409).**
  Reworking an existing kit is balance work and belongs here; *adding* new kits does not
  (no kitpack repo exists — create one only if that ever becomes a goal).
- **NOT here:** SoD encounters/companions → `chriz-sod-rebalance`; consolidation of legacy
  fixes → `chriz-bg-modpack`; per-mod patches (Aura, Bardic Wonders, Kitpack) → their own
  `*-Chriz-Balance-Patch` repos.
- Credit upstream mods (SCS: DavidW, SR: Demivrgvs/G3) prominently; report genuine bugs
  upstream before/alongside fixing locally.

## We overwrite

The mandatory game-modding policy **We overwrite** (2026-11-07) takes precedence
over older guidance, comments, plans, handovers and research in this repository.
Write our decided fields, effects and complete descriptions regardless of old
content; create what this mod supplies. Game data must never fail, warn, roll back
or silently veto a decided change. Missing optional targets and unreadable files
cost only that target, with a log line. Keep genuine game/EEex requirements, native
hook signatures, PC protection and our own component choices; mod versions are
never requirements. Runtime diagnostics belong only in the log.

Historical documents record earlier designs and evidence, not exceptions to this
policy. In particular, old instructions to require SR/SCS footprints, validate old
values or text, reject changed layouts, or disable a listener permanently because
of game data are superseded. Keep their historical test results labelled as such.

## Target install (read-only reference)

- A reference game is **not a testing ground or a repository.** Read its log,
  override and mod sources; never
  write, install, or test there without the user's explicit sign-off in that conversation.
- Target the newest official engine supported by EEex. Historical engine captures
  establish only the evidence explicitly recorded for them. Use standalone WeiDU
  249 and disposable game fixtures for offline installer tests.
- The user has an **active playthrough** — prefer changes that apply cleanly on next load.
- `gh` CLI auth is shared across concurrent agent sessions — check `gh auth status` before
  gh operations; this repo needs the `Chrizhermann` account.

## Inherited rules (follow exactly)

- **Never uninstall any WeiDU.log entry.** Fixes = direct `override` edits (hotfix, recorded
  in `research/`) OR new tail-install WeiDU mods appended after the current last log entry.
- **Never manually edit** `WeiDU.log`, `.dlg`, or `.baf` sources.
- Components must be **idempotent**, including over edited resources. SCS and SR
  are optional unless the feature truly needs them; test the actual capability,
  not an installation footprint. Apply independent targets independently.
- Resolve mod-added spells **dynamically via `spell.ids` symbols** (e.g.
  `WIZARD_TELEKINETIC_STORM`), never hardcoded resrefs — SCS allocates slots at install time.
- Domain knowledge (WeiDU, IE formats, EEex, verified gotchas) lives in the `bg-modding`
  skill — invoke it when implementing. Key empirical layout: SPL ability `0x1E`=nFx,
  `0x20`=firstFxIdx (IESDP is wrong); effect savetype dword at fx+`0x24`
  (bit 0 = vs. spell, bit 24 = EE bypass mirror image), special at fx+`0x2C`
  (op12 bit 8 = save-for-half). **No save bits set ⇒ no save is rolled ⇒ flag is inert.**

## Conventions

- Component labels: `cbr_<area>_<name>` (mirrors chriz-bg-modpack's `cbm_`).
- Numbering: 100–199 SCS, 200–299 SR, 300–399 cross-cutting, 400–499 class/kit revisions.
- Every component gets a `research/NN-*.md` diagnosis with binary evidence before code.
- Pristine pre-fix binaries → `research/originals/`.

## Validation

- Use `python -m unittest discover -s tests -q` for the full offline suite; set
  TEMP/TMP to a disposable directory inside the worktree and CBR_LUA to a standalone
  Lua executable when needed. Never run these tools from a reference game.
- Cover changed values/text, missing and extra effects, base-game and modded input,
  and repeat application. Assert the decided output and no installation warnings.
- Native-hook signature tests and offline assertions of our output remain useful.
  Automated evidence does not establish live gameplay acceptance.
- Leave releases, live-game/save writes and git publishing to explicit authorization.
