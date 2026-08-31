# Grok Bot - Wall of X

A live wall of recent X (Twitter) posts about Grok Bot, rendered as X-style cards with full post text, photos, videos, and quoted posts inline.

**Live site: https://grokbot-wall.vercel.app**

## How it works

A daily pipeline (7:00 AM SGT) rebuilds the wall as a single static HTML page:

1. **Harvest** - `refresh.sh` scrapes post URLs from public Grok Bot community sites (usegrokbot.com, grokbot.dev/wall).
2. **Verify** - every candidate URL is verified as a real X post through `publish.twitter.com/oembed` (no auth needed). Chinese-language posts are filtered out here.
3. **Enrich** - `fetch_synd.py` pulls each post's data (text, entities, media, quoted posts) from X's public syndication endpoint (`cdn.syndication.twimg.com`) - the same unauthenticated feed libraries like react-tweet use. For long-form posts (X "note tweets"), which the syndication endpoint truncates at ~280 chars, `fetch_fx.py` fetches the complete text from the public api.fxtwitter.com mirror.
4. **Render** - `build_wall.py` renders each post as a self-contained X-style card: avatar, author, full text with linked mentions/hashtags/URLs, photo grids, native video players, nested quote boxes, date, and like count. No iframes, no X widgets.js - posts render complete, never truncated behind a "Show more".
5. **Deploy** - the page is uploaded to Vercel via its REST API and the project aliases are pointed at the new deployment.

The result is one static HTML file (~165KB) with a client-side filter box, a responsive masonry layout (3/2/1 columns), and a view-mode toggle: **Full text** (the custom full-text cards, default) or **X embed - classic** (X's native widget embeds, lazy-loaded on first use; long posts show X's own "Show more" there). The choice persists in localStorage.

## Files

| File | Role |
| --- | --- |
| `index.html` | The built wall (regenerated daily - do not hand-edit) |
| `refresh.sh` | The daily pipeline: harvest, verify, enrich, build, deploy |
| `fetch_synd.py` | Fetches one post's JSON from the X syndication endpoint |
| `fetch_fx.py` | Fetches complete long-form (note tweet) text via api.fxtwitter.com |
| `build_wall.py` | Renders the static page from the fetched data |

## Running it yourself

```bash
# the pipeline expects a Vercel API token in .vercel-token (not committed)
echo "your-vercel-token" > .vercel-token
chmod 600 .vercel-token

./refresh.sh
```

Outputs the built page to `/downloads/grokbot-wall.html` and deploys it to the Vercel project named `grokbot-wall`, updating the aliases. To only build locally without deploying, run `build_wall.py` after the fetch steps and open `/downloads/grokbot-wall.html`.

## Notes

- No X API key required anywhere: oEmbed, the syndication endpoint, and the fxTwitter mirror are all public and unauthenticated.
- `.vercel-token` is gitignored and never committed.
