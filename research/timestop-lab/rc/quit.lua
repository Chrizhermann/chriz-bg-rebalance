-- End the lab game through the stock Quit path (no save), only after the capture was stopped
-- and exported, so the quiet runner sees a normal exit instead of its time limit.
assert(not (CBRTS and CBRTS.Status().armed), "STOP_FIRST")
Infinity_ShutdownGame()
return {quitting = true, frame = Infinity_GetFrameCounter()}
