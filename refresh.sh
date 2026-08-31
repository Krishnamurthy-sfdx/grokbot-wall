#!/bin/bash
# Daily refresh: harvest Grok Bot post URLs, verify via X oEmbed, rebuild wall, redeploy to Vercel.
set -u
D=/home/sandbox/grokbot-wall
TOKEN=$(cat "$D/.vercel-token")
mkdir -p /tmp/oembed /tmp/site
{ curl -sL -m 20 "https://usegrokbot.com/en"; curl -sL -m 20 "https://usegrokbot.com/en/use-cases"; curl -sL -m 20 "https://usegrokbot.com/en/templates"; curl -sL -m 20 "https://grokbot.dev/wall/"; } | grep -oE 'https?://(x|twitter)\.com/[A-Za-z0-9_]+/status/[0-9]+' | sort -u > /tmp/urls.txt
URLS=$(wc -l < /tmp/urls.txt)
while read -r u; do
  id=$(echo "$u" | grep -oE '[0-9]+$')
  enc=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$u")
  curl -sL -m 15 "https://publish.twitter.com/oembed?url=$enc&omit_script=1" -o "/tmp/oembed/$id.json"
done < /tmp/urls.txt
mkdir -p /tmp/synd
while read -r u; do
  id=$(echo "$u" | grep -oE '[0-9]+$')
  [ -f "/tmp/synd/$id.json" ] || python3 "$D/fetch_synd.py" "$id" || true
done < /tmp/urls.txt
mkdir -p /tmp/fx
for f in /tmp/synd/*.json; do
  id=$(basename "$f" .json)
  if grep -q '"note_tweet"' "$f" && [ ! -f "/tmp/fx/$id.json" ]; then
    python3 "$D/fetch_fx.py" "$id" || true
  fi
done
python3 "$D/build_wall.py"
cp /downloads/grokbot-wall.html /tmp/site/index.html
SHA=$(sha1sum /tmp/site/index.html | cut -d' ' -f1); SIZE=$(wc -c < /tmp/site/index.html)
curl -s -m 30 -X POST "https://api.vercel.com/v2/files" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/octet-stream" -H "x-vercel-digest: $SHA" --data-binary @/tmp/site/index.html > /dev/null
curl -s -m 45 -X POST "https://api.vercel.com/v13/deployments?forceNew=1" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"name\":\"grokbot-wall\",\"files\":[{\"file\":\"index.html\",\"sha\":\"$SHA\",\"size\":$SIZE}],\"projectSettings\":{\"framework\":null}}" > /tmp/deploy.json
DPLID=$(jq -r '.id // empty' /tmp/deploy.json)
if [ -n "$DPLID" ]; then
  for A in grokbot-wall.vercel.app grokbot-wall-rvaraghav-5036s-projects.vercel.app; do
    curl -s -m 20 -X POST "https://api.vercel.com/v2/deployments/$DPLID/aliases" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"alias\":\"$A\"}" > /dev/null
  done
fi
STATE=$(jq -r '.readyState // .error.code // "?"' /tmp/deploy.json)
sleep 5
CODE=$(curl -sL -m 20 "https://grokbot-wall.vercel.app" -o /tmp/site_check.html -w "%{http_code}")
CARDS=$(grep -c 'class="card"' /tmp/site_check.html || true)
TITLE=$(grep -o '<title>[^<]*' /tmp/site_check.html | head -1)
echo "urls_harvested=$URLS deploy_state=$STATE verify_http=$CODE cards=$CARDS title='$TITLE'"
