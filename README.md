# hardlyfunny.com

*Hardly Funny* is a webcomic by Samantha Degges about being married to a computer programmer (82 comics, 2012–2014). This repo is its move off WordPress.com to a static site.

## Quick start

```sh
pip install -r requirements-dev.txt
python -m hardlyfunny serve        # builds into _site/ and serves http://localhost:8000/
python -m pytest                   # checks content, SEO tags, accessibility basics, links and the feed
```

`python -m hardlyfunny build` only builds. Pass `--site-url https://preview.example.com` for a preview deploy, so canonical URLs and OG tags point at the preview.

## What the site includes

- **Clean, permanent URLs**: one page per comic at `/comics/<slug>/` (e.g. `/comics/infinite-recursion/`), plus `/archive/`, `/about/` and `/random/`.
- **Atom feed** at `/feed.xml`, linked from every page as "Feed". Entries embed the comic, its alt text, Samantha's note and the transcript. Entry IDs are tag URIs, so they never change.
- **Social sharing**: X, Facebook, LinkedIn, Reddit and Hacker News intent links with the title prefilled. The comic image comes from each page's `og:image`: a 1200×630 card generated per comic. Instagram has no web share link, so its button uses the device's share sheet with the image attached (phones), and otherwise copies the link and points to the image.
- **SEO/GEO**: a unique `<title>`, meta description and canonical URL on every page. Open Graph and Twitter card tags. `ComicStory`/`ComicSeries` JSON-LD. A `sitemap.xml`, a `robots.txt`, and `llms.txt` / `llms-full.txt` (with every transcript) for AI answer engines.
- **Accessibility**:
  - Every comic has written alt text and a full transcript.
  - Pages use skip links, landmarks, one `h1` each, and a visible focus style.
  - Colors meet WCAG AA contrast in both modes.
  - The shortcuts can be turned off, and the site respects `prefers-reduced-motion`.
  - An axe-core audit of WCAG 2.2 AA found no violations in either mode.
- **Samantha / Randall mode**: Randall mode is the dark theme and follows the OS until you pick. Its jokey labels live in `data-r` attributes and are swapped in by JavaScript. The HTML itself only ever contains the plain words, so nothing is duplicated for search engines, and screen readers still hear the plain meaning.

## Layout

| Path | What it is |
| --- | --- |
| `content/comics.json` | **Source of truth**: every comic's title, date, slug, images, alt text, transcript, note and tags, plus the About text |
| `content/comics/`, `content/brand/` | Comic artwork (named by slug) and the 2011 banner cut-outs |
| `hardlyfunny/` | The generator: `content.py` (model), `urls.py`, `build.py`, `feed.py`, `seo.py`, `share.py`, `images.py`, `templates/`, `static/` |
| `tests/` | pytest suite (builds the site once and inspects the output) |
| `render.yaml` | Render static-site Blueprint |
| `.github/workflows/ci.yml` | Runs the tests and a build on every PR |
| `archive/` | The untouched WordPress export and its generated descriptions (history, not edited) |
| `scripts/` | `export_wordpress.py` (WordPress → `archive/`) and `migrate_to_content.py` (one-time `archive/` → `content/`) |
| `index.html`, `designs/` | The design review page and the four clickable mockups it previews |

## Adding a comic

1. Put the image in `content/comics/<slug>.png`.
2. Add an entry to the end of `content/comics.json`, including `number`, `slug`, `title`, `date`, `images` (with `width`, `height` and `alt`), `transcript`, `note_html` and `tags`.
3. Run `python -m pytest`. It fails if alt text or a transcript is missing, or if a slug is reused.

## Deploying

Create a Render Blueprint from this repo. `render.yaml` builds with `python -m hardlyfunny build` and publishes `_site/`. Then point hardlyfunny.com at it.
