-- Offline prototype only. Returns a factory; no autoload, hooks or native calls.
-- The adapter must prove one begin/endInvocation pair per native delivery loop,
-- tag before AddMessage, and balance every enter with leave(ticket), including
-- unrelated messages. Destroy must be called for messages canceled before Run.
-- Keys are adapter-normalized identities, never persisted native pointers.
return function(core)
    local function requireValue(ok, message)
        if not ok then error("CBR potion messages: " .. message, 0) end
    end
    requireValue(type(core) == "table" and type(core.newDose) == "function", "invalid core")
    local MAX_EXACT_INTEGER, MAX_ORDINAL = 9007199254740991, 65534
    local function validKey(key)
        local kind = type(key)
        return kind == "table" or (kind == "string" and #key > 0)
            or (kind == "number" and key > 0 and key <= MAX_EXACT_INTEGER
                and key == math.floor(key))
    end
    local function checkKey(key, name)
        requireValue(validKey(key), "invalid " .. name)
    end
    local invocations, messages, effects, stack = {}, {}, {}, {}
    local frameMessages, frameEffects = {}, {}
    -- Weak keys let obsolete frame tickets be collected after reset. A caller
    -- retaining a ticket can still leave safely after a generation change.
    local tickets = setmetatable({}, {__mode = "k"})
    local doses = setmetatable({}, {__mode = "k"})
    local generation, sequence = 1, 0
    local M = {}

    local function removeTag(tag)
        if tag.messageKey and messages[tag.messageKey] == tag then messages[tag.messageKey] = nil end
        if effects[tag.effectKey] == tag then effects[tag.effectKey] = nil end
        tag.valid = false
    end

    function M.begin(invocationKey, family, abilityKey, quotas)
        checkKey(invocationKey, "invocation key")
        checkKey(abilityKey, "ability key")
        requireValue(type(family) == "string" and #family > 0, "invalid family")
        requireValue(invocations[invocationKey] == nil, "invocation key already live")
        requireValue(sequence < MAX_EXACT_INTEGER, "dose sequence exhausted")
        local token = setmetatable({}, {__metatable = "opaque potion dose"})
        -- Core validates and copies quotas before lifecycle state is published.
        local state = core.newDose(token, family, quotas)
        local dose = {token = token, state = state, family = family, abilityKey = abilityKey}
        doses[dose] = generation
        sequence = sequence + 1
        invocations[invocationKey] = {
            dose = dose, abilityKey = abilityKey, ordinals = {}, generation = generation, sequence = sequence,
        }
        return dose
    end

    function M.branch(invocationKey, dose, abilityKey)
        -- Original linked children retain the ROOT dose's policy state, while
        -- their own selected header supplies an independent ordinal namespace.
        -- The compiler/runtime must reserve that branch's quotas in the root
        -- dose before any admission; this method never invents new quotas.
        checkKey(invocationKey,"branch invocation key")
        checkKey(abilityKey,"branch ability key")
        requireValue(invocations[invocationKey]==nil,"branch invocation key already live")
        requireValue(type(dose)=="table" and doses[dose]==generation,"unknown or retired root dose")
        requireValue(sequence < MAX_EXACT_INTEGER,"dose sequence exhausted")
        sequence=sequence+1
        invocations[invocationKey]={dose=dose,abilityKey=abilityKey,ordinals={},
            generation=generation,sequence=sequence}
        return dose
    end

    local function tagEffect(invocationKey, messageKey, effectKey, ordinal)
        checkKey(invocationKey, "invocation key")
        if messageKey ~= nil then checkKey(messageKey, "message key") end
        checkKey(effectKey, "effect key")
        local invocation = invocations[invocationKey]
        requireValue(invocation ~= nil, "no open invocation")
        -- ITM/SPL ability effect counts are unsigned 16-bit. Quotas count owned
        -- records, so they are not a bound on unrelated delivery ordinals.
        requireValue(type(ordinal) == "number" and ordinal >= 0 and ordinal <= MAX_ORDINAL
            and ordinal == math.floor(ordinal), "invalid effect ordinal")
        requireValue(not invocation.ordinals[ordinal], "effect ordinal already queued")
        requireValue(messageKey == nil or (messages[messageKey] == nil and frameMessages[messageKey] == nil),
            "message key already live")
        requireValue(effects[effectKey] == nil and frameEffects[effectKey] == nil,
            "effect key already live")
        local tag = {
            messageKey = messageKey, effectKey = effectKey, ordinal = ordinal,
            dose = invocation.dose, abilityKey = invocation.abilityKey,
            generation = generation, valid = true, entered = false,
        }
        invocation.ordinals[ordinal] = true
        if messageKey then messages[messageKey] = tag end
        effects[effectKey] = tag
        return invocation.dose
    end

    function M.queue(invocationKey, messageKey, effectKey, ordinal)
        checkKey(messageKey, "message key")
        return tagEffect(invocationKey, messageKey, effectKey, ordinal)
    end

    function M.defer(invocationKey, effectKey, ordinal)
        -- Base CProjectile::DeliverEffects transfers this original pointer to a
        -- CMessageAddEffect. No timestamp/source-name inference or copied effect
        -- propagation is allowed. Native destruction must cancel a pending tag.
        return tagEffect(invocationKey, nil, effectKey, ordinal)
    end

    function M.attach(effectKey,messageKey)
        -- A proven child-construction hook tags the original before its native
        -- route is selected. Attach an allocated AddEffect message afterward
        -- so cancellation BEFORE Run retires that same pending dose tag.
        checkKey(effectKey,"effect key"); checkKey(messageKey,"message key")
        local tag=effects[effectKey]
        requireValue(tag~=nil and tag.valid and not tag.entered and tag.messageKey==nil,
            "effect is not awaiting native message attachment")
        requireValue(messages[messageKey]==nil and frameMessages[messageKey]==nil,
            "message key already live")
        tag.messageKey=messageKey
        messages[messageKey]=tag
    end

    function M.endInvocation(invocationKey)
        checkKey(invocationKey, "invocation key")
        requireValue(invocations[invocationKey] ~= nil, "no open invocation")
        invocations[invocationKey] = nil
    end

    function M.enter(messageKey, effectKey, noSave)
        checkKey(messageKey, "message key")
        checkKey(effectKey, "effect key")
        requireValue(type(noSave) == "boolean", "invalid noSave flag")
        local tag = messages[messageKey]
        local pending = effects[effectKey]
        if not tag and pending and pending.messageKey == nil then
            requireValue(pending.valid and not pending.entered, "pending effect is no longer valid")
            requireValue(frameMessages[messageKey] == nil, "message key already executing")
            tag = pending
            tag.messageKey = messageKey
            messages[messageKey] = tag
        end
        if tag then
            requireValue(tag.effectKey == effectKey, "message effect identity changed")
            requireValue(tag.valid and not tag.entered, "message already entered or destroyed")
        else
            requireValue(effects[effectKey] == nil, "effect belongs to another live message")
        end
        requireValue(frameMessages[messageKey] == nil, "message already entered or destroyed")
        requireValue(frameEffects[effectKey] == nil, "effect already entered")
        local frame = {messageKey = messageKey, effectKey = effectKey,
            unsupportedNoSave = tag ~= nil and noSave}
        local supported = tag ~= nil and not noSave
        if supported then
            frame.dose, frame.ordinal, frame.abilityKey = tag.dose, tag.ordinal, tag.abilityKey
        end
        local info = {generation = generation, tag = tag, supported = supported,
            messageKey = messageKey, effectKey = effectKey}
        if tag then tag.entered = true end
        tickets[frame] = info
        frameMessages[messageKey], frameEffects[effectKey] = frame, frame
        stack[#stack + 1] = frame
        return frame
    end

    function M.top(effectKey)
        local frame = stack[#stack]
        if not frame then return nil end
        local info = tickets[frame]
        if not info or info.effectKey ~= effectKey or info.generation ~= generation or not info.supported
            or not info.tag.valid then return nil end
        return frame
    end

    function M.leave(frame)
        local info = tickets[frame]
        requireValue(info ~= nil, "unknown or already left frame")
        if info.generation ~= generation then
            tickets[frame] = nil
            return false -- An old native return must not pop a new frame.
        end
        requireValue(stack[#stack] == frame, "message frames left out of order")
        stack[#stack] = nil
        tickets[frame] = nil
        frameMessages[info.messageKey], frameEffects[info.effectKey] = nil, nil
        if info.tag then removeTag(info.tag) end
        return true
    end

    function M.destroy(messageKey)
        checkKey(messageKey, "message key")
        local tag = messages[messageKey]
        if not tag then return false end
        if tag.entered then
            -- Invalidate admission immediately, but reserve the keys until its
            -- balanced leave. Reusing live frame keys would alias native state.
            tag.valid = false
        else
            removeTag(tag)
        end
        return true
    end

    function M.destroyEffect(effectKey)
        checkKey(effectKey, "effect key")
        local tag = effects[effectKey]
        if not tag then return false end
        if tag.entered then tag.valid = false else removeTag(tag) end
        return true
    end

    function M.hasLive()
        return next(invocations) ~= nil or next(effects) ~= nil or #stack > 0
    end

    function M.reset()
        requireValue(generation < MAX_EXACT_INTEGER, "generation exhausted")
        generation = generation + 1
        invocations, messages, effects, stack = {}, {}, {}, {}
        frameMessages, frameEffects = {}, {}
        -- sequence deliberately never resets; tokens are never reused.
    end

    return M
end
