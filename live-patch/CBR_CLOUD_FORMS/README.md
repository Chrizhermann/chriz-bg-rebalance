# Private stream-install adapter

New tail component 0 calls the exact library used by public BG Rebalance 320.
It never uninstalls/reinstalls an earlier component. Copy the canonical
`chriz-bg-rebalance/lib/cloud_forms.tpa` into this folder's `lib` directory.
The deployment script must check a closed game, preserve preimages and existing
TLK/log entries, and compare output with the already-tested captured resources.

No game launch or save editing. Resource/WeiDU checks do not establish combat
acceptance. This private adapter is not a published release or CEBG update recipe.
