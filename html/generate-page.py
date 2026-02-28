#!/usr/bin/env python3
"""Generate HTML pages from docs.json and Jinja2 template.

Usage:
    python generate-page.py                  # regenerate all pages
    python generate-page.py cli-install      # regenerate specific slug(s)
    python generate-page.py --print-missing  # list slugs with missing HTML files
"""

import json
import sys
from itertools import groupby
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = Path(__file__).parent
BASE_URL = "https://www.walbrix.co.jp/genpack/"
BEGIN_MARKER = "<!-- content:begin -->"
END_MARKER = "<!-- content:end -->"


def load_docs():
    with open(SCRIPT_DIR / "docs.json") as f:
        return json.load(f)


def load_history():
    path = SCRIPT_DIR / "history.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def extract_content(html_path):
    """Extract content between markers from an existing HTML file."""
    text = html_path.read_text()

    begin = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if begin == -1 or end == -1:
        raise ValueError(f"Markers not found in {html_path}")

    # Content is between the markers, exclusive of the marker lines themselves
    inner = text[begin + len(BEGIN_MARKER) : end]
    # Strip exactly one leading and one trailing newline
    if inner.startswith("\n"):
        inner = inner[1:]
    if inner.endswith("\n"):
        inner = inner[:-1]
    return inner


def generate_page(doc, lang, docs, history, env):
    """Generate a single HTML page for one doc entry and language."""
    slug = doc["slug"]
    if lang == "ja":
        filename = f"{slug}.html"
        title = doc["title"]["ja"]
        description = doc["description"]["ja"]
    else:
        filename = f"{slug}.en.html"
        title = doc["title"]["en"]
        description = doc["description"]["en"]

    html_path = SCRIPT_DIR / filename
    if not html_path.exists():
        print(f"WARNING: {filename} does not exist, skipping", file=sys.stderr)
        return

    content = extract_content(html_path)
    wrapped = f"{BEGIN_MARKER}\n{content}\n{END_MARKER}"

    # Filter history entries relevant to this slug
    history_entries = [e for e in history if slug in e.get("slugs", [])]
    last_updated = history_entries[0]["date"] if history_entries else None

    template = env.get_template("page.html.j2")
    result = template.render(
        lang=lang,
        title=title,
        description=description,
        base_url=BASE_URL,
        filename=filename,
        slug=slug,
        content=wrapped,
        docs=docs,
        current_id=doc["id"],
        history_entries=history_entries,
        last_updated=last_updated,
    )

    html_path.write_text(result)
    print(f"Generated {filename}")


def generate_history_page(lang, docs, history, env):
    """Generate the history.html / history.en.html page."""
    if lang == "ja":
        filename = "history.html"
        title = "更新履歴"
        description = "genpack ドキュメントの更新履歴"
    else:
        filename = "history.en.html"
        title = "Update History"
        description = "genpack documentation update history"

    # Group history entries by date
    grouped = []
    for date, entries in groupby(history, key=lambda e: e["date"]):
        grouped.append((date, list(entries)))

    # Build slug -> doc lookup
    docs_by_slug = {doc["slug"]: doc for doc in docs}

    template = env.get_template("history.html.j2")
    result = template.render(
        lang=lang,
        title=title,
        description=description,
        base_url=BASE_URL,
        filename=filename,
        grouped_history=grouped,
        docs_by_slug=docs_by_slug,
        docs=docs,
    )

    (SCRIPT_DIR / filename).write_text(result)
    print(f"Generated {filename}")


def print_missing(docs):
    """Print docs.json entries whose HTML files are missing."""
    for doc in docs:
        for filename in (f"{doc['slug']}.html", f"{doc['slug']}.en.html"):
            if not (SCRIPT_DIR / filename).exists():
                print(filename)


def main():
    docs = load_docs()
    history = load_history()

    if "--print-missing" in sys.argv:
        print_missing(docs)
        return

    env = Environment(
        loader=FileSystemLoader(SCRIPT_DIR / "templates"),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )

    slugs = [a for a in sys.argv[1:] if not a.startswith("-")]
    if slugs:
        slug_set = set(slugs)
        target_docs = [d for d in docs if d["slug"] in slug_set]
    else:
        target_docs = docs

    for doc in target_docs:
        for lang in ("ja", "en"):
            generate_page(doc, lang, docs, history, env)

    # Generate history pages (only on full regeneration)
    if not slugs:
        for lang in ("ja", "en"):
            generate_history_page(lang, docs, history, env)


if __name__ == "__main__":
    main()
