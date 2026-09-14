#!/usr/bin/env python3
"""Check the generated Hugo blog and discovery outputs; Python 3.10+, no packages."""
import argparse
from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlparse
import xml.etree.ElementTree as ET


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.links, self.meta, self.schemas, self.times, self.scripts = [], {}, [], [], []
        self.lang, self.h1, self._json = "", 0, None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "html":
            self.lang = attrs.get("lang", "")
        elif tag == "h1":
            self.h1 += 1
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "meta":
            key = attrs.get("name", attrs.get("property", ""))
            self.meta.setdefault(key, []).append(attrs.get("content", ""))
        elif tag == "time":
            self.times.append(attrs.get("datetime", ""))
        elif tag == "script":
            if attrs.get("src"):
                self.scripts.append(attrs["src"])
            if attrs.get("type") == "application/ld+json":
                self._json = ""

    def handle_data(self, data):
        if self._json is not None:
            self._json += data

    def handle_endtag(self, tag):
        if tag == "script" and self._json is not None:
            self.schemas.append(json.loads(self._json))
            self._json = None

    def link(self, rel, media=None):
        return [a.get("href", "") for a in self.links
                if rel in a.get("rel", "").split()
                and (media is None or a.get("type") == media)]


def validate(public):
    public = Path(public).resolve()
    errors = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    def read(name):
        path = public / name
        check(path.is_file(), f"Missing output: {name}")
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    index, full = read("llms.txt"), read("llms-full.txt")
    robots = read("robots.txt")
    home = Page(read("index.html"))
    check(home.lang.startswith("tr"), "Home must declare Turkish")
    check(any(s.get("@type") == "WebSite" for s in home.schemas), "Home WebSite schema missing")
    home_urls = home.link("canonical")
    check(len(home_urls) == 1, "Home must have one canonical")
    base = home_urls[0] if home_urls else "https://onurozkir.com/"

    def local(url):
        parsed = urlparse(url)
        check(parsed.netloc == urlparse(base).netloc, f"Unexpected site host: {url}")
        relative = unquote(parsed.path).lstrip("/")
        path = (public / relative).resolve()
        if not path.is_relative_to(public):
            check(False, f"Path escapes output directory: {url}")
            return public / "__invalid_path__"
        return path / "index.html" if path.is_dir() else path

    check(index.startswith("# "), "llms.txt must start with a Markdown H1")
    def check_assets(page, label):
        for url in page.link("stylesheet") + page.scripts:
            parsed = urlparse(url)
            if not parsed.netloc or parsed.netloc == urlparse(base).netloc:
                asset = base.rstrip("/") + "/" + url.lstrip("/") if not parsed.netloc else url
                check(local(asset).is_file(), f"{label}: missing CSS/JavaScript {url}")

    check_assets(home, "Home")
    check("Sitemap: " + base + "sitemap.xml" in robots, "robots sitemap URL mismatch")
    check("Disallow: /" not in robots, "robots blocks crawling")
    index_links = re.findall(r"^- \[[^\n]+?\]\((https?://[^)]+)\)", index, re.M)
    for link in index_links:
        check(local(link).is_file(), f"llms.txt target missing: {link}")

    sitemap = ET.fromstring(read("sitemap.xml"))
    sitemap_urls = {e.text for e in sitemap.iter() if e.tag.endswith("}loc")}
    rss = ET.fromstring(read("blogs/index.xml"))
    rss_urls = {e.text for e in rss.findall("./channel/item/link")}
    markdown_urls, blog_urls = set(), set()
    for path in sorted((public / "blogs").rglob("index.html")):
        label = str(path.relative_to(public))
        page = Page(path.read_text(encoding="utf-8"))
        check_assets(page, label)
        articles = [s for s in page.schemas if s.get("@type") == "BlogPosting"]
        if not articles:
            continue  # Archive/pagination/aliases are not articles.
        check(len(articles) == 1, f"{label}: duplicate article schema")
        schema = articles[0]
        url = schema.get("url", "")
        blog_urls.add(url)
        check(page.h1 == 1, f"{label}: expected one H1")
        check(page.lang.startswith("tr"), f"{label}: wrong language")
        check(page.link("canonical") == [url], f"{label}: canonical mismatch")
        check(page.link("describedby") == [base + "llms.txt"], f"{label}: llms discovery missing")
        check(url in sitemap_urls, f"{label}: absent from sitemap")
        check("noindex" not in " ".join(page.meta.get("robots", [])), f"{label}: published article is noindex")
        descriptions = page.meta.get("description", [])
        check(len(descriptions) == 1 and bool(descriptions[0].strip()), f"{label}: description empty or duplicate")
        check(schema.get("description") == (descriptions[0] if descriptions else ""), f"{label}: schema description mismatch")
        check(bool(schema.get("headline")), f"{label}: missing title")
        check(bool(schema.get("author", {}).get("name")), f"{label}: missing author")
        check(schema.get("inLanguage") == "tr-TR", f"{label}: schema language mismatch")
        check(schema.get("mainEntityOfPage", {}).get("@id") == url, f"{label}: schema canonical mismatch")
        dates = []
        for field in ("datePublished", "dateModified"):
            value = schema.get(field, "")
            try:
                date = datetime.fromisoformat(value.replace("Z", "+00:00"))
                check(date.tzinfo is not None, f"{label}: {field} needs timezone")
                dates.append(date)
            except ValueError:
                check(False, f"{label}: invalid {field}")
        if len(dates) == 2 and all(d.tzinfo for d in dates):
            check(dates[1] >= dates[0], f"{label}: modified before published")
        check(schema.get("datePublished") in page.times, f"{label}: publication time not visible")
        for image in schema.get("image", []):
            check(local(image).is_file(), f"{label}: missing cover {image}")
            check(image in page.meta.get("og:image", []), f"{label}: OG image mismatch")
            check(image in page.meta.get("twitter:image", []), f"{label}: Twitter image mismatch")
        alternate = page.link("alternate", "text/markdown")
        check(len(alternate) == 1, f"{label}: Markdown discovery missing or duplicate")
        if len(alternate) != 1:
            continue
        md_url = alternate[0]
        markdown_urls.add(md_url)
        md_path = local(md_url)
        check(md_path.is_file(), f"{label}: Markdown file missing")
        if not md_path.is_file():
            continue
        md = md_path.read_text(encoding="utf-8")
        check(md.startswith("# " + schema.get("headline", "") + "\n"), f"{label}: Markdown title corrupted")
        check("Asıl adres: " + url in md, f"{label}: Markdown canonical missing")
        check("Yayın: " + schema.get("datePublished", "") in md, f"{label}: Markdown date corrupted")
        check("{{<" not in md and "{{%" not in md, f"{label}: unrendered Hugo shortcode in Markdown")
        check(md.strip() in full, f"{label}: missing/corrupted full-text entry")
        check(md_url in index_links, f"{label}: not indexed in llms.txt")

    check(bool(blog_urls), "No blog articles found")
    check(rss_urls <= blog_urls, "RSS contains a non-published or missing blog URL")
    check(bool(rss_urls), "Blog RSS is empty")
    indexed_md = {url for url in index_links if url.endswith("/index.md")}
    check(indexed_md == markdown_urls, "llms.txt and published Markdown set differ")
    full_urls = set(re.findall(r"^Asıl adres: (\S+)$", full, re.M))
    check(full_urls == blog_urls, "llms-full.txt and published blog set differ")
    actual_md = {p.resolve() for p in (public / "blogs").rglob("*.md")}
    check(actual_md == {local(u) for u in markdown_urls}, "Unlisted/stale Markdown output found")
    return len(blog_urls), errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", default="public", type=Path)
    args = parser.parse_args()
    try:
        count, errors = validate(args.public)
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    if errors:
        return 1
    print(f"PASS: {count} articles; metadata, images, Markdown, llms, sitemap and RSS consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
