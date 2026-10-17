"""Pinned offline color7/spell-level102 instruction probe; never runs a game.

Synthetic actor/effects; allocator, list storage and animation render services
are substituted. Native Apply, Resolve and self OnAdd execute.
"""
from pathlib import Path
import argparse, hashlib, json, sys
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe',type=Path,required=True)
parser.add_argument('--python-libs',type=Path)
args=parser.parse_args()
if args.python_libs:
    sys.path.insert(0,str(args.python_libs))
import pefile, unicorn
from unicorn import x86_const
import probe_native_admission as n
from probe_native_potion_stats import StatsMachine, vtable_evidence

exe=args.exe
assert hashlib.sha256(exe.read_bytes()).hexdigest()==n.SHA256
image=pefile.PE(str(exe)).get_memory_mapped_image()
n.APPLY.update({7:0x1A98A0,102:0x1B6E10,101:0x1B6C10,169:0x1B6D20,267:0x1B6B50,296:0x1B6E50,166:0x1C1B70})

class ColorMachine(StatsMachine):
    def __init__(self,opcode):
        self.alloc=0x700000000;self.entries=[];self.colors=[]
        super().__init__(image,unicorn,x86_const,opcode)
        self.u.mem_map(self.alloc,0x10000)
        self.put(n.ACTOR+0x3C40,'Q',n.META+0xA000)
        self.put(n.META+0xA000,'Q',n.META+0xA100)
        self.put(n.META+0xA100+0x158,'Q',n.FAKE_CALLS+0x800)
        self.put(n.META+0xA100+0x160,'Q',n.FAKE_CALLS+0x808)
    def on_code(self,uc,address,size,data):
        rva=address-n.BASE
        if rva==0x4F7A88:
            assert self.reg_read('RCX')==2
            pointer=self.alloc;self.alloc+=16;self.ret(pointer);return
        if rva==0x4075C0:
            assert self.reg_read('RCX')==n.ACTOR+0x1AD0
            self.entries.append(tuple(self.read(self.reg_read('RDX'),2)))
            self.ret(0);return
        if address in (n.FAKE_CALLS+0x800,n.FAKE_CALLS+0x808):
            self.colors.append((address-n.FAKE_CALLS,self.reg_read('RDX'),self.reg_read('R8')))
            self.ret(0);return
        super().on_code(uc,address,size,data)

class ProtectionMachine(StatsMachine):
    def __init__(self,opcode):
        self.alloc=0x710000000;self.entries=[]
        super().__init__(image,unicorn,x86_const,opcode)
        self.u.mem_map(self.alloc,0x20000)
    def allocate(self,size):
        pointer=self.alloc;self.alloc+=(size+15)&~15;return pointer
    def on_code(self,uc,address,size,data):
        rva=address-n.BASE
        if rva==0x4F7A88:
            assert self.reg_read('RCX')==0x30
            self.ret(self.allocate(0x30));return
        if rva==0x1DE3D0:
            # Decoder service test double; native Apply builds its raw record.
            raw=self.read(self.reg_read('RCX'),0x30)
            pointer=self.allocate(0x180)
            self.put(pointer+0x10,'I',int.from_bytes(raw[:2],'little'))
            self.put(pointer+0x1C,'II',int.from_bytes(raw[4:8],'little'),int.from_bytes(raw[8:12],'little'))
            self.ret(pointer);return
        if rva==0x45E690:
            self.ret(0);return
        if rva==0x4075C0:
            assert self.reg_read('RCX')==n.ACTOR+0x1448
            pointer=self.reg_read('RDX');node=self.allocate(0x20)
            self.put(node,'QQQ',0,0,pointer)
            if self.entries:self.put(self.entries[-1][0],'Q',node)
            else:self.put(n.ACTOR+0x1450,'Q',node)
            self.entries.append((node,pointer));self.ret(node);return
        super().on_code(uc,address,size,data)

results=[]
for mode in (0,6,255):
    for amount in (0,53,72):
        p=ColorMachine(7);p.verify_self_on_add()
        lifecycle=vtable_evidence(image,0x19EC20)
        p.put(n.ACTIVE+0x1C,'iI',amount,mode)
        original=p.read(n.ACTIVE,0x180)
        for call in range(2):
            p.run(n.APPLY[7],n.ACTIVE,n.ACTOR)
            assert p.read(n.ACTIVE,0x180)==original
        expected=[(i+j,amount) for i in (0,16,32,48) for j in range(7)] if mode==255 else [(mode,amount)]
        assert p.entries==expected*2
        assert p.get(n.ACTOR+0x4BB8,'I')==1
        p.put(n.ACTIVE+0x28,'I',1900)
        refreshed=p.read(n.ACTIVE,0x180)
        p.put(n.GAME+0x3FA0,'I',1501)
        p.run(n.RESOLVE,n.ACTIVE,n.ACTOR)
        assert p.read(n.ACTIVE,0x180)==refreshed
        before=len(p.entries)
        p.put(n.GAME+0x3FA0,'I',1900)
        p.run(n.RESOLVE,n.ACTIVE,n.ACTOR)
        assert len(p.entries)==before and p.get(n.ACTIVE+0x114,'I')==1
        results.append({'opcode':7,'amount':amount,'mode':mode,'lifecycle':lifecycle})
