# Haftalık blog çalışma akışı

## Notu yazıya dönüştürme

İstersen `templates/blog-brief.md` dosyasını `notes/bir.md` olarak kopyala; serbest biçimli not da yeterlidir. `notes/`, `templates/`, `skills/` ve `docs/` Hugo içerik dizini değildir, web sayfasına dönüşmez. Gizli bilgileri yine de bu depoya ekleme.

Bir ajana verilebilecek örnek istek:

```text
AGENTS.md dosyasını oku. notes/bir.md içeriğini temel alarak
skills/technical-blog/SKILL.md ve skills/blog-seo/SKILL.md yönergelerine,
docs/blog-frontmatter.md şemasına ve archetypes/blogs.md taslağına uygun
bir Türkçe teknik blog yazısı hazırla. Konuya uygun eski yazıları bağla,
teknik iddiaları birincil kaynaklarla doğrula ve kontrolleri çalıştır.
content/blogs/ altında draft: true olarak bırak.
```

Yazı hazırsa son cümleyi “Kontroller geçince `draft: false` ile yayına hazırla.” olarak değiştir. Canlı deploy da istiyorsan hedefi/yöntemi belirt. Yerel dosyanın hazırlanması, canlı sitenin güncellenmesi değildir.

## Tek doğruluk kaynağı

Yeni yazıda yalnızca Markdown içeriğini ve gerekiyorsa görsellerini hazırlarsın. Hugo build şunları üretir:

| Adres | İçerik |
| --- | --- |
| `/blogs/<slug>/` | Okuyucu için HTML yazı |
| `/blogs/<slug>/index.md` | Başlık, asıl URL, yazar, tarihler, özet ve tam Markdown gövde |
| `/llms.txt` | Yayınlanmış yazılardan otomatik bağlantı dizini |
| `/llms-full.txt` | Aynı yazıların tam metin derlemesi |
| `/sitemap.xml` | Hugo sitemap |
| `/blogs/index.xml` | Blog RSS |

Eski `static/llms.txt` kaldırıldı. Yeni bir statik kopya eklemek otomatik çıktı ile çakışır. Yazıya özel elle bir llms dosyası doldurmak gerekmez. Yazı HTML'sindeki `alternate` bağlantısı Markdown sürümüne, `describedby` bağlantısı kök llms dosyasına yönlendirir.

## Haftalık ritim

1. Haftanın tek sorusunu ve okurun kazanımını seç; eski yazıları kontrol et.
2. Kod, deney veya mimari örneği hazırla; kaynakları ve gerçek sonuçları nota ekle.
3. Ajanın hazırladığı taslağı özellikle kişisel deneyim, ölçüm ve öneriler açısından oku.
4. Kod örneklerini ve sayfayı doğrula; yayına hazır olduğunda yayın durumunu değiştir.
5. Production build/deploy yap; sonra gerçek URL, sitemap, Markdown ve llms dosyalarını kontrol et.

Bu kurulum haftalık zamanlanmış iş oluşturmaz. Gelecekteki bir yayın tarihi için o tarihte yeni bir build/deploy tetiklenmelidir. Taslak/future/expired içeriği production'da oluşturulmaz. Önizlemede bu yazılar açılabilir, fakat llms dizinlerine girmez; preview çıktısını canlıya yükleme.

## LLM erişimi ve SEO'nun sınırı

`llms.txt` bir keşif önerisidir; sıralama, eğitim verisine girme veya asistanlarca kaynak gösterilme garantisi değildir. Bu sitede katkısı yazılara kısa bir dizin ve kolay okunur tam metin sunmaktır. Önerinin biçimi ve keşif bağlantıları için [llms.txt spesifikasyonu](https://llmstxt.org/) esas alındı.

Google, AI arama özellikleri için normal SEO ilkelerinin geçerli olduğunu ve özel AI metin dosyasının zorunlu olmadığını söylüyor. Bu nedenle görünür ve faydalı içerik, doğru metadata, iç bağlantılar ve taranabilir HTML temel alınır. [Google AI özellikleri rehberi](https://developers.google.com/search/docs/appearance/ai-features).

`BlogPosting` yapılandırılmış verisi görünür başlık, açıklama, yazar, tarih ve gerçek kapak görselinden üretilir; hayali resim, puan veya özel AI schema eklenmez. [Google Article rehberi](https://developers.google.com/search/docs/appearance/structured-data/article).

## Yayın sonrası gözlem

- Canlı HTML, Markdown ve llms adreslerinin `200` döndüğünü kontrol et. `robots.txt` ve CDN/WAF kuralları içeriği engellememeli.
- Search Console'da sitemap gönderimi, URL inceleme ve indeksleme durumunu kontrol et. Bu işlemler için site hesabına erişim gerekir; bu kurulum bunları gerçekleştirmez.
- Sunucu loglarında bot erişimleri ve analitikte yönlendirme trafiği gözlenebilir. User-Agent tek başına doğrulanmış bot kimliği değildir.
- Bir asistana yalnızca sitenin `llms.txt` adresini vererek bir yazıyı bulmasını ve somut soruları kaynak bağlantısıyla cevaplamasını iste. Bu erişilebilirlik deneyi, tüm LLM'lerin siteyi indekslediğinin kanıtı değildir.

Uygulama kaynakları: [Hugo output formats](https://gohugo.io/configuration/output-formats/), [Hugo front matter](https://gohugo.io/content-management/front-matter/). Altyapı 14 Eylül 2026'da Hugo Extended 0.166.0 ile doğrulandı.
