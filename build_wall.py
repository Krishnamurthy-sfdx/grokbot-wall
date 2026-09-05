import json, re, html, glob, os
from datetime import datetime, timezone

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cache')

def parse_oembed(path):
    try:
        d = json.load(open(path))
        if "html" not in d or "url" not in d:
            return None
    except Exception:
        return None
    h = d["html"]
    m = re.search(r'<p lang="(?P<lang>[^"]*)"', h)
    lang = m.group("lang") if m else "en"
    sid = re.search(r'/status/(\d+)', d["url"]).group(1)
    handle = d["author_url"].rstrip("/").split("/")[-1]
    return dict(id=sid, url=d["url"], author=d["author_name"], handle=handle,
                lang=lang, embed_html=h)

def esc(s): return html.escape(s or '', quote=True)

RX_URL = re.compile(r'https?://[^\s<>"]+')
RX_MENTION = re.compile(r'(?<![\w@])@([A-Za-z0-9_]{1,15})\b')
RX_HASH = re.compile(r'(?<![\w#])#([A-Za-z0-9_]+)')

def linkify_plain(text):
    """Linkify plain full text (fxTwitter): URLs, @mentions, #hashtags - span-based, no entity mangling."""
    spans = []
    for m in RX_URL.finditer(text):
        spans.append((m.start(), m.end(),
            f'<a href="{esc(m.group(0))}" target="_blank" rel="noopener">{esc(m.group(0))}</a>'))
    for rx, mk in ((RX_MENTION, lambda m: f'<a href="https://x.com/{m.group(1)}" target="_blank" rel="noopener">@{esc(m.group(1))}</a>'),
                   (RX_HASH, lambda m: f'<a href="https://x.com/hashtag/{m.group(1)}" target="_blank" rel="noopener">#{esc(m.group(1))}</a>')):
        for m in rx.finditer(text):
            spans.append((m.start(), m.end(), mk(m)))
    spans.sort()
    out, cur = [], 0
    for a, b, rep in spans:
        if a < cur:
            continue
        out.append(esc(text[cur:a])); out.append(rep); cur = b
    out.append(esc(text[cur:]))
    return ''.join(out).replace('\n', '<br>')

def link_entities(text, entities):
    """Render tweet text with mentions/urls/hashtags linked; drop media t.co spans."""
    if text is None: return ""
    spans = []
    for m in (entities or {}).get('media', []) or []:
        spans.append((m['indices'][0], m['indices'][1], ''))
    for u in (entities or {}).get('urls', []) or []:
        disp = u.get('display_url') or u.get('expanded_url') or u.get('url')
        href = u.get('expanded_url') or u.get('url')
        spans.append((u['indices'][0], u['indices'][1],
                      f'<a href="{esc(href)}" target="_blank" rel="noopener">{esc(disp)}</a>'))
    for um in (entities or {}).get('user_mentions', []) or []:
        sn = um.get('screen_name','')
        spans.append((um['indices'][0], um['indices'][1],
                      f'<a href="https://x.com/{esc(sn)}" target="_blank" rel="noopener">@{esc(sn)}</a>'))
    for htag in (entities or {}).get('hashtags', []) or []:
        t = htag.get('text','')
        spans.append((htag['indices'][0], htag['indices'][1],
                      f'<a href="https://x.com/hashtag/{esc(t)}" target="_blank" rel="noopener">#{esc(t)}</a>'))
    spans.sort()
    out, cur = [], 0
    for a, b, rep in spans:
        if a < cur:  # overlapping span (e.g. media + url same range)
            continue
        out.append(esc(text[cur:a])); out.append(rep); cur = b
    out.append(esc(text[cur:]))
    return ''.join(out).replace('\n', '<br>')

