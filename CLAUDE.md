# chriz-bg-rebalance

SCS- and SR-adjacent balance adjustments + spell-behavior fixes for a heavily-modded
**BG2:EE + EET** install. Research/design-first; components ship as tail-install WeiDU mods.

## Scope boundaries (respect them)

- **This repo:** SCS adjustments (1xx), SR adjustments (2xx), cross-cutting spell audits (3xx).
- **NOT here:** SoD encounters/companions → `chriz-sod-rebalance`; consolidation of legacy
  fixes → `chriz-bg-modpack`; per-mod patches (Aura, Bardic Wonders, Kitpack) → their own
  `*-Chriz-Balance-Patch` repos.
- Credit upstream mods (SCS: DavidW, SR: Demivrgvs/G3) prominently; report genuine bugs
  upstream before/alongside fixing locally.

## Target install (READ-ONLY reference — user directive 2026-07-03)

- Game dir: `C:\Games\Baldur's Gate II Enhanced Edition modded\` — **reference only: not a
  testing ground, not a repo.** Read anything (WeiDU.log, override, mod sources); never
  write, install, or test there without the user's explicit sign-off in that conversation.
- Launched via `InfinityLoader.exe` (EEex). WeiDU v24600 `weidu.exe` in game dir;
  v24900 template = copy `Setup-Branwen.exe` as `Setup-<modname>.exe`.
- The user has an **active playthrough** — prefer changes that apply cleanly on next load.
- `gh` CLI auth is shared across concurrent agent sessions — check `gh auth status` before
  gh operations; this repo needs the `Chrizhermann` account.

## Inherited rules (follow exactly)

- **Never uninstall any WeiDU.log entry.** Fixes = direct `override` edits (hotfix, recorded
  in `research/`) OR new tail-install WeiDU mods appended after the current last log entry.
- **Never manually edit** `WeiDU.log`, `.dlg`, or `.baf` sources.
- All components must be **idempotent** (safe over a pre-applied hotfix) and guarded by
  `REQUIRE_PREDICATE` so they no-op gracefully on installs missing the target mod.
- Resolve mod-added spells **dynamically via `spell.ids` symbols** (e.g.
  `WIZARD_TELEKINETIC_STORM`), never hardcoded resrefs — SCS allocates slots at install time.
- Domain knowledge (WeiDU, IE formats, EEex, verified gotchas) lives in the `bg-modding`
  skill — invoke it when implementing. Key empirical layout: SPL ability `0x1E`=nFx,
  `0x20`=firstFxIdx (IESDP is wrong); effect savetype dword at fx+`0x24`
  (bit 0 = vs. spell, bit 24 = EE bypass mirror image), special at fx+`0x2C`
  (op12 bit 8 = save-for-half). **No save bits set ⇒ no save is rolled ⇒ flag is inert.**

## Conventions

- Component labels: `cbr_<area>_<name>` (mirrors chriz-bg-modpack's `cbm_`).
- Numbering: 100–199 SCS, 200–299 SR, 300–399 cross-cutting.
- Every component gets a `research/NN-*.md` diagnosis with binary evidence before code.
- Pristine pre-fix binaries → `research/originals/`.
