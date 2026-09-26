# IWDEE Emotion presentation assets

These files are the original *Icewind Dale: Enhanced Edition* presentation
resources used by Emotion, Courage and Emotion, Hope. The A/B/C spell icons and
delivery graph were extracted with WeiDU from the user's pristine IWDEE
installation. The D status icons are deterministic one-frame BAMs built from
the original 13x13 heart sprites in pristine IWDEE `STATES.BAM`: cycle 251 /
frame 177 for Hope and cycle 252 / frame 178 for Courage. No IWDification or
SCS binary was copied. A second pristine IWDEE installation contains
byte-identical source resources.

Component 301 installs them only when it must create a missing beneficial
Emotion spell. The projectile, VVC, animation, and sounds are published under
private `CBR301*` resrefs. The icons are published as the dynamically allocated
spell resref plus `A`, `B`, `C`, or `D`; the D BAM is referenced by a newly
allocated `STATDESC.2DA` row for the character-sheet status list.

| File | SHA-256 |
|---|---|
| `#ARE_M21.WAV` | `46BDF9F2E7631AA717B2ADA6870B2F6A6D7DE71CA7BC5480B1AD6DE654EBE3B2` |
| `#EFF_E03.WAV` | `634DFE623FA34E096637F82487373B382CF290CB80E56D5D5DC8DE67EB61DC1F` |
| `#GENENCH.VVC` | `670B8A6AC5A403263DC2CB64BCCA126BFDF77C9DB87F258E6FA4393DA42F9D8A` |
| `ENCHANX.BAM` | `730E330EF9390EDF139C77EC01730630D89D1D4030CA86A1E450B7F155C6C33B` |
| `IDPRO407.PRO` | `B4725639B39D11DE292932EFC59693C6B6B2D32925472E63A353087FACF1E6BE` |
| `SPWI427A.BAM` | `E0E53967D41C708828C42233C5C750624FE9E7B208976B9996ACC8440F29958C` |
| `SPWI427B.BAM` | `B107A950BD2AA2E0D7252DB6260CD831024808E763AE02218912205E4B1729AB` |
| `SPWI427C.BAM` | `BC563D88057570B69AE28EB678116EA8441FA5744351FAF38A190E925379797E` |
| `SPWI427D.BAM` | `6156D0716907E4DD3195CCBF957B061F97A68051CE20FF9CE9C64A04422DFBCC` |
| `SPWI429A.BAM` | `869D53B72C94D6C5D2AA028F13E6C4C498E1E359678FB7CD8F534D990ED9B033` |
| `SPWI429B.BAM` | `DAF665ABBDD70F84BCFF678EC0F50640FFB106252AC1B4C79D1FD7A16EFF926D` |
| `SPWI429C.BAM` | `7EDD84FE668D42A80BEC7F8BDB6074802EFD5BC3CD30DB58E58FCFB1EF98B778` |
| `SPWI429D.BAM` | `4045A535EAF4BD0B90E377B232D7EE8964AE9A09CAD50BC01D7BB523FF00E93E` |

IWDification by CamDawg and contributors was used as a behavioral reference
for the final resource graph and scroll contract. Component 301's WeiDU code
and spell descriptions are original CBR work. All game assets remain the
property of their respective rights holders.
