---
title: '“Ucuz Model %70’ini Çözüyor.” Peki Kalan %30’u Nasıl Ayırt Ederiz?'
date: "2026-10-26T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/ai-native-swe/ucuz-model-yeterli-mi/"
series: "ai-native-swe"
translationKey: "is-cheap-model-sufficient"
description: 'LLM routing ile ucuz ve pahalı model arasında maliyet-kalite dengesi: pre-router, quality gate, shadow evaluation ve rollback stratejisi.'
summary: "Ucuz modelin pahalı modelle %70 aynı sonucu vermesi, isteklerin %70’ini güvenle ona devredebileceğimiz anlamına gelmiyor. Bu düşünce deneyinde pre-router ile zor belgeleri baştan ayırmayı, deterministik ve semantik doğrulama katmanlarıyla çıktı kalitesini kontrol etmeyi, shadow sampling ile sessiz bozulmayı yakalamayı ve segment bazlı rollback stratejisi kurmayı ele alıyorum."
tags: ["AI Native SWE", "AI", "LLM", "LLM Routing", "AI Reliability", "Model Evaluation", "Cost Optimization", "LiteLLM"]
image: "/images/is-cheap-model-sufficient.png"
imageAlt: "Ucuz ve pahalı model arasında yönlendirme kararını gösteren LLM routing akış diyagramı."
toc: true
summaryForLLM: true
mathjax: false
---

*LLM routing ile maliyeti düşürürken kaliteyi, gecikmeyi ve sessiz hataları nasıl yönetiriz?*

Bir LLM sistemini daha ekonomik hâle getirmek için her zaman daha ucuz bir modele geçmek gerekmiyor. Bazen asıl kazanç, **hangi isteğin hangi modele gitmesi gerektiğini** doğru belirlemekten geliyor.

Bu yazıda başka bir soru-cevap düşüncesini tartışacağız. Önceki [golden dataset ve canary değerlendirmesi yazısında](/ai-native-swe/llmler-icin-golden-dataset-tasarlamak/) olduğu gibi, burada anlattığım sistem yaşanmış bir production vakası değil; mühendislik kararlarını görünür kılmak için kurgulanmış bir düşünce deneyi.

> Demo : https://github.com/onurozkir/assured-route

Soru şu:

> Bir doküman sınıflandırma ve alan çıkarımı servisi yönetiyorsun. Buna RAG veya bir karar modeli diyebiliriz.
> Sistem ayda **4 milyon istek** alıyor. Şu anda tek bir güçlü model kullanılıyor ve aylık model faturası **60.000 USD**.
>
> Daha ucuz bir model deniyorsun. Offline testlerde ucuz model, isteklerin yaklaşık **%70'inde pahalı modelle aynı sonucu** veriyor; kalan %30'unda daha kötü sonuçlar üretiyor.
>
> Yönetim şöyle diyor: **“Önce ucuz modeli çağıralım. Sonuç kötüyse pahalı modele geçeriz.”**
>
> Ama çalışırken sonucun kötü olduğunu nasıl anlayacağız? Her istekte iki modeli çağırırsak tasarruf azalacak. Bazı alanlarda hata tolere edilebilirken `tutar`, `tarih` ve `taraf_adı` gibi alanlardaki hatalar finansal süreçleri bozabilir. Üstelik uçtan uca gecikme bütçemiz yalnızca **1,5 saniye**. Kaliteyi takip etmek için elimizde şimdilik manuel örnekleme var.
>
> **Maliyet düşerken kalitenin korunacağını nasıl kanıtlarız? Bu sistem bozulduğunda bunu nasıl fark eder ve nasıl geri döneriz?**


