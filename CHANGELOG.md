# Changelog

## v0.3.2 — 2026-09-07

- Fix component 401 on installations without Spell Revisions when Improved Haste
  delegates its doubling effect through opcode 146. Validate every child header,
  preserve both spells, and reject unsafe or ambiguous delivery.
- Recognize the existing non-SR Divine Power cleanup prefix and upgrade it to the
  Tempus cleanup while preserving its self-refresh and unrelated effects.
- Retain direct SR/additive and non-SR/doubling support, including opcode 317.
  SCS and Spell Revisions are optional for the Holy Power component family.
- Add captured base-game and SCS/no-SR regression fixtures, graph validation,
  override/KEY lookup, byte-exact rollback, and repeat-application coverage.

Validation: 281 automated tests pass with WeiDU 24900. Full installation tests use
captured resources in disposable synthetic games; live playthrough acceptance and
collection installation recovery remain separate.

## v0.3.1 — 2026-09-04

- Accept Artisan's legitimate `AP_C0PR#CL` grants in ordinary Tempus CLAB cells,
  preserving those grants while capping the late Holy Power uses.
