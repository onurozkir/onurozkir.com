# Blog metadata şeması

Dosya yolu: `content/blogs/<ascii-kebab-case-slug>.md`. YAML front matter `---` ile açılıp kapanır. Şablon `archetypes/blogs.md`; `hugo new content blogs/<slug>.md` ile kullanılır.

| Alan | Tip | Yeni yazı kuralı |
| --- | --- | --- |
| `title` | string | Zorunlu; açık ve içeriği karşılayan başlık. Gövdede ikinci H1 kullanma. |
| `date` | RFC 3339 datetime | Zorunlu; gerçek yayın tarihi, Türkiye için `+03:00`. |
| `draft` | boolean | Zorunlu; başlangıçta `true`, yayına hazır içerikte `false`. |
| `author` | string | Zorunlu; varsayılan `Onur Özkır`. |
| `description` | string | Zorunlu; özgün, kısa Türkçe tanıtım. Yaklaşık 140–170 karakter editoryal hedef, teknik zorunluluk değil. |
| `summary` | string | Zorunlu; konuyu, yaklaşımı ve sınırını anlatan 2–4 cümle. Okuyucuya görünür. |
| `tags` | string[] | Zorunlu; genellikle 3–6 ilgili etiket. Mevcut yazılardaki adları tercih et. |
| `image` | string | İsteğe bağlı; var olan `/images/...` kapak görseli. |
| `imageAlt` | string | Kapak varsa yaz; görselin ne anlattığını tarif et. |
| `toc` | boolean | Varsayılan `true`; kısa yazıda kapatılabilir. |
| `summaryForLLM` | boolean | Varsayılan `true`; geriye uyumlu alan adı, okuyucudaki başlık “Kısa özet”. |
| `mathjax` | boolean | Varsayılan `false`; yalnızca denklem gerekiyorsa aç. |
| `lastmod` | RFC 3339 datetime | Anlamlı içerik güncellemesi varsa gerçek tarih. Yoksa Hugo yayın tarihini kullanır. |
| `publishDate` | RFC 3339 datetime | İsteğe bağlı yayın eşiği. Gelecekteyse yeniden build gerektirir. |
| `expiryDate` | RFC 3339 datetime | İsteğe bağlı yayından kalkma eşiği; o tarihte yeniden build/deploy gerekir. |
| `slug` | string | Genellikle gereksiz; dosya adından gelir. Mevcut slug'ı değiştirme. |
| `aliases` | string[] | Yalnızca istenen URL taşımasında eski adresler. |

Yazı başına `outputs` ekleme; Hugo cascade HTML + Markdown üretir. `featured_image` kullanma; sitenin kapak alanı `image`. Özel SEO keywords veya LLM için ayrı gizli içerik gerekmez. Yeni özel alan eklemeden önce onu okuyan şablon var mı kontrol et.

Kod bloklarında dil etiketi kullan (`csharp`, `go`, `python`, `yaml`, `bash`, `text`). Standart Markdown görsel ve bağlantıları hem HTML hem Markdown çıktısında okunur. Markdown çıktısı ham gövdeyi içerdiğinden editör yorumları dahil yayınlanmayacak notların tamamını kaldır.

Mevcut yazılar geriye uyumluluk için korunmuştur; bu şema geçmiş yazıların teknik iddialarının doğrulandığı anlamına gelmez. Eski yazıyı düzenlerken kaynak/ölçüm gerektiren iddiaları ayrıca gözden geçir.
