-- Inert persistence composition. This factory neither registers handlers nor
-- replaces EEex functions. Install the returned binding plan TOGETHER, only
-- after the native context, copy, effect-destruction and sprite-lifetime hooks
-- have passed their own preflight. A function-shaped dependency is not proof
-- that its native observer has been installed.
--
-- Ordinary ownership failure is sticky. Keep observing native contexts and
-- effect lifetimes until their actual returns/destructors: clearing those on
-- failure can make the stock EEex writer use stale/out-of-allocation state.
-- Context corruption, collector/writer errors and native allocation failure
-- are diagnostics, NOT native save/load rollback. No fallback reader retry.
-- The caller's hasDelivery() must exclude this module's own live contexts.
-- requireSprite() is an admission preflight; onSpriteRetire/onContentsReset
-- take the authoritative sprite-lifetime token and never read retired memory.
--
-- SaveExport.invalidate marks an already-sized pending schema invalid without
-- changing its size. Invalidation after the writer has started, or a changed
-- native sprite/context between calculation and writing, remains unrecoverable.
-- No safe save abort or rollback of arbitrary replaced writers is claimed.
return function(api, modules, reader, contextAPI, handlerName)
    local function check(ok, message)
        if not ok then error("CBR potion persistence: " .. message, 0) end
    end
    local function functions(value, names, label)
        check(type(value)=="table", "missing "..label)
        for _,name in ipairs(names) do
            check(type(value[name])=="function", "missing "..label.."."..name)
        end
    end
    functions(modules, {"Marshal","Unmarshal","SaveExport","SaveImport"}, "modules")
    functions(modules.Saved, {"export","restore"}, "Saved")
    functions(modules.SavedBinary, {"read"}, "SavedBinary")
    functions(reader, {"ptr","savedRecords","savedOwners","restoreSaved","copyLinked",
        "retire","resetTokens"}, "reader")
    functions(contextAPI, {"timedListPointer","spriteFromPointer","spriteIdentity",
        "hasDelivery","onInvalidate","report"}, "context API")
    handlerName=handlerName or "CBRPQ"
    check(type(handlerName)=="string" and #handlerName>0
        and not handlerName:find("\0",1,true), "invalid handler name")
    local names={"EEex_Sprite_Hook_CalculateExtraEffectListMarshalSize",
        "EEex_Sprite_Hook_WriteExtraEffectListMarshal",
        "EEex_Sprite_LuaHook_ReadExtraEffectListUnmarshal"}
    functions(api,names,"EEex")
    check(type(api.EEex_Sprite_Private_MarshalHandlers)=="table", "missing EEex handler registry")
    check(api.EEex_Sprite_Private_MarshalHandlers[handlerName]==nil, "handler namespace already registered")
    local originals={}
    for _,name in ipairs(names) do originals[name]=api[name] end
    local registry=api.EEex_Sprite_Private_MarshalHandlers
    local failure,notificationFailure,invalidationError=nil,nil,nil
    local exporter
    local calls,writePending=0,false
    local marshalStack,marshalFrames,unmarshalStack,unmarshalFrames={},{},{},{}
    local M={}

    function M.invalidate(reason)
        local first=failure==nil
        failure=failure or tostring(reason)
        if exporter then
            local ok,why=pcall(exporter.invalidate,failure)
            if not ok then invalidationError=invalidationError or tostring(why) end
        end
        if first then
            local ok,why=pcall(contextAPI.onInvalidate,failure)
            if not ok then notificationFailure=tostring(why) end
            pcall(contextAPI.report,failure)
        end
        return false
    end
    local function liveSprite(sprite,expected)
        local pointer=reader.ptr(sprite)
        local token=contextAPI.spriteIdentity(pointer)
        check(token~=nil, "sprite lifetime was not observed")
        if expected then
            check(expected.pointer==pointer and expected.identity==token,
                "sprite lifetime changed during native serialization")
        end
        return {pointer=pointer,identity=token}
    end
    function M.requireSprite(sprite)
        -- Admission calls this BEFORE binding an original or changing expiry.
        -- A pointer/object ID cannot adopt an allocation missed at hook startup.
        check(failure==nil,failure or "ownership disabled")
        return liveSprite(sprite).identity
    end
    local marshal=modules.Marshal(contextAPI.timedListPointer)
    local unmarshal=modules.Unmarshal(function(list,pointer)
        local sprite=contextAPI.spriteFromPointer(pointer)
        check(reader.ptr(sprite)==pointer, "native sprite conversion changed pointer")
        liveSprite(sprite)
        check(contextAPI.timedListPointer(sprite)==list, "Unmarshal is not the sprite timed list")
        local result={}
        for i,record in ipairs(reader.savedRecords(sprite)) do result[i]=record.identity end
        return result
    end,reader.ptr)
    local function marshalContext(sprite)
        local top=marshalStack[#marshalStack]
        check(top~=nil,"missing native Marshal frame")
        -- Validate the allocation BEFORE timed-list field access.
        local owner=liveSprite(sprite,top.owner)
        local ctx=marshal.context(sprite)
        top.owner=owner
        return ctx
    end
    local function unmarshalContext(sprite,memory)
        local ctx=unmarshal.context(sprite,memory)
        if ctx then
            local top=unmarshalStack[#unmarshalStack]
            check(top and top.owner, "missing native Unmarshal lifetime")
            liveSprite(sprite,top.owner)
        end
        return ctx
    end
    exporter=modules.SaveExport(api,modules.Saved,{
        context=marshalContext,
        records=function(sprite) liveSprite(sprite); return reader.savedRecords(sprite) end,
        owners=function(sprite)
            liveSprite(sprite)
            -- SaveExport's own failure path preserves the foreign collection,
            -- corrects its allocation/footer and emits an explicit invalid
            -- marker. Reuse it for failures originating outside its collector.
            check(failure==nil, failure or "ownership disabled")
            local delivery=contextAPI.hasDelivery()
            check(type(delivery)=="boolean", "delivery observer did not return a boolean")
            check(not delivery, "native potion delivery survives the save boundary")
            return reader.savedOwners()
        end,
        invalidate=M.invalidate,
    },handlerName)
    local importer=modules.SaveImport(api,modules.SavedBinary,modules.Saved,{
        savedRecords=reader.savedRecords,
        restoreSaved=function(records,data,saved)
            check(failure==nil, failure or "ownership disabled")
            return reader.restoreSaved(records,data,saved)
        end,
    },{context=unmarshalContext,invalidate=M.invalidate},handlerName)

    -- Protected observational callbacks preserve native control flow. They
    -- deliberately do not early-return merely because ownership was disabled.
    local function observed(fn)
        return function(...)
            local ok,result=pcall(fn,...)
            if not ok then return M.invalidate(result) end
            return result==nil and true or result
        end
    end
    M.marshalEnter=observed(function(frame,list,version,onlyTiming9,excludeTiming2)
        check(marshalFrames[frame]==nil,"native Marshal frame already live")
        marshal.enter(frame,list,version,onlyTiming9,excludeTiming2)
        local entry={frame=frame}
        marshalStack[#marshalStack+1],marshalFrames[frame]=entry,entry
    end)
    M.marshalCounted=observed(marshal.counted)
    M.marshalLeave=observed(function(frame)
        local entry=marshalFrames[frame]
        if entry then check(marshalStack[#marshalStack]==entry,"unbalanced native output return") end
        local result=marshal.leave(frame)
        if entry then marshalStack[#marshalStack],marshalFrames[frame]=nil,nil end
        return result
    end)
    M.unmarshalEnter=observed(function(frame,list,data,size,pointer,version)
        check(unmarshalFrames[frame]==nil,"native Unmarshal frame already live")
        local owner
        if pointer~=0 and version~=0 then
            check(contextAPI.spriteIdentity(pointer)~=nil,"sprite lifetime was not observed")
            local sprite=contextAPI.spriteFromPointer(pointer)
            check(reader.ptr(sprite)==pointer,"native sprite conversion changed pointer")
            owner=liveSprite(sprite)
        end
        unmarshal.enter(frame,list,data,size,pointer,version)
        local entry={frame=frame,owner=owner}
        unmarshalStack[#unmarshalStack+1],unmarshalFrames[frame]=entry,entry
    end)
    M.unmarshalLeave=observed(function(frame)
        local entry=unmarshalFrames[frame]
        if entry then check(unmarshalStack[#unmarshalStack]==entry,"unbalanced native input return") end
        local result=unmarshal.leave(frame)
        if entry then unmarshalStack[#unmarshalStack],unmarshalFrames[frame]=nil,nil end
        return result
    end)
    -- The source pointer is trusted ONLY from the guarded post-CopyFromBase
    -- transport, which excludes DecodeEffectFromBase. No save-buffer guessing.
    M.effectCopy=observed(reader.copyLinked)
    M.effectDestroy=observed(reader.retire)
    local function spriteChanged(pointer,identity,label)
        check(identity~=nil,"missing sprite lifecycle token")
        for _,stack in ipairs({marshalStack,unmarshalStack}) do
            for _,entry in ipairs(stack) do
                local owner=entry.owner
                if owner and owner.pointer==pointer and owner.identity==identity then
                    return M.invalidate(label.." during native persistence")
                end
            end
        end
        return true
    end
    M.onSpriteRetire=observed(function(pointer,identity)
        return spriteChanged(pointer,identity,"sprite allocation retired")
    end)
    M.onContentsReset=observed(function(pointer,identity)
        return spriteChanged(pointer,identity,"sprite contents reset")
    end)

    -- EEex catches importer/exporter exceptions. Remember them outside its
    -- TryIgnore call as well. Serializer failures still propagate; swallowing
    -- them as a successful zero size/count is unsafe.
    local function invoked(fn,...)
        calls=calls+1
        local ok,result=pcall(fn,...)
        calls=calls-1
        if not ok then M.invalidate(result); error(result,0) end
        return result
    end
    function M.exporter(sprite) return invoked(exporter.exporter,sprite) end
    function M.importer(sprite,data) return invoked(importer.importer,sprite,data) end
    function M.calculate(sprite)
        local result=invoked(exporter.calculate,sprite)
        writePending=true
        return result
    end
    function M.write(memory)
        local result=invoked(exporter.write,memory)
        writePending=false
        return result
    end
    function M.read(sprite,memory) return invoked(importer.read,sprite,memory) end
    function M.hasLive()
        return calls>0 or writePending or marshal.hasLive() or unmarshal.hasLive()
    end
    function M.status()
        return {enabled=failure==nil,failure=failure,notificationFailure=notificationFailure,
            invalidationError=invalidationError,
            live=M.hasLive(),writePending=writePending}
    end
    function M.reset()
        -- A quiescent lifecycle reset is explicit; never use this as failure
        -- cleanup. A failed writer leaves its allocation pending and requires
        -- a restart, not forgetting that allocation. Failure stays sticky.
        check(not M.hasLive(),"cannot reset in-flight native persistence")
        reader.resetTokens()
        marshal.reset(); unmarshal.reset()
        marshalStack,marshalFrames,unmarshalStack,unmarshalFrames={},{},{},{}
        return failure==nil
    end
    function M.bindings()
        -- Lab owns the atomic registration/replacement and its rollback. This
        -- method performs no mutations and rejects stale preflight snapshots.
        check(registry==api.EEex_Sprite_Private_MarshalHandlers
            and registry[handlerName]==nil,"handler registry changed before binding")
        local replacements={}
        local wrapped={M.calculate,M.write,M.read}
        for i,name in ipairs(names) do
            check(api[name]==originals[name],"EEex function changed before binding: "..name)
            replacements[i]={name=name,original=originals[name],replacement=wrapped[i]}
        end
        return {handlerName=handlerName,registry=registry,exporter=M.exporter,
            importer=M.importer,replacements=replacements}
    end
    return M
end
