import json,struct,os,collections
_T=json.load(open(os.path.join(os.path.dirname(__file__),'table.json')))
for r in _T:
    if r['mn']=='AND Dm,Dn' and len(r['pat'])==6: r['pat']+= [['reg','Dm'],['reg','Dn']]
    if r['mn']=='PC+7': r['mn']='CALL label'
    if r['mn']=='MOV Dm,MDR': r['pat'][7]=['bits',2]          # F2 F2|Dm<<2
    if r['mn']=='MOV Dm,(d8,An)': r['pat'][4]=['bits',0]; r['pat'][5]=['bits',1]   # F8 1x
    if r['mn']=='SUB imm32,Dn': r['pat'][6]=['bits',1]        # FC C4+n
    if r['mn']=='LCS': r['pat'][2]=['bits',1]; r['pat'][3]=['bits',0]   # D4
    if r['mn']=='MOV imm32,Dn': r['pat'][6]=['bits',3]   # manual typo: FC CC+n (CMP is FC C8+n)
    if r['mn']=='OR imm32,Dn' and len(r['pat'])==6: r['pat']+= [['bits',1],['reg','Dn'],['imm','imm32',32]]
REG={'Dm':'d','Dn':'d','Am':'a','An':'a','Di':'d','Rm':'r','Rn':'r'}
class Op:
    __slots__=('mn','size','fixmask','fixval','fields')
OPS=[]
for r in _T:
    bitpos=0; fm=0; fv=0; fields=[]; total=sum(p[2] if p[0]=='imm' else 2 for p in r['pat'])
    if total%8: continue
    for p in r['pat']:
        if p[0]=='bits':
            sh=total-bitpos-2; fm|=3<<sh; fv|=p[1]<<sh; bitpos+=2
        elif p[0]=='reg':
            fields.append(('reg',p[1],total-bitpos-2,2)); bitpos+=2
        else:
            fields.append(('imm',p[1],bitpos,p[2])); bitpos+=p[2]
    o=Op(); o.mn=r['mn']; o.size=total//8; o.fixmask=fm; o.fixval=fv; o.fields=fields; OPS.append(o)
# index by first byte; only fixed opcode bits matter (immediates are not in fixmask)
BY=collections.defaultdict(list)
for o in OPS:
    fb_mask=(o.fixmask>>(o.size*8-8))&0xff; fb_val=(o.fixval>>(o.size*8-8))&0xff
    for b in range(256):
        if b&fb_mask==fb_val: BY[b].append(o)
def _prio(o):
    names=[f[1] for f in o.fields if f[0]=='reg']
    return (-(len(names)-len(set(names))), -bin(o.fixmask).count('1'))
for b in BY: BY[b].sort(key=_prio)
def decode(buf,off,pc):
    """returns (size, mnemonic_text, info dict) or None"""
    b0=buf[off]
    for o in BY.get(b0,()):
        if off+o.size>len(buf): continue
        word=int.from_bytes(buf[off:off+o.size],'big')
        if word&o.fixmask!=o.fixval: continue
        vals={}; regs={}; okk=True
        for kind,name,pos,w in o.fields:
            if kind=='reg':
                v=(word>>pos)&3
                if name in regs and regs[name]!=v: okk=False
                regs[name]=v
            else:
                bs=buf[off+pos//8:off+pos//8+w//8]
                v=int.from_bytes(bs,'little')
                if name.startswith('d') or (name.startswith('imm') ):
                    if v&(1<<(w-1)): sv=v-(1<<w)
                    else: sv=v
                else: sv=v
                vals[name]=(v,sv,w)
        if not okk: continue
        txt=o.mn
        info={'mn':o.mn.split()[0],'regs':regs,'vals':vals}
        for name,(v,sv,w) in vals.items():
            m0=o.mn.split()[0]
            if name.startswith('d') and m0[0]=='B' and m0 not in ('BTST','BSET','BCLR') and ',PC)' in o.mn:
                tgt=(pc+sv)&0xffffffff; info['target']=tgt
                txt=txt.replace('(%s,PC)'%name,'0x%08x'%tgt)
            elif name.startswith('d') and ('label' in o.mn or o.mn.split()[0] in ('CALL','JMP') or o.mn.split()[0].startswith('B')) and '(d' not in o.mn:
                tgt=(pc+sv)&0xffffffff; info['target']=tgt; rep='0x%08x'%tgt
                txt=txt.replace('label',rep)
            elif name.startswith('imm'):
                rep='0x%x'%v if w>8 else ('%d'%sv)
                txt=txt.replace(name,rep,1)
            else:
                rep=('0x%x'%v) if name.startswith('abs') or name=='regs' else '%d'%sv
                txt=txt.replace(name,rep,1)
        # register names
        import re
        def rr(m):
            k=m.group(0); return REG[k]+str(regs.get(k,'?'))
        txt=re.sub(r'Dm|Dn|Am|An|Di|Rm|Rn',rr,txt)
        return o.size,txt,info
    return None
