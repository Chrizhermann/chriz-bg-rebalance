-- Exact native Marshal context; inert until the composition connects callbacks.
-- Tracks ALL invocations, including unrelated/equipped lists as sentinels.
-- No serialization, native writes, hook installation, or saved native pointers.
return function(timedListPointer)
    assert(type(timedListPointer)=="function","potion marshal: missing timed-list reader")
    local stack,byFrame={},{}
    local M={}
    local function check(ok,message)
        if not ok then error("CBR potion marshal: "..message,0) end
    end
    local function integer(value,low,high,label)
        check(type(value)=="number" and value==math.floor(value)
            and value>=low and value<=high,"invalid "..label)
        return value
    end
    local function pointer(value,label) return integer(value,1,9007199254740991,label) end
    function M.enter(frame,list,version,onlyTiming9,excludeTiming2)
        pointer(frame,"entry frame"); pointer(list,"effect-list pointer")
        integer(version,0,255,"version byte")
        integer(onlyTiming9,0,4294967295,"timing9 argument")
        integer(excludeTiming2,0,4294967295,"timing2 argument")
        check(byFrame[frame]==nil,"native entry frame is already live")
        local context={identity={},frame=frame,list=list,version=version~=0 and 1 or 0,
            onlyTiming9=onlyTiming9~=0,excludeTiming2=excludeTiming2~=0}
        stack[#stack+1],byFrame[frame]=context,context
    end
    function M.counted(frame,list,bytes)
        local context=byFrame[frame]
        check(context~=nil and stack[#stack]==context,"count outside current native frame")
        check(context.list==list,"count belongs to a different native list")
        check(context.version==1,"V1 marshal cannot supply a V2 byte count")
        check(context.normalBytes==nil,"native effects were counted twice")
        integer(bytes,0,2147483647,"normal-effect byte count")
        check(bytes%0x108==0,"normal-effect byte count is not V2 aligned")
        context.normalBytes=bytes
    end
    function M.context(sprite)
        local context=stack[#stack]
        check(context~=nil,"export outside native Marshal")
        local list=pointer(timedListPointer(sprite),"sprite timed-list pointer")
        check(list==context.list,"current Marshal is not this sprite's timed list")
        check(context.version==1 and context.normalBytes~=nil,"native V2 count is unavailable")
        -- Fresh value prevents exporters from mutating the observer's context.
        return {identity=context.identity,version=1,onlyTiming9=context.onlyTiming9,
            excludeTiming2=context.excludeTiming2,normalBytes=context.normalBytes}
    end
    function M.leave(frame)
        local context=byFrame[frame]
        if not context then return false end -- Old native return after reset.
        check(stack[#stack]==context,"native Marshal returns are unbalanced")
        stack[#stack],byFrame[frame]=nil,nil
        return true
    end
    function M.hasLive() return #stack>0 end
    function M.reset() stack,byFrame={},{} end
    return M
end
