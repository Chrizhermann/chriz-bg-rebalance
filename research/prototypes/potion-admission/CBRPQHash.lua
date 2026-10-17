-- Pure LuaJIT SHA256 for immutable resource/compiler keys. No files or globals.
local bit = require("bit")
local band, bxor, bnot, ror, shr = bit.band, bit.bxor, bit.bnot, bit.ror, bit.rshift
local K = {
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
}
local function be32(value)
    return string.char(band(shr(value,24),255), band(shr(value,16),255),
                       band(shr(value,8),255), band(value,255))
end
local function sha256(message)
    assert(type(message)=="string", "SHA256 input must be a binary string")
    local length = #message
    local data = message .. "\128" .. string.rep("\0", (55-length)%64)
        .. be32(math.floor(length/536870912)) .. be32((length*8)%4294967296)
    local H = {0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
               0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19}
    local W = {}
    for offset=1,#data,64 do
        for i=0,15 do
            local a,b,c,d = data:byte(offset+i*4,offset+i*4+3)
            W[i] = a*16777216+b*65536+c*256+d
        end
        for i=16,63 do
            local x,y = W[i-15],W[i-2]
            W[i] = bit.tobit(W[i-16]+bxor(ror(x,7),ror(x,18),shr(x,3))
                +W[i-7]+bxor(ror(y,17),ror(y,19),shr(y,10)))
        end
        local a,b,c,d,e,f,g,h = unpack(H)
        for i=0,63 do
            local t1 = bit.tobit(h+bxor(ror(e,6),ror(e,11),ror(e,25))
                +bxor(band(e,f),band(bnot(e),g))+K[i+1]+W[i])
            local t2 = bit.tobit(bxor(ror(a,2),ror(a,13),ror(a,22))
                +bxor(band(a,b),band(a,c),band(b,c)))
            h,g,f,e,d,c,b,a = g,f,e,bit.tobit(d+t1),c,b,a,bit.tobit(t1+t2)
        end
        local values={a,b,c,d,e,f,g,h}
        for i=1,8 do H[i]=bit.tobit(H[i]+values[i]) end
    end
    local output={}
    for i=1,8 do output[i]=string.format("%08x",H[i]<0 and H[i]+4294967296 or H[i]) end
    return table.concat(output)
end
return {sha256=sha256}
