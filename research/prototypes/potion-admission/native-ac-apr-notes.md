# AC0 and APR1 classifier evidence — 2026-10-09

For finite effects, ordinary positive AC0 additive amounts are **bonuses**:
the native engine subtracts the amount from the armor-class accumulator. Positive
APR1 mode0 amounts also grant a bonus, using the native signed half-attack
encoding. Neither may be classified as an unowned penalty merely because the
raw parameter is nonnegative. AC mode16 is a nonaccumulating minimum/setter.

This is bounded offline evidence for classification and expiry-only refresh.
No compiler, runtime hook, source resource, game installation or save was changed.

## Input and source identity

Executable: `%USERPROFILE%\Games\CBR-TimeStop-2.7.3.0\Baldur.exe`,
BG2EE2.7.3.0, SHA256
`b51093a49140b2b8a7c046b4652bb8e535be24ebbc12b1d735e0b94217a14d57`.
All addresses below are image-relative RVAs; image base is `0x140000000`.
Function names come from that lab's
`EEex\loader\v2.7.3.0\bg2ee\function_names.db`.

## AC0

`CGameEffectAC::ApplyEffect` is `1A5F70`. Its17-entry dispatch table at `1A6208`
accepts these exact parameter2 values:

| Mode | Finite branch | Actor field | Native operation |
| --- | --- | --- | --- |
|0 general AC|`1A5FDE`|`+2A76`|subtract low16(parameter1)|
|1 crushing AC|`1A6044`|`+2A78`|subtract low16(parameter1)|
|2 missile AC|`1A60AA`|`+2A7A`|subtract low16(parameter1)|
|4 piercing AC|`1A6110`|`+2A7C`|subtract low16(parameter1)|
|8 slashing AC|`1A6176`|`+2A7E`|subtract low16(parameter1)|
|16 base AC limit|`1A61EA`|`+1126`|signed16 minimum(current, parameter1)|

Modes1/2/4/8 are exact selectors here, **not combinable masks**. Values3,5,6,7,
9..15 and values greater than16 go to the no-operation return `1A6201`.
The probe executes several such combinations as negative controls.

Every additive branch uses a16-bit subtraction. From accumulator0, p1=+10
produces-10 and a second application produces-20; p1=-10 produces+10 then+20.
Lower AC is better. Thus positive amounts accumulate beneficially in the normal
stat range; negative amounts accumulate penalties.

The engine consumes only the low16 bits. Examples tested on every additive mode:

| Raw parameter1 | Native signed16 amount | First/repeated accumulator |
| --- | --- | --- |
|1,65537,-65535|+1|-1,-2|
|-1,65535|-1|+1,+2|
|0|0|0,0|

Classification must use actual signed16 semantics rather than the sign of the
raw32-bit value. This does not authorize rewriting the original field or dropping
raw identity checks. Extreme16-bit accumulator overflow/final-stat clamping is
not classified by these tests.

Mode16 is better described as a minimum, not an unconditional setter:
`1A61F1` compares signed words and `1A61F5` keeps the smaller value. From AC10,
p1=2 gives2 on both applications; p1=12 leaves10; p1=-10 gives-10 on both.
There is no accumulating potency or first-use side effect in the reviewed finite
branch. It can remain native under the agreed policy for nonaccumulating setters;
refresh policy is separate from this native idempotence finding.

Timing1 takes separate permanent paths that change actor base fields
`+5A0/+5A2/+5A4/+5A6/+5A8`, clamp to[-20,20], and set effect done/repass.
Finite safety must not be extrapolated to permanent timing. The probe includes
permanent general-AC and mode16 negative controls.

## APR1 mode0

`CGameEffectAttackNo::ApplyEffect` is `1A7330`. For finite mode0,
`1A759A..1A75C7` performs:

1. Convert existing signed16 accumulator at actor `+2A82` to a float with
   `CDerivedStats::NumAttacksShortToFloat(153750)`.
2. Convert low16(parameter1) with the same helper.
3. Add the floats at `1A75B2`.
4. Convert back with `NumAttacksFloatToShort(153670)` and store at `1A75BE`.

The source and executed helper agree on this signed encoding:

