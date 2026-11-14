import re,sys,json
lines=open(sys.argv[1]).read().splitlines()
WID={'d8':8,'imm8':8,'abs8':8,'regs':8,'d16':16,'imm16':16,'abs16':16,'d32':32,'imm32':32,'abs32':32,'d24':24,'imm24':24,'abs24':24}
out=[];prev=None
for l in lines[8500:9900]  # instruction summary tables (MN1030 manual appendix):
    m=re.search(r'\s([SD][0-9])\s{1,3}([01]{4}\b.*)$',l)
    if not m: continue
    pre=l[:m.start()][18:].strip()
    segs=[s for s in re.split(r'\s{2,}',pre) if s]
    # drop flag/size columns
    mn=None
    if segs:
        w=segs[0].split()
        if segs[0].startswith('IF') or segs[0].startswith('mem') : mn=prev
        elif len(w)==1 and len(segs)>1 and re.match(r'[A-Z]{2,}',segs[1]) and '→' not in segs[1] and not segs[1].startswith('IF'):
            mn=segs[1]
        elif len(w)>=2 and re.fullmatch(r'[A-Z][A-Za-z0-9]*',w[1]) and w[1].isupper():
            mn=' '.join(w[1:])
        else: mn=segs[0]
    else: mn=prev
    mn=re.sub(r'\s+[A-Za-z0-9(]*\s*(→|IF|PC|mem|←).*$','',mn) if mn else mn
    prev=mn
    # pattern
    pat=[];fields=[]; rest=m.group(2)
    toks=re.findall(r'<[^>]*>?|\S+',rest)
    ok=True
    for t in toks:
        if t.startswith('<'):
            name=re.match(r'<\s*([a-z]+\d*)',t)
            if not name or name.group(1) not in WID: ok=False;break
            pat.append(('imm',name.group(1),WID[name.group(1)]))
        elif re.fullmatch(r'\.+>?',t): continue
        elif len(t)==4 and re.fullmatch(r'(?:[01]{2}|Dm|Dn|Am|An|Di|Rm|Rn)+',t):
            for k in (0,2):
                p=t[k:k+2]
                if p in ('00','01','10','11'): pat.append(('bits',int(p,2)))
                else: pat.append(('reg',p))
        else: break
    if not ok or not pat: continue
    out.append({'mn':mn,'fmt':m.group(1),'pat':pat})
json.dump(out,open(sys.argv[2],'w'),indent=0)
print(len(out))
import collections
for r in out[::25]: print(r['mn'],r['fmt'],''.join(str(p[1])+'.' for p in r['pat']))
