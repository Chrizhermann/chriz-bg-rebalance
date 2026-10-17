-- Original146/mode1 cast lineage. No hooks, engine calls, or resource mutation.
-- The caller registers guarded callbacks and composes direct admission frames.
return function(messages,env,manifest,enterDirect,leaveDirect,requireSprite)
    local function check(ok,message)
        if not ok then error("CBR potion lineage: "..message,0) end
    end
    check(type(env)=="table" and type(messages)=="table"
        and type(manifest)=="table" and type(manifest.sources)=="table","missing lineage dependencies")
    for _,name in ipairs({"top","branch","defer","attach","endInvocation"}) do
        check(type(messages[name])=="function","missing message lifecycle "..name)
    end
    for _,name in ipairs({"ptr","carrier","bindLinked","isSelf","isInstantProjectile"}) do
        check(type(env[name])=="function","missing native reader "..name)
    end
    check(type(enterDirect)=="function" and type(leaveDirect)=="function","missing direct admission frame bridge")
    check(type(requireSprite)=="function","missing sprite allocation identity")
    local pending,running,entries,stack,children={},{},{},{},{}
    local M={}
    local function pointer(value,label)
        check(type(value)=="number" and value==math.floor(value) and value>0
            and value<=9007199254740991,"invalid "..label)
    end
    local function index(value,label)
        check(type(value)=="number" and value==math.floor(value) and value>=0 and value<=65534,
            "invalid "..label)
        return tostring(value)
    end
    local function current(frame)
        local context=stack[#stack]
        if not context then return nil end
        check(frame==context.entry-0x70,"child frame is not the original tracked mode1 call")
        return context
    end
    function M.parentQueued(parent,message,target)
        if message==0 then return end
        pointer(message,"cast message pointer")
        local frame=messages.top(env.ptr(parent))
        if not frame then return end
        local ref=frame.abilityKey
        check(type(ref)=="table" and type(ref.ability)=="table","carrier lacks explicit registry context")
        local carrier=ref.ability.carriers and ref.ability.carriers[tostring(frame.ordinal)]
        if not carrier then return end
        env.carrier(parent,ref.source,carrier.fields,false,ref.nativeSource)
        check(env.isSelf(parent,target),"carrier cast target is not its drinker")
        check(pending[message]==nil and running[message]==nil,"cast message identity already live")
        local source=manifest.sources[ref.source]
        check(source~=nil,"unknown owning item")
        local call=source.calls and source.calls[carrier.call]
        check(call~=nil,"undeclared owned child cast")
        local identity=requireSprite(target)
        check(type(identity)=="table","missing sprite allocation token")
        pending[message]={dose=frame.dose,source=ref.source,call=call,target=env.ptr(target),targetIdentity=identity}
    end
    function M.castEnter(message,entry)
        pointer(message,"cast message pointer")
        pointer(entry,"cast entry frame")
        check(entry>0x70,"invalid cast entry frame")
        check(running[message]==nil,"cast message is already running")
        check(entries[entry]==nil,"native cast entry frame is already running")
        local context={message=message,entry=entry,tag=pending[message],token={},children={}}
        pending[message]=nil
        running[message],entries[entry]=context,context; stack[#stack+1]=context
    end
    function M.childCreated(frame,effect,ordinal,ability,caster,target)
        local context=current(frame)
        if not context or not context.tag then return end
        local tag=context.tag
        check(env.ptr(caster)==tag.target and env.ptr(target)==tag.target,"child caster/target is not the drinker")
        check(requireSprite(target)==tag.targetIdentity,"child target allocation changed after cast was queued")
        local abilityKey=index(ability,"selected ability")
        local header=tag.call.abilities[abilityKey]
        check(header~=nil,"native selected ability is absent from registry")
        local ordinalKey=index(ordinal,"child ordinal")
        check(ordinal<header.count and header.effects[ordinalKey]~=nil,"native child ordinal is absent from registry")
        if not context.ref then
            context.ability=abilityKey
            context.ref={source=tag.source,ability=header,nativeSource=tag.call.resource}
            messages.branch(context.token,tag.dose,context.ref)
        end
        check(context.ability==abilityKey,"selected native ability changed within one cast")
        check(ordinal==(context.lastOrdinal or -1)+1,"native child order changed or repeated")
        context.lastOrdinal=ordinal
        local key=header.effects[ordinalKey]
        local carrier=header.carriers and header.carriers[ordinalKey]
        if key==false and not carrier then return end
        local pointer=env.ptr(effect)
        check(children[pointer]==nil,"original child pointer is already pending")
        if key~=false then env.bindLinked(effect,tag.source,key,tag.call.resource)
        else env.carrier(effect,tag.source,carrier.fields,true,tag.call.resource) end
        local child={context=context,ordinal=ordinal,effect=pointer}
        children[pointer],context.children[pointer]=child,child
        messages.defer(context.token,pointer,ordinal)
    end
    function M.childQueued(frame,message,effect,ordinal)
        local context=current(frame)
        local pointer=env.ptr(effect)
        local child=children[pointer]
        if not child then return end
        check(child.context==context and child.ordinal==ordinal,"queued child disagrees with construction")
        if message~=0 then messages.attach(pointer,message) end
    end
    function M.childProjectile(frame,effect,ordinal,projectile)
        local context=current(frame)
        local child=children[env.ptr(effect)]
        if not child then return end
        check(child.context==context and child.ordinal==ordinal,"projectile child disagrees with construction")
        check(env.isInstantProjectile(projectile),"owned child projectile is not the verified instant class")
    end
    function M.childDirectEnter(frame,effect,noSave)
        local context=current(frame)
        if not context then return end
        check(context.direct==nil,"direct child frame is already active")
        local child=children[effect]
        check(not child or child.context==context,"direct child belongs to another cast")
        local key={}
        context.direct=key
        enterDirect(key,effect,noSave)
    end
    function M.childDirectLeave(frame)
        local context=current(frame)
        if not context then return end
        check(context.direct~=nil,"direct child return has no entry")
        leaveDirect(context.direct)
        context.direct=nil
    end
    function M.castLeave(message)
        pointer(message,"cast message pointer")
        local context=running[message]
        if not context then return end -- Invalidated native return after reset.
        check(stack[#stack]==context and context.direct==nil,"cast returns are unbalanced")
        if context.ref then messages.endInvocation(context.token) end
        for pointer,child in pairs(context.children) do
            if children[pointer]==child then children[pointer]=nil end
        end
        running[message],entries[context.entry],stack[#stack]=nil,nil,nil
    end
    function M.castDestroy(message)
        pointer(message,"cast message pointer")
        check(running[message]==nil,"native cast was destroyed while still executing")
        pending[message]=nil
    end
    function M.effectDestroy(pointer)
        local child=children[pointer]
        if child then child.context.children[pointer]=nil; children[pointer]=nil end
    end
    function M.hasLive() return next(pending)~=nil or #stack>0 end
    function M.referencesSprite(pointer,identity)
        for _,tag in pairs(pending) do
            if tag.target==pointer and tag.targetIdentity==identity then return true end
        end
        for _,context in ipairs(stack) do
            local tag=context.tag
            if tag and tag.target==pointer and tag.targetIdentity==identity then return true end
        end
        return false
    end
    function M.reset() pending,running,entries,stack,children={},{},{},{},{} end
    return M
end
