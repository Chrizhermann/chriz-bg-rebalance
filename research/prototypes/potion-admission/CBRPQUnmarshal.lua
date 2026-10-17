-- Pure native input context for the two pinned Unmarshal callers.
-- baseline(list,sprite) returns existing lifetime identities in native order.
-- Sprite and projectile calls are both tracked; null sprite is a sentinel.
return function(baseline,spritePointer)
    assert(type(baseline)=="function" and type(spritePointer)=="function",
        "potion unmarshal: missing native readers")
    local stack,byFrame={},{}
    local M={}
    local function check(ok,message)
        if not ok then error("CBR potion unmarshal: "..message,0) end
    end
    local function int(value,low,high,label)
        check(type(value)=="number" and value==math.floor(value)
            and value>=low and value<=high,"invalid "..label)
        return value
    end
    function M.enter(frame,list,data,size,sprite,version)
        int(frame,1,9007199254740991,"caller frame")
        int(list,1,9007199254740991,"list pointer")
        int(data,0,9007199254740991,"data pointer")
        int(size,0,4294967295,"native byte size")
        int(sprite,0,9007199254740991,"sprite pointer")
        int(version,0,255,"version byte")
        check(data+size<=9007199254740991,"input interval overflows exact pointer range")
        check(byFrame[frame]==nil,"native caller frame already live")
        local original={}
        if sprite~=0 and version~=0 then
            local source=baseline(list,sprite)
            check(type(source)=="table","missing original list prefix")
            local seen={}
            for i,identity in ipairs(source) do
                check(identity~=nil and not seen[identity],"duplicate prefix lifetime")
                seen[identity]=true; original[i]=identity
            end
            local count=0
            for key in pairs(source) do
                check(type(key)=="number" and key==math.floor(key) and key>=1 and key<=#original,
                    "sparse native prefix")
                count=count+1
            end
            check(count==#original,"sparse native prefix")
        end
        local context={identity={},frame=frame,list=list,data=data,size=size,sprite=sprite,
            version=version~=0 and 1 or 0,baseline=original}
        stack[#stack+1],byFrame[frame]=context,context
    end
    function M.context(sprite,memory)
        local context=stack[#stack]
        if not context or context.sprite==0 or context.version==0 then return nil end
        check(spritePointer(sprite)==context.sprite,"metadata targets a different sprite")
        int(memory,context.data,context.data+context.size-1,"metadata pointer")
        local original={}
        for i,identity in ipairs(context.baseline) do original[i]=identity end
        return {identity=context.identity,version=context.version,data=context.data,
            size=context.size,baseline=original}
    end
    function M.leave(frame)
        local context=byFrame[frame]
        if not context then return false end
        check(stack[#stack]==context,"native Unmarshal returns are unbalanced")
        stack[#stack],byFrame[frame]=nil,nil
        return true
    end
    function M.hasLive() return #stack>0 end
    function M.reset() stack,byFrame={},{} end
    return M
end
