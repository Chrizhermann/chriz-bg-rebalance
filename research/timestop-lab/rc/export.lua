-- ARGS.name: the trace name; CBRTS.Export refuses an existing file.
assert(type(ARGS) == "table" and type(ARGS.name) == "string", "ARGS.name required")
return CBRTS.Export(ARGS.name)