def media_html(md):
    if not md: return ''
    photos = [m for m in md if m.get('type') == 'photo']
    vids   = [m for m in md if m.get('type') in ('video', 'animated_gif')]
    parts = []
    if photos:
        n = len(photos)
        cls = 'media1' if n == 1 else 'media2'
        imgs = ''.join(f'<img src="{esc(p["media_url_https"])}?name=small" loading="lazy" alt="">' for p in photos[:4])
        parts.append(f'<div class="media {cls}">{imgs}</div>')
    for v in vids[:1]:
        variants = [x for x in (v.get('video_info') or {}).get('variants', []) if x.get('content_type') == 'video/mp4']
        variants.sort(key=lambda x: x.get('bitrate') or 0)
        src = None
        for x in variants:
            if (x.get('bitrate') or 0) <= 2500000: src = x['url']
        if not src and variants: src = variants[0]['url']
        poster = v.get('media_url_https')
        if src and v.get('type') == 'animated_gif':
            parts.append(f'<video class="media vid" src="{esc(src)}" poster="{esc(poster)}" autoplay loop muted playsinline></video>')
        elif src:
            parts.append(f'<video class="media vid" src="{esc(src)}" poster="{esc(poster)}" controls preload="none" playsinline></video>')
    return ''.join(parts)

def quote_html(q):
    if not q or not q.get('user'): return ''
    u = q['user']; sn = u.get('screen_name','')
    url = f'https://x.com/{sn}/status/{q.get("id_str","")}'
    body = link_entities(q.get('text',''), q.get('entities'))
    av = u.get('profile_image_url_https','')
    return (f'<a class="quote" href="{esc(url)}" target="_blank" rel="noopener">'
            f'<div class="qhead"><img class="qav" src="{esc(av)}" alt="">'
            f'<b>{esc(u.get("name",""))}</b><span>@{esc(sn)}</span></div>'
            f'<div class="qtext">{body}</div>{media_html(q.get("mediaDetails"))}</a>')

