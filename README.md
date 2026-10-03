# hardlyfunny.com

*Hardly Funny* is a webcomic by Samantha Degges about being married to a computer programmer (82 comics, 2012–2014). This repo is its move off WordPress.com to a static site.

## Quick start

```sh
pip install -r requirements-dev.txt
python -m hardlyfunny serve        # builds into _site/ and serves http://localhost:8000/
python -m pytest                   # checks content, SEO tags, accessibility basics, links and the feed
```

`python -m hardlyfunny build --portable` makes a preview with relative links that works opened straight from disk (open `_site/index.html`). It skips the thumbnails and social cards. `python -m hardlyfunny build` only builds. Pass `--site-url https://preview.example.com` for a preview deploy, so canonical URLs and OG tags point at the preview.

## What the site includes

- **Clean, permanent URLs**: one page per comic at `/comics/<slug>/` (e.g. `/comics/infinite-recursion/`), plus `/archive/`, `/about/` and `/random/`.
- **Old WordPress links still work**: the build writes a Cloudflare `_redirects` file that 301s every old post URL (`/2013/05/15/infinite-recursion/`, with or without the slash, and its attachment pages), every hotlinked `/wp-content/uploads/…` image, `/feed/`, and tag/category/date/page listings to their new homes. It's generated from `archive/wordpress_urls.json`, and the tests check that every old URL lands on a page that exists and that no rule shadows a real page.
- **Atom feed** at `/feed.xml`, linked from every page as "Feed". Entries embed the comic, its alt text, Samantha's note and the transcript. Entry IDs are tag URIs, so they never change.
- **Social sharing**: X, Facebook, LinkedIn, Reddit and Hacker News intent links with the title prefilled. The comic image comes from each page's `og:image`: a 1200×630 card generated per comic. Instagram has no web share link, so its button uses the device's share sheet with the image attached (phones), and otherwise copies the link and points to the image.
- **SEO/GEO**: a unique `<title>`, meta description and canonical URL on every page. Open Graph and Twitter card tags. `ComicStory`/`ComicSeries` JSON-LD. A `sitemap.xml`, a `robots.txt`, and `llms.txt` / `llms-full.txt` (with every transcript) for AI answer engines.
- **Accessibility**:
  - Every comic has written alt text and a full transcript.
  - Pages use skip links, landmarks, one `h1` each, and a visible focus style.
  - Colors meet WCAG AA contrast in both modes.
  - The shortcuts can be turned off, and the site respects `prefers-reduced-motion`.
  - An axe-core audit of WCAG 2.2 AA found no violations in either mode, and Lighthouse scores 100 for accessibility, best practices and SEO.
- **Privacy and speed**: fonts are self-hosted (`hardlyfunny/static/fonts/`, SIL Open Font License), so pages make no third-party requests and no analytics or trackers run.
- **Samantha / Randall mode**: Randall mode is the dark theme and follows the OS until you pick. Its jokey labels live in `data-r` attributes and are swapped in by JavaScript. The HTML itself only ever contains the plain words, so nothing is duplicated for search engines, and screen readers still hear the plain meaning.

## Layout

| Path | What it is |
| --- | --- |
| `content/comics.json` | **Source of truth**: every comic's title, date, slug, images, alt text, transcript, note and tags, plus the About text |
| `content/comics/`, `content/brand/` | Comic artwork (named by slug) and the 2011 banner cut-outs |
| `hardlyfunny/` | The generator: `content.py` (model), `urls.py`, `build.py`, `feed.py`, `seo.py`, `share.py`, `images.py`, `templates/`, `static/` |
| `tests/` | pytest suite (builds the site once and inspects the output) |
| `hardlyfunny/static/_headers` | Cloudflare Pages response headers, copied into the build |
| `.github/workflows/ci.yml` | Runs the tests and a build on every PR |
| `archive/` | The untouched WordPress export and its generated descriptions (history, not edited) |
| `scripts/` | `export_wordpress.py` (WordPress → `archive/`) and `migrate_to_content.py` (one-time `archive/` → `content/`) |
| `index.html`, `designs/` | The design review page and the four clickable mockups it previews |

## Adding a comic

1. Put the image in `content/comics/<slug>.png`.
2. Add an entry to the end of `content/comics.json`, including `number`, `slug`, `title`, `date`, `images` (with `width`, `height` and `alt`), `transcript`, `note_html` and `tags`.
3. Run `python -m pytest`. The build also refuses to run if numbers aren't sequential, dates are out of order, a slug is reused or malformed, or an image has no alt text, and the tests check that image sizes match the files.

## Deploying (Cloudflare Pages)

Create a Pages project connected to this GitHub repo, with:

| Setting | Value |
| --- | --- |
| Production branch | `main` |
| Build command | `pip install -r requirements.txt && python -m hardlyfunny build` |
| Build output directory | `_site` |

Python is pinned by `.python-version`. The build writes `_headers` (security and cache headers) and `_redirects` (old WordPress URLs) into `_site/`; Pages compresses responses and serves `404.html` for missing pages on its own. Every pull request gets its own preview deployment, and `main` only changes through pull requests that pass CI. Then add hardlyfunny.com as a custom domain on the project.
