# hardlyfunny.com

*Hardly Funny* is a webcomic by Samantha Degges about being married to a computer programmer (82 comics, 2012–2014). This repo is its move off WordPress.com to a static site.

## What's here

| Path | What it is |
| --- | --- |
| `index.html` | Design review page: what's on the current site, plus live previews of the four design directions |
| `designs/` | Four clickable design mockups (`classic`, `terminal`, `engineering-pad`, `his-and-hers`) and the navigation code they share (`reader.js`) |
| `archive/comics.json` | The full export: titles, dates, notes, tags, image sizes and original WordPress URLs for all 82 comics |
| `archive/comics/` | Original comic artwork, renamed `NNN-slug.ext` |
| `archive/brand/` | The 2011 banner, plus Scribbles and the couple cut out of it |
| `scripts/export_wordpress.py` | Re-runs the export from the WordPress.com public API (stdlib only) |

## Viewing the designs

The mockups load data and images with relative paths, so serve the repo root:

```sh
python3 -m http.server 8000
# open http://localhost:8000/
```

In every design: `←` / `→` to read, `r` for a random comic, `a` for the archive, `Esc` to go back.

## Re-exporting

```sh
python3 scripts/export_wordpress.py
```

Images that already exist are skipped. Known data quirks are handled in the script: the 2013-02-04 post has no title (its slug, `404`, becomes the title), and "Engineers" carries a `date_flag` because it is probably misdated.