def fmt_date(iso):
    try:
        dt = datetime.strptime(iso, '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc)
        return dt.strftime('%b %-d, %Y')
    except Exception:
        return ''

def card_from_synd(s, fallback):
    u = s.get('user') or {}
    sn = u.get('screen_name') or fallback['handle']
    name = u.get('name') or fallback['author']
    av = u.get('profile_image_url_https','')
    av = av.replace('_normal.', '_200x200.') if av else ''
    body = link_entities(s.get('text',''), s.get('entities'))
    long_post = ('note_tweet' in s) and (s.get('display_text_range') or [0,0])[1] >= 280
    fx_text = None
    fxp = f'{CACHE}/fx/{s.get("id_str", fallback["id"])}.json'
    if os.path.exists(fxp):
        fxt = html.unescape(json.load(open(fxp)).get('text',''))
        synd_visible = len(re.sub(r'https?://t\.co/\w+\s*$', '', s.get('text','')).strip())
        if len(fxt.strip()) > synd_visible + 10:
            fx_text = fxt.strip()
            body = linkify_plain(fx_text)
            long_post = False
    if long_post:
        body = body.rstrip()
        if not body.endswith('&hellip;'):
            body += ' &hellip;'
    media = media_html(s.get('mediaDetails'))
    quote = quote_html(s.get('quoted_tweet'))
    date = fmt_date(s.get('created_at',''))
    favs = s.get('favorite_count') or 0
    url = f'https://x.com/{sn}/status/{s.get("id_str", fallback["id"])}'
    search = ' '.join(((fx_text or s.get('text','')) + ' ' + name + ' @' + sn).lower().split())
    return url, search, f'''<div class="tweet">
  <div class="thead">
    <img class="av" src="{esc(av)}" loading="lazy" alt="">
    <div class="who"><b>{esc(name)}</b><span>@{esc(sn)}</span></div>
    <a class="xlogo" href="{esc(url)}" target="_blank" rel="noopener" aria-label="Open on X"><svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg></a>
  </div>
  <div class="ttext">{body}</div>
  {media}{quote}
  {f'<div class="longpost">Long post - <a href="{esc(url)}" target="_blank" rel="noopener">read it in full on X &nearr;</a></div>' if long_post else ''}
  <div class="tfoot"><span class="date">{esc(date)}</span><span class="fav">&hearts; {favs:,}</span><a href="{esc(url)}" target="_blank" rel="noopener">Open on X &nearr;</a></div>
</div>'''

def card_from_oembed(p):
    h = p['embed_html']
    pm = re.search(r'<blockquote[^>]*>(.*)</blockquote>', h, re.S)
    inner = pm.group(1) if pm else h
    dm = re.search(r'>([A-Z][a-z]+ \d{1,2}, \d{4})</a>', h)
    date = dm.group(1) if dm else ''
    text = html.unescape(re.sub(r'<[^>]+>', ' ', inner))
    search = ' '.join((text + ' ' + p['author'] + ' @' + p['handle']).lower().split())
    inner = inner.replace('twsrc%5Etfw', 'twsrc%5Etfw')
    return p['url'], search, f'''<div class="tweet">
  <div class="thead"><div class="who"><b>{esc(p["author"])}</b><span>@{esc(p["handle"])}</span></div></div>
  <div class="ttext fallback">{inner}</div>
  <div class="tfoot"><span class="date">{esc(date)}</span><a href="{esc(p["url"])}" target="_blank" rel="noopener">Open on X &nearr;</a></div>
</div>'''

posts = [p for p in (parse_oembed(f) for f in glob.glob(f"{CACHE}/oembed/*.json")) if p]
posts = [p for p in posts if not p["lang"].lower().startswith("zh")]
posts.sort(key=lambda p: int(p["id"]), reverse=True)
now = datetime.now(timezone.utc).astimezone().strftime("%b %-d, %Y, %-I:%M %p %Z")
today = datetime.now(timezone.utc).astimezone().strftime("%B %-d")

cards = []
nsynd = 0
today_count = 0
today_str = datetime.now(timezone.utc).astimezone().strftime("%b %-d, %Y")
for p in posts:
    sp = f'{CACHE}/synd/{p["id"]}.json'
    if os.path.exists(sp):
        s = json.load(open(sp))
        url, search, card = card_from_synd(s, p)
        nsynd += 1
        if fmt_date(s.get('created_at','')) == today_str:
            today_count += 1
    else:
        url, search, card = card_from_oembed(p)
        if today in p.get("embed_html", ""):
            today_count += 1
    ds = esc(search)
    cards.append(f'<div class="card" data-search="{ds}"><div class="render-custom">{card}</div><div class="render-widget"><template>{p["embed_html"]}</template></div></div>')

page = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Grok Bot - Wall of X</title>
<style>
  :root {{ --bg:#000; --page-text:#e7e9ea; --page-dim:#71767b; --page-bright:#a8b0b8;
           --border:#cfd9de; --text:#0f1419; --dim:#536471; --accent:#1d9bf0; --soft:#f7f9f9; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--page-text); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1560px; margin:0 auto; padding:28px 16px 60px; }}
  header.top {{ display:flex; flex-wrap:wrap; align-items:baseline; gap:10px 16px; margin-bottom:6px; }}
  h1 {{ font-size:26px; letter-spacing:-0.3px; }}
  h1 .x {{ color:var(--accent); }}
  .sub {{ color:var(--page-dim); font-size:14px; margin-bottom:20px; }}
  .sub b {{ color:var(--page-bright); font-weight:600; }}
  .controls {{ position:sticky; top:0; background:var(--bg); padding:10px 0 14px; z-index:5; }}
  #q {{ width:100%; max-width:420px; background:#16181c; border:1px solid #2f3336; border-radius:999px;
        padding:10px 18px; color:var(--page-text); font-size:15px; outline:none; }}
  #q:focus {{ border-color:var(--accent); }}
  .wall {{ column-count:3; column-gap:16px; }}
  @media (max-width:1100px) {{ .wall {{ column-count:2; }} }}
  @media (max-width:680px) {{ .wall {{ column-count:1; }} }}
  .card {{ break-inside:avoid; margin-bottom:16px; display:inline-block; width:100%;
          border:1px solid var(--border); border-radius:16px; padding:14px 16px 10px; background:#fff; color:var(--text); }}
  body.mode-widget .card {{ border:none; padding:0; background:transparent; }}
  body.mode-widget .render-custom {{ display:none; }}
  body.mode-custom .render-widget {{ display:none; }}
  .render-widget blockquote.twitter-tweet {{ margin:0; }}
  body.mode-widget .render-widget {{ display:block; background:#fff; border-radius:14px; overflow:hidden; min-height:220px; }}
  .modes {{ display:flex; gap:8px; margin-top:10px; }}
  .modes button {{ background:#16181c; border:1px solid #2f3336; color:var(--page-dim); border-radius:999px;
                   padding:6px 14px; font-size:13px; cursor:pointer; }}
  .modes button.active {{ background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }}
  .tweet .thead {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
  .tweet .av {{ width:40px; height:40px; border-radius:50%; background:var(--soft); }}
  .tweet .who {{ display:flex; flex-direction:column; line-height:1.25; min-width:0; }}
  .tweet .who b {{ font-size:15px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .tweet .who span {{ color:var(--dim); font-size:14px; }}
  .tweet .xlogo {{ margin-left:auto; color:var(--text); opacity:.85; }}
  .tweet .ttext {{ font-size:15px; line-height:1.45; word-wrap:break-word; }}
  .tweet .ttext a {{ color:var(--accent); text-decoration:none; }}
  .tweet .ttext.fallback p {{ margin:0; }}
  .tweet .media {{ margin-top:10px; border-radius:14px; overflow:hidden; border:1px solid var(--border); display:grid; gap:2px; }}
  .tweet .media.media2 {{ grid-template-columns:1fr 1fr; }}
  .tweet .media img {{ width:100%; height:100%; object-fit:cover; display:block; max-height:340px; }}
  .tweet video.media {{ width:100%; display:block; max-height:420px; background:#000; }}
  .tweet a.quote {{ display:block; margin-top:10px; border:1px solid var(--border); border-radius:14px; padding:10px 12px;
                    text-decoration:none; color:var(--text); }}
  .tweet a.quote:hover {{ background:var(--soft); }}
  .tweet .qhead {{ display:flex; align-items:center; gap:6px; margin-bottom:4px; font-size:14px; }}
  .tweet .qhead img.qav {{ width:20px; height:20px; border-radius:50%; }}
  .tweet .qhead span {{ color:var(--dim); }}
  .tweet .qtext {{ font-size:14px; line-height:1.4; color:#2f3336; }}
  .tweet .qtext a {{ color:var(--accent); text-decoration:none; }}
  .tweet .longpost {{ margin-top:10px; font-size:14px; color:var(--dim); }}
  .tweet .longpost a {{ color:var(--accent); text-decoration:none; font-weight:600; }}
  .tweet .tfoot {{ display:flex; gap:14px; align-items:center; margin-top:10px; color:var(--dim); font-size:13px; }}
  .tweet .tfoot a {{ color:var(--dim); text-decoration:none; margin-left:auto; }}
  .tweet .tfoot a:hover {{ color:var(--accent); }}
  .badge {{ background:#1d9bf022; color:var(--accent); border-radius:999px; padding:3px 10px; font-size:13px; font-weight:600; }}
  .none {{ color:var(--page-dim); text-align:center; padding:40px; display:none; }}
  footer.site {{ color:var(--page-dim); font-size:13px; margin-top:26px; text-align:center; }}
  footer.site a {{ color:var(--accent); text-decoration:none; }}
</style>
</head>
<body>
<script>
var savedMode = localStorage.getItem('wallmode') || 'custom';
document.body.className = 'mode-' + savedMode;
</script>
<div class="wrap">
  <header class="top">
    <h1>Grok Bot <span class="x">/ wall of X</span></h1>
    <span class="badge">{today_count} posts today</span>
  </header>
  <p class="sub"><b>{len(posts)} recent X posts</b> about Grok Bot, newest first &middot; refreshed {now}</p>
  <div class="controls">
    <input id="q" type="search" placeholder="Filter posts&hellip;" oninput="filt()">
    <div class="modes">
      <button id="m-custom" onclick="setMode('custom')">Full text</button>
      <button id="m-widget" onclick="setMode('widget')">X embed &middot; classic</button>
    </div>
  </div>
  <main class="wall" id="wall">
  {"".join(cards)}
  </main>
  <p class="none" id="none">No posts match.</p>
  <footer class="site">Real X posts, full text inline - switch to X embed &middot; classic for the native widget look - refreshed daily.</footer>
</div>
<script>
var widgetObserver = null;
function hydrateWidget(w) {{
  var t = w.querySelector('template');
  if (!t) return true;
  if (!window.twttr || !twttr.widgets || !twttr.widgets.load) return false;
  w.appendChild(t.content.cloneNode(true));
  t.remove();
  twttr.widgets.load(w);
  return true;
}}
function startWidgetObserver() {{
  if (widgetObserver) {{ document.querySelectorAll('.render-widget').forEach(function(w) {{ widgetObserver.observe(w); }}); return; }}
  widgetObserver = new IntersectionObserver(function(entries) {{
    entries.forEach(function(en) {{
      if (en.isIntersecting) {{
        var r = en.target.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) return;
        if (hydrateWidget(en.target)) widgetObserver.unobserve(en.target);
      }}
    }});
  }}, {{ rootMargin: '800px' }});
  document.querySelectorAll('.render-widget').forEach(function(w) {{ widgetObserver.observe(w); }});
}}
setInterval(function() {{
  if (!document.body.classList.contains('mode-widget')) return;
  document.querySelectorAll('.render-widget').forEach(function(w) {{
    if (!w.querySelector('template')) return;
    var r = w.getBoundingClientRect();
    if (r.width === 0) return;
    if (r.top < window.innerHeight + 800 && r.bottom > -800) hydrateWidget(w);
  }});
}}, 1500);
var widgetsLoaded = false;
function loadWidgets() {{
  if (widgetsLoaded) {{ startWidgetObserver(); return; }}
  widgetsLoaded = true;
  var sc = document.createElement('script');
  sc.src = 'https://platform.twitter.com/widgets.js';
  sc.async = true; sc.charset = 'utf-8';
  sc.onload = function() {{ if (window.twttr && twttr.ready) {{ twttr.ready(startWidgetObserver); }} else {{ startWidgetObserver(); }} }};
  document.head.appendChild(sc);
}}
function setMode(m) {{
  localStorage.setItem('wallmode', m);
  document.body.className = 'mode-' + m;
  document.getElementById('m-custom').className = m === 'custom' ? 'active' : '';
  document.getElementById('m-widget').className = m === 'widget' ? 'active' : '';
  if (m === 'widget') loadWidgets();
}}
setMode(savedMode);
function filt() {{
  var q = document.getElementById('q').value.toLowerCase();
  var cards = document.querySelectorAll('.card'); var n = 0;
  cards.forEach(function(c) {{
    var hit = !q || (c.getAttribute('data-search')||'').includes(q);
    c.style.display = hit ? '' : 'none'; if (hit) n++;
  }});
  document.getElementById('none').style.display = n ? 'none' : 'block';
}}
</script>
</body>
</html>'''

os.makedirs("/downloads", exist_ok=True)
with open("/downloads/grokbot-wall.html", "w") as f:
    f.write(page)
print(f"wrote {len(posts)} posts ({nsynd} via syndication, {today_count} today), zh excluded")
