#!/usr/bin/env python3
"""Exercise publishing boundaries in an isolated copy, never in real content/."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

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
        for name in ("content", "layouts", "assets", "static", "archetypes"):
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
    print("PASS: archetype, automatic indexing, raw Markdown, publication boundaries and negative validation")


if __name__ == "__main__":
    main()
