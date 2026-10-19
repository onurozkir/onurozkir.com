#!/usr/bin/env python3
"""Exercise publishing boundaries in an isolated copy, never in real content/."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

from validate_blog import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hugo", default="hugo")
    args = parser.parse_args()
    hugo = shutil.which(args.hugo)
    if not hugo:
        parser.error("Hugo executable not found; pass --hugo with its absolute path")
    repo = Path(__file__).resolve().parents[1]
    scratch = repo / "public"
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="blog-pipeline-", dir=scratch) as directory:
        root = Path(directory).resolve()
        assert root.is_relative_to(scratch.resolve())
        for name in ("content", "layouts", "assets", "static", "archetypes", "i18n"):
            shutil.copytree(repo / name, root / name)
        shutil.copy2(repo / "hugo.yaml", root / "hugo.yaml")
        (root / "themes/hugo-profile").mkdir(parents=True)

        def run(*options):
            result = subprocess.run(
                [hugo, "--source", str(root), "--cacheDir", str(root / "cache"), *options],
                capture_output=True, text=True, encoding="utf-8", errors="replace")
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)

        run("new", "content", "blogs/archetype-probe.md")
        scaffold = (root / "content/blogs/archetype-probe.md").read_text(encoding="utf-8")
        assert "draft: true" in scaffold and "summary:" in scaffold
        assert "{{" not in scaffold, "Archetype expressions were not expanded"

        title = 'Pipeline & Türkçe "kanıt" <test>'
        body = '## Örnek\n\nİçerik & doğru + işaretleri.\n\n```python\nprint("a < b && c > d")\n```\n'
        filename = root / "content/blogs/pipeline-probe.md"
        for state in ("published", "draft", "future", "expired"):
            fields = {
                "title": title, "date": "2020-01-02T12:00:00+03:00",
                "draft": state == "draft", "author": "Onur Özkır",
                "description": "Yayın akışının doğrulama yazısı.",
                "summary": "Özel karakter ve yayın eşiği kontrolü.", "tags": ["Testing"],
            }
            if state == "future":
                fields["publishDate"] = "2099-01-01T00:00:00+03:00"
                fields["lastmod"] = "2099-01-01T00:00:00+03:00"
            if state == "expired":
                fields["expiryDate"] = "2020-01-03T12:00:00+03:00"
            frontmatter = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items())
            filename.write_text("---\n" + frontmatter + "\n---\n\n" + body, encoding="utf-8")
            output = root / f"production-{state}"
            run("--minify", "--destination", str(output))
            count, errors = validate(output)
            assert not errors, "\n".join(errors)
            md = output / "blogs/pipeline-probe/index.md"
            assert md.exists() == (state == "published"), f"{state} publication boundary failed"
            assert not (output / "blogs/archetype-probe").exists(), "Scaffold draft leaked"
            if state == "published":
                text = md.read_text(encoding="utf-8")
                assert body in text, "Raw Markdown/code was escaped or modified"
                assert title in text, "Markdown title escaped"
                # A missing discovery entry must actually fail the validator.
                index = output / "llms.txt"
                original = index.read_text(encoding="utf-8")
                index.write_text("\n".join(line for line in original.splitlines()
                                           if "/pipeline-probe/" not in line), encoding="utf-8")
                assert validate(output)[1], "Validator missed an unindexed article"
                index.write_text(original, encoding="utf-8")
            else:
                preview = root / f"preview-{state}"
                run("--buildDrafts", "--buildFuture", "--buildExpired", "--destination", str(preview))
                assert (preview / "blogs/pipeline-probe/index.md").exists()
                for name in ("llms.txt", "llms-full.txt"):
                    text = (preview / name).read_text(encoding="utf-8")
                    assert "/pipeline-probe/" not in text, f"{state} leaked into {name}"
                    assert "/archetype-probe/" not in text, f"Scaffold leaked into {name}"
            print(f"PASS: {state}; {count} published articles")

        # Series keep their blog identity while using a separate public URL.
        filename.unlink()
        for language in ("tr", "en"):
            suffix = "" if language == "tr" else ".en"
            prefix = "" if language == "tr" else "/en"
            series = root / "content/ai-native-swe"
            series.mkdir(exist_ok=True)
            (series / f"_index{suffix}.md").write_text(
                '---\ntitle: "AI Native SWE"\nseries: "ai-native-swe"\n---\n\nSeries introduction.\n',
                encoding="utf-8")
            for state in ("published", "draft", "future", "expired"):
                fields = {
                    "title": f"Series {state}", "date": "2020-01-02T12:00:00+03:00",
                    "draft": state == "draft", "author": "Onur Özkır",
                    "description": "Series publishing boundary.", "summary": "Series summary.",
                    "tags": ["Testing"], "series": "ai-native-swe",
                    "url": f"{prefix}/ai-native-swe/series-{state}/",
                }
                if state == "future":
                    fields["publishDate"] = "2099-01-01T00:00:00+03:00"
                if state == "expired":
                    fields["expiryDate"] = "2020-01-03T12:00:00+03:00"
                fm = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fields.items())
                (root / f"content/blogs/series-{state}{suffix}.md").write_text(
                    "---\n" + fm + "\n---\n\n" + body, encoding="utf-8")
        output = root / "production-series"
        run("--minify", "--destination", str(output))
        for prefix in ("", "en/"):
            archive = (output / f"{prefix}ai-native-swe/index.html").read_text(encoding="utf-8")
            article_url = f"/{prefix}ai-native-swe/series-published/"
            assert f'href={article_url}' in archive or f'href="{article_url}"' in archive, "Series archive omits its articles"
            assert "Series introduction." in archive, "Series introduction missing"
            assert "kirk-katir" not in archive.split("<footer>", 1)[0], "Unrelated post leaked into series"
            html = (output / f"{prefix}ai-native-swe/series-published/index.html").read_text(encoding="utf-8")
            assert f'/{prefix}ai-native-swe/' in html, "Article omits series navigation"
            assert f"/{prefix}tags/testing" in html, "Article tags link to the wrong language"
            md = (output / f"{prefix}ai-native-swe/series-published/index.md").read_text(encoding="utf-8")
            assert body in md, "Series Markdown body corrupted"
            search = json.loads((output / f"{prefix}index.json").read_text(encoding="utf-8"))
            assert any(article_url in item["permalink"] for item in search), "Series article absent from search"
            rss = (output / f"{prefix}blogs/index.xml").read_text(encoding="utf-8")
            assert article_url in rss, "Series article absent from blog RSS"
            feed = ET.parse(output / f"{prefix}ai-native-swe/index.xml")
            feed_links = [item.text for item in feed.findall("./channel/item/link")]
            assert f"https://onurozkir.com{article_url}" in feed_links, "Series article absent from series RSS"
            assert all(f"/{prefix}ai-native-swe/" in link for link in feed_links), "Unrelated article leaked into series RSS"
            assert not any(f"/series-{state}/" in link for link in feed_links
                           for state in ("draft", "future", "expired")), "Unpublished article leaked into series RSS"
            for name in ("llms.txt", "llms-full.txt"):
                text = (output / f"{prefix}{name}").read_text(encoding="utf-8")
                assert article_url in text, "Series article absent from discovery"
                for state in ("draft", "future", "expired"):
                    assert f"/series-{state}/" not in text, "Unpublished series article leaked"
        count, errors = validate(output)
        assert not errors, "\n".join(errors)
        english_index = output / "en/llms.txt"
        original = english_index.read_text(encoding="utf-8")
        english_index.write_text("\n".join(line for line in original.splitlines()
                                            if "/series-published/" not in line), encoding="utf-8")
        assert validate(output)[1], "Validator missed an unindexed English series article"
        english_index.write_text(original, encoding="utf-8")
        preview = root / "preview-series"
        run("--buildDrafts", "--buildFuture", "--buildExpired", "--destination", str(preview))
        for prefix in ("", "en/"):
            archive = (preview / f"{prefix}ai-native-swe/index.html").read_text(encoding="utf-8").split("<footer>", 1)[0]
            for state in ("draft", "future", "expired"):
                assert f"/series-{state}/" not in archive, "Unpublished article leaked into series preview"
        print(f"PASS: bilingual series routing, archive, discovery, search and publication boundaries; {count} articles")
    print("PASS: archetype, automatic indexing, raw Markdown, publication boundaries and negative validation")


if __name__ == "__main__":
    main()
