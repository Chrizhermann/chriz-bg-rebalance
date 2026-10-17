-- Read-only semantic compiler. Binary resources and SHA256 are explicit inputs.
-- Mirrors build_manifest.py; no engine, file, installation or hook dependency.
local M = {}
local function fail(code, context, detail)
    error(code .. ": " .. tostring(context) .. ": " .. detail, 0)
end
local function copy(value)
    local result={}; for k,v in pairs(value) do result[k]=v end; return result
end
local function keys(value)
    local result={}; for k in pairs(value) do result[#result+1]=k end
    table.sort(result); return result
end
local function any(value) return next(value)~=nil end
local function set(values)
    local result={}; for _,v in ipairs(values) do result[v]=true end; return result
end
local function subset(a,b,excluded)
    for k in pairs(a) do if not (excluded and excluded[k]) and not b[k] then return false end end
    return true
end
local function sameSet(a,b) return subset(a,b) and subset(b,a) end
local function append(to,from) for _,v in ipairs(from) do to[#to+1]=v end end
local ARRAY={}
local function array(value) return setmetatable(value,ARRAY) end
local function jsonString(value)
    local out={'"'}
    for i=1,#value do
        local n=value:byte(i)
        local escapes={[8]="\\b",[9]="\\t",[10]="\\n",[12]="\\f",[13]="\\r"}
        if n==34 then out[#out+1]='\\"'
        elseif n==92 then out[#out+1]="\\\\"
        elseif escapes[n] then out[#out+1]=escapes[n]
        elseif n<32 or n>=127 then out[#out+1]=string.format("\\u%04x",n)
        else out[#out+1]=string.char(n) end
    end
    out[#out+1]='"'; return table.concat(out)
end
local function canonical(value)
    if type(value)=="string" then return jsonString(value) end
    if type(value)=="number" then return string.format("%.0f",value) end
    if type(value)=="boolean" then return value and "true" or "false" end
    local parts={}
    if getmetatable(value)==ARRAY then
        for _,v in ipairs(value) do parts[#parts+1]=canonical(v) end
        return "["..table.concat(parts,",").."]"
    end
    for _,k in ipairs(keys(value)) do parts[#parts+1]=jsonString(k)..":"..canonical(value[k]) end
    return "{"..table.concat(parts,",").."}"
end
local function signature(values)
    table.sort(values)
    local out={}; for _,v in ipairs(values) do out[#out+1]=jsonString(v) end
    return "["..table.concat(out,",").."]"
end
local function uniqueSignature(values) return signature(keys(set(values))) end
local LINKS={[146]="SPL",[148]="SPL",[177]="EFF",[183]="EFF",[232]="SPL",
    [248]="EFF",[249]="EFF",[272]="EFF",[283]="EFF",[326]="SPL",[333]="SPL"}
local PRESENTATION=set{7,50,51,132,139,142,155,174,215}
local HP_COSMETIC=set{7,142}
local HARMFUL=set{12,24,25,38,39,40,45,74,76,80}
local NATIVE_UNIQUE=set{16,48}
local ADDITIVE=set{6,10,15,21,22,27,28,29,30,31,33,34,35,36,37,44,49,59,73}
local SKILLS=set{90,91,92,275,276,277}
local SETTERS=set{6,10,15,44,49}
local function checked(data,offset,size)
    if type(data)~="string" or offset<0 or size<0 or offset+size>#data then
        error("resource field out of bounds",0)
    end
    return data:sub(offset+1,offset+size)
end
local function byte(data,offset) return checked(data,offset,1):byte() end
local function u16(data,offset)
    local a,b=checked(data,offset,2):byte(1,2); return a+b*256
end
local function u32(data,offset)
    local a,b,c,d=checked(data,offset,4):byte(1,4); return a+b*256+c*65536+d*16777216
end
local function i32(data,offset)
    local n=u32(data,offset); return n>=2147483648 and n-4294967296 or n
end
local function ascii(raw)
    for i=1,#raw do if raw:byte(i)>127 then return false end end
    return true
end
local function nul(raw) return (raw:match("^[^%z]*")) end
local function hex(raw) return (raw:gsub(".",function(c) return string.format("%02x",c:byte()) end)) end
local function operand(raw,link)
    local value=nul(raw)
    if link then
        value=value:gsub(" +$","")
        if not ascii(value) or value:find("[\\/:]")
                or value=="." or value==".." then error("invalid resource operand",0) end
    elseif not ascii(value) then
        value=value:gsub("[\128-\255]",function(c) return string.format("\\x%02x",c:byte()) end)
    end
    return value:upper()
end
local function effect(raw,external)
    local e={raw=raw}
    if external then
        e.opcode,e.target,e.power=u32(raw,16),u32(raw,20),u32(raw,24)
        e.parameter1,e.parameter2=i32(raw,28),u32(raw,32)
        e.timing,e.duration=u16(raw,36),u32(raw,40)
        e.probability1,e.probability2=u16(raw,44),u16(raw,46)
        e.special=u32(raw,72); e.resource=operand(raw:sub(49,56),LINKS[e.opcode])
    else
        e.opcode,e.target,e.power=u16(raw,0),byte(raw,2),byte(raw,3)
        e.parameter1,e.parameter2=i32(raw,4),u32(raw,8)
        e.timing,e.duration=byte(raw,12),u32(raw,14)
        e.probability1,e.probability2=byte(raw,18),byte(raw,19)
        e.special=u32(raw,44); e.resource=operand(raw:sub(21,28),LINKS[e.opcode])
    end
    return e
end
local function parseResource(name,data)
    local ext=name:match("%.([^.]*)$")
    if ext=="EFF" then
        checked(data,0,0x110)
        if data:sub(1,8)~="EFF V2.0" then error("external EFF requires V2",0) end
        return {{kind="external",effects={effect(data:sub(1,0x110),true)}}}
    end
    if ext~="ITM" and ext~="SPL" then error("unsupported payload extension",0) end
    checked(data,0,0x72)
    if data:sub(1,8)~=ext.." V1  " then error(ext.." requires V1",0) end
    local aoff,acount,foff=u32(data,0x64),u16(data,0x68),u32(data,0x6A)
    local stride=ext=="ITM" and 0x38 or 0x28
    if acount>0 then
        checked(data,aoff,acount*stride)
        if aoff<0x72 then error("ability table overlaps header",0) end
    end
    local slices={}
    local function add(kind,first,count,ability)
        local effects={}
        if count>0 then
            local start,size=foff+first*48,count*48
            checked(data,start,size)
            if start<0x72 or (acount>0 and start<aoff+acount*stride and start+size>aoff) then
                error("effect slice overlaps header/abilities",0)
            end
            for i=first,first+count-1 do effects[#effects+1]=effect(checked(data,foff+i*48,48)) end
        end
        slices[#slices+1]={kind=kind,effects=effects,ability=ability}
    end
    add(ext=="ITM" and "equipped" or "casting",u16(data,0x6E),u16(data,0x70))
    for i=0,acount-1 do
        local a=checked(data,aoff+i*stride,stride)
        add("ability:"..i,u16(a,0x20),u16(a,0x1E),a)
    end
    return slices
end
local function signed16(value) return (value+32768)%65536-32768 end
local function decodedDword20(raw)
    local value=u32(raw,0x20)
    return value==4294967295 and 0 or value
end
local function owned(e,context,hp)
    local op,mode,amount=e.opcode,e.parameter2,e.parameter1
    if LINKS[op] then fail("LINK_CAPABILITY",context,"linked payload requires proof") end
    if op>=400 then fail("OPCODE_CAPABILITY",context,"extension opcode is not reviewed") end
    if (PRESENTATION[op] and not(HP_COSMETIC[op] and hp)) or HARMFUL[op] or op==11 or op==17 then return false end
    if op==23 and e.special==0 then return false end
    local timing,duration=e.timing,e.duration
    if set{1,2,4,7,8,9}[timing] or ((timing==0 or timing==10) and duration==0) then return false end
    if timing~=0 and timing~=10 then fail("TIMING_CAPABILITY",context,"unreviewed finite timing") end
    if HP_COSMETIC[op] then return true end
    if op==98 then
        -- Native Apply dispatches LOW16 mode. Mode2: signed16 heal amount,
        -- interval1. Mode3: positive signed16 interval, heal1. Keep raw DWORD
        -- fields in the native descriptor/key; only classification uses LOW16.
        local effectiveMode,effective=mode%65536,signed16(amount)
        if effectiveMode~=2 and effectiveMode~=3 then
            fail("OPCODE_CAPABILITY",context,"opcode98 mode lacks reviewed mode2/3 cache adapter")
        end
        if e.special~=0 then fail("SPECIAL_CAPABILITY",context,"regeneration Special native path is unreviewed") end
        if effectiveMode==2 and effective<=0 then return false end -- Native adverse/zero Heal17.
        if effectiveMode==3 and effective<=0 then
            fail("AMOUNT_CAPABILITY",context,"regeneration interval must be positive signed16")
        end
        if timing==10 and duration>2147483647 then
            fail("DURATION_CAPABILITY",context,"regeneration countdown must fit positive signed32 ticks")
        end
        -- UsesDice=false. HP/CON package policy is inherited, not inferred98.
        return true
    end
    if op==20 then
        if mode==0 then return hp end
        fail("MODE_CAPABILITY",context,"invisibility mode may deliver a separate effect")
    end
    if op==23 then
        fail("MORALE_CAPABILITY",context,"nonzero-Special morale can repeatedly alter base morale")
    end
    if op==63 then return hp end
    -- Native projectile consumers compare U16 IDs with non-consuming Find.
    if op==83 then return hp and mode<=65535 end
    if op==86 or op==87 or op==88 or op==89 then
        if mode~=0 then fail("MODE_CAPABILITY",context,"physical-resistance setter/percentage polarity unreviewed") end
        local effective=signed16(amount)
        -- Native WORD addition precedes the signed upper cap100. This
        -- range is monotone over every accumulator in[-32768,100].
        if effective<0 or effective>32667 then
            fail("AMOUNT_CAPABILITY",context,"native physical-resistance WORD addition can reverse polarity through wrap")
        end
        return effective>0
    end
    if op==106 then
        if mode==1 then return hp end
        fail("MODE_CAPABILITY",context,"unreviewed morale-break additive/percentage mode")
    end
    if op==120 then
        -- Apply builds predicates; native OnList does not consume capacity.
        -- Out-of-range modes append the zero/enchantment0 descriptor.
        if hp then fail("HP_COMPANION_CAPABILITY",context,"weapon immunity HP package lifetime unreviewed") end
        return false
    end
    if op==126 then
        if mode==1 or mode==2 then
            if hp then fail("HP_COMPANION_CAPABILITY",context,"movement setter HP polarity policy is unreviewed") end
            return false
        end
        if mode==0 or mode==5 then fail("MODE_CAPABILITY",context,"current-speed movement mode is cumulative") end
        return false
    end
    if op==233 then
        local index=mode%65536
        if index<89 or index>134 then return false end
        if mode>=65536 then fail("MODE_CAPABILITY",context,"additive proficiency derives first-call parameter3") end
        return hp
    end
    if op==282 then return hp and mode<45 end
    if op==102 then
        if amount<0 then fail("LEVEL_CAPABILITY",context,"negative immunity level indexes before native table") end
        return hp and amount<=9
    end
    if set{101,169,267,296}[op] then
        if hp then fail("HP_COMPANION_CAPABILITY",context,"boolean immunity HP expiry/rebuild removal unreviewed") end
        return false
    end
    if op==166 then
        if mode==0 then
            -- Signed32 addition to any signed16 MR baseline must not wrap
            -- before native clamping: INT_MIN+32768 .. INT_MAX-32767.
            if amount < -2147450880 or amount > 2147450880 then
                fail("AMOUNT_CAPABILITY",context,"native signed32 MR addition can overflow")
            end
            return amount>0
        end
        if mode==1 then return hp and amount>0 end
        fail("MODE_CAPABILITY",context,"unreviewed MR mode")
    end
    if op==0 or op==1 then
        local effective=signed16(amount)
        if op==0 then
            if set{0,1,2,4,8}[mode] then return effective>0 end
            if mode==16 then return hp end
        elseif mode==0 then return effective>=1 and effective<=10 end
        fail("MODE_CAPABILITY",context,"unreviewed AC/APR mode")
    end
    if NATIVE_UNIQUE[op] then
        if hp then fail("HP_COMPANION_CAPABILITY",context,"native unique HP companion requires review") end
        return false
    end
    if op==328 then
        if e.special~=0 then return hp and mode<256 end
        fail("STATE_CAPABILITY",context,"unreviewed scripting state")
    end
    if ADDITIVE[op] then
        if mode==0 then return signed16(amount)>0 end
        if op==30 and mode==1 then return hp and signed16(amount)>0 end
        if SETTERS[op] and mode==1 then return hp and amount>0 end
        if SETTERS[op] and mode==2 then return hp and signed16(amount)>100 end
        if op>=33 and op<=37 and mode==3 then return signed16(amount)>0 end
        fail("MODE_CAPABILITY",context,"unreviewed additive stat mode")
    end
    if op==19 or SKILLS[op] then
        -- 275/276/277 consume signed LOW16 into DWORD bonus accumulators.
        -- Nominal polarity does not repair native aggregate overflow.
        if mode==0 then return signed16(amount)>0 end
        if mode==1 then
            if op==275 or op==276 or op==277 then return hp and amount%256>0 end
            return hp and amount>0
        end
        if mode==2 then
            local effective=signed16(amount)
            if op==90 or op==91 then
                if op==90 and not hp then return false end
                local low,high=-65535,65536
                if op==90 then low,high=-8421504,8421504 end
                if amount<low or amount>high then
                    fail("AMOUNT_CAPABILITY",context,"native signed32 percentage product can overflow")
                end
                effective=amount
            end
            return effective>100 and (hp or op==91)
        end
        fail("MODE_CAPABILITY",context,"unreviewed stat mode")
    end
    if op==18 then
        if mode~=0 and mode~=2 then fail("HP_MODE_CAPABILITY",context,"unreviewed HP mode") end
        local positive=amount>(mode==2 and 100 or 0)
        if positive and (i32(e.raw,0x1C)~=0 or decodedDword20(e.raw)~=0) then
            fail("HP_DICE_CAPABILITY",context,"rolled HP mutates native amount")
        end
        return positive
    end
    if op==54 then
        if mode==0 then return signed16(amount)>0 end
        if mode==2 then
            local effective=signed16(amount)
            if hp and effective<0 then fail("BASELINE_CAPABILITY",context,"negative THAC0 percentage has baseline-dependent polarity") end
            if hp then return effective>=0 and effective<=100 end
            return effective>0 and effective<100
        end
        if mode==1 then return hp end
        fail("MODE_CAPABILITY",context,"unreviewed THAC0 mode")
    end
    fail("OPCODE_CAPABILITY",context,"finite opcode may supply an unreviewed cumulative bonus")
end
local function fields(e,ability,strict)
    local raw,usesDice=e.raw,e.opcode==18
    if strict and byte(raw,13)>=4 then fail("FLAGS_CAPABILITY","effect flags","native timing bits unreviewed") end
    local decodedSize=decodedDword20(raw)
    local minLevel=usesDice and 0 or decodedSize
    if strict and minLevel>65535 then fail("LEVEL_CAPABILITY","effect minimum level","native level normalization") end
    local resource=nul(raw:sub(21,28))
    if not ascii(resource) then
        if strict then fail("FINGERPRINT_CAPABILITY","effect resource","non-ASCII operand") end
        resource=hex(raw:sub(21,28))
    else resource=resource:upper() end
    return {opcode=e.opcode,target=e.target,power=e.power,amount=e.parameter1,mode=e.parameter2,
        resource=resource,diceCount=usesDice and i32(raw,0x1C) or 0,
        diceSize=usesDice and ((decodedSize+2147483648)%4294967296-2147483648) or 0,
        minLevel=minLevel,maxLevel=usesDice and 0 or u32(raw,0x1C),saveType=u32(raw,0x24),saveBonus=i32(raw,0x28),
        special=e.special,flags=byte(raw,13),school=byte(ability,0x17),secondary=byte(ability,0x19),
        sourceFlags=u32(ability,0x26),probUpper=e.probability1,probLower=e.probability2,
        timing=e.timing,duration=e.duration}
end
local function stable(f)
    local s=copy(f); s.timing,s.duration,s.nativeSources=nil,nil,nil
    s.flags=s.flags-s.flags%16+s.flags%8
    if s.opcode==18 then s.special=s.special-s.special%2 end
    return s
end
local function transport(e,ability,context)
    if e.target==1 or (e.target==2 and byte(ability,12)==5 and u16(ability,0x2A)==1) then return end
    fail("TARGET_CAPABILITY",context,"owned effect has unreviewed delivery route")
end
local function unownedLink(e,context,reader,hp,ancestors,nodes)
    if not reader then fail("LINK_CAPABILITY",context,"explicit resource resolver required") end
    ancestors,nodes=ancestors or {},nodes or {}
    local child=e.resource.."."..LINKS[e.opcode]
    if e.resource=="" then fail("LINK_CAPABILITY",context,"implicit/empty child") end
    for _,name in ipairs(ancestors) do if child==name then fail("LINK_CYCLE",context,child) end end
    if #ancestors>=16 or (not nodes[child] and #keys(nodes)>=256) then fail("LINK_BOUNDS",context,"depth/node bound") end
    nodes[child]=true
    local ok,slices=pcall(function() return parseResource(child,reader(child)) end)
    if not ok then fail("LINK_RESOURCE",context,"cannot inspect "..child..": "..tostring(slices)) end
    local removals={}
    for _,part in ipairs(slices) do
      -- Native opcode146 mode1 does not deliver either casting-effect pass.
      if not (e.opcode==146 and e.parameter2==1 and part.kind=="casting") then
      for ordinal,original in ipairs(part.effects) do
        local candidate=copy(original)
        if e.opcode==177 then candidate.timing,candidate.duration=e.timing,e.duration end
        local where=context.." -> "..child.." "..part.kind.." effect "..(ordinal-1)
        if LINKS[candidate.opcode] then
            local nextAncestors={}; append(nextAncestors,ancestors); nextAncestors[#nextAncestors+1]=child
            append(removals,unownedLink(candidate,where,reader,hp,nextAncestors,nodes))
        elseif candidate.opcode==318 and (candidate.timing==0 or candidate.timing==10)
            and candidate.duration>0 and candidate.resource~="" then
            if hp then fail("HP_COMPANION_CAPABILITY",where,"conditional resource immunity HP ownership is unreviewed") end
            -- Keep both native predicate outcomes; family guard check below
            -- prevents silently preserving a guard that blocks owned refresh.
        elseif owned(candidate,where,hp or candidate.opcode==10 or candidate.opcode==18) then
            fail("LINK_OWNED_CAPABILITY",where,"child bonus needs native dose provenance")
        end
        if candidate.opcode==321 and candidate.resource~="" then
            removals[#removals+1]={source=candidate.resource,context=where}
        end
        if candidate.opcode==318 and candidate.resource~="" then
            removals[#removals+1]={source=candidate.resource,context=where,kind="resource_guard"}
        end
      end
    end end
    return removals
end
local function register(result,e,f,context,sha256)
    local s=stable(f)
    local lifetime={timing=f.timing,duration=f.duration}
    local key=sha256(canonical({fields=s,lifetime=lifetime}))
    assert(type(key)=="string" and #key==64 and not key:find("[^0-9a-f]"),"invalid SHA256 result")
    local old=result.records[key]
    if old and f.nativeSources then
        for name in pairs(f.nativeSources) do old.nativeSources[name]=true end
    else result.records[key]=f end
    result.keys[key]=true; result.owned_ops[e.opcode]=true
    if HP_COSMETIC[e.opcode] then result.non_blocking_keys[key]=true end
    result.entries[#result.entries+1]={base=canonical(s),fields=s,lifetime=canonical(lifetime),
        special=e.special,flags=byte(e.raw,13),context=context}
    return key
end
local function addQuota(to,key,count,context)
    local maximum=4294967295
    local previous=to[key]
    if previous==nil then previous=0 end
    if type(count)~="number" or count~=math.floor(count) or count<1 or count>maximum
            or type(previous)~="number" or previous~=math.floor(previous)
            or previous<0 or previous>maximum or count>maximum-previous then
        fail("QUOTA_CAPABILITY",context,"expanded effect quota exceeds the exact unsigned32 Core capacity")
    end
    -- Merge once per original route, bounding every intermediate before add.
    -- Both the subtraction and accepted sum are exact in LuaJIT's number.
    to[key]=previous+count
end
local function addQuotas(to,from,context)
    for key,count in pairs(from) do addQuota(to,key,count,context) end
end
local function callGraph(e,context,reader,result,hp,sha256,ancestors)
    if e.opcode~=146 or e.parameter2~=1 then
        fail("LINK_OWNED_CAPABILITY",context,"owned child requires original opcode146 mode1 transport")
    end
    -- Native Resolve defers3..8 beyond the original AddEffect frame. The
    -- other raw-byte timings apply immediately;146 then marks itself Done.
    if e.timing>=3 and e.timing<=8 then
        fail("LINK_TIMING_CAPABILITY",context,"delayed owned carrier outlives its dose delivery frame")
    end
    ancestors=ancestors or {}
    local name=e.resource
    if name=="" then fail("LINK_CYCLE",context,"empty or cyclic owned spell route") end
    for _,ancestor in ipairs(ancestors) do
        if name==ancestor then fail("LINK_CYCLE",context,"empty or cyclic owned spell route") end
    end
    if #ancestors>=16 or (not result.calls[name] and #keys(result.calls)>=256) then
        fail("LINK_BOUNDS",context,"owned spell graph exceeds depth16/node256 inspection bound")
    end
    if result.calls[name] then return name end
    local data
    local ok,slices=pcall(function()
        data=reader(name..".SPL")
        return parseResource(name..".SPL",data)
    end)
    if not ok then fail("LINK_RESOURCE",context,"cannot inspect "..name..".SPL: "..tostring(slices)) end
    local call={resource=name,abilities={},quotas={},semantic=array({}),baseSemantic=array({})}
    result.calls[name]=call
    for _,part in ipairs(slices) do if part.kind:match("^ability:") then
        local index=part.kind:match("^ability:(%d+)$")
        local children,carriers,quotas,sig,baseSig={},{},{},{},{}
        for ordinal,candidate in ipairs(part.effects) do
            local where=context.." -> "..name..".SPL "..part.kind.." effect "..(ordinal-1)
            local linked,isOwned=nil,false
            if LINKS[candidate.opcode] then
                local unowned,removals=pcall(unownedLink,candidate,where,reader,hp)
                if unowned then append(result.removals,removals)
                elseif tostring(removals):match("^LINK_OWNED_CAPABILITY:") then
                    local nextAncestors={}; append(nextAncestors,ancestors)
                    nextAncestors[#nextAncestors+1]=name
                    linked=callGraph(candidate,where,reader,result,hp,sha256,nextAncestors)
                else error(removals,0) end
            else isOwned=owned(candidate,where,hp) end
            local f=fields(candidate,string.rep("\0",56),isOwned or linked~=nil)
            f.school,f.secondary,f.sourceFlags=byte(data,0x25),byte(data,0x27),u32(data,0x18)
            f.nativeSourceType,f.nativeSources=1,{[name]=true}
            if (isOwned or linked) and candidate.target~=1 and candidate.target~=2 then
                fail("TARGET_CAPABILITY",where,"owned mode1 child requires target1/2 and runtime drinker identity validation")
            end
            if isOwned and candidate.timing==0 and candidate.duration>0x08888888 then
                fail("DURATION_CAPABILITY",where,"native seconds clamp")
            end
            if candidate.opcode==10 or candidate.opcode==18 then
                result.hp=result.hp or owned(candidate,where,true)
            end
            if candidate.opcode==321 and f.resource~="" then
                result.removals[#result.removals+1]={source=f.resource,context=where}
            end
            local s=stable(f)
            local descriptor={fields=s,lifetime={timing=f.timing,duration=f.duration}}
            local baseDescriptor={fields=s}
            local ordinalKey=tostring(ordinal-1)
            if linked then
                local linkedFields=copy(s); linkedFields.resource=""
                descriptor.fields,descriptor.linked=linkedFields,result.calls[linked].semantic
                baseDescriptor={fields=linkedFields,linked=result.calls[linked].baseSemantic}
                carriers[ordinalKey]={call=linked,fields=f}
                addQuotas(quotas,result.calls[linked].quotas,where)
            end
            if not PRESENTATION[candidate.opcode] then
                sig[#sig+1]=canonical(descriptor); baseSig[#baseSig+1]=canonical(baseDescriptor)
            end
            if isOwned then
                local key=register(result,candidate,f,where,sha256)
                children[ordinalKey]=key; addQuota(quotas,key,1,where)
            else
                children[ordinalKey]=false
                result.other_native_buff=result.other_native_buff or NATIVE_UNIQUE[candidate.opcode] or false
            end
        end
        local minimum=u16(part.ability,0x10)
        call.abilities[index]={count=#part.effects,effects=children,carriers=carriers,
            quotas=quotas,minimumLevel=minimum}
        table.sort(sig); table.sort(baseSig)
        -- Cast semantics only: type chooses native caster/duration rules;
        -- GetSpellLevel consumes the low16 header level in the mage branch.
        local spellType,spellLevel=u16(data,0x1C),u16(data,0x34)
        call.semantic[#call.semantic+1]={spellType=spellType,spellLevel=spellLevel,
            minimumLevel=minimum,effects=array(sig)}
        call.baseSemantic[#call.baseSemantic+1]={spellType=spellType,spellLevel=spellLevel,
            minimumLevel=minimum,effects=array(baseSig)}
        for key,count in pairs(quotas) do call.quotas[key]=math.max(call.quotas[key] or 0,count) end
    end end
    local previous
    for _,header in pairs(call.abilities) do
        if previous and not sameSet(previous,header.quotas) then
            fail("LINK_VARIANT_CAPABILITY",context,"selected headers have different owned bonus descriptors; refresh potency policy is unresolved")
        end
        previous=header.quotas
    end
    return name
end
local function parse(name,data,hp,reader,sha256)
    local ok,slices=pcall(function()
        checked(data,0,0x1E)
        if u16(data,0x1C)~=9 then return nil end
        return parseResource(name..".ITM",data)
    end)
    if not ok then fail("FORMAT",name,tostring(slices)) end
    if not slices then return nil end
    local result={name=name,keys={},non_blocking_keys={},records={},abilities={},calls={},entries={},hp=false,
        owned_ops={},other_native_buff=false,removals={}}
    local signatures,baseSignatures={},{}
    for _,part in ipairs(slices) do
        local context=name.." "..part.kind
        local ability=part.ability or string.rep("\0",56)
        local emitted,carriers,quotas,sig,baseSig={},{},{},{},{}
        for ordinal,e in ipairs(part.effects) do
            local where=context.." effect "..(ordinal-1)
            local isOwned,linked=false,nil
            if LINKS[e.opcode] then
                local unowned,removals=pcall(unownedLink,e,where,reader,hp)
                if unowned then append(result.removals,removals)
                elseif tostring(removals):match("^LINK_OWNED_CAPABILITY:") then
                    linked=callGraph(e,where,reader,result,hp,sha256)
                else error(removals,0) end
            else isOwned=owned(e,where,hp) end
            if isOwned or linked then transport(e,ability,where) end
            if isOwned and e.timing==0 and e.duration>0x08888888 then fail("DURATION_CAPABILITY",where,"native seconds clamp") end
            if part.kind=="equipped" and (isOwned or linked) then fail("EQUIPPED_CAPABILITY",where,"no item-use dose boundary") end
            result.hp=result.hp or ((e.opcode==10 or e.opcode==18) and owned(e,where,true))
            local f=fields(e,ability,isOwned or linked~=nil)
            if e.opcode==321 and f.resource~="" then result.removals[#result.removals+1]={source=f.resource,context=where} end
            local s=stable(f)
            local lifetime={timing=e.timing,duration=e.duration}
            local descriptor={fields=s,lifetime=lifetime}
            local baseDescriptor={fields=s}
            local ordinalKey=tostring(ordinal-1)
            if linked then
                local linkedFields=copy(s); linkedFields.resource=""
                descriptor.fields,descriptor.linked=linkedFields,result.calls[linked].semantic
                baseDescriptor={fields=linkedFields,linked=result.calls[linked].baseSemantic}
                carriers[ordinalKey]={call=linked,fields=f}
                addQuotas(quotas,result.calls[linked].quotas,where)
            end
            if not PRESENTATION[e.opcode] then
                sig[#sig+1]=canonical(descriptor); baseSig[#baseSig+1]=canonical(baseDescriptor)
            end
            if not isOwned then
                emitted[ordinalKey]=false
                result.other_native_buff=result.other_native_buff or NATIVE_UNIQUE[e.opcode] or false
            else
                local key=register(result,e,f,where,sha256)
                emitted[ordinalKey]=key; addQuota(quotas,key,1,where)
            end
        end
        if part.kind~="equipped" then
            local index=part.kind:match("^ability:(%d+)$")
            result.abilities[index]={quotas=quotas,effects=emitted,count=#part.effects}
            if any(carriers) then result.abilities[index].carriers=carriers end
            signatures[#signatures+1]=signature(sig); baseSignatures[#baseSignatures+1]=signature(baseSig)
        end
    end
    result.signature=uniqueSignature(signatures); result.base_signature=uniqueSignature(baseSignatures)
    return result
end
local function resolvable(items,label)
    local seen,variants={},{}
    for _,item in ipairs(items) do for _,entry in ipairs(item.entries) do
        local old=seen[entry.base]
        if old and old.lifetime~=entry.lifetime then fail("DURATION_AMBIGUITY",label,"active records lose original lifetime") end
        if old and old.special~=entry.special then fail("SPECIAL_AMBIGUITY",label,"HP first-call normalization collision") end
        if old and old.flags~=entry.flags then fail("FLAGS_AMBIGUITY",label,"native self flag collision") end
        seen[entry.base]=entry
        local bonuses={[entry.fields.saveBonus]=true}
        if entry.fields.school~=0 then bonuses[(entry.fields.saveBonus-2+2147483648)%4294967296-2147483648]=true end
        for bonus in pairs(bonuses) do
            local f=copy(entry.fields); f.saveBonus=bonus
            local variant=canonical(f); local previous=variants[variant]
            if previous and previous.base~=entry.base then fail("SPECIALIST_AMBIGUITY",label,"specialist save-bonus collision") end
            variants[variant]=entry
        end
    end end
end
local function nameOf(filename)
    if type(filename)~="string" or filename:upper():sub(-4)~=".ITM" then fail("INPUT",filename,"explicit ITM name required") end
    local stem=filename:sub(1,-5)
    if #stem<1 or #stem>8 or stem:find("[^\33-\126]") or stem:find("[\\/:.]") then
        fail("INPUT",filename,"invalid eight-byte resource identity")
    end
    return stem:upper()
end
function M.build(options,readResource,sha256)
    if type(options)~="table" or options.version~=1 then fail("INPUT","reader schema","version 1 required") end
    local policy=options.policy or "unique"
    if policy~="unique" and policy~="except_genius" then fail("POLICY",policy,"unknown policy") end
    if type(options.names)~="table" or type(readResource)~="function" or type(sha256)~="function" then
        fail("INPUT","resources","explicit names, binary reader and SHA256 required")
    end
    local filenames={}
    local linkReader=options.resolveLinks~=false and readResource or nil
    for i,value in pairs(options.names) do
        if type(i)~="number" or i<1 or i%1~=0 then fail("INPUT","names","dense list required") end
        filenames[#filenames+1]=value
    end
    for i=1,#filenames do if options.names[i]==nil then fail("INPUT","names","dense list required") end end
    for _,filename in ipairs(filenames) do nameOf(filename) end
    table.sort(filenames)
    local items,originals,identities={},{},{}
    for _,filename in ipairs(filenames) do
        local name=nameOf(filename)
        if identities[name] then fail("INPUT",name,"duplicate case-insensitive resource identity") end
        identities[name]=true
        local ok,data=pcall(readResource,filename)
        if not ok or type(data)~="string" then fail("INPUT",name,"resource reader must return binary string") end
        local item=parse(name,data,false,linkReader,sha256)
        if item then resolvable({item},name); items[name]=item; originals[name]=data end
    end
    local familyOf,anchors={},{}
    for _,name in ipairs(keys(items)) do
        familyOf[name]=name
        if name:match("^POTN%d%d$") then anchors[name]=items[name] end
    end
    for _,name in ipairs(keys(items)) do
        local item=items[name]; local suffix=name:match("^DW#PTN(%d%d)$")
        if suffix then
            local anchor="POTN"..suffix; local candidate=items[anchor]
            if not candidate then fail("PROVENANCE",name,"canonical input required") end
            if not subset(item.keys,candidate.keys) then fail("PROVENANCE",name,"owned payload not canonical subset") end
            if not candidate.hp and not sameSet(item.keys,candidate.keys) then fail("PAYLOAD_CAPABILITY",name,"partial safe payload") end
            familyOf[name]=anchor
        elseif not anchors[name] and (any(item.keys) or item.hp) then
            local matches,possible={},{}
            for _,a in ipairs(keys(anchors)) do
                if anchors[a].signature==item.signature then matches[#matches+1]=a end
                if anchors[a].base_signature==item.base_signature then possible[#possible+1]=a end
            end
            if #matches>1 then fail("IDENTITY_AMBIGUITY",name,"matches distinct canonical types") end
            if #matches==1 then familyOf[name]=matches[1]
            elseif #possible>0 then fail("DURATION_AMBIGUITY",name,"canonical original lifetime differs") end
        end
    end
    local unknown={}
    for _,name in ipairs(keys(items)) do
        local item=items[name]
        if (any(item.keys) or item.hp) and familyOf[name]==name and not anchors[name] then
            for _,other in ipairs(unknown) do if item.base_signature==other.base_signature then
                fail(item.signature==other.signature and "IDENTITY_AMBIGUITY" or "DURATION_AMBIGUITY",
                     name..", "..other.name,"copy-versus-distinct type has no anchor")
            end end
            unknown[#unknown+1]=item
        end
    end
    local groups={}
    for _,name in ipairs(keys(familyOf)) do
        local family=familyOf[name]; groups[family]=groups[family] or {}
        groups[family][#groups[family]+1]=items[name]
    end
    local families,sources={},{}
    for _,family in ipairs(keys(groups)) do
        local members=groups[family]; local hp=false
        for _,item in ipairs(members) do hp=hp or item.hp end
        if hp then
            local canonicalMember
            for i,item in ipairs(members) do
                members[i]=parse(item.name,originals[item.name],true,linkReader,sha256)
                if item.name==family then canonicalMember=members[i] end
            end
            if canonicalMember then for _,item in ipairs(members) do
                if item.name:match("^DW#PTN%d%d$") and not subset(item.keys,canonicalMember.keys,item.non_blocking_keys) then
                    fail("PROVENANCE",item.name,"HP companion differs after ownership resolution")
                end
            end end
        end
        resolvable(members,family)
        local hasOwned,names=false,{}
        for _,item in ipairs(members) do
            hasOwned=hasOwned or any(item.keys); names[item.name]=true
            for _,record in pairs(item.records) do
                for name in pairs(record.nativeSources or {}) do names[name]=true end
            end
        end
        if hasOwned then for _,item in ipairs(members) do for _,removal in ipairs(item.removals) do
            if names[removal.source] then
                if removal.kind=="resource_guard" then fail("RESOURCE_GUARD_CAPABILITY",removal.context,"family immunity can block refresh admission") end
                fail("REMOVAL_CAPABILITY",removal.context,"family source removal requires adapter")
            end
        end end end
        local anchor=items[family]
        local genius=family=="POTN29" and anchor and sameSet(anchor.owned_ops,{[19]=true})
            and not anchor.other_native_buff and not anchor.hp or false
        families[family]={hp=hp,genius=genius}
        for _,item in ipairs(members) do
            sources[item.name]={family=family,keys=item.keys,nonBlockingKeys=item.non_blocking_keys,
                records=item.records,abilities=item.abilities}
            if any(item.calls) then
                local calls={}
                for name,call in pairs(item.calls) do
                    calls[name]={resource=call.resource,abilities=call.abilities,quotas=call.quotas}
                end
                sources[item.name].calls=calls
            end
        end
    end
    return {policy=policy,families=families,sources=sources}
end
return M
