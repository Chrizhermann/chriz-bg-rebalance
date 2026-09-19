# Bard progression: quick 2.7.3 playtest

The user reported a successful BG2EE/EET check on 2026-09-20 ("Works great").
This records the quick acceptance scope, not an exhaustive kit compatibility test.
IWDEE support has executable and offline checks; its in-game check remains open.

## Install

Use Windows BG2EE/EET or IWDEE with compatible EEex, launched through InfinityLoader.
The provider's native layout is verified on **2.7.3.0**; **EEex 1.2 or 1.3** supplies
the required APIs. Installation checks the actual capabilities and hook instructions.
Install the kits and their other tweaks first, then:

1. `setup-chriz-bg-rebalance.tp2` component **420** (shared provider).
2. The same installer, component **421** (base Bard/Jester/Blade/Skald policy).
3. `BardicWonders/Setup-BardicWonders.tp2` component **3010** (optional Artisan bard integration).

Standalone users may omit 421 when they want only the custom Bardic Wonders mappings.
No SCS, SR, collection, or other rebalance components are prerequisites. Darkbloom
is optional: the adapter skips it when absent and assigns IWD8 when present. Its
separate imported-spell issue under SR does not gate this progression component.
Close the game during installation.
The provider deliberately rejects an executable whose verified hook bytes do not match.

Installed on 2026-09-20 in `C:\BG-EET-RC-20260903\game` in the order above. Its
existing EEex 1.2 supplies all required APIs; no EEex upgrade was needed. The installed
CDTweaks table remains byte-for-byte unchanged. Darkbloom is absent from this installation.
The user subsequently confirmed that this installation works. The IWDEE portability
changes were made in source only; that working BG installation was not changed again.

## Check

Use disposable characters/saves for a Bard, Blade or Skald, and Kapellmeister. Dancer
is a useful fourth check because it combines the vanilla table with a slot penalty.
For the BG test installation, give each **5,000,000 total XP** and complete level-up.
Its inspected bard XP table puts this at **level 32**; eighth-level spells become
available at bard level 29. On IWDEE or another XP/level-cap setup, use the displayed
bard level and the corresponding progression row; do not assume that XP produces
level 32 everywhere. Level 29 or higher suffices to check the eighth-level unlock.

Inspect the wizard spellbook. Remove bonus-slot equipment and avoid extra-slot HLAs
when comparing exact counts. Expected level-32 capacities, including ordinary kit
slot modifiers:

| Kit | Spell levels 1–9 |
| --- | --- |
| Bard / Jester | 6, 6, 6, 6, 6, 5, 5, 0, 0 |
| Blade / Skald | 5, 5, 5, 5, 5, 4, 0, 0, 0 |
| Dancer | 4, 4, 4, 4, 4, 3, 0, 0, 0 |
| Kapellmeister | 8, 8, 8, 8, 8, 7, 7, 3, 0 |
| Darkbloom, if installed | 7, 7, 7, 7, 7, 6, 6, 2, 0 |

The tables grant capacity, not spell knowledge. Learn a suitable spell if necessary
to inspect/use a higher tier. Memorizing, resting and casting one seventh/eighth-level
spell is a useful brief follow-up to the visible-slot check.

The runtime logs `CBR bard progression: active (...)` in EEex's output. The Lua value
`CBRSpellProgression.Status` gives the same status, and
`CBRSpellProgression.GetBaseSlots(kitID, level, spellLevel)` is a read-only diagnostic
that excludes bonus slots.

Existing saves receive the normal new table calculation when leveling up. This build
does not force a migration or refill spent spells on load. Kapellmeister's separate
Song of Universal Harmony can still offer ninth-level spells; that is not a failure
of the eighth-level normal spellbook cap.
