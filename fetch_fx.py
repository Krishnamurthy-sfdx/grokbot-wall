import json, sys, subprocess, os
tid = sys.argv[1]
out = subprocess.run(['curl','-s','-m','15',f'https://api.fxtwitter.com/status/{tid}','-H','User-Agent: Mozilla/5.0'],capture_output=True,text=True).stdout
try:
    d = json.loads(out)
    t = d.get('tweet') or {}
    if not t.get('text'): sys.exit(1)
    CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache', 'fx')
    os.makedirs(CACHE, exist_ok=True)
    json.dump(t, open(os.path.join(CACHE, f'{tid}.json'),'w'))
except Exception:
    sys.exit(1)
