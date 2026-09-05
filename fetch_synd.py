import json, math, re, sys, subprocess, os
def b36(n):
    chars='0123456789abcdefghijklmnopqrstuvwxyz'; r=''
    while n>0: r=chars[n%36]+r; n//=36
    return r or '0'
def js36(x):
    ip=int(x); fp=x-ip; s=b36(ip)
    if fp>0:
        s+='.'
        for _ in range(20):
            fp*=36; d=int(fp); s+='0123456789abcdefghijklmnopqrstuvwxyz'[d]; fp-=d
            if fp==0: break
    return s
def tok(tid): return re.sub(r'(0+|\.)','',js36((int(tid)/1e15)*math.pi))
tid = sys.argv[1]
out = subprocess.run(['curl','-s','-m','15',f'https://cdn.syndication.twimg.com/tweet-result?id={tid}&lang=en&token={tok(tid)}','-H','User-Agent: Mozilla/5.0'],capture_output=True,text=True).stdout
try:
    d = json.loads(out)
    if d.get('__typename') != 'Tweet' or 'text' not in d: sys.exit(1)
    CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'synd')
    os.makedirs(CACHE, exist_ok=True)
    json.dump(d, open(os.path.join(CACHE, f'{tid}.json'),'w'))
except Exception:
    sys.exit(1)
