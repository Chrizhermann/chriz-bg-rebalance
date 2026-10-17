-- Inert early-startup handoff. Nothing is installed by loading this file or
-- calling prepare(). The explicit arm() belongs to the pinned EEex_Modules
-- startup call, before CBaldurChitin construction. There is no late adoption.
local M={}
local chitinGlobalRva,gamePointerOffset=0x667548,0x1090
M.chitinGlobalRva=chitinGlobalRva -- g_pBaldurChitin; NOT SDL's pointer at 667558.
M.gamePointerOffset=gamePointerOffset
local keys={"beginDefault","beginData","readyDefault","readyData","destroy","clear"}
local providerNames={"EEex_GetImageBase","EEex_ReadPtr","EEex_ReadU8",
    "EEex_GenLuaCall","EEex_FlattenTable","EEex_HookBeforeRestoreWithLabels",
    "EEex_DisableCodeProtection","EEex_EnableCodeProtection"}

function M.prepare(api,parts,config)
    local function check(ok,message)
        if not ok then error("CBR potion early startup: "..message,0) end
    end
    local function pointer(value)
        return type(value)=="number" and value==math.floor(value)
            and value>0 and value<9007199250000000
    end
    check(type(api)=="table" and type(parts)=="table" and type(config)=="table",
        "API, modules and configuration are required")
    local lifetime=parts.spriteLifetime
    check(type(lifetime)=="table" and type(lifetime.new)=="function"
        and type(lifetime.prepare)=="function","SpriteLifetime provider is unavailable")
    check(type(config.report)=="function","early report callback is required")
    local prefix=config.callbackPrefix or "CBRPQ_Early_"
    local receiptName=config.receiptName or "CBRPQEarlyReceipt"
    check(type(prefix)=="string" and prefix:match("^[%a_][%w_]*$"),"invalid callback prefix")
    check(type(receiptName)=="string" and receiptName:match("^[%a_][%w_]*$"),"invalid receipt name")
    local names,providers={},{}
    for _,key in ipairs(keys) do
        names[key]=prefix..key
        check(names[key]~=receiptName,"receipt and callback names overlap")
    end
    for _,name in ipairs(providerNames) do
        check(type(api[name])=="function","missing API "..name)
        providers[name]=api[name]
    end
    local watchdog,watchdogEnabled=parts.watchdog,api.EEex_HookIntegrityWatchdog_Load
    check(type(watchdogEnabled)=="boolean","watchdog state unavailable")
    local watchdogValidate,watchdogPreserve
    if watchdogEnabled then
        check(type(watchdog)=="table" and type(watchdog.validate)=="function"
            and type(watchdog.withPreservation)=="function","watchdog provider unavailable")
        watchdogValidate,watchdogPreserve=watchdog.validate,watchdog.withPreservation
    end
    local lifetimeNew,lifetimePrepare=lifetime.new,lifetime.prepare
    local earlyReport=config.report
    local attempted,complete,attached=false,false,false
    local failure,registry,receipt,base,sinks,registryMethods,callbacks,callbackRefs
    local completionIdentity=setmetatable({}, {
        __newindex=function() error("CBR potion early startup: immutable completion identity",0) end,
        __metatable=false,
    })

    local function providersUnchanged()
        for name,fn in pairs(providers) do
            check(api[name]==fn,"provider changed: "..name)
        end
        check(lifetime.new==lifetimeNew and lifetime.prepare==lifetimePrepare,
            "SpriteLifetime provider changed")
        check(api.EEex_HookIntegrityWatchdog_Load==watchdogEnabled,"watchdog state changed")
        if watchdogEnabled then
            check(watchdog.validate==watchdogValidate and watchdog.withPreservation==watchdogPreserve,
                "watchdog provider changed")
        end
    end
    local function earlyPhase()
        check(api.EEex_Active~=true,"EEex startup already completed")
        local current=providers.EEex_GetImageBase()
        check(pointer(current) and (base==nil or current==base),"image base changed or invalid")
        check(providers.EEex_ReadPtr(current+chitinGlobalRva)==0,
            "CBaldurChitin already exists; lifetime observation must begin earlier")
        return current
    end
    local function healthy()
        check(not failure,"startup failed: "..tostring(failure))
        check(registry and registry.callbacks==callbacks,"lifetime callback table changed")
        for name,fn in pairs(registryMethods) do
            check(registry[name]==fn,"lifetime method changed: "..name)
        end
        for _,key in ipairs(keys) do
            check(callbacks[key]==callbackRefs[key],"lifetime callback changed: "..key)
            check(api[names[key]]==callbacks[key],"published callback changed: "..names[key])
        end
        local state=registry.status()
        check(type(state)=="table" and not state.halted,
            "lifetime observer is halted: "..tostring(state and state.error))
    end
    local function latePhase()
        check(complete and receipt~=nil and api[receiptName]==receipt,"completed early receipt is unavailable or replaced")
        check(next(receipt)==nil and next(completionIdentity)==nil,"early receipt or completion identity was modified")
        providersUnchanged();healthy()
        check(api.EEex_Active==true,"EEex startup has not completed")
        check(providers.EEex_GetImageBase()==base,"image base changed")
        local chitin=providers.EEex_ReadPtr(base+chitinGlobalRva)
        check(pointer(chitin),"CBaldurChitin is unavailable during late setup")
        check(providers.EEex_ReadPtr(chitin+gamePointerOffset)==0,
            "CInfGame already exists; late observer setup is no longer permitted")
        return true
    end
    local function notify(name,...)
        if sinks then return sinks[name](...) end
        -- Before attachment no component owns sprite content. Allocation
        -- bookkeeping still runs, including default constructors and failure.
    end
    local function report(reason)
        if sinks then return sinks.report(reason) end
        return earlyReport(reason)
    end

    local B={}
    function B.status()
        local state=registry and registry.status()
        return {attempted=attempted,complete=complete,attached=attached,
            halted=failure~=nil or (state and state.halted) or false,
            error=failure or (state and state.error)}
    end
    function B.arm()
        check(not attempted,"installation was already attempted; restart required")
        providersUnchanged()
        base=earlyPhase()
        check(api[receiptName]==nil,"receipt namespace is occupied: "..receiptName)
        for _,key in ipairs(keys) do
            check(api[names[key]]==nil,"callback namespace is occupied: "..names[key])
        end
        registry=lifetimeNew({imageBase=base,readPtr=providers.EEex_ReadPtr,
            onRetire=function(...) return notify("onRetire",...) end,
            onContentsReset=function(...) return notify("onContentsReset",...) end,
            onReset=function(...) return notify("onReset",...) end,report=report})
        callbacks=registry.callbacks
        registryMethods={identity=registry.identity,reset=registry.reset,status=registry.status}
        callbackRefs={}
        local overlay=setmetatable({}, {__index=api})
        for _,key in ipairs(keys) do
            check(type(callbacks[key])=="function","missing lifetime callback "..key)
            callbackRefs[key]=callbacks[key]
            overlay[names[key]]=callbacks[key]
        end
        local plan=lifetimePrepare(overlay,{callbacks=names},watchdog)
        check(plan.base==base and #plan.descriptors==6,"lifetime plan does not contain all six observers")
        providersUnchanged();earlyPhase()
        check(api[receiptName]==nil,"receipt namespace changed during preflight")
        for _,key in ipairs(keys) do
            check(api[names[key]]==nil,"callback namespace changed during preflight: "..names[key])
        end
        -- All format/provider/namespace checks above precede publication or
        -- native patching. After this point a failure is restart-only: a hook
        -- call may have modified native code before throwing.
        attempted=true
        local ok,why=pcall(function()
            for _,key in ipairs(keys) do api[names[key]]=callbacks[key] end
            local function install()
                local disabled,disableError=pcall(providers.EEex_DisableCodeProtection)
                local installed,installError=pcall(function()
                    if not disabled then error(disableError,0) end
                    for _,entry in ipairs(plan.descriptors) do
                        local result=providers.EEex_HookBeforeRestoreWithLabels(entry.address,0,entry.restoreSize,
                            entry.restoreSize,entry.labels,entry.assembly)
                        check(result~=false,"native observer installation rejected "..entry.key)
                    end
                end)
                local protected,protectError=pcall(providers.EEex_EnableCodeProtection)
                if not installed then
                    if not protected then error(tostring(installError).."; protection restore failed: "..tostring(protectError),0) end
                    error(installError,0)
                end
                if not protected then error(protectError,0) end
            end
            if plan.watchdog then watchdogPreserve(api,install) else install() end
            providersUnchanged();earlyPhase();healthy()
            local contents={registry=registry,completionIdentity=completionIdentity,validateLate=latePhase}
            contents.attach=function(newSinks)
                check(not attached,"runtime sinks have already been attached")
                latePhase()
                check(type(newSinks)=="table","runtime sinks are required")
                local captured={}
                for _,name in ipairs({"onRetire","onContentsReset","onReset","report"}) do
                    check(type(newSinks[name])=="function","missing runtime sink "..name)
                    captured[name]=newSinks[name]
                end
                sinks=captured;attached=true
                return registry
            end
            receipt=setmetatable({}, {__index=contents,
                __newindex=function() error("CBR potion early startup: receipt is immutable",0) end,
                __metatable=false})
            api[receiptName]=receipt
            check(api[receiptName]==receipt,"receipt publication failed")
            complete=true
        end)
        if not ok then
            failure=tostring(why)
            if receipt and api[receiptName]==receipt then api[receiptName]=nil end
            receipt=nil;complete=false
            pcall(earlyReport,failure)
            error(failure,0)
        end
        return receipt
    end
    return B
end
return M
