"""Pinned copied-instruction operand-width audit; no engine process or game writes.

Native Apply/Resolve and constructor lifecycle signatures execute/check against
synthetic actor/effect data. Derived-stat baseline reset is a test double.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--exe',type=Path,required=True)
parser.add_argument('--python-libs',type=Path)
args=parser.parse_args()
if args.python_libs: sys.path.insert(0,str(args.python_libs))
import pefile,unicorn
from unicorn import x86_const
import probe_native_admission as n
from probe_native_potion_stats import STATS, StatsMachine, vtable_evidence

n.require(hashlib.sha256(args.exe.read_bytes()).hexdigest()==n.SHA256,'unreviewed executable')
image=pefile.PE(str(args.exe)).get_memory_mapped_image()
entries=dict(STATS)
entries.update({19:('INT',0x1A0100,0x1B6250,0x2AC2,'h',1),
                54:('THAC0',0x1A2F00,0x1C8F90,0x2A80,'h',-1),
                90:('PickPockets',0x1A2940,0x1C6940,0x2AA6,'h',1),
                92:('OpenLocks',0x1A2980,0x1C6B00,0x2AAC,'h',1)})
n.APPLY.update({op:data[2] for op,data in entries.items()})
def i16(value):return (value+32768)%65536-32768
def i32(value):return (value+2**31)%2**32-2**31
def truncate_div(value,denominator):return (abs(value)//denominator)*(-1 if value<0 else 1)
results=[]
amounts=(32767,32768,65535,65536,65537,-65535,2147483647,-2147483648)
for op,(_,ctor,apply,offset,fmt,sign) in sorted(entries.items()):
    vtable_evidence(image,ctor)
    for mode in ((0,3) if op in range(33,38) else (0,)):
        for amount in amounts:
            p=StatsMachine(image,unicorn,x86_const,op);p.verify_self_on_add()
            p.put(n.ACTIVE+0x1C,'iI',amount,mode)
            if mode==3:
                p.put(n.ACTIVE+0xCC,'I',1)
                p.run(apply,n.ACTIVE,n.ACTOR)
                n.require(p.get(n.ACTIVE+0xCC,'I')==0,'save mode3 marker not consumed')
            original=p.read(n.ACTIVE,0x180)
            p.put(n.ACTIVE+0x28,'I',1900);refreshed=p.read(n.ACTIVE,0x180)
            expected=i16(amount)*sign
            if fmt=='h':expected=i16(expected)
            for now in (1000,1501,1899):
                p.put(n.GAME+0x3FA0,'I',now);p.put(n.ACTOR+offset,fmt,0)
                p.run(n.RESOLVE,n.ACTIVE,n.ACTOR)
                n.require(p.get(n.ACTOR+offset,fmt)==expected,f'{op}/{mode}/{amount}: additive width mismatch')
                n.require(p.read(n.ACTIVE,0x180)==refreshed,'effect fields changed')
            count=p.events['apply_active'];p.put(n.GAME+0x3FA0,'I',1900)
            p.run(n.RESOLVE,n.ACTIVE,n.ACTOR)
            n.require(p.events['apply_active']==count,'expiry no longer stops effect')
            results.append({'opcode':op,'mode':mode,'raw_amount':amount,'effective_signed16':i16(amount),'result':expected})

# opcode: base-byte offset, derived offset/format, native setter width, percent
# width, maximum clamp. The finite90 percentage branch differs from92/275.
forms={6:(0x796,0x117A,'h',32,16,25),10:(0x795,0x1178,'h',32,16,25),
       15:(0x794,0x1176,'h',32,16,25),19:(0x792,0x1172,'h',32,16,25),
       44:(0x790,0x116E,'h',32,16,25),49:(0x793,0x1174,'h',32,16,25),
       54:(0x5AA,0x1130,'h',16,16,25),90:(0x5BF,0x1156,'h',32,32,255),
       91:(0x5C1,0x115A,'h',32,32,255),92:(0x5C2,0x115C,'h',32,16,255),
       275:(0x59D,0x1194,'i',8,16,None)}
for op,(base,derived,fmt,set_width,pct_width,maximum) in sorted(forms.items()):
    for mode in (1,2):
        for amount in (-65535,-1,0,65535,65536,65537,65686,2147483647):
            p=StatsMachine(image,unicorn,x86_const,op);p.verify_self_on_add()
            p.put(n.ACTIVE+0x1C,'iI',amount,mode)
            baseline=20 if op in (6,10,15,19,44,49,54) else 50
            p.put(n.ACTOR+base,'B',baseline);p.put(n.ACTOR+derived,fmt,baseline)
            original=p.read(n.ACTIVE,0x180)
            if mode==1:
                effective=amount%256 if set_width==8 else i16(amount) if set_width==16 else amount
                expected=effective
            else:
                effective=i16(amount) if pct_width==16 else amount
                expected=truncate_div(i32(baseline*effective),100)
                if op==54:expected=i16(expected)
            if maximum is not None:expected=max(0,min(maximum,expected))
            p.run(n.APPLY[op],n.ACTIVE,n.ACTOR)
            n.require(p.get(n.ACTOR+derived,fmt)==expected,f'{op}/{mode}/{amount}: set/percent width mismatch')
            n.require(p.read(n.ACTIVE,0x180)==original,'set/percent changed effect fields')
            results.append({'opcode':op,'mode':mode,'raw_amount':amount,'effective_operand':effective,'result':expected})
for baseline in (-128,-10,-1,0,20,127):
    for amount in (-100,0,90,100,150):
        p=StatsMachine(image,unicorn,x86_const,54);p.verify_self_on_add()
        p.put(n.ACTIVE+0x1C,'iI',amount,2)
        p.put(n.ACTOR+0x5AA,'b',baseline);p.put(n.ACTOR+0x1130,'h',baseline)
        expected=max(0,min(25,truncate_div(baseline*amount,100)))
        original=p.read(n.ACTIVE,0x180)
        p.run(n.APPLY[54],n.ACTIVE,n.ACTOR)
        n.require(p.get(n.ACTOR+0x1130,'h')==expected,'negative THAC0 baseline arithmetic mismatch')
        n.require(p.read(n.ACTIVE,0x180)==original,'negative baseline effect fields changed')
        results.append({'opcode':54,'mode':2,'raw_amount':amount,'base_signed8':baseline,
                        'result':expected,'native_100_percent_control':max(0,min(25,baseline))})
print(json.dumps({'exe_sha256':n.SHA256,'cases':results,'count':len(results),
    'limitations':['Synthetic baseline resets, no whole game stat rebuild/admission/HP arithmetic.','Original raw operands retained; this probe does not rewrite resources or implement policy.']},indent=2))
