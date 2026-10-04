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
- **Old WordPress links still work**: the build writes a Cloudflare `_redirects` file that 301s every old post URL (`/2013/05/15/infinite-recursion/`, with or without the slash, and anything under it, like attachment pages and the post's feed), every hotlinked `/wp-content/uploads/…` image, the old feed formats (`/feed/atom/`, `/feed/rss2/`, `/comments/feed/`, …), tag and category listings, and every year, month and day archive with its pages and feed. It's generated from `archive/wordpress_urls.json`. Date archives are listed one by one, not with a catch-all per year, because Cloudflare doesn't apply overlapping catch-alls in file order. The build refuses to write two catch-alls that overlap. A URL the old site never served gets the 404 page. The tests check that every old URL lands on a page that exists and that no rule shadows a real page. `tests/test_cloudflare_runtime.py` sends the same requests to a running server.
- **Atom feed** at `/feed/`, linked from every page as "Feed". It's the URL the WordPress feed used, so old subscribers get it with no redirect. `/feed.xml`, its URL right after the move, 301s to it. The build writes it as `feed/index.html`, because that's how Cloudflare serves a URL ending in `/`, and `_headers` sends it as `application/atom+xml`. Entries embed the comic, its alt text, Samantha's note and the transcript. Entry IDs are tag URIs, so they never change.
- **Social sharing**: each side of the switch has its own networks: X, Facebook and Instagram in Samantha mode; Bluesky, LinkedIn, Reddit and Hacker News in Randall mode. They're intent links that open each network's composer with the post prefilled (Facebook and LinkedIn only accept the link, and build the post's card from it). The comic image comes from each page's `og:image`: a 1200×630 card generated per comic. Instagram has no web share link, so its button uses the device's share sheet with the image attached (phones), and otherwise copies the link and points to the image.
- **SEO/GEO**: a unique `<title>`, meta description and canonical URL on every page. Open Graph and Twitter card tags. `ComicStory`/`ComicSeries` JSON-LD, with a `BreadcrumbList` on comic pages and an `AboutPage` on `/about/`. `Person` nodes for Samantha (the author) and Randall (a character) are on every page that refers to them. Samantha's node links only to `/about/`. A `sitemap.xml` that also lists every comic image, a `robots.txt` with Content Signals that allow search, AI answers and AI training, and `llms.txt` / `llms-full.txt` (with every transcript) for AI answer engines. The site does not answer `Accept: text/markdown` with Markdown. That needs Worker code or Cloudflare's Pro plan, and `llms-full.txt` already gives agents every transcript as plain text.
- **Accessibility**:
  - Every comic has written alt text and a full transcript.
  - Pages use skip links, landmarks, one `h1` each, and a visible focus style.
  - Colors meet WCAG AA contrast in both modes.
  - The shortcuts can be turned off, and the site respects `prefers-reduced-motion`.
  - An axe-core audit of WCAG 2.2 AA found no violations in either mode, and Lighthouse scores 100 for accessibility, best practices and SEO.
- **Privacy and speed**: fonts are self-hosted (`hardlyfunny/static/fonts/`, SIL Open Font License), so the only third-party request is Cloudflare Web Analytics (cookieless). No other analytics or trackers run.
- **Samantha / Randall mode**: Randall mode is the dark theme and follows the OS until you pick. Its jokey labels live in `data-r` attributes and are swapped in by JavaScript. The HTML itself only ever contains the plain words, so nothing is duplicated for search engines, and screen readers still hear the plain meaning.

## Layout

| Path | What it is |
| --- | --- |
| `content/comics.json` | **Source of truth**: every comic's title, date, slug, images, alt text, transcript, note and tags, plus the About text |
| `content/comics/`, `content/brand/` | Comic artwork (named by slug) and the 2011 banner cut-outs |
| `hardlyfunny/` | The generator: `content.py` (model), `urls.py`, `build.py`, `feed.py`, `seo.py`, `share.py`, `images.py`, `templates/`, `static/` |
| `tests/` | pytest suite (builds the site once and inspects the output) |
| `hardlyfunny/static/_headers` | Cloudflare response headers, copied into the build |
| `.github/workflows/ci.yml` | Runs the tests and a build on every PR and push. Deploys `main` to Cloudflare |
| `package.json`, `cloudflare.config.ts`, `wrangler.config.ts` | Deploy tooling only. The site is built by Python |
| `archive/` | The untouched WordPress export and its generated descriptions (history, not edited) |
| `scripts/` | `export_wordpress.py` (WordPress → `archive/`), `migrate_to_content.py` (one-time `archive/` → `content/`) and `check_links.py` (link checker run by CI) |
| `index.html`, `designs/` | The design review page and the four clickable mockups it previews |

## Link checking

`.github/workflows/links.yml` runs `scripts/check_links.py` on every pull request, every push to `main`, and every Monday (links die even when nothing changes). It fails on links that are definitely broken (404/410, a domain that no longer resolves) and only warns about links a script can't verify, like Reddit's and YouTube's bot blocking or a server error, which you can check in a browser. Results show as annotations and a summary table on the run. Fix a dead link by pointing it at an Internet Archive snapshot from around the comic's date.

Internal links (pages, images, CSS) are checked by the test suite on every build.

## Adding a comic

1. Put the image in `content/comics/<slug>.png`.
2. Add an entry to the end of `content/comics.json`, including `number`, `slug`, `title`, `date`, `images` (with `width`, `height` and `alt`), `transcript`, `note_html` and `tags`.
3. Run `python -m pytest`. The build also refuses to run if numbers aren't sequential, dates are out of order, a slug is reused or malformed, or an image has no alt text, and the tests check that image sizes match the files.

## Deploying (Cloudflare)

The site runs on Cloudflare as a Worker with static assets and no Worker code. The `deploy` job in `.github/workflows/ci.yml` publishes it with the [`cf` CLI](https://developers.cloudflare.com/cf/):

- On a push to `main`, the job builds `_site` and runs `npx cf deploy`. It starts only after the `test` job in the same run passes.
- On a pull request, the job runs `npx cf deploy --dry-run`. This run uses no credentials and publishes nothing.
- After a deploy to `main`, the `verify` job runs `tests/test_cloudflare_runtime.py` and `tests/test_live_domain.py` against `https://hardlyfunny.com`. It fails unless the tests ran, so a red `verify` means the live site does not match the build.

Two repository secrets give the job access: `CLOUDFLARE_API_TOKEN` (an account token with only Workers Scripts Write) and `CLOUDFLARE_ACCOUNT_ID`.

`wrangler.config.ts` sets `_site` as the assets directory. `cloudflare.config.ts` names the Worker `hardlyfunny` and makes Cloudflare serve `404.html` for missing pages. The build writes `_headers` (security and cache headers) and `_redirects` (old WordPress URLs) into `_site/`. Cloudflare reads both files as rules and does not serve them as pages.

Cloudflare injects it by default until you choose otherwise in the zone's Speed → Real user monitoring page (Enable Globally, Exclude EU, or Disable completely).

To run the site locally on the Cloudflare runtime, build it first. Then run `npm ci && npx cf dev` in a Node container.

## Domains

- **`hardlyfunny.com`** is a custom domain on the `hardlyfunny` Worker, set by `domains` in `cloudflare.config.ts`. Cloudflare manages its DNS record (a proxied `AAAA 100::`). Every deploy re-asserts the domain. Removing the `domains` line does not detach it; only the dashboard does (Workers & Pages → `hardlyfunny` → Settings → Domains & Routes).
- **`www.hardlyfunny.com`** 301s to `https://hardlyfunny.com` with the same path and query. A zone Single Redirect rule does this (Rules → Redirect Rules), on a proxied `AAAA www 100::` record. The rule matches `http.host eq "www.hardlyfunny.com"`, redirects dynamically to `concat("https://hardlyfunny.com", http.request.uri.path)` with status 301, and keeps the query string. `_redirects` cannot match on the host name.
- **workers.dev and Preview URLs are off.** `workersDev: false` and `previewUrls: false` in `cloudflare.config.ts` make `hardlyfunny.com` the only host that serves the site. `previewUrls` must stay explicit, because leaving it out keeps whatever the dashboard has. `verify` checks that `https://hardlyfunny.randall-degges.workers.dev/` returns 404 with no site page.
- **The deploy token needs no zone access.** In the rehearsal, Cloudflare refused to attach the domain over hand-made A records (code 100117) with every token scope tried, and after the records were deleted a Workers Scripts Write token was enough. `cf` asks Cloudflare to override existing DNS records when it is not run in a terminal, as in CI, so in a rollback the `domains` removal (step 1) must deploy before the A records come back.
- **Zone settings the site depends on:** Always Use HTTPS on, Bot Fight Mode off, Block AI bots off (the robots.txt Content Signals allow AI crawlers), managed robots.txt off, security level medium, Browser Cache TTL "Respect Existing Headers", Rocket Loader off, Email Address Obfuscation off, zone HSTS (SSL/TLS → Edge Certificates) off because `_headers` sets it, and Crawler Hints (Caching → Configuration) on, so Cloudflare tells IndexNow search engines like Bing when a page changes. Cloudflare Web Analytics is on and adds one beacon script to each HTML page. The runtime tests allow exactly that one tag.
- **Search engines and site claims.** Google Search Console has a Domain property for `hardlyfunny.com`, verified by a `google-site-verification=…` TXT record on the zone apex. Bing Webmaster Tools imported the site from Search Console, so it has no DNS record of its own. Pinterest claims the site through a `pinterest-site-verification=…` TXT record on the apex. Do not delete either TXT record: the property or claim stops being verified. `sitemap.xml` is submitted to Google and Bing.
- **A URL without its trailing slash gets a 307, not a 301.** Cloudflare sends `/comics/engineers` and `/comics/engineers/index.html` to `/comics/engineers/` with a 307, and its static assets have no setting to change that. Every link the site writes ends in `/`, and the old WordPress URLs get their own 301s, so these are left as they are.

### Rollback to WordPress.com

Use this only while the WordPress.com site still exists.

1. In one commit on `main`, remove the `domains` line from `cloudflare.config.ts` and the `domains` assertion (the `domains = re.search(...)` line and the assert after it) from `tests/test_deploy_config.py`. Do not `git revert` the cutover commit. Wait for that commit's CI deploy to finish before step 3. Otherwise a later deploy attaches the domain again.
2. In the dashboard, detach `hardlyfunny.com` from the `hardlyfunny` Worker.
3. Create two DNS-only A records for `hardlyfunny.com`: `192.0.78.24` and `192.0.78.25`.

After a rollback, `verify` stays red until the Worker serves the domain again. Rerunning it does not fix anything.
