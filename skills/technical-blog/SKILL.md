---
name: technical-blog
description: onurozkir.com için yazılım geliştirme, mimari ve yapay zekâ konulu Türkçe teknik blog yazıları oluştur veya düzenle; verilen Markdown notunu kaynaklı, örnekli ve Hugo ile yayınlanabilir yazıya dönüştür.
---

# Teknik blog yazımı

Bu skill depo kökündeki `AGENTS.md` ile birlikte kullanılır. Bütün depo yolları köke göredir.

## Girdiden yazıya

Kullanıcının gösterdiği notu oku. Konu, hedef okur, çözülmek istenen problem ve özgün katkıyı çıkar. Konu zaten yeterince belirginse ayrıca brief doldurtma. Eksik isteğe bağlı ayrıntılarda makul varsayım kullan; deney sonucu veya kişisel tecrübe gerektiren boşlukları uydurma. Girdi hazırlamak isteyen kullanıcı için `templates/blog-brief.md` mevcut.

`content/blogs/` içindeki başlıkları tarayıp tekrarları ve ilgili iç bağlantıları belirle. Ton için `kirk-katir-mi-kirk-satir-mi.md` ile konuya yakın bir yazıyı oku. Samimi, doğrudan, yer yer mizahlı Türkçe; gündelik benzetmelerden teknik açıklamaya geç. Mizahı zorunlu hale getirme. “Devrim niteliğinde”, “kusursuz”, temelsiz “%100 garanti” gibi pazarlama ifadeleri kullanma.

`docs/blog-frontmatter.md` ve `archetypes/blogs.md` dosyalarını oku. `hugo new content blogs/<slug>.md` şablonu doldurur. Hugo yoksa aynı şemayla dosyayı oluştur; Go template ifadelerini yazıya kopyalama. Başlıkları konunun ihtiyacına göre değiştir; her yazıyı aynı başlık ve uzunluğa zorlamadan problem, çözüm, kararın bedeli ve çıkarımı anlaşılır kıl.

## Kanıt ve teknik derinlik

- Değişebilen API, sürüm, model yeteneği, fiyat, lisans ve performans iddialarını güncel birincil kaynaklardan doğrula. Resmî doküman, sürüm notu, kaynak kodu veya makale kullan; bağlantıyı desteklediği iddianın yakınına koy.
- Not, kişisel görüş, mimari düşünce deneyi, ölçüm ve dış kaynaktan gelen bulguyu ayır. “Ben yaptım/ölçtüm” ancak kullanıcı veya repo bunu destekliyorsa yazılabilir. Uydurma alıntı ve kaynak kullanma.
- Kod örneğinde kullanılan sürümleri, gerekli bağımlılıkları, çalıştırma komutunu ve beklenen davranışı açıkla. Küçük ve bütünlüklü örnek kullan. Çalıştırdıysan komut ve sonucu kaydet; çalıştırmadıysan doğrulanmış gibi sunma. Pseudocode'u açıkça etiketle.
- Mimari yazıda hata akışı, retry/idempotency, veri tutarlılığı veya operasyon maliyetinden konuya gerçekten etki edeni incele. Önerinin uygun olmadığı bir durumu ve en ilgili alternatifi açıkla.
- Benchmark varsa ortam, veri büyüklüğü, yük modeli, yöntem ve sınırlamaları belirt. Ölçülmemiş sayısal sonuçları varsayım/senaryo olarak adlandır veya çıkar.
- AI yazısında ilgili model kimliği/sürümü, sağlayıcı, deney tarihi, prompt ve önemli ayarları belirt. RAG/agent örneğinde veri kaynağı, retrieval/tool akışı ve anlamlı başarısızlık örneği göster. Değerlendirmede veri seti, metrik, baseline ve veri sızıntısı riskini ele al; tek örnekten genel başarı oranı çıkarma. Maliyet/gecikme sayıları ölçüm veya tarihli kaynağa dayanmalı. Gerekliyse gizlilik, prompt injection ve lisans sınırlarını somut tasarıma bağla.

## Yazı ve teslim

İlk paragraflarda problemi ve okurun ne öğreneceğini söyle. H1 tema tarafından gelir; gövdeyi H2 ile bölümle. Teknik terimi ilk kullanımda bağlamıyla tanımla. Açıklayıcı bağlantı metni, gerçek görsele ait alt metin ve gerektiği kadar iç bağlantı kullan. Alakasız SSS, anahtar kelime tekrarı veya yalnızca botlar için görünmez içerik ekleme.

`description` arama/paylaşım için kısa tanıtım; `summary` yazının okuyucuya görünen özeti olmalı. İkisi de gövdede bulunmayan vaat veya sonuç içermemeli. İngilizce özet zorunlu değildir; Türkçe varsayılandır.

Sonrasında `skills/blog-seo/SKILL.md` akışını uygula. Şablonun yönerge/yer tutucularını kaldır. Yayın durumunu kullanıcının isteğine göre ayarla; doğrulanamayan kritik bir iddia varsa kaldır, sınırlandır veya kullanıcıya somut eksikliği bildir. Derleme başarısını içerik doğruluğunun kanıtı sayma.