| Magnitude of signed16 value | APR magnitude |
| --- | --- |
|0..5|the same number|
|6|0.5|
|7|1.5|
|8|2.5|
|9|3.5|
|10|4.5|
|greater than10|0|

The sign is retained. The conversion back clamps the accumulator's absolute
value to5APR and re-encodes integer/half values. This is native arithmetic, not a
new prototype cap. For example, p1=1 produces1APR then2APR; p1=6 produces0.5APR
then1APR; p1=7 produces1.5APR then3APR. Corresponding negative amounts reduce
APR. p1=5 reaches the native5APR cap immediately, but this saturation is not a
general reason to call positive mode0 nonaccumulating or unowned.

All encodings-11..11, representative larger values, -32768, and the aliases
1/65537/-65535 and-1/65535 were executed. The valid positive encodings are
beneficial; valid negative encodings are adverse; zero/invalid magnitudes decode
to0. The lookup applies to the signed low16 value, not the raw32 sign.

There is an additional native interaction: `1A733A..1A7396` scans both equipped
and timed effect lists for any opcode1 with mode3 and returns without applying
mode0 if one exists. Both lists were tested. A uniqueness layer must leave that
native interaction intact; it does not make mode0 generally a no-op. APR
modes1/2/3, their setter/percentage/override policy, and final attack-rate
combination with Haste/Slow are outside this bounded classification proof.

## Lifecycle and native field preservation

| Class | Constructor | Installed vtable | Apply |
| --- | --- | --- | --- |
|AC0|`19DE10`|`591768`|`1A5F70`|
|APR1|`19E110`|`5917C0`|`1A7330`|

Both constructors pass UsesDice=false through `[rsp+28]=0` at constructor+16.
Their actual native vtables have scalar destructor `14C8E0`, class-specific
OnAdd at slot28=`1E1E0`, and OnRemove at slot50=`1E1E0`. The latter two are
the native no-op function. The existing generic effect-destruction transport
already observes this destructor; no new destructor hook is indicated.

For every tested finite record, two actual Apply calls with firstCall=1 preserve
the entire `0x180`-byte synthetic effect allocation. Only the identified actor
stat field changes; all other `0x6000` actor bytes remain unchanged. Native base
self OnAdd is also executed with source flags0 and0x400 and changes neither
effect nor actor. No nested delivery occurs.

The expiry test then uses the already-processed firstCall=0 state, changes only
expiry `+28`, and executes actual ResolveEffect with fresh synthetic stat bases
at three world times spanning the old deadline. Results and all effect fields
remain stable. At the new deadline, Resolve marks done and does not call Apply.
This proves the bounded native arithmetic/state property needed by duration-only
refresh; it does not replace whole-actor/live admission tests.

## Connection to captured potion resources

Existing audit inputs in
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\audit-*.json`
show these relevant forms (reference observations, not shape requirements):

- Vanilla/default/non-SR POTN18.ITM has AC0 p1=10,p2=1,timing0,duration600 at
  effect byte offset`AA`: this is the accumulating crushing-AC bonus.
- Vanilla POTN11/POTN24/POTN46 have AC0 p1=0,p2=16; these are nonaccumulating
  minima, with durations300/600/300 respectively. Default/non-SR POTN46 moves
  that AC form into a linked SPL, whose lineage is a separate capability question.
- IR/IRR POTN11.SPL has AC0 +2/mode0/duration60 at`12A`; POTN24.SPL has
  +4/mode0/duration300 at`9A`. These are also accumulating bonuses. Their linked
  delivery is not made supported merely by proving the AC operator.

## Reproduction and limits

`probe_native_ac_apr.py --exe <pinned Baldur.exe> --python-libs <pefile/Unicorn>`
passes **74 stat cases and13 controls**. Saved result:
`%USERPROFILE%\AppData\Local\Temp\cbr-potion-inventory-20261009\native-ac-apr-result.json`.
It reuses the existing probe's synthetic objects and the stat probe's
no-recursive-delivery guard without changing those shared helpers.

Actual Apply/Resolve/base OnAdd/APR conversion instructions execute. Full
ProcessEffectList, native admission, destructor execution, scheduler, persistence,
and a live EEex runtime do not. Native vtables are read as lifecycle evidence.
The code is offline research only; no game process or DLL was executed.
