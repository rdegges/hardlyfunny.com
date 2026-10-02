#!/usr/bin/env python3
"""One-time migration: WordPress export (archive/) + descriptions -> site source (content/).

After this runs, content/comics.json is the source of truth and is edited by hand
(new comics, fixes). archive/ stays as the untouched WordPress export.

    python3 scripts/migrate_to_content.py path/to/descriptions.json

descriptions.json maps comic number -> {"alt": "...", "transcript": ["Randall: ...", ...]}.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hardlyfunny.content import slugify  # noqa: E402

ARCHIVE = ROOT / "archive"
CONTENT = ROOT / "content"
SITE_URL = "https://hardlyfunny.com"

# Titles whose automatic slug reads badly.
SLUG_OVERRIDES = {"W.o.W.": "wow"}


def unique_slugs(titles: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    slugs = []
    for title in titles:
        base = SLUG_OVERRIDES.get(title) or slugify(title)
        seen[base] = seen.get(base, 0) + 1
        slugs.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    return slugs


def main(descriptions_path: str) -> int:
    if (CONTENT / "comics.json").exists() and "--force" not in sys.argv:
        print("content/comics.json already exists and may have hand edits. Re-run with --force to overwrite it.")
        return 1
    export = json.loads((ARCHIVE / "comics.json").read_text())
    descriptions = json.loads(Path(descriptions_path).read_text())
    comics_out = CONTENT / "comics"
    comics_out.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ARCHIVE / "brand", CONTENT / "brand", dirs_exist_ok=True)

    slugs = unique_slugs([c["title"] for c in export["comics"]])
    comics = []
    for comic, slug in zip(export["comics"], slugs):
        desc = descriptions[str(comic["number"])]
        images = []
        for i, img in enumerate(comic["images"]):
            ext = Path(img["src"]).suffix
            name = f"{slug}{'' if i == 0 else f'-{i + 1}'}{ext}"
            shutil.copy2(ARCHIVE / img["src"], comics_out / name)
            alt = desc["alt"] if i == 0 else f"Part {i + 1} of “{comic['title']}”, described in the transcript."
            images.append({"file": f"comics/{name}", "width": img["width"], "height": img["height"], "alt": alt})
        comics.append({
            "number": comic["number"],
            "slug": slug,
            "title": comic["title"],
            "date": comic["date"],
            "images": images,
            "transcript": desc["transcript"],
            "note_html": comic["note_html"],
            "tags": comic["tags"],
        })

    site = {
        "title": export["site"],
        "tagline": export["tagline"],
        "author": export["author"],
        "url": SITE_URL,
        "about_html": export["about_html"],
    }
    (CONTENT / "comics.json").write_text(json.dumps({"site": site, "comics": comics}, indent=2, ensure_ascii=False) + "\n")
    print(f"Migrated {len(comics)} comics into content/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