for level in (0,1,5,9,10):
    p=ColorMachine(102);p.verify_self_on_add()
    lifecycle=vtable_evidence(image,0x1A0580)
    p.put(n.ACTIVE+0x1C,'I',level)
    original=p.read(n.ACTIVE,0x180)
    for call in range(2):
        p.run(n.APPLY[102],n.ACTIVE,n.ACTOR)
        assert p.read(n.ACTIVE,0x180)==original
        assert p.get(n.ACTOR+0x14B8+level*4,'I')==(1 if level<10 else 0)
    results.append({'opcode':102,'level':level,'lifecycle':lifecycle})
# Execute the actual boolean lookup rather than its parent probe's gate stub.
n.STUBS.pop(0x1F8E30)
for opcode,amount,mode,child,ctor in ((101,0,5,5,0x1A0480),(101,0,24,24,0x1A0480),
                                   (169,0,22,142,0x1A04C0),(267,8364,5,139,0x1A0440),
                                   (296,0,5,215,0x1A0640)):
    p=ProtectionMachine(opcode);p.verify_self_on_add()
    if opcode!=101:vtable_evidence(image,ctor)
    p.put(n.ACTIVE+0x1C,'iI',amount,mode)
    p.u.mem_write(n.ACTIVE+0x30,b'TESTVFX\0')
    original=p.read(n.ACTIVE,0x180)
    for count in (1,2):
        p.run(n.APPLY[opcode],n.ACTIVE,n.ACTOR)
        assert p.read(n.ACTIVE,0x180)==original
        assert len(p.entries)==count
        for matched in (False,True):
            p.put(n.EFFECT+0x10,'I',child if matched else 999)
            p.put(n.EFFECT+0x1C,'II',amount,0 if opcode==101 else mode)
            p.u.mem_write(n.EFFECT+0x30,b'TESTVFX\0')
            before=[p.read(pointer,0x180) for _,pointer in p.entries]
            p.run(0x1F8E30,n.ACTOR+0x1448,n.EFFECT)
            assert p.reg_read('EAX')==int(matched)
            assert before==[p.read(pointer,0x180) for _,pointer in p.entries]
    results.append({'opcode':opcode,'amount':amount,'mode':mode,'duplicates':'same boolean lookup result; no entry consumption',
                    'on_remove_reviewed':opcode!=101})
for mode in (0,1):
    for amount in (-50,-1,0,1,50,127,65537,2147450880,2147483647):
        p=StatsMachine(image,unicorn,x86_const,166);p.verify_self_on_add()
        lifecycle=vtable_evidence(image,0x1A1DC0)
        p.put(n.ACTIVE+0x1C,'iI',amount,mode)
        p.put(n.ACTOR+0x1146,'h',10)
        original=p.read(n.ACTIVE,0x180);expected=10;outputs=[]
        for call in range(2):
            p.run(n.APPLY[166],n.ACTIVE,n.ACTOR)
            raw=amount if mode==1 else (expected+amount+2**31)%2**32-2**31
            expected=max(-128,min(127,raw));outputs.append(expected)
            assert p.get(n.ACTOR+0x1146,'h')==expected
            assert p.read(n.ACTIVE,0x180)==original
        p.put(n.ACTIVE+0x28,'I',1900);refreshed=p.read(n.ACTIVE,0x180)
        for now in (1000,1501,1899):
            p.put(n.ACTOR+0x1146,'h',10);p.put(n.GAME+0x3FA0,'I',now)
            p.run(n.RESOLVE,n.ACTIVE,n.ACTOR)
            assert p.read(n.ACTIVE,0x180)==refreshed
        count=p.events['apply_active'];p.put(n.GAME+0x3FA0,'I',1900)
        p.run(n.RESOLVE,n.ACTIVE,n.ACTOR)
        assert p.events['apply_active']==count and p.get(n.ACTIVE+0x114,'I')==1
        results.append({'opcode':166,'amount':amount,'mode':mode,'consecutive_values':outputs,'lifecycle':lifecycle})
report={'exe_sha256':n.SHA256,'cases':results,'limitations':['Synthetic actor/effect data; allocator/list AddTail, pattern DecodeEffect and animation rendering methods stubbed.','Native Apply, Resolve, self OnAdd and immunity lookup execute; constructor/lifecycle table signatures verified except101 nontrivialOnRemove remains unprobed.','MR baseline resets are synthetic; no whole derived-stat rebuild or magic-resistance admission roll executes.','No native engine process, game, resources or saves changed.']}
print(json.dumps(report,indent=2))
