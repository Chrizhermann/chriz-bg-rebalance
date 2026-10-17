-- Inert composition for original146/mode1 lineage and persistence observers.
-- The outer lab validates EVERY provider before its first native patch. This
-- file neither loads itself nor invokes install/bind during construction.
return function(api,parts,reader,manifest,report,getRuntime)
    local function check(ok,message)
        if not ok then error("CBR linked potion composition: "..message,0) end
    end
    for _,name in ipairs({"EEex_GetImageBase","EEex_ReadPtr","EEex_PtrToUD",
            "EEex_UDToPtr","EEex_HookBeforeRestoreWithLabels",
            "EEex_DisableCodeProtection","EEex_EnableCodeProtection"}) do
        check(type(api[name])=="function","missing API "..name)
    end
    for _,name in ipairs({"persistence","lineage","marshal","unmarshal","saveExport","saveImport"}) do
        check(type(parts[name])=="function","missing module "..name)
    end
    for _,name in ipairs({"saved","savedBinary","castTransport",
            "marshalTransport","unmarshalTransport","copyTransport"}) do
        check(type(parts[name])=="table","missing module "..name)
    end
    local needsLinked,needsRegen=false,false
    for _,source in pairs(manifest.sources) do
        for _,record in pairs(source.records) do
            needsLinked=needsLinked or record.nativeSourceType~=nil
            needsRegen=needsRegen or record.opcode==98
        end
    end
    local receipt=parts.earlyReceipt
    check(type(receipt)=="table" and type(receipt.registry)=="table"
        and type(receipt.validateLate)=="function" and type(receipt.attach)=="function"
        and type(receipt.completionIdentity)=="table","completed early lifetime receipt is required")
    local lifetime=receipt.registry
    local completionIdentity=receipt.completionIdentity
    local persistence,regeneration
    local M={callbacks={},configs={}}
    local function runtime() return assert(getRuntime(),"runtime is not constructed") end
    local function failure(reason)
        local value=getRuntime()
        if value then value.disable(reason) else pcall(report,reason) end
    end
    local sinks={
        onRetire=function(pointer,identity)
            runtime().onSpriteContentsInvalidated(pointer,identity)
            persistence.onSpriteRetire(pointer,identity)
            if regeneration then regeneration.onSpriteDestroy(pointer) end
        end,
        onContentsReset=function(pointer,identity)
            runtime().onSpriteContentsInvalidated(pointer,identity)
            persistence.onContentsReset(pointer,identity)
            if regeneration then regeneration.onSpriteDestroy(pointer) end
        end,
        onReset=function() check(runtime().reset()~=false,"runtime reset did not complete") end,
        report=failure,
    }
    persistence=parts.persistence(api,{
        Marshal=parts.marshal,Unmarshal=parts.unmarshal,SaveExport=parts.saveExport,
        SaveImport=parts.saveImport,Saved=parts.saved,SavedBinary=parts.savedBinary,
    },reader,{
        timedListPointer=function(sprite)
            local pointer=reader.ptr(sprite)
            local list=api.EEex_UDToPtr(sprite.m_timedEffectList)
            check(list==pointer+0x4A00,"sprite timed-list binding differs from pinned native offset")
            return list
        end,
        spriteFromPointer=function(pointer) return api.EEex_PtrToUD(pointer,"CGameSprite") end,
        spriteIdentity=lifetime.identity,
        hasDelivery=function() return runtime().hasDelivery() end,
        onInvalidate=failure,report=report,
    },"CBRPQ")
    for _,name in ipairs({"requireSprite","onSpriteRetire","onContentsReset"}) do
        check(type(persistence[name])=="function","missing persistence lifecycle "..name)
    end
    M.persistence,M.lifetime=persistence,lifetime
    M.runtimeParts={lineage=parts.lineage,persistence=persistence}
    if needsRegen then
        for _,name in ipairs({"regenNative","regenServices","regenLifecycle"}) do
            check(type(parts[name])=="table","missing module "..name)
        end
        regeneration=parts.regenNative.new(api,reader,lifetime,{
            adapter=parts.regenAdapter,cache=parts.regenCache,recovery=parts.regenRecovery,services=parts.regenServices,
        },failure)
        M.regeneration,M.runtimeParts.regeneration=regeneration,regeneration
        for name,fn in pairs(regeneration.callbacks) do M.callbacks["regen_"..name]=fn end
    end
    M.callbacks.marshalEnter=persistence.marshalEnter
    M.callbacks.marshalCounted=persistence.marshalCounted
    M.callbacks.marshalLeave=persistence.marshalLeave
    M.callbacks.unmarshalEnter=persistence.unmarshalEnter
    M.callbacks.unmarshalLeave=persistence.unmarshalLeave
    M.callbacks.effectCopy=persistence.effectCopy
    local castKeys=needsLinked and {"parentQueued","castEnter","castLeave","castDestroy","childCreated",
        "childQueued","childProjectile","childDirectEnter","childDirectLeave"} or {}

    function M.configure(names)
        M.configs.marshal={callbacks={enter=names.marshalEnter,counted=names.marshalCounted,leave=names.marshalLeave}}
        M.configs.unmarshal={callbacks={enter=names.unmarshalEnter,leave=names.unmarshalLeave}}
        M.configs.copy={callbacks={copied=names.effectCopy}}
        M.configs.cast={callbacks={}}
        for _,name in ipairs(castKeys) do M.configs.cast.callbacks[name]=names[name] end
        if regeneration then
            M.configs.regen={callbacks={}}
            for name in pairs(regeneration.callbacks) do M.configs.regen.callbacks[name]=names["regen_"..name] end
        end
    end
    function M.castKeys() return castKeys end
    function M.reset() return lifetime.reset() end

    local regenPlan,bindingPlan,bound,attempted,nativeInstalled,attached
    local function validateReceipt()
        check(receipt.registry==lifetime and receipt.completionIdentity==completionIdentity,
            "early lifetime receipt changed")
        check(receipt.validateLate()==true,"early lifetime receipt validation failed")
    end
    function M.validate()
        check(not bound,"persistence is already bound")
        validateReceipt()
        check(not lifetime.status().halted,"sprite lifetime observer is halted")
        check(persistence.status().enabled,"persistence is disabled")
        bindingPlan=persistence.bindings()
        if needsLinked then parts.castTransport.validate(api,M.configs.cast,parts.watchdog) end
        parts.marshalTransport.validate(api,M.configs.marshal,parts.watchdog)
        parts.unmarshalTransport.validate(api,M.configs.unmarshal,parts.watchdog)
        parts.copyTransport.validate(api,M.configs.copy,parts.watchdog)
        if regeneration then
            regeneration.validateServices("CBRPQ_PreparedRegen")
            regenPlan=parts.regenLifecycle.prepare(api,M.configs.regen,parts.watchdog)
        end
        return true
    end
    function M.install()
        check(attached and bindingPlan~=nil,"composition has not attached its early lifetime registry")
        check(not attempted,"native installation already attempted; restart required")
        attempted=true
        if regeneration then check(regeneration.status().servicesPrepared,"native services are not prepared") end
        local function regenHooks()
            api.EEex_DisableCodeProtection()
            local ok,why=pcall(function()
                if regenPlan then
                    for _,entry in ipairs(regenPlan.descriptors) do
                        api.EEex_HookBeforeRestoreWithLabels(entry.address,0,entry.restoreSize,
                            entry.restoreSize,entry.labels,entry.assembly)
                    end
                end
            end)
            api.EEex_EnableCodeProtection()
            if not ok then error(why,0) end
        end
        if regenPlan then
            if regenPlan.watchdog then parts.watchdog.withPreservation(api,regenHooks)
            else regenHooks() end
        end
        parts.marshalTransport.install(api,M.configs.marshal,parts.watchdog)
        parts.unmarshalTransport.install(api,M.configs.unmarshal,parts.watchdog)
        parts.copyTransport.install(api,M.configs.copy,parts.watchdog)
        if needsLinked then parts.castTransport.install(api,M.configs.cast,parts.watchdog) end
        nativeInstalled=true
    end
    function M.prepareNative()
        check(bindingPlan~=nil,"composition has not passed preflight")
        check(not attached,"early lifetime sinks are already attached")
        validateReceipt()
        check(receipt.attach(sinks)==lifetime,"early lifetime attachment returned another registry")
        attached=true
        if regeneration then regeneration.prepareServices("CBRPQ_PreparedRegen") end
    end
    function M.bind()
        -- Recheck exactly the captured registry/functions immediately before
        -- publishing all three wrappers and the single owned handler. No native
        -- call or Lua yield occurs between these ordinary table assignments.
        check(not bound,"persistence is already bound")
        check(nativeInstalled,"native persistence observers are not installed")
        local plan=persistence.bindings()
        local handler={exporter=plan.exporter,importer=plan.importer}
        local changed={}
        local ok,why=pcall(function()
            for _,entry in ipairs(plan.replacements) do
                api[entry.name]=entry.replacement
                changed[#changed+1]=entry
            end
            plan.registry[plan.handlerName]=handler
        end)
        if not ok then
            if plan.registry[plan.handlerName]==handler then plan.registry[plan.handlerName]=nil end
            for _,entry in ipairs(changed) do
                if api[entry.name]==entry.replacement then api[entry.name]=entry.original end
            end
            persistence.invalidate(why)
            error(why,0)
        end
        bound=true
    end
    return M
end
