# 07 — Component 407 spec-APR listener: runaway attacks-per-round (live bug, 2026-08-22)

**Symptom (user report, live playthrough):** Branwen (Cleric of Tempus, comp 407 installed
2026-07-20) shows attacks-per-round climbing 1.5 → 2 → 2.5 → … and snapping back to 1.5,
cycling rapidly whenever the game is unpaused.

**Verdict: component 407's design premise is wrong, not its code.** `M_CBRAPR.lua` does a
*relative* write (`m_nNumberOfAttacks += ½`) on every `EEex_Opcode_AddListsResolvedListener`
fire, assuming the hook fires once per *rebuild* of `CDerivedStats`. The hook actually fires
once per `CGameSprite::ProcessEffectList()` *pass* — and the engine only rebuilds the stats
on 1 of every 15 passes (or when an effect was added). On the other 14 passes the write lands
on the previous result and accumulates; the next rebuild resets it. The Lua stat write itself
works — the runaway is the proof.

## Evidence (static, from the live binary — no game launch needed)

Baldur.exe 2.6.6.0 (x64, ImageBase 0x140000000). Hook addresses recovered from
`InfinityLoader.db` (`CachedAddress`, INI-style text despite the `.db` name); function bounds
from the PE exception table; field names from EEex-Docs `CGameSprite`/`CDerivedStats`.

`CGameSprite::ProcessEffectList(this, bool)` = RVA `0x3AB390`–`0x3ADA0E`:

| RVA | What | Field |
|---|---|---|
| `0x3AB528` | `mov [rsi+0x4EA4], 0` | `m_bAllowEffectListCall = 0` (re-entrancy guard) |
| `0x3AB570`–`0x3AB585` | `m_id % 15 == [+0x3A0] % 15` ‖ `[+0x4BA4]` ‖ `[+0x4E44]` else **`je 0x3AD88F`** | slot test ‖ `m_newEffect` ‖ `m_bHPCONBonusTotalUpdate` → otherwise **fast path** |
| `0x3AB9B8` | `m_tempStats = m_derivedStats` (operator=) | snapshot of the previous stats |
| `0x3ABEB8` | `call CDerivedStats::Reload(&m_derivedStats, &m_baseStats, …)` | **the only rebuild** (EEex hook `…-CDerivedStats::Reload()` sits here) |
| `0x3ABF2B`… | equipped list, timed list applied into `m_derivedStats` | full path only |
| `0x3AD88F`–`0x3AD8B4` | fast path: tick `m_nEffectListCalls`, then `m_bAllowEffectListCall = 1` | **no Reload, no list application** |
| `0x3AD9BC` | `m_bAllowEffectListCall = 1` (restore) | both paths converge here |
| `0x3AD9D7` / `0x3AD9E0` / `0x3AD9E5` | EEex `AfterListsResolved-1/2/3` hooks | **fire on both paths**, flag already 1 |

CFG reachability (capstone over the whole function): all three hook sites are reachable from
the entry **without** executing the `Reload` call — via the `je 0x3AD88F` at `0x3AB585`.
EEex's own hook comment agrees: "once the engine permits the sprite's effect list to be
evaluated once again" — it is a per-pass hook, not a per-rebuild hook.

Consequences for any listener that writes derived stats:

- `sprite:getActiveStats()` returns `m_derivedStats` at hook time (flag = 1), i.e. the struct
  that is **reused unchanged** for ~14 passes. Relative writes accumulate; absolute writes
  are fine (they are simply re-applied).
- Cadence: one pass per AI tick per sprite; rebuild every 15th pass or when `m_newEffect`
  is set (effect added/expired, equipment change). With 1-s op272 pulses on the sprite (405's
  Divination toll, HouseTweaks' C0FSDROP on every CRE) rebuilds are frequent — hence the
  "snap back to 1.5" the user sees, and the cap at 5 (`cbrAprEncode` ceiling) in between.

Scripts: `scratchpad/disasm_pel.py`, `analyze2.py`, `analyze3.py` (session 2026-08-22; the
PE-exception-table + capstone recipe is the reusable part).

## Fix design

Make the write idempotent per rebuild by keying it to a marker that lives **in the same
`CDerivedStats` struct** and is cleared by `Reload`: a private spell-state bit.

- `CDerivedStats::m_spellStates` is `Array<unsigned int,8>` at +0xC88 (bit `id` = word
  `id/32`, mask `1<<(id%32)`; EEex.cpp `SetSpellState` uses exactly this packing). Spell
  states are rebuilt from scratch on every full pass (op328 re-applies them), so a bit we set
  after the bump is clear **iff** this pass rebuilt the stats.
- The Lua bindings expose `m_spellStates` with the Array `:get(i)` / `:set(i, v)` pair
  (EEex itself uses `m_buttonTypes:set(...)`), `GetSpellState(id)` for reads, and the bit
  helpers `EEex_BAnd/BOr/LShift` (LuaJIT — no `|`/`&` syntax in the file).
- Allocate `CBR_TEMPUS_SPEC_APR` in SPLSTATE.IDS (planned 242, free on the live install;
  243–246 are 401's) via the existing `cbr_find_or_allocate_splstate`, stamp the resolved
  value into the Lua next to the kit id (`%CBR_TEMPUS_SPEC_APR_STATE%`).
- Listener order: kit stat 152 → marker bit set? return → selected-slot/prof/pips gates →
  bump `m_derivedStats.m_nNumberOfAttacks` → set marker bit. Read and write the same struct
  (`sprite.m_derivedStats`, the one `Reload` targets), not `getActiveStats()`.
- Worst-case lag after a weapon swap that does not dirty the list: ≤ 1 rebuild (≤ 15 ticks);
  swaps that add/remove equipped effects dirty it immediately. Save-clean, zero residue on
  removal — the properties 407 was chosen for are preserved.

Rejected: per-sprite "last written value" cache (ambiguous when the fresh engine value
equals the previous bumped value — exactly the Holy Power tier-1 case); Lua-managed op1
effect (engine-native but persists in saves, needs refresh/removal bookkeeping and
re-entrancy care inside the hook); forcing `m_newEffect` each tick (15× effect processing).

## Delivery (live install rules: never uninstall mid-stack)

1. Fix the template `chriz-bg-rebalance/lua/M_CBRAPR.lua` + extend
   `lib/tempus_spec_apr_eeex.tpa` (second placeholder, SPLSTATE allocation). Fresh installs
   of 407 get the fixed listener.
2. New **tail component 409** `cbr_cleric_tempus_spec_apr_eeex_refresh`: re-runs the same
   LAF over the live `override/M_CBRAPR.lua` (+ SPLSTATE.IDS append); predicates: 407's
   artifact present. WeiDU-tracked; uninstalling 409 restores the v0.1.0 listener.
3. Tests (TDD): Lua simulation harness under EET's `lua.exe` (fake EEex API: scenarios
   rebuild→bump once, 14 fast passes→unchanged, rebuild→reset, baseline 1.5→2.0 under Holy
   Power, non-qualifying weapon→no write/no marker, fuse on missing `:set`); extend the
   --nogame harness + installer suite (407 fresh, 407→409 chain, byte-exact uninstall).
4. Game restart required after deployment (`M_*.lua` load at process start).