Öncelikle nereden çıktı bu soru: Tabii ki [LiteLLM](https://www.litellm.ai/). Tabii ki her şey LiteLLM değil. Burada aslında LiteLLM ve RouteLLM ne yapıyorlar ve nasıl yapıyorlar diye düşünürken bir de bunların üstüne **Quality Decision Layer** ekleyebilir miyiz?

Burada akla ilk gelen çözüm, önce ucuz modeli çalıştırır, confidence düşükse pahalıya geçeriz. Fakat bu önerinin içinde iki cevaplanmamış soru var: **Confidence doğruyu mu ölçüyor?** Ve **pahalı modele geçmek için yeterli zamanımız kalacak mı?**

Bence burada challenge sadece bir *model router* yazmak değil. Görev, model hatasının maliyetini, hatayı fark etme olasılığını ve karar vermek için kalan süreyi aynı sistem içinde yönetmek.

## 1. %70 agreement, %70 accuracy değildir

Başlangıç bilgimiz, ucuz modelin pahalı modelle isteklerin %70'inde **aynı sonucu verdiği**. Bu, ucuz modelin %70 doğru olduğu anlamına gelmez.

- İki modelin aynı yanıtı verdiği bir dokümanda ikisi de hatalı olabilir. 
- Farklı yanıt verdikleri bir dokümanda ise ucuz model haklı, pahalı model haksız olabilir. 
- Pahalı modelin güçlü olması, onun otomatik olarak *ground truth* olduğu anlamına gelmez.

Bu ayrım önemli; çünkü router'ı yalnızca iki modelin anlaşamadığı örneklerle eğitirsek “pahalı modelden farklı olmayı” hata gibi öğretmiş oluruz.

Önce üç ayrı şeyi ölçmemiz gerekiyor:

| Ölçüm | Cevapladığı soru |
| --- | --- |
| **Model agreement** | Ucuz ve pahalı model ne sıklıkta aynı sonucu veriyor? |
| **Ground-truth accuracy** | Her model bağımsız doğrulanmış doğru sonuca ne kadar yakın? |
| **Critical field error** | Hata, iş açısından kritik bir alanda mı oluşuyor? |

Bu yüzden daha önce tartıştığımız **golden dataset** yaklaşımı burada da temel gereksinim. Doküman tipi, OCR kalitesi, şablon, dil, kritik alanlar ve zorluk dağılımı bakımından tabakalı bir değerlendirme seti oluştururum. İnsan tarafından doğrulanan tutar, tarih ve taraf bilgilerini referans alırım.

Ayrıca bütün hataları tek skorla değerlendirmem.

Yanlış bir `etiket`, belgeyi yanlış kuyruğa gönderebilir ve yeniden sınıflandırmayla düzeltilebilir. Yanlış bir `genel_toplam` ise ERP'ye veya ödeme sürecine aktarılırsa çok daha pahalı bir hataya dönüşebilir.

> **Temel ilke:** Router, yalnızca yanlış cevap verme olasılığını değil, *yanlış cevabın iş üzerindeki etkisini* de dikkate almalı.

## 2. Ucuz modelin çıktısının yeterli olduğunu nasıl anlayacağız?

Tek bir confidence eşiği koymam. Bunun yerine, çıktının birden fazla bağımsız kontrolden geçtiği bir **Quality Gate** tasarlarım.

### İlk katman: Şema ve tip doğrulaması

Beklenen JSON alanları var mı? Tarih geçerli formatta mı? Tutar sayısal mı? Zorunlu alanlar boş mu? VKN veya IBAN için uygulanabilir checksum kuralları sağlanıyor mu?

Bu kontroller hızlıdır ve gereklidir. Ama bir belgeye ait olmayan `12500.00` değeri de geçerli bir JSON sayısıdır.

**Schema valid olması, içeriğin doğru olduğu anlamına gelmez.**

### İkinci katman: Deterministik kurallar ve grounding

Örneğin bir faturada:

```text
Ara toplam + Vergiler - İndirimler ≈ Genel toplam
```

ilişkisini uygun para birimi, yuvarlama ve belgeye özgü istisnalarla kontrol edebilirim.

Ayrıca modelin çıkardığı alanın kaynak metindeki karşılığını ararım:

```json
{
  "field": "invoice_total",
  "value": 12800.00,
  "currency": "TRY",
  "evidence": {
    "page": 1,
    "text": "GENEL TOPLAM: 12.800,00 TL"
  }
}
```

Burada önemli bir ayrıntı var: `evidence` alanını modelin üretmiş olması yeterli değil. Bu metnin gerçekten OCR sonucunda, belirtilen sayfada bulunduğunu ve değerin doğru alanla eşleştiğini ayrıca kontrol etmeliyim.

Örneğin aynı belgede hem `Ara Toplam: 10.000 TL` hem de `Genel Toplam: 12.800 TL` yazabilir. Çıkarılan tutarın belgede geçmesi, doğru tutarın seçildiğini tek başına kanıtlamaz. Satıcı ve alıcı adları için de aynı sorun geçerli.

OCR gürültüsü nedeniyle katı metin eşleşmesi bazen doğru sonuçları reddedebilir. Bu yüzden normalizasyon ve gerektiğinde kontrollü fuzzy matching kullanırım; ancak bulanık eşleşmenin yanlış alanı da eşleştirebileceğini unutmam.

### Üçüncü katman: Alan bazlı belirsizlik sinyalleri

Ucuz modelin token olasılıkları erişilebilir durumdaysa bunları kullanmak isteyebilirim. Özellikle `tutar`, `tarih` ve `taraf_adı` gibi kritik değerleri oluşturan token'ların olasılıkları, genel bir cevap confidence değerinden daha anlamlı olabilir.

Ama bir ayrım şart:

- `P(token)` 0 ile 1 arasında bir olasılıktır.
- `log P(token)` sıfır veya negatif bir değerdir.
- Uzun bir şirket adı, tek bir düşük olasılıklı alt-token yüzünden gereğinden riskli görünebilir.
- Model, yanlış bir cevabı da yüksek olasılıkla üretebilir.

Dolayısıyla `min token probability > 0.90` gibi bir eşiği doğrudan production kabul kuralı yapmam. Bunun yerine token-level sinyalleri, alan uzunluğunu, OCR kalitesini, kaynak eşleşmesini ve kural sonuçlarını birleştirip **kalibre edilmiş bir hata tahminleyicisine** özellik olarak veririm.

Bu yaklaşım modelin kendi güven puanını nihai hakem olarak görmez. Hata tahminleyicisinin ne kadar güvenilir olduğunu da golden dataset üzerinde sınar.

### Dördüncü katman: Selective verifier

Bazı hatalar matematikle yakalanamaz. Özellikle **rol eşleştirmesi** bunlardan biri.

Bir sözleşmedeki iki şirket adını doğru bulmuş olabiliriz, ama hangisi hizmet sağlayıcı, hangisi müşteri? Veya belgede geçen iki tarihten hangisi düzenleme, hangisi vade tarihi?

Burada ikinci bir büyük LLM çağırmak yerine **hafif bir cross-encoder verifier** deneyebilirim. Girdi olarak bütün dokümanı değil, ilgili OCR kesitini ve çıkarılan alanı veririm. Model, değerin doğru semantik role bağlanıp bağlanmadığını puanlar.

80M parametreli bir model veya ONNX/TensorRT ile optimize edilmiş çıkarım iyi bir aday olabilir. Fakat “20 ms'de çalışır” ya da “kritik hataların çoğunu yakalar” diyebilmem için hedef donanım ve gerçek veri üzerinde benchmark gerekir.

Üstelik verifier da yanılabilir. Özellikle yeni şablonlarda veya nadir belge türlerinde hem ucuz model hem de verifier aynı yanlışı yapabilir.

### Bu sinyallerin bedeli ne?

Burada *pozitif karar*ı “escalation gerekli” olarak tanımlıyorum.

| Kontrol | Gereksiz escalation riski | Kaçırılan hata riski |
| --- | --- | --- |
| Schema / tip | Doğru ama formatı bozuk çıktı pahalıya gider | Yanlış ama geçerli JSON kabul edilebilir |
| İş kuralları / grounding | OCR gürültüsü yüzünden doğru alan reddedilir | Kendi içinde tutarlı ama yanlış alan kabul edilir |
| Token-level sinyaller | Uzun veya nadir değerler gereksiz şüpheli görülür | Kendinden emin halüsinasyon kabul edilir |
| Cross-encoder verifier | Doğru rol eşleşmesini reddedebilir | Benzer semantik hatayı o da kaçırabilir |

Gereksiz escalation çoğunlukla ek inference maliyeti ve gecikme doğurur. **Kaçırılan kritik hata ise yanlış verinin downstream'e yazılmasına yol açabilir.** Bu iki maliyeti eşit görmem.

## 3. Model seçimini çıktıdan önce başlatmak: Pre-router

Yönetimin “ucuzdan başla, kötüyse pahalıya geç” önerisindeki temel darboğaz şu: Bütün istekleri önce ucuz modele gönderirsek, zor olanlarda hem zaman hem para harcarız.

Bunun yerine *pre-routing* kullanırım.

Doküman geldiğinde OCR ve metadata üzerinden hafif bir sınıflandırıcı çalıştırırım. Başlangıç için LightGBM gibi bir model makul bir aday:

- OCR kalite istatistikleri
- Sayfa sayısı, metin uzunluğu ve tablo yoğunluğu
- Sayısal alanların karmaşıklığı, çoklu para birimi işaretleri
- Bilinen / bilinmeyen şablon ve doküman türü
- İlgili iş akışının hata maliyeti
- Geçmişte aynı segmentte ucuz modelin ölçülmüş hata oranı

Böylece yüksek riskli veya ucuz modelin zorlanacağı tahmin edilen belgeleri **en baştan pahalı modele** gönderebilirim.

Burada çok cazip ama tehlikeli bir varsayım var: “Ucuz model %30'unda kötü; router bunların üçte ikisini baştan bulur, böylece yalnızca %10 fallback kalır.”

Bu sonucu hedeflemek mantıklı. Ama henüz elimizde kanıt yok. Dahası hatalı kabul edilen grubun %20'sini, trafiğin yalnızca %20'sini bypass ederek yakalamak, teorik olarak o bypass kümesinde **%100 precision** anlamına gelir. Bu oldukça güçlü bir beklenti.

Dolayısıyla %20'lik bypass oranını kararın kendisi yapmam. **Pre-router precision, recall, latency ve maliyet eğrilerini ölçerek** kabul edilebilir bir çalışma noktası seçerim.

Ve önemli bir teknik ayrıntı: Pre-router yalnızca **ucuz model çağrılmadan önce gerçekten elde bulunan** özellikleri kullanmalı. Sonradan ortaya çıkan bilgiyle eğitilmiş bir model offline testte başarılı, production'da uygulanamaz olabilir.

## 4. Üç rota ve bir güvenli çıkış

Sistemi dört olası sonuca göre tasarlarım:

| Yol | Ne zaman? | Karar |
| --- | --- | --- |
| **A — Cheap + Rules** | Bilinen şablon, düşük risk, bütün deterministik kontroller başarılı | Çıktıyı kabul et |
| **B — Cheap + Verifier** | Alan metinde var, fakat semantik rol veya eşleşme belirsiz | Seçici olarak doğrula; gerekirse yükselt |
| **C — Direct Expensive** | Pre-router yüksek risk veya zor belge tespit etti | Ucuz modeli hiç çağırma |
| **D — Pending / Review** | Kritik alan hâlâ belirsiz veya deadline dolmak üzere | Doğrulanmamış çıktıyı iş sistemine yazma |

Basitleştirilmiş akış:

```text
                  Gelen doküman
                        |
                  OCR + metadata
                        |
              Pre-Router (LightGBM)
                   /         \
            Yüksek risk     Cheap-eligible
                |               |
          Expensive Model    Cheap Model
                |               |
        Critical Validation  Schema + Rules
                |               |
                |        Calibrated Risk Gate
                |          /      |       \
                |       Accept  Verify   Escalate
                |          |      |         |
                |          |  Cross-Encoder  |
                |          |      |         |
                |          |   Accept /     |
                |          |   Escalate     |
                |          |      |         |
                +----------+------+---------+
                           |
                  Deadline + Final Gate
                       /        \
              Validated Output   Pending / Review
                           |
                 Async Quality Monitoring
```

Burada `ACCEPT` kararı, yalnızca modelin kendinden emin olması nedeniyle verilmez. Alanın iş riskiyle uyumlu doğrulama koşullarının sağlanması gerekir.

`PENDING / REVIEW` da başarısız tasarımın işareti değildir. Kritik alanlarda bazı isteklerin otomatik sonuçlanamayacağını kabul etmek, hatayı sessizce saklamaktan daha güvenli olabilir. Elbette bu yolun iş süreciyle uyumlu olması gerekir.

## 5. 1,5 saniye bütçesinde sıralı fallback gerçekten mümkün mü?

Örnek bir süre hesabı yapalım:

| Aşama | Örnek süre |
| --- | ---: |
| OCR / hazırlık | 150 ms |
| Cheap model | 450 ms |
| Expensive model | 950 ms |
| **Toplam** | **1550 ms** |

Bu hesapta ağ, validation ve servis overhead'leri bile yok. Dolayısıyla “her şüpheli cevapta pahalıya geçeriz” yaklaşımı 1,5 saniye bütçesiyle çelişebilir.

Çözüm yalnızca daha hızlı model bulmak değil; **hangi kararı ne zaman vereceğimizi değiştirmek**.

### Streaming early-exit

Çıktı üretimi üzerinde yeterli kontrolüm varsa kritik alanların JSON içinde daha erken üretilmesini isteyebilirim. Böylece bütün çıktıyı beklemeden, tamamlanmış kritik alanlar için erken validation sinyalleri toplayabilirim.

Örneğin ilk gelen kritik alan kaynak metinle açıkça çelişiyorsa ucuz modelin üretimini iptal edip pahalı modele geçmeyi deneyebilirim.

Ancak bunun gerçekten latency kazancı sağlaması için üç şey doğrulanmalı:

1. Kullanılan inference API'si streaming ve ihtiyaç duyulan token sinyallerini gerçekten sunuyor mu?
2. Kritik alanlar yeterince erken, **tamamlanmış ve doğrulanabilir** biçimde geliyor mu?
3. Stream iptal edildiğinde gerçek hesaplama ve faturalama maliyeti ne kadar azalıyor?

Bu cevapları almadan “180 ms'de erken çıkış” rakamını production garantisi olarak sunmam.

### Deadline-aware escalation

Her istek için kalan süreyi takip ederim. Pahalı modele geçiş kararı verildiğinde yalnızca kalite riskine değil, **kalan deadline'a** da bakarım.

Yeterli zaman varsa synchronous escalation yaparım. Yoksa ve kritik çıktı doğrulanamıyorsa isteği beklemeye alıp asenkron işleme veya insan incelemesine yönlendiririm.

Burada önemli bir sözleşme farkı var: **p95 latency ≤ 1,5 saniye** demek, bütün isteklerin 1,5 saniyede tamamlandığı anlamına gelmez. Eğer 1,5 saniye gerçek bir *hard deadline* ise timeout ve pending davranışı en baştan API sözleşmesine yazılmalı.

### Peki paralel çağrı ve hedging?

Bütün isteklerde ucuz ve pahalı modeli paralel çağırmam. Bu, tasarruf hedefimizi anlamsızlaştırabilir.

Ama çok sınırlı bir **hedging** stratejisi kullanabilirim. Örneğin ucuz model, o doküman türünün beklenen gecikmesini anlamlı biçimde aşıyorsa ve kalan süre kritikse pahalı modeli spekülatif olarak başlatmak mümkün.

Bunun bedeli açıktır: Hedging bazen bilinçli olarak iki model çağrısı yapar. Dolayısıyla ancak nadir tail-latency sorunlarında, ölçülmüş faydası ek maliyeti karşılıyorsa açarım. Ayrıca daha erken cevap veren modelin otomatik olarak daha doğru olduğunu varsaymam; final quality gate yine çalışır.

> **Benim varsayılanım:** Önce doğru pre-routing, sonra ucuz doğrulama. Streaming ve hedging ise ölçülebilir bir latency problemi kaldığında eklenen optimizasyonlar.

## 6. Doğru kararı veren bir Quality Gate'i nasıl eğitiriz?

Şimdi kritik soru şu: Quality Gate hangi noktada **Accept**, hangi noktada **Verify**, hangi noktada **Escalate** demeli?

Tek başına `confidence > 0.90` gibi bir kural, gözlemlenebilir bir hata bütçesi sunmaz.

Bunun yerine golden dataset üzerinde bir **error predictor** eğitirim. Girdileri; OCR kalitesi, doküman tipi, token-level sinyaller, source alignment, validator sonuçları ve benzeri özellikler olabilir. Hedef değişken ise bağımsız doğrulanmış **alan bazlı hata** olur.

Örneğin:

```text
P(invoice_total_wrong | document_features, model_output_signals)
P(seller_name_wrong | document_features, model_output_signals)
```

Bu olasılıkların gerçekten kalibre edilip edilmediğini ayrı bir doğrulama setinde incelerim. Probability calibration, Brier score ve reliability diagram burada kullanılabilir. Temperature scaling bazı modellerde yararlı bir teknik olsa da, her LLM ve her alan için otomatik çözüm olduğunu varsaymam.

Sonrasında **risk–coverage curve** üretirim:

- *Coverage:* Ucuz modelin çıktılarının ne kadarını pahalı modele gitmeden kabul ediyorum?
- *Selective risk:* Kabul ettiğim bu çıktılarda gerçek kritik hata oranı ne?

Örnek olarak %50 coverage'da kritik hata %0,05; %70'te %0,15; %85'te %0,60 çıkabilir. Bunlar gerçek ölçüm değil, mantığı göstermek için temsili değerler.

Eğer iş birimi %0,2'lik bir kritik hata bütçesi üzerinde uzlaştıysa, ancak uygun örneklem büyüklüğü ve güven aralıklarıyla bu bütçeyi sağladığımızı gösterebildiğimiz coverage seviyesine çıkarım.

Daha da önemlisi, **“tutar alanında sıfır hata toleransı”** ifadesini gerçekçi olmayan “model hiçbir zaman hata yapmayacak” vaadi olarak yorumlamam. Bunu, *doğrulanmamış kritik verinin downstream sisteme yazılmaması* şeklinde operasyonel bir politika olarak tanımlarım. İşin gerçek hata bütçesi ayrıca belirlenir.

## 7. Ucuz model sessizce kötüleşirse nasıl fark edeceğiz?

Offline test bir başlangıçtır. Production'a çıktıktan sonra yeni müşteri şablonları, farklı OCR özellikleri, belge dağılımı ve model güncellemeleri kaliteyi değiştirebilir.

Bunun için canlı sistemin yanına, kullanıcı yanıt süresinden bağımsız çalışan bir **Async Evaluation Plane** kurarım.

Ucuz modelden kabul edilen bazı dokümanlar, izin ve gizlilik kurallarına uygun şekilde bir kuyruğa alınır. Bu örnekler shadow pahalı modelle karşılaştırılır; seçilen bir alt küme de bağımsız insan doğrulamasına gider.

### Stratified shadow sampling

Başlangıç için şu politikayı deneyebilirim:

| Trafik grubu | Örnekleme hedefi | Amaç |
| --- | ---: | --- |
| Yüksek güvenle kabul edilenler | %0,5 | Sessizce kaçan hataları aramak |
| Gri bölge / verifier görenler | %5 | Karar sınırındaki bozulmayı yakalamak |
| Yeni veya düşük hacimli şablonlar | %10 | Bilinmeyen dağılımları izlemek |

Bu oranlar başlangıç varsayımlarıdır; toplam örnekleme hacmi segmentlerin gerçek trafik payına bağlıdır. Nadir ama kritik segmentleri fazla örneklersem global hata oranını hesaplarken bu ağırlıkları düzeltirim.

Ve iki ayrı sinyal izlerim:

**Critical Field Disagreement Rate (CFDR):** Ucuz model ile pahalı modelin kritik alanlarda uyuşmama oranı.

**Human-validated Critical Error Rate:** Bağımsız doğrulanmış referanslara göre gerçekten yanlış olan kritik alanların oranı.

İlki hızlı ve geniş ölçekli drift sinyali sağlar. İkincisi gerçek kalite kararına dayanak olur. **Teacher disagreement, ground truth değildir.** İki model aynı yanlışı yapabilir.

### Alarm yalnızca dashboard olmamalı

Başlangıçta şu guardrail'leri oluştururum:

| Sinyal | Örnek tetikleyici | Aksiyon |
| --- | --- | --- |
| CFDR | Kalibre edilmiş baseline'a göre anlamlı artış | Örneklemeyi artır; ilgili segmenti incele |
| Golden / insan doğrulamalı kritik hata | Önceden tanımlı hata bütçesinin güvenilir biçimde aşılması | Segment bazında pahalı modele dön |
| Escalation rate | Normal seviyesinden hem yukarı hem aşağı anormal sapma | Router, validator ve trafik dağılımını kontrol et |
| p95 / p99 latency | SLO ihlali veya tail-latency artışı | Timeout, capacity ve yönlendirmeyi incele |
| Doğrulanmış ciddi finansal veri hatası | Tek bir P0 olay | Etkilenen akış için fail-closed / incident süreci |

Bu eşikleri örnek sayısını dikkate almadan çalıştırmam. Düşük hacimli segmentte üç hatadan “sistem %200 kötüleşti” sonucu çıkarmak da, yüksek hacimli segmentte küçük ama anlamlı bir artışı görmezden gelmek de yanlış.

Ayrıca production'da küçük bir **expensive-only control cohort** tutarım. Böylece kalite değişiminin ucuz modelden mi, trafik dağılımından mı, yoksa tüm sistemin karşılaştığı yeni belgelerden mi kaynaklandığını daha iyi ayırabilirim.

## 8. Tasarruf gerçekten ne kadar? Birim ekonomiyi hesaplayalım

Başlangıç maliyeti açık:

```text
Aylık istek                4.000.000
Aylık pahalı model maliyeti 60.000 USD
Ortalama pahalı çağrı      0,015 USD
```

Ucuz modelin çağrı başına **0,0015 USD** olduğunu varsayalım. Bu ve aşağıdaki trafik oranları bir maliyet senaryosudur; ölçülmüş production sonucu değildir.

İç tutarlılığı olan bir routing dağılımı şöyle olabilir:

| Sonuçlanan yol | Toplam trafik |
| --- | ---: |
| Doğrudan pahalı model | %20 |
| Cheap + rules → kabul | %55 |
| Cheap + verifier → kabul | %15 |
| Cheap + verifier → pahalı model | %5 |
| Cheap → erken iptal / escalation → pahalı model | %5 |
| **Toplam** | **%100** |

Böylece:

- Ucuz model toplam trafiğin **%80'inde** çağrılır.
- Pahalı model toplam trafiğin **%30'unda** çağrılır (%20 doğrudan + %10 escalation).
- Verifier toplam trafiğin **%20'sinde** çalışır.
- Aynı görevde iki büyük model çağrılması **%10** olur; erken iptal edilen çağrıların gerçek ücreti ayrıca ölçülmelidir.

Aylık temel inference hesabı:

| Kalem | Hesap | Maliyet |
| --- | --- | ---: |
| Cheap | 3,2 milyon × 0,0015 USD | **4.800 USD** |
| Expensive | 1,2 milyon × 0,015 USD | **18.000 USD** |
| **Temel inference toplamı** | | **22.800 USD** |

Örneğin ayda 60.000 shadow pahalı model çağrısı yaparsam bu da yaklaşık **900 USD** ekler. Hafif verifier ve kuyruk altyapısı için ayrıca **300 USD** gibi tamamen varsayımsal bir hesaplama bütçesi ayırdığımı düşünelim.

Bu durumda örnek toplam **24.000 USD/ay**, mevcut duruma göre yaklaşık **36.000 USD (%60) brüt model ve örnek altyapı tasarrufu** olur.

Burada özellikle *brüt* diyorum. İnsan etiketleme, tekrar işleme, incident müdahalesi, farklı token uzunlukları, iptal edilen stream'in faturası ve downstream hatalar bu örnekte tam maliyetlendirilmiş değil.

Daha büyük tehlike ise şurada:

Ucuz yönlendirmeye geçtikten sonra gerçek kritik hata oranı yalnızca **0,1 yüzde puan** artarsa ayda yaklaşık **4.000 ek hatalı doküman** oluşabilir. Her birinin beklenen operasyonel zararı 10 USD ise:

```text
4.000 hata × 10 USD = 40.000 USD / ay
```

Bu, 36.000 USD'lik tasarrufu silmeye yeter.

Dolayısıyla yönetim toplantısında tek KPI olarak “token faturasını %60 azalttık” demem.

Ana metriğim **Cost per Successfully Resolved Task**.


Ayrıca **reprocessing rate**, **downstream error rate**, **cheap acceptance coverage** ve **kritik alan hata oranını** ayrı raporlarım. Bir dokümanın üç kez işlenmesi üç başarılı görev sayılmamalı.

> **Optimizasyon hedefi:** En ucuz inference değil, kalite ve latency sınırları altında *başarıyla çözülmüş görev başına en düşük toplam maliyet*.

## 9. Bozulduğunda nasıl geri döneriz?

Kalite düşüşünü tespit edebilen ama davranışını değiştiremeyen bir monitoring sistemi yeterli değil. Rollback mekanizması mimarinin bir parçası olmalı.

Ben üç seviyeli bir strateji kurarım:

**1. Segment bazlı izolasyon.** Sorun yalnızca yeni bir fatura şablonundaysa o segmenti doğrudan pahalı modele yönlendiririm. Diğer segmentlerin tasarrufunu korurum.

**2. Quality Gate'i sıkılaştırma veya cheap routing'i durdurma.** Belirsizlik belirli bir alanda artıyorsa kritik kabul koşullarını sıkılaştırabilirim. Ancak bunu körlemesine confidence eşiğini artırarak değil, ölçülmüş error/coverage ilişkisine göre yaparım.

**3. Full bypass.** Sistematik bozulmada bütün uygun trafiği mevcut pahalı modele geçiririm. Pahalı modelin de validation'dan muaf olmadığını unutmam.

Burada operasyonel bir sürpriz var: Normalde trafiğin %30'unu alan pahalı modele bir anda %100 trafik yönlendirirsek sağlayıcı rate limit'ine çarpabiliriz. Bu yüzden kapasiteyi ve maliyet sıçramasını önceden planlamalı, gerekirse kritik olmayan batch işleri geciktirmeliyiz.

İkinci mesele daha ciddi: **Rollback yapmak, daha önce downstream'e yazılmış hatalı kayıtları geri almaz.**

Bu nedenle request ID, belge hash'i, model/prompt/router/validator versiyonları, routing kararı ve validation sonucunu denetlenebilir biçimde tutarım. Bir sorun bulunduğunda etkilenen dokümanları tespit eder, yeniden işleme ve mutabakat akışını başlatırım. İdempotency kontrolleriyle aynı finansal kaydı iki kez oluşturmam. Kişisel ve ticari verilerin saklanmasını da erişim ve veri minimizasyonu politikalarına bağlarım.

## 10. Hangi sırayla production'a alırdım?

Bütün bileşenleri ilk günden devreye sokmak cazip. Ama LightGBM, calibrated gate, cross-encoder, streaming, hedging ve shadow evaluator aynı anda eklenirse kalitenin hangi değişiklikten etkilendiğini anlamak zorlaşır.

Bunun yerine kademeli ilerlerim:

| Aşama | Ne kurarım? | Bir sonraki aşamaya geçiş koşulu |
| --- | --- | --- |
| **P0 — Ölçüm zemini** | Golden dataset, alan bazlı hata tanımları, validation, audit log | Gerçek kaliteyi ölçebiliyorum |
| **P1 — Basit routing** | Pre-router + cheap + rules + direct expensive | Offline ve shadow testleri geçiyor |
| **P2 — Selective verification** | Cross-encoder ve calibrated risk gate | Aynı hata bütçesinde anlamlı coverage kazancı var |
| **P3 — Latency optimizasyonu** | Streaming early-exit, deadline-aware fallback, sınırlı hedging | p95/p99 ve toplam maliyet ölçülebilir biçimde iyileşiyor |
| **P4 — Controlled rollout** | Canary, control cohort, guardrail ve otomatik rollback | Gerçek trafik üzerinde kalite kaybı kabul edilen sınırda |

En önemli deneylerden biri, sadece ucuz modelin değil, **router'ın kendisinin** ne kadar iyi çalıştığını ölçmek. Bunun için aşağıdaki karşılaştırmalar faydalı:

- Pre-router olmadan vs LightGBM pre-router ile
- Sabit confidence eşiği vs kalibre edilmiş risk tahmini
- Deterministik gate vs gate + cross-encoder
- Full inference vs streaming early-exit
- Sequential fallback vs deadline-aware fallback vs sınırlı hedging
- Shadow disagreement vs insan doğrulamalı gerçek hata

Her yeni katmanın kazancını **marjinal kalite artışı, ek maliyet, ek latency ve operasyonel karmaşıklık** üzerinden değerlendiririm. Kazancı kanıtlanmayan bileşeni sırf teknik olarak ilginç diye production'a taşımam.

## 11. Bugün Tech Lead'e ne söylerdim?

Şunu:

> “Ucuz modelin pahalı modelle %70 aynı sonucu vermesi, isteklerin %70’ini güvenle ona devredebileceğimiz anlamına gelmiyor. Önce bu farkların gerçek hata olup olmadığını ve hangi alanlarda oluştuğunu golden dataset üzerinde ölçmeliyiz.
>
> Ardından zor belgeleri baştan pahalıya gönderen bir pre-router, kolay çıktılar için deterministik kontrol, belirsiz semantik alanlar için küçük bir verifier ve kritik hatalarda fail-closed davranış kurabiliriz.
>
> Streaming early-exit ile gecikmeyi azaltmayı deneyebiliriz, ama bu optimizasyonun faydasını ölçmeden SLA garantisi veremeyiz. Production'da shadow sampling ve insan doğrulamasıyla kaliteyi izleyecek; bozulma olduğunda segment bazında pahalı modele döneceğiz.
>
> Hedefimiz ucuz modeli mümkün olduğunca fazla çağırmak değil. **Kritik hata bütçesini aşmadan, başarıyla çözülen görev başına maliyeti düşürmek.**”

Bu yaklaşım daha az gösterişli olabilir; çünkü ilk gün “%60 tasarruf garantisi” vermiyor. Ama production sorumluluğu açısından daha savunulabilir. Hangi varsayımın test edilmesi gerektiğini, hangi veri gelirse kararımızın değişeceğini ve sistem bozulduğunda ne yapacağımızı açıkça tarif ediyor.

## 12. Bu tasarımın asıl trade-off'ları

| Tercih | Kazancı | Bedeli |
| --- | --- | --- |
| LightGBM pre-router | Zor isteklerde gereksiz çift çağrıyı azaltır | Yanlış yönlendirme ve model bakım maliyeti |
| Deterministik kurallar | Hızlı ve yorumlanabilir güvenlik hattı | Semantik hataları ve belge istisnalarını kaçırabilir |
| Field-level calibrated risk | Confidence'ı ölçülebilir karara dönüştürür | Etiketli veri ve sürekli kalibrasyon gerekir |
| Selective cross-encoder | Küçük maliyetle rol/eşleşme hatalarını yakalayabilir | Yeni bir modelin yanlılıkları ve operasyonel maliyeti |
| Streaming early-exit | Bazı fallback'leri hızlandırabilir | API bağımlılığı, parçalı çıktıyı doğrulama karmaşıklığı |
| Hedging | Nadir tail-latency sorunlarını azaltabilir | Bilerek çift çağrı ve ek kapasite tüketimi |
| Stratified shadow + golden review | Sessiz drift ve gerçek kaliteyi birlikte izler | Örnekleme, insan emeği ve istatistiksel belirsizlik |
| Fail-closed + rollback | Kritik veri bütünlüğünü korur | Pending işler, yeniden işleme ve daha yüksek maliyet |

Sonuçta bu problem bir *“küçük model mi, büyük model mi?”* karşılaştırmasından daha fazlası.

Asıl sorumuz şu:

> **Bir model çıktısına ne zaman güvenebiliriz; ne zaman doğrulama istemeliyiz; ne zaman daha güçlü modele gitmeliyiz; ne zaman da otomatik karar vermemeliyiz?**

Bence bu soruya veriye dayalı cevap verebilen sistem, basit bir LLM router'dan daha değerli. Çünkü sadece modeli seçmiyor; **modelin üretimde ne kadar sorumluluk alabileceğini** yönetiyor.

Belki bunu ileride bağımsız bir **Quality-Aware Inference Gateway** olarak tasarlamak da mümkün. Router, validator, calibrator, shadow evaluator ve rollback controller'ın tek bir ürün fikrinde birleştiği bir altyapı.

Önceki yazıda “Kalite düştü mü?” diye sormuştuk. Bu yazıda soruyu bir adım ileri taşıyoruz:

**“Kalitenin düşmesine izin vermeden, pahalı modele ne kadar az ihtiyaç duyabiliriz?”**

---

## Kavram sözlüğü

| Terim | Kısa açıklama |
| --- | --- |
| Model routing | İsteğin hangi model veya doğrulama yolundan geçeceğine karar verme |
| Agreement | İki modelin aynı sonuçta buluşma oranı; doğrulukla aynı şey değil |
| Pre-router | Ana inference çağrısından önce çalışan hafif yönlendirme bileşeni |
| Quality Gate | Çıktının kabul, doğrulama, escalation veya review kararını veren kontrol katmanı |
| Grounding | Çıkarılan bilginin kaynak dokümanla ilişkilendirilmesi |
| Logprob | Modelin token olasılığının logaritması |
| Calibration | Güven veya hata olasılığı tahminlerinin gerçek sıklıklarla uyumu |
| Cross-encoder | Metin ve aday çıktıyı birlikte değerlendirerek eşleşme/uyum puanlayan model türü |
| Selective prediction | Riskli görülen örneklerde cevap vermemeyi veya başka yola yönlendirmeyi seçen yaklaşım |
| Coverage | Belirli bir yolun otomatik olarak kabul ettiği görevlerin oranı |
| Risk–coverage curve | Otomatik kabul oranı arttıkça kabul edilenlerde hata oranının nasıl değiştiği |
| Shadow evaluation | Canlı kullanıcı sonucunu etkilemeden alternatif modeli değerlendirme |
| Hedging | Gecikmeyi azaltmak için bazı isteklerde yedek çağrıyı spekülatif başlatma |
| Fail-closed | Yeterli güvence yoksa kritik çıktıyı otomatik olarak kullanıma sokmama |
| CPSRT | Başarıyla tamamlanmış görev başına toplam maliyet |

## İleri okuma

1. [Geifman & El-Yaniv (NeurIPS 2017) — *Selective Classification for Deep Neural Networks*](https://arxiv.org/abs/1705.08500). Risk ile otomatik kabul oranı arasındaki ilişki.
2. [Guo ve diğerleri (ICML 2017) — *On Calibration of Modern Neural Networks*](https://proceedings.mlr.press/v70/guo17a.html). Güven tahminlerini gerçek doğrulukla kalibre etme problemi.
3. [Ong ve diğerleri (ICLR 2025) — *RouteLLM: Learning to Route LLMs from Preference Data*](https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html). Güçlü ve ekonomik modeller arasında öğrenilmiş yönlendirme.
4. [Chuang ve diğerleri (ICML 2025) — *Learning to Route LLMs with Confidence Tokens*](https://proceedings.mlr.press/v267/chuang25b.html). Confidence sinyalleriyle routing ve gerektiğinde cevap vermeme.
5. [Dean & Barroso (Communications of the ACM, 2013) — *The Tail at Scale*](https://research.google/pubs/the-tail-at-scale/). Tail-latency ve hedged requests yaklaşımının sistem tarafındaki temelleri.

*Not: Bu yazı bir sistem tasarımı ve düşünce deneyidir. Model fiyatları, trafik dağılımı, süreler, doğrulayıcı kapasitesi, örnekleme oranları ve tasarruf hesapları senaryo varsayımlarıdır; production'da ölçülmüş sonuçlar gibi yorumlanmamalıdır.*
