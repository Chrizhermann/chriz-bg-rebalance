# SCS weapon-semantics BCS fixtures

These are minimized, compiled BCS fixtures for component 120. They were generated with the
repository's WeiDU 24900 against the active install's IDS tables on 2026-08-29; compilation
wrote only this fixture directory. The active game's ten Task-1 control hashes were identical
before and after generation.

The target block in each of the first three files is byte-for-byte identical to a block in
the preserved installed script named below. Synthetic global-only sentinels surround the
live block, and the first-round / renewal fixtures retain the next real SCS Mantle fallback
block so tests can prove deleting the false candidate exposes rather than removes it.

| Fixture | SHA-256 | Exact installed target donor |
|---|---|---|
| `first_round.bcs` | `ce006369bb4d91a70efeffbc26a65323f2a004af822e3e8ec17e032d65da04cf` | `research/originals/dw#mg144.bcs.orig` |
| `renew.bcs` | `29898cbd182a2a9aff0ea8a6dec64083f6378b2897d2a9b5bced7a2eec3ff124` | `research/originals/dw#mg148.bcs.orig` |
| `chain_contingency.bcs` | `6e483114daf63063ed6665998748026e59906cf5ce4ad21bec51f90660f93824` | `research/originals/dw#mg14.bcs.orig` |
| `unrelated_mop.bcs` | `8144895116c8ed3d5b8566087d38b66d33b982a0129ee88a2e9577c4bd1774ee` | synthetic non-allowlisted controls |

`unrelated_mop.bcs` contains one ordinary Moment of Prescience use and one deliberately
near-matching `instantprep=2` block. Both must remain byte-identical; only the latter is
reported as an unknown target-like shape.

Tests create the minimum needed IDS tables in a temporary directory and decompile/recompile
these files under `--nogame --search-ids`. They never consult or mutate the active game.
