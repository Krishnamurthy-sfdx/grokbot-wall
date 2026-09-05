#!/bin/bash
# Daily refresh: harvest Grok Bot post URLs from community-site catalogues, verify via X oEmbed,
# enrich via syndication/fxTwitter, rebuild wall, redeploy to Vercel.
# Archive mode: caches live in $D/cache (committed to the repo), so every post ever collected
# stays on the wall permanently and the count is monotonic across sandbox rebuilds.
set -u
D=/home/sandbox/grokbot-wall
TOKEN=$(cat "$D/.vercel-token")
CACHE="$D/cache"
RX='https?://(x|twitter)\.com/[A-Za-z0-9_]+/status/[0-9]+'
mkdir -p "$CACHE/oembed" "$CACHE/synd" "$CACHE/fx" /tmp/site

# --- 1. harvest: static seed pages ---
{ curl -sL -m 20 "https://usegrokbot.com/en"
  curl -sL -m 20 "https://usegrokbot.com/en/use-cases"
  curl -sL -m 20 "https://usegrokbot.com/en/templates"
  curl -sL -m 20 "https://grokbot.dev/wall/"
  curl -sL -m 20 "https://grokbot.dev/integrations/x/"
  curl -sL -m 20 "https://grokbot.dev/marketplace/"
} | grep -oE "$RX" > /tmp/urls_seed.txt || true

# --- 1b. harvest: usegrokbot discover case pages (from sitemap) ---
curl -sL -m 20 "https://usegrokbot.com/sitemap.xml" | grep -oE '<loc>[^<]*' | sed 's/<loc>//' | grep '/en/discover/' > /tmp/pages_discover.txt || true
while read -r p; do curl -sL -m 15 "$p"; done < /tmp/pages_discover.txt | grep -oE "$RX" > /tmp/urls_discover.txt || true

# --- 1c. harvest: grokbot.dev use-case pages (via pagination) ---
> /tmp/gd_pages.txt
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  path="/use-cases/"; [ "$i" -gt 1 ] && path="/use-cases/$i/"
  curl -sL -m 15 "https://grokbot.dev$path" | grep -oE 'href="/use-cases/[a-z0-9-]+/"' | sed 's/href="//;s/"$//' >> /tmp/gd_pages.txt
done
sort -u /tmp/gd_pages.txt | grep -vE '^/use-cases/([0-9]+)?/$' > /tmp/gd_case_pages.txt
while read -r p; do curl -sL -m 15 "https://grokbot.dev$p"; done < /tmp/gd_case_pages.txt | grep -oE "$RX" > /tmp/urls_cases.txt || true

cat /tmp/urls_seed.txt /tmp/urls_discover.txt /tmp/urls_cases.txt 2>/dev/null | sort -u > /tmp/urls.txt
URLS=$(wc -l < /tmp/urls.txt)

# --- 2. verify via oEmbed (archive: fetch only posts not already cached; keep only successes) ---
fetch_oembed() {
  u="$1"
  id=$(echo "$u" | grep -oE '[0-9]+$')
  [ -f "$CACHE/oembed/$id.json" ] && return 0
  enc=$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=''))" "$u")
  out=$(curl -sL -m 15 "https://publish.twitter.com/oembed?url=$enc&omit_script=1")
  case "$out" in *'"html"'*) printf '%s' "$out" > "$CACHE/oembed/$id.json";; esac
}
export CACHE
cat /tmp/urls.txt | xargs -P 6 -I{} bash -c "$(declare -f fetch_oembed); fetch_oembed {}" 2>/dev/null || \
while read -r u; do fetch_oembed "$u"; done < /tmp/urls.txt

# --- 3. enrich via syndication (only missing) ---
cat /tmp/urls.txt | xargs -P 6 -I{} bash -c 'id=$(echo "{}" | grep -oE "[0-9]+$"); [ -f "'"$CACHE"'/synd/$id.json" ] || python3 "'"$D"'/fetch_synd.py" "$id" >/dev/null 2>&1' || true

# --- 3b. long-form (note tweet) text via fxTwitter (only missing) ---
for f in "$CACHE"/synd/*.json; do
  id=$(basename "$f" .json)
  if grep -q '"note_tweet"' "$f" && [ ! -f "$CACHE/fx/$id.json" ]; then
    python3 "$D/fetch_fx.py" "$id" >/dev/null 2>&1 || true
  fi
done

# --- 4. build ---
python3 "$D/build_wall.py"
cp /downloads/grokbot-wall.html /tmp/site/index.html

# --- 5. deploy ---
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
