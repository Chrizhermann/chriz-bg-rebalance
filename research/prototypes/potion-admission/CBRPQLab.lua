-- Manual lab composition only. Loading this file has no side effects.
-- No M_ loader, WeiDU component or automatic game installation is provided.
local M = {}
local keys = {"useBegin", "useQueue", "useEnd", "fireBegin", "fireQueue", "fireEnd",
    "useProjectile", "fireProjectile", "messageEnter", "messageLeave", "destroy", "effectDestroy", "admit"}

function M.prepare(api, parts, manifest, report)
    assert(api == _G, "potion lab callbacks must be registered in the global Lua state")
    assert(not M.prepared, "potion lab already prepared; restart for another manifest/policy")
    assert(type(report) == "function", "potion lab requires a visible diagnostic callback")
    assert(type(api.EEex_GameState_AddDestroyedListener) == "function",
        "potion lab requires game-session destruction notification")
    local reader = parts.native(api, manifest)
    local needsExtended=false
    for _,source in pairs(manifest.sources or {}) do
        for _,record in pairs(source.records or {}) do
            needsExtended=needsExtended or record.nativeSourceType~=nil or record.opcode==98
        end
    end
    local runtime,linked
    if needsExtended then
        assert(type(parts.linked)=="function","linked potion composition is unavailable")
        linked=parts.linked(api,parts,reader,manifest,report,function() return runtime end)
    end
    runtime = parts.runtime(parts.core, parts.messages, reader, manifest, report,
        linked and linked.runtimeParts or nil)
    local config,callbacks = {callbacks = {}},{}
    for _, key in ipairs(keys) do
        assert(type(runtime[key]) == "function", "missing potion runtime callback " .. key)
        callbacks[key]=runtime[key]
    end
    if linked then
        for _,key in ipairs(linked.castKeys()) do
            callbacks[key]=assert(runtime[key],"missing linked runtime callback "..key)
        end
        for key,fn in pairs(linked.callbacks) do
            assert(callbacks[key]==nil,"overlapping linked callback "..key)
            callbacks[key]=fn
        end
    end
    callbacks.reset=linked and linked.reset or runtime.reset
    -- Check the entire namespace before publishing its first function.
    for key,fn in pairs(callbacks) do
        assert(type(fn)=="function","missing callback "..key)
        local name="CBRPQ_Lab_"..key
        assert(api[name]==nil,"potion lab callback namespace is already occupied: "..name)
        config.callbacks[key]=name
    end
    for key,fn in pairs(callbacks) do api[config.callbacks[key]]=fn end
    if linked then linked.configure(config.callbacks) end
    local lab = {runtime = runtime, linked=linked, config = config, attempted = false, armed = false}

    function lab.validate()
        -- Read-only validation runs for BOTH modules before any code patch.
        for key,fn in pairs(callbacks) do
            assert(api[config.callbacks[key]]==fn,"potion callback changed before installation: "..key)
        end
        parts.transport.validate(api, config, parts.watchdog)
        parts.hook.validate(api, config.callbacks.admit, parts.watchdog)
        if linked then linked.validate() end
        return true
    end
    local ok, err = pcall(lab.validate)
    if not ok then
        for key,fn in pairs(callbacks) do
            if api[config.callbacks[key]]==fn then api[config.callbacks[key]]=nil end
        end
        runtime.disable(err)
        error(err, 0)
    end
    M.prepared = true
    api.EEex_GameState_AddDestroyedListener(callbacks.reset)
    function lab.arm()
        assert(not lab.attempted, "potion lab hook installation was already attempted; restart required")
        lab.validate()
        lab.attempted = true
        local installed, installError = pcall(function()
            if linked then linked.prepareNative() end
            parts.transport.install(api, config, parts.watchdog)
            if linked then linked.install() end
            parts.hook.install(api, config.callbacks.admit, parts.watchdog)
            if linked then linked.bind() end
        end)
        if not installed then
            runtime.disable(installError)
            error("potion lab installation failed; restart required: " .. tostring(installError), 0)
        end
        lab.armed = true
        return lab
    end
    function lab.disable(reason) runtime.disable(reason) end
    return lab
end

return M
