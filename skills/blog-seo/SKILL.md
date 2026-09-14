---
name: blog-seo
description: onurozkir.com Hugo blogunda front matter, canonical, sosyal paylaşım görselleri, JSON-LD, sitemap, RSS ve otomatik llms.txt/Markdown çıktılarının tutarlılığını kur ve doğrula. Yeni yazı yayınında ve SEO altyapısı değişikliğinde kullan.
---

# Blog SEO ve LLM erişimi

Önce `AGENTS.md` ve `docs/blog-frontmatter.md` oku. Bakım notları ve kaynaklar `docs/blog-workflow.md` içinde. Amaç doğru, erişilebilir içerik ve tutarlı yayın metadata'sıdır; arama veya LLM atıf garantisi verme.

## Yazı ekleme/güncelleme

Başlık, description, summary, gerçek yazar, yayın tarihi ve etiketleri kontrol et. `lastmod` yalnızca anlamlı güncellemede değişmeli; var olan URL'yi koru. Yeni yazılarda Türkiye için `+03:00` kullan; eski tarihleri sırf timezone standardizasyonu için değiştirme.

`image` varsa `/images/...` dosyasının `static/` altında bulunduğunu ve `imageAlt` metnini doğrula. Görsel yoksa alanı çıkar; hayali fallback URL üretme. Gövde bağlantılarının hedefini ve kaynakların iddialarla ilişkisini gözden geçir.

Şema ve içerik aynı şeyi söylemeli. `BlogPosting` yalnızca bloglarda, `WebSite` ana sayfada üretilir. Yazar ve tarih okuyucuya da görünür. Yeni bir SEO eklentisi ekleyerek canonical, description veya JSON-LD'yi çoğaltma.

## Otomatik çıktılar

- `hugo.yaml` home çıktıları `LLMS` ve `LLMSFull`; blog cascade çıktıları `HTML` ve `Markdown`.
- `layouts/partials/blogs/published.html` yayımlanmış yazıları seçer; preview'da da draft, gelecek tarih ve süresi dolan yazıları llms dizinlerine almaz.
- `layouts/index.llms.txt` başlık/description ve Markdown bağlantılarını üretir.
- `layouts/partials/blogs/markdown.txt` asıl URL, tarihler, özet ve gövdeyi üretir. Kaynak Markdown içinde yayınlanmaması gereken editör notları/HTML yorumları bırakma: ham metinde görünürler.
- `layouts/partials/head/extensions.html` canonical, `rel="alternate" type="text/markdown"`, `rel="describedby"` ve RSS keşif bağlantılarını üretir.
- Sitemap ve RSS Hugo tarafından oluşturulur. Bunları ve `public/` dosyalarını elle güncelleme.

## Kontroller

Temiz production çıktısıyla `hugo --minify --gc`, sonra `python scripts/validate_blog.py --public public` çalıştır. Alternatif destination kullanırsan iki komutta da aynı dizini seç. Hata varsa teslimden önce gider. Geçen kontrolleri yalnızca gerçekten çalıştırıldıysa raporla.

Yeni veya değişen yazıyı `hugo server --buildDrafts` ile incele: başlık hiyerarşisi, kod taşması, görseller, özet ve bağlantılar. Gövdedeki kod örneklerinin doğruluğu HTML doğrulayıcısından ayrı kontrol edilir.

Altyapı değişikliğinde `python scripts/test_blog_pipeline.py --hugo <hugo-executable>` çalıştır: taslak/gelecek/süresi dolmuş yazıların production çıktısına girmediğini ve yeni yazının otomatik indekslendiğini sınar.

Canlıya dağıtım istendiyse verilen dağıtım yöntemiyle ilerle. Sunucuda `.txt` için `text/plain`, `.md` için `text/markdown; charset=utf-8` ve Markdown cevaplarında HTML adresine canonical `Link` header'ını doğrula. Docker yolu `deploy/nginx-default.conf` kullanır. CDN/WAF bunları değiştirebilir; gerçek HTTP cevaplarını görmeden doğrulandı deme.

`robots.txt` keşif içindir; gizlilik veya botun gerçekten uyduğunun garantisi değildir. Sitenin llms dosyası yayınlaması, bir sağlayıcının dosyayı okuyacağını veya yazıyı kaynak göstereceğini garanti etmez. Canlı ölçüm için Search Console, sunucu erişim logları ve yönlendirme trafiği kullanılır; erişim yoksa yapılmış gibi raporlama.
