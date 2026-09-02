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
