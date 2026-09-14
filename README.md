# onurozkir.com

Onur Özkır'ın Hugo tabanlı kişisel sitesi ve Türkçe teknik blogu.

## AI ile blog hazırlama

Başlangıç: [AGENTS.md](AGENTS.md). [Kullanım rehberi ve örnek prompt](docs/blog-workflow.md), [metadata şeması](docs/blog-frontmatter.md), [konu girdisi](templates/blog-brief.md).

Depoya özel skill'ler: [teknik blog yazımı](skills/technical-blog/SKILL.md) ve [SEO/LLM erişimi](skills/blog-seo/SKILL.md). Ajan bunları `AGENTS.md` üzerinden okur; global kurulum gerekmez.

## Yerel geliştirme

Gereksinimler: Hugo Extended **0.166.0**, doğrulama için Python **3.10+** (ek paket yok).

```sh
hugo new content blogs/yeni-yazi.md
hugo server --buildDrafts
```

`archetypes/blogs.md` yeni yazıyı `draft: true` ile oluşturur. İçeriği ve metadata alanlarını doldur; yayın isteğinde kontrollerden sonra `draft: false` yap.

## Production build ve kontroller

```sh
hugo --minify --gc --baseURL "https://onurozkir.com/"
python scripts/validate_blog.py --public public
```

Temiz çıktı diziniyle çalış. Önizleme için production'dan ayrı destination kullan; eski draft çıktıları yeniden build ile kendiliğinden silinmeyebilir. Alternatif temiz bir dizine örnek:

```sh
hugo --minify --gc --destination public/release-check
python scripts/validate_blog.py --public public/release-check
```

`release-check` örneğini ilk kullanımda veya boş dizinle çalıştır. **Deploy edilecek kök seçtiğin destination olmalı**; üst `public/` dizini değil. Production'da draft/future/expired bayrakları kullanma.

Altyapı değişikliklerini izole test etmek için:

```sh
python scripts/test_blog_pipeline.py --hugo hugo
```

Doğrulayıcı HTML metadata, JSON-LD, gerçek kapak dosyaları, Markdown, llms dizinleri, sitemap ve RSS tutarlılığını kontrol eder. Yazının teknik iddialarını veya dış kaynakların içeriğini doğrulamaz.

## Docker ile sunma

```sh
docker build -t onurozkir-blog .
docker run --rm -p 8080:80 onurozkir-blog
```

Dockerfile Hugo sürümünü sabitler ve Nginx üzerinden sunar. `.dockerignore` eski build çıktıları ve yerel notları build bağlamından çıkarır. `deploy/nginx-default.conf`, Markdown için MIME type ve HTML canonical header'ını tanımlar; llms dosyalarını UTF-8 düz metin olarak sunar. Docker daemon bu geliştirme ortamında çalışmadığı için Docker image build/çalıştırma testi burada yapılmadı.

## Otomatik LLM çıktıları

`/llms.txt`, `/llms-full.txt` ve `/blogs/<slug>/index.md` her build'de üretilir. Elle llms dosyası doldurman gerekmez. Bunlar bot erişimini kolaylaştırır; indekslenme veya LLM'lerde alıntılanma garantisi vermez.
