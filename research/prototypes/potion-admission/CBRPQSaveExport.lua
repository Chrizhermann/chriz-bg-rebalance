-- Inert EEex1.3 export composition. No handler registration or function replacement.
-- A future native Marshal context adapter supplies the actual V2 filter arguments.
-- Finalize our placeholder AFTER all EEex exporters, BEFORE extra-data sizing.
-- Native normal-effect bytes were already counted. Return the proven count
-- delta with extra bytes, and shift the writer's footer address by that delta.
-- Do not install without the corresponding lifetime/import/native context hooks.
return function(api, saved, adapter, handlerName)
    local function check(ok, message)
        if not ok then error("CBR potion save export: " .. message, 0) end
    end
    check(type(api)=="table" and type(saved)=="table" and type(saved.export)=="function"
        and type(adapter)=="table", "missing modules")
    for _,name in ipairs({"context", "records", "owners", "invalidate"}) do
        check(type(adapter[name])=="function", "missing adapter "..name)
    end
    for _,name in ipairs({"EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize",
            "EEex_Sprite_Hook_WriteExtraEffectListMarshal",
            "EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize",
            "EEex_Sprite_Private_DetermineSpriteMarshalHandlerNumberInfo", "EEex_RoundUp"}) do
        check(type(api[name])=="function", "missing EEex function "..name)
    end
    check(api.CGameEffectBase~=nil and api.CGameEffectBase.sizeof==0x108,
        "unsupported V2 effect size")
    local originalCalculate=api.EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize
    local originalWrite=api.EEex_Sprite_Hook_WriteExtraEffectListMarshal
    local numberInfo=api.EEex_Sprite_Private_DetermineSpriteMarshalHandlerNumberInfo
    local pending,writePending=nil,nil
    local failure=nil
    handlerName=handlerName or "CBRPQ"
    check(type(handlerName)=="string" and #handlerName>0,"invalid handler name")
    local M={}

    local function context(sprite)
        local value=adapter.context(sprite)
        check(type(value)=="table" and value.identity~=nil and value.version==1,
            "missing exact V2 Marshal context")
        check(type(value.onlyTiming9)=="boolean" and type(value.excludeTiming2)=="boolean",
            "missing native timing filters")
        check(type(value.normalBytes)=="number" and value.normalBytes==math.floor(value.normalBytes)
            and value.normalBytes>=0 and value.normalBytes<=2147483647
            and value.normalBytes%0x108==0,"missing exact native normal-effect byte count")
        return {identity=value.identity, version=value.version,
            onlyTiming9=value.onlyTiming9, excludeTiming2=value.excludeTiming2,
            normalBytes=value.normalBytes}
    end
    local function sameContext(left,right)
        return left.identity==right.identity and left.version==right.version
            and left.onlyTiming9==right.onlyTiming9 and left.excludeTiming2==right.excludeTiming2
            and left.normalBytes==right.normalBytes
    end
    local function selected(records,ctx)
        check(type(records)=="table", "missing fresh effect list")
        local size,count=#records,0
        for key in pairs(records) do
            check(type(key)=="number" and key==math.floor(key) and key>=1 and key<=size,
                "invalid fresh effect list index")
            count=count+1
        end
        check(size==count,"sparse fresh effect list")
        local result={}
        for _,record in ipairs(records) do
            check(type(record)=="table" and type(record.body)=="string" and #record.body>=0xD4,
                "truncated fresh effect body")
            local a,b,c,d=record.body:byte(0x25,0x28)
            local timing=a+b*256+c*65536+d*16777216
            if (not ctx.onlyTiming9 or timing==9) and (not ctx.excludeTiming2 or timing~=2) then
                result[#result+1]=record
            end
        end
        return result
    end

    function M.exporter(sprite)
        check(pending~=nil and pending.sprite==sprite,"export outside wrapped calculation")
        check(pending.placeholder==nil,"duplicate ownership exporter")
        local placeholder={version=1,groups={}}
        pending.placeholder=placeholder
        return placeholder
    end

    local function resize(invocation,records)
        local collection=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData
        local normalBytes=#records*0x108
        local delta=normalBytes-invocation.context.normalBytes
        local unrounded=8+api.EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize(collection)
        local bytes=api.EEex_RoundUp(unrounded,0x108)
        check(type(bytes)=="number" and bytes==math.floor(bytes) and bytes>=unrounded
            and bytes<=2147483647 and bytes%0x108==0,"invalid EEex serialized size")
        check(normalBytes+bytes<=2147483647,"native serialization exceeds signed byte range")
        api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize=bytes-8
        writePending={delta=delta,context=invocation.context,sprite=invocation.sprite,
            placeholder=invocation.serializedPlaceholder or invocation.placeholder,
            collection=collection,metadata=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta,
            tableSize=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableSize,
            memorySize=bytes-8,unrounded=unrounded}
        return bytes+delta
    end

    local function allocationUnchanged(invocation)
        check(api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData==invocation.collection
            and api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta==invocation.metadata
            and api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableSize==invocation.tableSize
            and api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_MemorySize==invocation.memorySize,
            "pending EEex allocation/collection changed")
        local occurrences=0
        for _,value in pairs(invocation.collection) do
            local metadata=invocation.metadata[value]
            check(type(metadata)=="table" and type(metadata.handlerName)=="string",
                "pending exporter identity changed")
            if metadata.handlerName==handlerName then
                check(value==invocation.placeholder,"pending ownership placeholder changed")
                occurrences=occurrences+1
            end
        end
        check(occurrences==1 and type(invocation.placeholder)=="table"
            and getmetatable(invocation.placeholder)==nil,"pending ownership placeholder missing/duplicated")
        check(8+api.EEex_Sprite_Private_CalculateSpriteMarshalHandlerDataSize(invocation.collection)
            ==invocation.unrounded,"pending serialized byte size changed")
    end

    local function markPendingInvalid(invocation)
        check(not invocation.writeStarted,"cannot invalidate metadata after writer began")
        allocationUnchanged(invocation)
        local placeholder=invocation.placeholder
        check(placeholder.version==1 or placeholder.version==0,"pending ownership schema changed")
        check(api.EEex_Sprite_Private_DetermineSpriteMarshalHandlerNumberInfo==numberInfo,
            "EEex integer encoder changed")
        local kind1,writer1,width1=numberInfo(1)
        local kind0,writer0,width0=numberInfo(0)
        check(kind1==kind0 and writer1==writer0 and type(writer1)=="function"
            and width1==1 and width0==1,"schema invalidation changes integer encoding width")
        -- Pinned EEex encodes both 1 and 0 as INTU8 (type4, one payload
        -- byte). Change the EXISTING value only, preserving its table/key,
        -- group data, foreign namespaces and exact allocated byte count.
        -- Saved.restore rejects version0 before publishing any binding.
        placeholder.version=0
    end
    function M.invalidate(reason)
        failure=failure or tostring(reason)
        if writePending then
            local ok,why=pcall(markPendingInvalid,writePending)
            if not ok then
                writePending.invalidationError=writePending.invalidationError or tostring(why)
                error(why,0)
            end
        end
        return false
    end

    local function recover(invocation,reason)
        M.invalidate(reason)
        pcall(adapter.invalidate,failure)
        -- Only metadata in our own namespace is folded into this explicit
        -- invalid marker. Preserve other handlers and retain old own/fallback
        -- data for diagnosis; never silently choose one as authoritative.
        local current=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData
        local metadata=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta
        check(type(current)=="table" and type(metadata)=="table","cannot preserve EEex export state")
        local collection,previous={},{}
        for _,value in pairs(current) do
            local entry=metadata[value]
            check(type(entry)=="table" and type(entry.handlerName)=="string","cannot preserve exporter identity")
            if entry.handlerName==handlerName then previous[#previous+1]=value
            else collection[#collection+1]=value end
        end
        local invalid={version=1,invalid=true,groups={},previous=previous}
        collection[#collection+1]=invalid
        metadata[invalid]={handlerName=handlerName}
        api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData=collection
        api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableSize=#collection
        invocation.serializedPlaceholder=invalid
        check(sameContext(invocation.context,context(invocation.sprite)),"Marshal context changed; cannot recover")
        return resize(invocation,selected(adapter.records(invocation.sprite,invocation.context),invocation.context))
    end

    function M.calculate(sprite)
        -- EEex's underlying collector uses global single-sprite state too.
        -- A recursive marshal cannot be made safe merely by stacking our data.
        check(pending==nil,"reentrant EEex effect-list serialization")
        check(writePending==nil,"previous metadata allocation has not been written")
        check(not api.EEex_Debug_DisableExtraCreatureMarshalling,
            "EEex extra creature marshalling is disabled")
        local invocation={sprite=sprite,context=context(sprite)}
        pending=invocation
        local ok,result=pcall(function()
            originalCalculate(sprite)
            invocation.collected=true
            check(sameContext(invocation.context,context(sprite)),"Marshal context changed during exporters")
            local placeholder=invocation.placeholder
            check(placeholder~=nil,"ownership exporter did not run")
            local collection=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData
            local occurrences=0
            for _,value in pairs(collection) do if value==placeholder then occurrences=occurrences+1 end end
            check(occurrences==1,"ownership placeholder missing or duplicated in EEex export")
            local metadata=api.EEex_Sprite_Private_CurrentSpriteMarshalHandlerData_TableToMeta
            local ownMeta=type(metadata)=="table" and metadata[placeholder]
            check(type(ownMeta)=="table" and type(ownMeta.handlerName)=="string",
                "ownership handler metadata is missing")
            check(ownMeta.handlerName==handlerName,"registered ownership handler name changed")
            local named=0
            for _,value in pairs(collection) do
                local entry=metadata[value]
                if entry and entry.handlerName==ownMeta.handlerName then named=named+1 end
            end
            -- EEex exports fallback storage even when that handler is now
            -- registered. A stale fallback must not create a second ownership
            -- block, nor be silently discarded or treated as current data.
            check(named==1,"duplicate ownership handler in export/fallback storage")
            local records=selected(adapter.records(sprite,invocation.context),invocation.context)
            -- The stock hook adds our signed64 return to old EBX, retaining
            -- old EBX as OriginalMarshalSize. Compensate BOTH allocation and
            -- footer placement; merely increasing metadata bytes is unsafe.
            local data=failure and {version=1,groups={},invalid=true}
                or saved.export(records,adapter.owners(sprite))
            -- Preserve the exact table identity registered with EEex's metadata
            -- map; only our fields change. Other exporters are not called again.
            placeholder.version,placeholder.groups=data.version,data.groups
            placeholder.invalid=data.invalid
            return resize(invocation,records)
        end)
        pending=nil
        if not ok then
            -- A Lua error here would make stock EEex return zero extra bytes,
            -- while its writer could retain a positive MemorySize. Do not
            -- introduce that out-of-allocation write for recoverable ownership
            -- errors after the normal collector finished.
            if invocation.collected then return recover(invocation,result) end
            error(result,0)
        end
        return result
    end
    function M.write(memory)
        local invocation=writePending
        check(invocation~=nil,"metadata writer has no matching allocation")
        check(invocation.invalidationError==nil,"pending ownership invalidation failed; output is not repaired")
        check(not invocation.writeStarted,"metadata writer already began; restart required")
        check(sameContext(invocation.context,context(invocation.sprite)),"Marshal context changed before writer")
        check(type(memory)=="number" and memory==math.floor(memory)
            and memory+invocation.delta>0 and memory+invocation.delta<=9007199254740991,
            "invalid allocated footer pointer")
        allocationUnchanged(invocation)
        invocation.writeStarted=true
        local ok,result=pcall(originalWrite,memory+invocation.delta)
        if not ok then error(result,0) end
        -- Native pinned write primitives do not dispatch gameplay/Lua lifecycle
        -- callbacks. An arbitrarily replaced writer may do so; after any byte
        -- was serialized we cannot claim the version field was still unwritten.
        -- Keep the pending allocation diagnostic and require restart, even if
        -- that writer completed. This is not rollback of its native writes.
        check(invocation.invalidationError==nil,"ownership invalidated after writer began; output is not repaired")
        writePending=nil
    end
    function M.status() return failure==nil,failure end
    -- Requires stock pinned EEex writer/memory primitives and no later native
    -- hook that mutates this list between final snapshot and the native copy.
    -- Corrupted native context/collector state, recursive Marshal and allocation
    -- failure are still outside this recovery contract; no save abort is claimed.
    return M
end
