# Tempus Holy Power: Artisan CLAB row packing

## Finding

The first clean EET 2.7 release-candidate install of component `401` against the curated
Artisan's Kitpack stack failed its `OHTEMPUS.2DA` preflight at `ABILITY1` level 2. The
effective table was valid: Artisan's proficiency infrastructure supplies `AP_C0PR#CL` at
every level and packs each grant into the first free `ABILITY*` row. Consequently,
`ABILITY1` contains `AP_C0PR#CL` at ordinary levels, while Holy Power levels retain their
strict `GA_OHTMPS1` cells and the level-25 symbol remains `AP_CDHLYSYM`.

This is compatible with the component's byte-surgical CLAB change. Component `401` clears
only late `GA_OHTMPS1` grants at levels 26, 31, 36, 41, and 46. It must preserve the
Artisan permission cells byte-for-byte.

## Narrow compatibility rule

At ordinary `ABILITY1` levels, accept only either `****` or exact `AP_C0PR#CL`. Keep every
existing special position strict:

- levels 1, 6, 11, 16, and 21 must be `GA_OHTMPS1`;
- level 25 must be `AP_CDHLYSYM`;
- levels 26, 31, 36, 41, and 46 must be either the complete original set of
  `GA_OHTMPS1` grants or the complete capped set of `****` cells; and
- any other nonempty token still fails closed.

The regression fixture reproduces Artisan's packed `ABILITY1` layout. Before the source
change it failed at level 2; afterward the full transformation succeeds, clears exactly the
five late Holy Power grants, and preserves every `AP_C0PR#CL` cell and all other bytes.

The complete Holy Power module then passed all 68 tests. In the isolated EET release
candidate, the previously rolled-back component `401` installed alone with exit code 0 and
no warnings/errors. The resulting `OHTEMPUS.2DA` retained the early grants and level-25
symbol, cleared exactly the five late grants, and contained `AP_C0PR#CL` exactly once at
every level 1–50 across `ABILITY1`–`ABILITY6` (SHA-256
`52F53F48191D4AB9B84CCC98C18A9FEC7CD44EE7A809646FC4FB394E28F28229`).

## Superseded by meaning-based ownership (2026-10-17)

The narrow rule above has been replaced, following the compatibility audit of
2026-10-08 (item 5). The component now owns only `GA_OHTMPS1` cells
(case-insensitive) in any row and at any level of a table with at least one level
column; the level is the data-column index. Uses are ordered by (level, row
order), the first five are kept, and every later one is replaced with `****` by
the same byte-surgical edit. `AP_CDHLYSYM`, `AP_C0PR#CL`, row names, table
width, and other mods' cells are no longer validated and stay byte-identical. A
table that is already at five uses or fewer stays untouched.

Retained refusals, each naming `OHTEMPUS.2DA`: no 2DA signature or missing
default/column-label lines; a `GA_OHTMPS1` beyond the columns the header
declares (whether the engine grants it is undefined); and a table with no
`GA_OHTMPS1` at all, because then the kit does not grant the Holy Power innate
this component caps, so the five-use result cannot be established. The packed
Artisan fixture above still produces the exact same bytes. Variation coverage
is in `tests/test_tempus_clab_variants.py`.
