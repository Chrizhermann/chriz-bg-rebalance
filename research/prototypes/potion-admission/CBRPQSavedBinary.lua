-- Read-only pre-parser for the pinned EEex1.3 X-BIV1.0 table format.
-- Extract only our metadata before ANY foreign importer can copy an original.
-- Other handlers are skipped, not invoked, replaced, or reserialized.
-- Caller must supply the exact native input end from an Unmarshal context.
local M={}
local function check(ok,message)
    if not ok then error("CBR potion saved binary: "..message,0) end
end
local function integer(value,low,high,label)
    check(type(value)=="number" and value==math.floor(value) and value>=low and value<=high,
        "invalid "..label)
    return value
end
function M.read(readByte,start,finish,handlerName)
    check(type(readByte)=="function","missing byte reader")
    integer(start,1,9007199254740991,"footer pointer")
    integer(finish,start+8,9007199254740991,"native input end")
    check(type(handlerName)=="string" and #handlerName>0 and not handlerName:find("\0",1,true),
        "invalid handler name")
    local position=start
    local function byte()
        check(position<finish,"metadata reads beyond native input")
        local value=integer(readByte(position),0,255,"metadata byte")
        position=position+1
        return value
    end
    local function str(keep)
        local value=keep and {} or nil
        while true do
            local c=byte()
            if c==0 then return keep and table.concat(value) or nil end
            if keep then value[#value+1]=string.char(c) end
        end
    end
    local signature={}
    for i=1,8 do signature[i]=string.char(byte()) end
    check(table.concat(signature)=="X-BIV1.0","unsupported metadata signature")
    local widths={[3]=1,[4]=1,[5]=2,[6]=2,[7]=4,[8]=4,[9]=8,[10]=8}
    local function scalar(code,keep)
        if code==2 then return str(keep) end
        if code==11 then return false end
        if code==12 then return true end
        local width=widths[code]
        check(width~=nil,"unsupported scalar field type")
        local digits={}
        for i=1,width do digits[i]=byte() end
        if not keep then return nil end
        -- Our schema needs exact integer indices only. Unrelated handlers may
        -- contain arbitrary64-bit values; skipping them never rounds/rejects.
        local negative=code%2==1 and digits[width]>=128
        local value=0
        if negative then
            for i=width,1,-1 do value=value*256+(255-digits[i]) end
            value=-value-1
        else
            for i=width,1,-1 do value=value*256+digits[i] end
        end
        integer(value,-9007199254740991,9007199254740991,"exact owner integer")
        return value
    end
    local result,seen=nil,false
    while true do
        local name=str(true)
        if name=="" then break end
        local keep=name==handlerName
        check(not keep or not seen,"duplicate ownership handler")
        if keep then seen=true end
        local root=keep and {} or false
        local stack={root}
        while #stack>0 do
            local keyType=byte()
            if keyType==0 then stack[#stack]=nil
            else
                local key=scalar(keyType,keep)
                local valueType=byte()
                local current=stack[#stack]
                if keep then check(current[key]==nil,"duplicate ownership table key") end
                if valueType==1 then
                    local child=keep and {} or false
                    if keep then current[key]=child end
                    stack[#stack+1]=child
                else
                    local value=scalar(valueType,keep)
                    if keep then current[key]=value end
                end
            end
        end
        if keep then result=root end
    end
    local bytes=math.ceil((position-start)/0x108)*0x108
    check(start+bytes==finish,"metadata is not the final native input block")
    return result,bytes/0x108
end
return M
