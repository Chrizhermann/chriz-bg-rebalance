-- Explicit lab bridge. No autoload, installation, resource edits or persisted pointers.
-- env is CBRPQNative's read-only adapter; every native callback is contained here.
return function(core, messageFactory, env, manifest, report, parts)
    parts=parts or {}
    local needsLinked,needsRegen=false,false
    -- The read-only reader and isolated adapter tests have broader capabilities
    -- than this connected runtime. Never silently advertise those as active.
    for source,entry in pairs(manifest.sources) do
        for _,record in pairs(entry.records or {}) do
            needsLinked=needsLinked or record.nativeSourceType~=nil
            needsRegen=needsRegen or record.opcode==98
        end
    end
    if needsRegen then
        assert(type(parts.regeneration)=="table",
            "potion regeneration cache/recovery integration is unavailable")
        for _,name in ipairs({"prepare","status","onOriginalDestroy","reset"}) do
            assert(type(parts.regeneration[name])=="function","potion regeneration lacks "..name)
        end
    end
    if needsLinked or needsRegen then
        assert(type(parts.persistence)=="table" and (not needsLinked or type(parts.lineage)=="function"),
            "linked potion transport/save integration is unavailable")
        for _,name in ipairs({"hasLive","reset","invalidate","status","requireSprite"}) do
            assert(type(parts.persistence[name])=="function",
                "linked potion persistence lacks "..name)
        end
        for _,name in ipairs({"carrier","bindLinked","retire","resetTokens"}) do
            assert(type(env[name])=="function","linked potion native reader lacks "..name)
        end
    end
    local messages = messageFactory(core)
    local enabled, failure = true, nil
    local invocations, frames, frameByMessage = {use = {}, fire = {}}, {}, {}
    local ownedDepth, admitting = 0, false
    local actorEpochs=setmetatable({},{__mode="k"})
    local M, lineage = {}, nil

    local function clearDelivery()
        messages.reset()
        if lineage then lineage.reset() end
        invocations, frames, frameByMessage = {use = {}, fire = {}}, {}, {}
        ownedDepth, admitting = 0, false
        actorEpochs=setmetatable({},{__mode="k"})
    end
    local function stop(reason)
        enabled, failure = false, tostring(reason)
        -- Metadata invalidation must leave a native Marshal/Unmarshal frame
        -- alive until its matching return. Delivery state is independent.
        if parts.persistence then pcall(parts.persistence.invalidate,failure) end
        clearDelivery()
        if report then pcall(report, failure) end
        return false -- Preserve native admission on any unsupported/error path.
    end
    local function guarded(fn, observeAfterDisable)
        return function(...)
            if not enabled and not observeAfterDisable then return false end
            local ok, result = pcall(fn, ...)
            if not ok then return stop(result) end
            return result
        end
    end
    local function index(value, name)
        assert(type(value) == "number" and value >= 0 and value <= 65534
            and value == math.floor(value), "invalid " .. name)
        return tostring(value)
    end
    local function begin(kind, frame, ability)
        assert(frame ~= nil and frame ~= 0, "missing native invocation frame")
        assert(invocations[kind][frame] == nil, "native invocation frame already live")
        invocations[kind][frame] = {abilityIndex = index(ability, "ability index"), token = {}}
    end
    local function queue(kind, frame, message, effect, ordinal, projectile)
        if message == 0 then return end -- Native allocation failure, no tag to retain.
        local context = assert(invocations[kind][frame], "queue outside native invocation")
        local ordinalKey = index(ordinal, "effect ordinal")
        local sourceName, sourceType = env.source(effect)
        if sourceType ~= 2 then return end
        local source = manifest.sources[sourceName]
        if not source then return end
        local ability = assert(source.abilities[context.abilityIndex], "ability absent from manifest")
        local expectedKey = ability.effects[ordinalKey]
        local carrier = ability.carriers and ability.carriers[ordinalKey]
        assert(ordinal < ability.count and expectedKey ~= nil, "ordinal absent from manifest")
        if expectedKey == false and not carrier then return end -- Original instant/adverse/unowned record.
        if projectile ~= nil then
            assert(type(env.isInstantProjectile) == "function" and env.isInstantProjectile(projectile),
                "owned potion projectile is not the verified instant delivery class")
        end
        if carrier then
            assert(expectedKey==false,"carrier is also classified as a bonus")
            env.carrier(effect,sourceName,carrier.fields,true)
        else
            local record = assert(env.identify(effect, expectedKey, true), "owned native record changed")
            assert(record.key == expectedKey and record.source == sourceName,
                "native record disagrees with manifest")
        end
        if not context.dose then
            context.source = sourceName
            context.dose = messages.begin(context.token, source.family,
                {source=sourceName,ability=ability}, ability.quotas)
            context.dose.objects = {}
        end
        assert(context.source == sourceName, "source changed within one native invocation")
        if projectile ~= nil then messages.defer(context.token, env.ptr(effect), ordinal)
        else messages.queue(context.token, message, env.ptr(effect), ordinal) end
    end
    local function finish(kind, frame)
        local context = assert(invocations[kind][frame], "end outside native invocation")
        if context.dose then messages.endInvocation(context.token) end
        invocations[kind][frame] = nil
    end

    M.useBegin = guarded(function(frame, ability) begin("use", frame, ability) end)
    M.useQueue = guarded(function(frame, message, effect, ordinal) queue("use", frame, message, effect, ordinal) end)
    M.useEnd = guarded(function(frame) finish("use", frame) end)
    M.fireBegin = guarded(function(frame, ability) begin("fire", frame, ability) end)
    M.fireQueue = guarded(function(frame, message, effect, ordinal) queue("fire", frame, message, effect, ordinal) end)
    M.fireEnd = guarded(function(frame) finish("fire", frame) end)
    M.useProjectile = guarded(function(frame, effect, ordinal, projectile)
        assert(projectile ~= nil, "missing potion projectile pointer")
        queue("use", frame, nil, effect, ordinal, projectile)
    end)
    M.fireProjectile = guarded(function(frame, effect, ordinal, projectile)
        assert(projectile ~= nil, "missing potion projectile pointer")
        queue("fire", frame, nil, effect, ordinal, projectile)
    end)

    local function enter(message, effect, noSave)
        assert(type(noSave) == "number" or type(noSave) == "boolean", "invalid native noSave")
        local skipSave = noSave == true or (type(noSave) == "number" and noSave ~= 0)
        local ticket = messages.enter(message, effect, skipSave)
        assert(not ticket.unsupportedNoSave, "owned potion delivery bypasses native rejection with noSave")
        -- A nested owned delivery can run before its parent's original effect
        -- has reached the timed list. Lifetime tokens handle address reuse, but
        -- partial native application still needs a separate transaction design.
        if ticket.dose then
            local ref=ticket.abilityKey
            assert(type(ref)=="table" and type(ref.ability)=="table","missing dose registry context")
            ticket.bonus=ref.ability.effects[tostring(ticket.ordinal)]~=false
        end
        assert(not ticket.bonus or ownedDepth == 0, "nested owned AddEffect is outside this lab")
        if ticket.bonus then ownedDepth = ownedDepth + 1 end
        assert(frameByMessage[message] == nil, "message already executing")
        frames[#frames + 1], frameByMessage[message] = ticket, ticket
    end
    local function leave(message)
        local ticket = frameByMessage[message]
        if not ticket then return end -- A reset can invalidate an in-flight return.
        assert(frames[#frames] == ticket, "native message returns are unbalanced")
        if ticket.bonus then ownedDepth = ownedDepth - 1 end
        messages.leave(ticket)
        frames[#frames], frameByMessage[message] = nil, nil
    end
    M.messageEnter, M.messageLeave = guarded(enter), guarded(leave)
    if needsLinked then
        lineage=parts.lineage(messages,env,manifest,enter,leave,parts.persistence.requireSprite)
        for _,name in ipairs({"parentQueued","castEnter","childCreated","childQueued",
                "childProjectile","childDirectEnter","childDirectLeave","castLeave","castDestroy"}) do
            M[name]=guarded(assert(lineage[name],"missing lineage callback "..name))
        end
    end
    M.destroy = guarded(function(message)
        if message ~= 0 then messages.destroy(message) end
    end)
    M.effectDestroy = guarded(function(effectPointer)
        assert(type(env.retire) == "function", "native effect lifetime tracking is unavailable")
        local ok,why=true,nil
        if needsRegen then ok,why=pcall(parts.regeneration.onOriginalDestroy,effectPointer) end
        if lineage then lineage.effectDestroy(effectPointer) end
        messages.destroyEffect(effectPointer)
        env.retire(effectPointer)
        if not ok then error(why,0) end
    end,true)
    M.admit = guarded(function(effect, sprite)
        local frame = messages.top(env.ptr(effect))
        if not frame then return false end -- Unrelated/reconstructed/noSave=true.
        assert(not admitting, "reentrant admission callback")
        assert(env.isSelf(effect, sprite), "tagged potion did not reach its drinker")
        if needsLinked or needsRegen then
            local identity=parts.persistence.requireSprite(sprite)
            local pointer=env.ptr(sprite)
            local epoch=actorEpochs[identity]
            if not epoch then epoch={}; actorEpochs[identity]=epoch end
            local dose=frame.dose
            if dose.actorIdentity==nil then
                dose.actorIdentity,dose.actorPointer,dose.actorEpoch=identity,pointer,epoch
            end
            assert(dose.actorIdentity==identity and dose.actorPointer==pointer
                and dose.actorEpoch==epoch,"potion dose target allocation/contents changed before admission")
        end
        local ref=frame.abilityKey
        local sourceName=ref.source
        local source = assert(manifest.sources[sourceName])
        local ability=ref.ability
        local ordinal=tostring(frame.ordinal)
        local expectedKey=ability.effects[ordinal]
        assert(expectedKey~=nil,"tagged ordinal disappeared")
        if expectedKey==false then
            local carrier=assert(ability.carriers and ability.carriers[ordinal],"tagged unowned record")
            env.carrier(effect,sourceName,carrier.fields,true,ref.nativeSource)
            return false -- Preserve native casting; only its proven children own bonuses.
        end
        local incoming = assert(env.identify(effect, expectedKey, true), "tagged effect changed before admission")
        assert((incoming.ownerSource or incoming.source) == sourceName and source.family == frame.dose.family
            and incoming.key == expectedKey, "dose record changed before admission")
        admitting = true
        local active = env.active(sprite, frame.dose.objects)
        local plan = core.plan(incoming, active, manifest, env.now(), frame.dose.state)
        local transaction=needsRegen and parts.regeneration.prepare(plan,sprite) or nil
        local allow, state = core.commit(plan)
        frame.dose.state=state
        if transaction then
            -- Core has committed the original deadlines. A later native cache
            -- failure cannot turn this rejected repeat into a newly admitted
            -- bonus. Preserve the completed admission decision, halt, and keep
            -- the adapter's uncertain allocation handles for diagnosis.
            local ok,why=pcall(function()
                transaction.commit()
                local status=parts.regeneration.status()
                assert(not status.halted,status.error or "regeneration adapter halted")
            end)
            if not ok then stop(why); return not allow end
        end
        admitting = false
        return not allow
    end)

    function M.reset()
        -- Normal DestroyGame cancels native messages before EEex's destroyed
        -- listener; LoadGame does so before Unmarshal. Forgetting a surviving
        -- tag could silently admit its bonus as unrelated after a direct reset.
        if M.hasDelivery() or parts.persistence and parts.persistence.hasLive() then
            return stop("game-state reset with surviving potion delivery; restart required")
        end
        if parts.persistence then
            if needsRegen then
                local ok,reason=pcall(parts.regeneration.reset)
                if not ok then return stop(reason) end
            end
            local ok,reason=pcall(parts.persistence.reset)
            if not ok then return stop(reason) end
        end
        clearDelivery() -- Never serializes or replays a native pointer/token.
        if env.resetTokens then env.resetTokens() end
    end
    function M.hasDelivery()
        return messages.hasLive() or next(invocations.use)~=nil or next(invocations.fire)~=nil
            or #frames>0 or lineage~=nil and lineage.hasLive()
    end
    function M.onSpriteContentsInvalidated(pointer,identity)
        -- ClearMarshal may reuse the same allocation for newly decoded
        -- contents. Outstanding child messages retain the previous dose epoch;
        -- a new dose after a legitimate clear obtains the new epoch normally.
        actorEpochs[identity]={}
        if enabled and lineage and lineage.referencesSprite(pointer,identity) then
            return stop("potion cast target was destroyed or cleared before delivery completed")
        end
    end
    function M.disable(reason) if enabled then stop(reason or "lab disabled") end end
    function M.status() return enabled, failure end
    return M
end
