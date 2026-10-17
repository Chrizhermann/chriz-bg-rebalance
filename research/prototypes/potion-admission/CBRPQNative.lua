-- Read-only BG2EE 2.7.3 effect reader. No hooks, autoload, writes or saved state.
-- Runtime offsets are native object offsets, not 0x30-byte ITM record offsets.
-- GetAbilityEffect 1FB4DF-1FB55F establishes the source/school/level fields and
-- the possible specialist save-bonus adjustment. V2 saves retain those fields.
-- The caller owns each dose's identity cache and native object lifetime rules.
return function(api, manifest)
    local function requireValue(ok, text)
        if not ok then error("CBR potion reader: " .. text, 0) end
    end
    local function integer(value, lower, upper, name)
        requireValue(type(value) == "number" and value == math.floor(value)
            and value >= lower and value <= upper, "invalid " .. name)
        return value
    end
    requireValue(type(api) == "table", "API")
    for _, name in ipairs({"EEex_ReadU32", "EEex_ReadU16", "EEex_ReadU8", "EEex_Read32",
            "EEex_UDToPtr", "EEex_Utility_IterateCPtrList"}) do
        requireValue(type(api[name]) == "function", "missing API " .. name)
    end
    requireValue(type(manifest) == "table" and type(manifest.sources) == "table", "manifest")
    local U32_MAX, EXACT_MAX = 4294967295, 9007199254740991
    local function u32(address)
        return integer(api.EEex_ReadU32(address), 0, U32_MAX, "unsigned dword")
    end
    local function i32(address)
        return integer(api.EEex_Read32(address), -2147483648, 2147483647, "signed dword")
    end
    local function classPointer(pointer)
        return integer(u32(pointer)+u32(pointer+4)*4294967296,1,EXACT_MAX,"native class pointer")
    end
    local function u16(address)
        return integer(api.EEex_ReadU16(address), 0, 65535, "unsigned word")
    end
    local function resref(address)
        local chars = {}
        for offset = 0, 7 do
            local byte = integer(api.EEex_ReadU8(address + offset), 0, 255, "resource byte")
            if byte == 0 then break end
            chars[#chars + 1] = string.char(byte)
        end
        return string.upper(table.concat(chars))
    end
    local function normalizedFlags(value)
        -- Native self delivery sets bit3; identified delivery can set bit31.
        -- Arithmetic avoids LuaJIT bit operations returning signed dwords.
        value = value % 2147483648
        return value - (math.floor(value / 8) % 2) * 8
    end
    local function nativeSourceMatches(expected,source)
        return expected.nativeSource==source
            or (expected.nativeSources~=nil and expected.nativeSources[source]==true)
    end
    local fields = {
        {"opcode", 0x10, u32}, {"target", 0x14, u32}, {"power", 0x18, u32},
        {"amount", 0x1C, i32}, {"mode", 0x20, u32},
        {"resource", 0x30, resref}, {"diceCount", 0x38, i32}, {"diceSize", 0x3C, i32},
        {"saveType", 0x40, u32}, {"saveBonus", 0x44, i32}, {"special", 0x48, u32},
        {"flags", 0x5C, u32}, {"school", 0x4C, u32}, {"secondary", 0xD0, u32},
        {"sourceFlags", 0x9C, u32}, {"probUpper", 0x2C, u16}, {"probLower", 0x2E, u16},
        -- Non-dice opcodes19/54/90/92 map ITM+20/+1C to these level gates
        -- (constructor19DD79-82), leaving actual dice+38/+3C zero. HP18
        -- uses the dice branch19DD87-90 and leaves both level fields zero.
        {"minLevel", 0x54, u32}, {"maxLevel", 0x58, u32},
    }
    for source, entry in pairs(manifest.sources) do
        requireValue(type(source) == "string" and source == source:upper()
            and #source > 0 and #source <= 8, "manifest source")
        requireValue(type(entry) == "table" and type(entry.records) == "table"
            and type(entry.keys) == "table", "manifest source records")
        for key, expected in pairs(entry.records) do
            requireValue(type(key) == "string" and #key > 0 and entry.keys[key] == true
                and type(expected) == "table", "manifest record key")
            for _, field in ipairs(fields) do
                local name, reader = field[1], field[3]
                local value = expected[name]
                if reader == resref then
                    requireValue(type(value) == "string" and #value <= 8
                        and value == value:upper() and not value:find("\0", 1, true), "manifest " .. name)
                elseif reader == i32 then
                    integer(value, -2147483648, 2147483647, "manifest " .. name)
                else
                    integer(value, 0, reader == u16 and 65535 or U32_MAX, "manifest " .. name)
                end
            end
            integer(expected.timing, 0, U32_MAX, "manifest timing")
            integer(expected.duration, 0, U32_MAX, "manifest duration")
            if expected.nativeSourceType~=nil then
                requireValue(expected.nativeSourceType==1,"manifest linked native type")
                local sources=expected.nativeSources or {[expected.nativeSource or ""]=true}
                requireValue(type(sources)=="table" and next(sources)~=nil
                    and not (expected.nativeSources and expected.nativeSource),"manifest linked native sources")
                for source,enabled in pairs(sources) do
                    requireValue(enabled==true and type(source)=="string" and #source>0 and #source<=8
                        and source==source:upper() and not source:find("\0",1,true),
                        "manifest linked native source")
                end
            else
                requireValue(expected.nativeSource==nil and expected.nativeSources==nil,
                    "native source without linked source type")
            end
        end
        for key, enabled in pairs(entry.keys) do
            requireValue(enabled == true and entry.records[key] ~= nil, "manifest missing record")
        end
    end

    -- Tokens identify native lifetimes, not EEex userdata wrappers or addresses.
    -- A native destructor callback MUST retire the pointer before reuse. Weak
    -- values avoid retaining every observed lifetime after doses release them.
    local tokenByPointer = setmetatable({}, {__mode = "v"})
    local linkedByPointer = {}
    local function identity(pointer)
        local token = tokenByPointer[pointer]
        if not token then token = {}; tokenByPointer[pointer] = token end
        return token
    end
    local M = {}
    function M.ptr(object)
        requireValue(object ~= nil, "missing native object")
        return integer(api.EEex_UDToPtr(object), 1, EXACT_MAX - 0x180, "native pointer")
    end

    function M.retire(pointer)
        integer(pointer, 1, EXACT_MAX - 0x180, "retired pointer")
        tokenByPointer[pointer] = nil -- No userdata conversion or native read.
        linkedByPointer[pointer] = nil
    end

    function M.resetTokens()
        tokenByPointer = setmetatable({}, {__mode = "v"})
        linkedByPointer = {}
    end

    function M.source(effect)
        local pointer = M.ptr(effect)
        local sourceType = u32(pointer + 0x90)
        return resref(pointer + 0x94), sourceType
    end

    local function matches(actual, expected, incoming, duration)
        if incoming and (actual.timing ~= expected.timing or actual.expiry ~= (duration or expected.duration)) then
            return false
        end
        for _, field in ipairs(fields) do
            local name = field[1]
            local got, want = actual[name], expected[name]
            if name == "flags" then
                got, want = normalizedFlags(got), normalizedFlags(want)
            elseif name == "special" and actual.opcode == 18 and not incoming then
                -- Opcode18 sets bit0 on first use. Never normalize the incoming
                -- original: deliberate Special1 has different first-use behavior.
                got, want = got - got % 2, want - want % 2
            elseif name == "saveBonus" then
                -- Native x86 dword subtraction wraps before signed comparison.
                local specialist = (want - 2 + 2147483648) % 4294967296 - 2147483648
                if got ~= want and not (expected.school ~= 0 and got == specialist) then return false end
                got = want
            end
            if got ~= want then return false end
        end
        return true
    end

    local function actualFields(pointer)
        local actual = {timing = u32(pointer + 0x24), expiry = u32(pointer + 0x28)}
        for _, field in ipairs(fields) do actual[field[1]] = field[3](pointer + field[2]) end
        return actual
    end

    function M.carrier(effect,ownerSource,expected,incoming,expectedNativeSource)
        -- A carrier is tracked through its exact item/call ordinal, never
        -- treated as a buff or inferred from a resource name. It creates the
        -- native child cast after ordinary immunity/save admission succeeds.
        requireValue(type(expected)=="table" and expected.opcode==146 and expected.mode==1,
            "unreviewed linked carrier")
        requireValue(type(incoming)=="boolean","carrier incoming flag")
        local pointer=M.ptr(effect)
        local sourceType,source=u32(pointer+0x90),resref(pointer+0x94)
        local linked=expected.nativeSourceType==1
        requireValue(sourceType==(linked and 1 or 2)
            and (linked and nativeSourceMatches(expected,source) or not linked and source==ownerSource)
            and (expectedNativeSource==nil or source==expectedNativeSource),"carrier native source changed")
        local actual=actualFields(pointer)
        requireValue(matches(actual,expected,incoming,linked and actual.expiry or nil),
            "carrier fields differ from registry")
        local caster=u32(pointer+0xC8)
        if linked then
            requireValue(caster<=32767 or caster>=4294934528,"carrier caster is not native signed16")
            if incoming then requireValue(u32(pointer+0x11C)==expected.duration,"carrier original duration changed") end
        else requireValue(caster==10,"item carrier caster level is not native level10") end
        return {object=effect,identity=identity(pointer),source=source,sourceType=sourceType}
    end

    function M.bindLinked(effect, ownerSource, key, expectedNativeSource)
        -- Call ONLY at the proven original mode1 FireSpell child boundary, with
        -- an owning potion dose + selected header/ordinal from the registry.
        -- Merely recognizing a SPL name must never call this method.
        requireValue(type(ownerSource)=="string" and ownerSource==ownerSource:upper()
            and type(key)=="string", "linked binding identity")
        local entry=manifest.sources[ownerSource]
        local expected=entry and entry.records[key]
        requireValue(expected and expected.nativeSourceType==1,"undeclared linked binding")
        local pointer=M.ptr(effect)
        requireValue(linkedByPointer[pointer]==nil,"linked original already bound")
        local nativeSource=resref(pointer+0x94)
        requireValue(u32(pointer+0x90)==1 and nativeSourceMatches(expected,nativeSource)
            and (expectedNativeSource==nil or nativeSource==expectedNativeSource),
            "linked original has different native source")
        local actual=actualFields(pointer)
        requireValue(matches(actual,expected,true,actual.expiry),"linked original fields differ from manifest")
        -- Native op99 scaling changes +28, keeping the original resource
        -- duration in +11C. Preserve both; the admission deadline uses +28.
        requireValue(u32(pointer+0x11C)==expected.duration,"linked original duration differs from resource")
        local caster=u32(pointer+0xC8)
        requireValue(caster<=32767 or caster>=4294934528,"linked caster is not native signed16")
        requireValue(u32(pointer+0x114)==0,"linked original is already done")
        linkedByPointer[pointer]={identity=identity(pointer),ownerSource=ownerSource,key=key,
            nativeSource=nativeSource,duration=actual.expiry,caster=caster,vtable=classPointer(pointer)}
    end

    function M.identify(effect, key, incoming)
        requireValue(type(incoming) == "boolean", "incoming flag")
        requireValue(key == nil or (type(key) == "string" and #key > 0), "requested key")
        local pointer = M.ptr(effect)
        local sourceType = u32(pointer + 0x90)
        local binding=linkedByPointer[pointer]
        if not binding and sourceType ~= 2 then return nil end
        local source = resref(pointer + 0x94)
        local entry = manifest.sources[binding and binding.ownerSource or source]
        if not entry then return nil end
        if key then requireValue(entry.records[key] ~= nil, "requested key is absent from " .. source) end
        local actual = actualFields(pointer)
        local matched
        -- Even an explicit incoming key cannot conceal an ambiguous manifest.
        -- Active effects have no original ability ordinal or duration after load.
        if binding then
            local expected=entry.records[binding.key]
            requireValue(binding.identity==identity(pointer) and sourceType==1
                and expected and expected.nativeSourceType==1 and source==binding.nativeSource
                and nativeSourceMatches(expected,source)
                and classPointer(pointer)==binding.vtable,
                "linked original source/lifetime changed")
            requireValue(u32(pointer+0xC8)==binding.caster,"linked original caster level changed")
            requireValue(not incoming or not binding.restored,"restored linked effect is not a newly constructed child")
            requireValue(matches(actual,expected,incoming,binding.duration),"linked original fields changed")
            matched=binding.key
        else
            for candidate, expected in pairs(entry.records) do
                if expected.nativeSourceType==nil and matches(actual, expected, incoming) then
                    requireValue(matched == nil, "ambiguous native record in " .. source)
                    matched = candidate
                end
            end
        end
        if key then requireValue(matched == key, "requested key mismatch in " .. source) end
        if not matched then return nil end
        if not binding then
            requireValue(u32(pointer + 0xC8) == 10, "item caster level is not native level10 in " .. source)
        end
        return {object = effect, identity = identity(pointer), sourceType = sourceType, source = source, key = matched,
            ownerSource=binding and binding.ownerSource or nil,
            timing = actual.timing, expiry = actual.expiry, done = u32(pointer + 0x114) ~= 0}
    end

    function M.active(sprite, identityCache)
        requireValue(sprite ~= nil and sprite.m_timedEffectList ~= nil, "missing timed effect list")
        requireValue(type(identityCache) == "table", "missing per-dose identity cache")
        local records, staged, seen = {}, {}, {}
        api.EEex_Utility_IterateCPtrList(sprite.m_timedEffectList, function(effect)
            local pointer = M.ptr(effect)
            requireValue(not seen[pointer], "duplicate pointer or cyclic timed effect list")
            seen[pointer] = true
            local record = M.identify(effect, nil, false)
            if record then
                -- Always expose the freshly enumerated native object and data.
                -- A retained/cached userdata may refer to a destroyed lifetime;
                -- neither dereference it nor use it to infer current identity.
                staged[pointer] = {identity = record.identity, object = effect}
                records[#records + 1] = record
            end
        end)
        -- Publish only after every record was read and validated. This changes
        -- caller-owned Lua bookkeeping, never the native list or its cursors.
        for pointer, entry in pairs(staged) do identityCache[pointer] = entry end
        return records
    end

    local function savedBody(pointer)
        local pieces={}
        for offset=0,0xD0,4 do
            local value=u32(pointer+offset)
            pieces[#pieces+1]=string.char(value%256,math.floor(value/256)%256,
                math.floor(value/65536)%256,math.floor(value/16777216)%256)
        end
        return table.concat(pieces)
    end

    function M.savedRecords(sprite)
        -- Exact native list order, including unowned records and Done entries.
        -- Marshal timing filters belong to the caller's actual native context.
        requireValue(sprite~=nil and sprite.m_timedEffectList~=nil,"missing saved timed effect list")
        local result,seen={},{}
        api.EEex_Utility_IterateCPtrList(sprite.m_timedEffectList,function(effect)
            local pointer=M.ptr(effect)
            requireValue(not seen[pointer],"duplicate pointer or cyclic saved effect list")
            seen[pointer]=true
            result[#result+1]={object=effect,identity=identity(pointer),body=savedBody(pointer)}
        end)
        return result
    end

    function M.savedOwners()
        local owners={}
        for _,binding in pairs(linkedByPointer) do
            owners[binding.identity]={source=binding.ownerSource,key=binding.key}
        end
        return owners
    end

    function M.restoreSaved(records,data,saved)
        -- Saved.restore verifies full durable projection and relative occurrence
        -- first. Add current-manifest verification before publishing ANY binding.
        -- This does not infer ownership in a save without our metadata.
        requireValue(type(saved)=="table" and type(saved.restore)=="function","missing saved metadata module")
        local staged={}
        local restored=saved.restore(records,data,function(record,owner)
            local entry=manifest.sources[owner.source]
            local expected=entry and entry.records[owner.key]
            requireValue(expected and expected.nativeSourceType==1,"saved linked key differs from manifest")
            local pointer=M.ptr(record.object)
            requireValue(record.identity==identity(pointer) and linkedByPointer[pointer]==nil,
                "saved linked lifetime is stale or already bound")
            requireValue(savedBody(pointer)==record.body:sub(1,0xD4),"saved linked fields changed after snapshot")
            local nativeSource=resref(pointer+0x94)
            requireValue(u32(pointer+0x90)==1 and nativeSourceMatches(expected,nativeSource),
                "saved linked native source changed")
            local actual=actualFields(pointer)
            requireValue(actual.timing==4096 and matches(actual,expected,false),
                "saved linked fields differ from manifest")
            local caster=u32(pointer+0xC8)
            requireValue(caster<=32767 or caster>=4294934528,"saved linked caster is not native signed16")
            staged[pointer]={identity=record.identity,ownerSource=owner.source,key=owner.key,
                nativeSource=nativeSource,caster=caster,restored=true,vtable=classPointer(pointer)}
            return true
        end)
        for pointer,binding in pairs(staged) do linkedByPointer[pointer]=binding end
        return restored
    end

    function M.copyLinked(destination,sourcePointer)
        -- Only the guarded post-CopyFromBase observer may call this. It MUST
        -- exclude DecodeEffectFromBase's caller even if sourceBase-8 happens
        -- to reference a live effect. No decode/save-buffer guessing here.
        integer(sourcePointer,1,EXACT_MAX-0x180,"copied source pointer")
        local binding=linkedByPointer[sourcePointer]
        if not binding then return false end
        local pointer=M.ptr(destination)
        requireValue(pointer~=sourcePointer and linkedByPointer[pointer]==nil,"copy destination already owned")
        local expected=manifest.sources[binding.ownerSource].records[binding.key]
        requireValue(identity(sourcePointer)==binding.identity and classPointer(sourcePointer)==binding.vtable,
            "copied source lifetime/class changed")
        requireValue(classPointer(pointer)==binding.vtable,"copy changed native effect class")
        requireValue(u32(sourcePointer+0x90)==1 and u32(pointer+0x90)==1
            and resref(sourcePointer+0x94)==binding.nativeSource
            and resref(pointer+0x94)==binding.nativeSource
            and nativeSourceMatches(expected,binding.nativeSource),"copy changed native source")
        local source,copy=actualFields(sourcePointer),actualFields(pointer)
        requireValue(matches(source,expected,false),"copied source fields changed")
        for _,field in ipairs(fields) do
            requireValue(source[field[1]]==copy[field[1]],"copy changed native field "..field[1])
        end
        requireValue(copy.timing==source.timing and copy.expiry==source.expiry
            and u32(sourcePointer+0xC8)==binding.caster and u32(pointer+0xC8)==binding.caster,
            "copy changed native timing/caster")
        requireValue(u32(pointer+0x110)==u32(sourcePointer+0x110) and u32(pointer+0x114)==0
            and u32(pointer+0x11C)==source.expiry and u32(pointer+0x150)==U32_MAX,
            "copy constructor fields differ from proven live-copy contract")
        linkedByPointer[pointer]={identity=identity(pointer),ownerSource=binding.ownerSource,
            key=binding.key,nativeSource=binding.nativeSource,duration=binding.duration,
            caster=binding.caster,vtable=binding.vtable,
            restored=binding.restored or source.timing~=expected.timing}
        return true
    end

    function M.isSelf(effect, sprite)
        return u32(M.ptr(effect) + 0x110) == u32(M.ptr(sprite) + 0x48)
    end

    function M.isInstantProjectile(pointer)
        -- A resource's projectile ID is not a runtime class guarantee: EEex
        -- type mutators can replace the decoded object. Read the actual vtable,
        -- as EEex_Projectile_GetType does, without dereferencing any userdata.
        -- Only the deferred target2 adapter needs these additional APIs.
        integer(pointer, 1, EXACT_MAX - 8, "projectile pointer")
        requireValue(type(api.EEex_ReadPtr) == "function", "missing API EEex_ReadPtr")
        requireValue(type(api.EEex_GetImageBase) == "function", "missing API EEex_GetImageBase")
        local base = integer(api.EEex_GetImageBase(), 1, EXACT_MAX - 0x59BFF0, "image base")
        local vtable = integer(api.EEex_ReadPtr(pointer), 0, EXACT_MAX, "projectile vtable")
        -- Pinned BG2EE2.7.3 CProjectileInstant: Fire231600, OnArrival233030,
        -- DeliverEffects22EFC0. Transport independently guards the native sites.
        return vtable == base + 0x59BFF0
    end

    function M.now()
        local globals = api.EngineGlobals
        requireValue(globals and globals.g_pBaldurChitin
            and globals.g_pBaldurChitin.m_pObjectGame
            and globals.g_pBaldurChitin.m_pObjectGame.m_worldTime, "missing engine world time")
        return integer(globals.g_pBaldurChitin.m_pObjectGame.m_worldTime.m_gameTime,
            0, U32_MAX, "world time")
    end
    return M
end
