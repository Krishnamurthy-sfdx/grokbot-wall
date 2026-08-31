import json, sys, subprocess, os
tid = sys.argv[1]
out = subprocess.run(['curl','-s','-m','15',f'https://api.fxtwitter.com/status/{tid}','-H','User-Agent: Mozilla/5.0'],capture_output=True,text=True).stdout
try:
    d = json.loads(out)
    t = d.get('tweet') or {}
    if not t.get('text'): sys.exit(1)
    os.makedirs('/tmp/fx', exist_ok=True)
    json.dump(t, open(f'/tmp/fx/{tid}.json','w'))
except Exception:
    sys.exit(1)
