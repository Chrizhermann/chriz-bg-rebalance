-- Inert composition around the original EEex1.3 metadata reader.
-- Bind provenance before foreign importers may copy/remove/reorder originals.
-- Does not register handlers, replace functions, read files, or edit saves.
return function(api,binary,saved,reader,adapter,handlerName)
    local function check(ok,message)
        if not ok then error("CBR potion save import: "..message,0) end
    end
    check(type(api)=="table" and type(api.EEex_ReadU8)=="function"
        and type(api.EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal)=="function",
        "missing pinned EEex reader")
    check(type(binary)=="table" and type(binary.read)=="function"
        and type(saved)=="table" and type(saved.restore)=="function","missing metadata modules")
    check(type(reader)=="table" and type(reader.savedRecords)=="function"
        and type(reader.restoreSaved)=="function","missing native ownership reader")
    check(type(adapter)=="table" and type(adapter.context)=="function"
        and type(adapter.invalidate)=="function","missing native input context/failure callback")
    check(type(handlerName)=="string" and #handlerName>0,"missing registered handler name")
    local original=api.EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal
    local stack={}
    local M={}
    local function equal(left,right)
        if type(left)~=type(right) then return false end
        if type(left)~="table" then return left==right end
        for key,value in pairs(left) do if not equal(value,right[key]) then return false end end
        for key in pairs(right) do if left[key]==nil then return false end end
        return true
    end
    function M.importer(sprite,data)
        local invocation=stack[#stack]
        if invocation then
            -- The stock reader catches handler errors. Retain the failure so
            -- its outer wrapper cannot mistakenly report a successful import.
            if invocation.sprite~=sprite or invocation.seen
                    or not equal(invocation.data,data) then
                invocation.invalid=true
                error("CBR potion save import: ownership handler data/order changed",0)
            end
            invocation.seen=true
        else
            error("CBR potion save import: ownership handler outside proven native input",0)
        end
    end
    function M.read(sprite,memory)
        -- A projectile/non-sprite Unmarshal is a sentinel, not an owning list.
        -- Its normal EEex behavior stays intact. Our importer cannot restore
        -- potion metadata on that path merely because a handler name matches.
        local context=adapter.context(sprite,memory)
        if context==nil then return original(sprite,memory) end
        check(type(context)=="table" and context.identity~=nil and context.version==1
            and type(context.baseline)=="table","missing exact V2 native input")
        check(type(context.data)=="number" and type(context.size)=="number"
            and context.size>=0 and context.size==math.floor(context.size)
            and context.size%0x108==0,"invalid native input interval")
        local normalBytes=memory-context.data
        check(normalBytes>=0 and normalBytes%0x108==0 and normalBytes<context.size,
            "footer is outside the native effect interval")
        local data,count=binary.read(api.EEex_ReadU8,memory,context.data+context.size,handlerName)
        local all=reader.savedRecords(sprite)
        local prefix=#context.baseline
        check(#all==prefix+normalBytes/0x108,"decoded native list differs from input count")
        for i,identity in ipairs(context.baseline) do
            check(all[i].identity==identity,"pre-existing native list prefix changed")
        end
        local records={}
        for i=prefix+1,#all do records[#records+1]=all[i] end
        -- No external handler has run: strings and original lifetimes still
        -- describe the exact serialized order. This operation publishes only
        -- Lua ownership bindings after the whole metadata set is validated.
        if data~=nil then
            if data.invalid==true then
                adapter.invalidate("saved potion ownership was explicitly invalidated")
            else
                local restored,reason=pcall(reader.restoreSaved,records,data,saved)
                if not restored then adapter.invalidate(tostring(reason)) end
            end
        end
        local invocation={sprite=sprite,data=data,seen=false}
        stack[#stack+1]=invocation
        local ok,result=pcall(original,sprite,memory)
        stack[#stack]=nil
        if not ok then error(result,0) end
        check(not invocation.invalid and invocation.seen==(data~=nil),
            "ownership handler failed, disappeared, or changed during import")
        check(result==count,"EEex consumed a different metadata interval")
        local after=adapter.context(sprite,memory)
        check(after~=nil and after.identity==context.identity,"native input context changed during import")
        return result
    end
    -- Requires live-copy/destructor observation throughout foreign importers.
    -- Exceptions diagnose unsupported state; they are not native load rollback.
    return M
end
