---
title: '“Kalite Düştü mü?”: LLM’ler İçin Golden Dataset’ten Canary’ye Güvenilir Değerlendirme Tasarlamak'
date: "2026-10-22T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/ai-native-swe/llmler-icin-golden-dataset-tasarlamak/"
series: "ai-native-swe"
translationKey: "llm-golden-dataset"
description: 'Sınırlı etiketleme bütçesi, değişen ticket trafiği ve LLM-as-judge önyargıları altında güvenilir model kalitesi ölçümü nasıl tasarlanır?'
summary: "Kabul oranındaki düşüş gerçek bir model regresyonu mu, yoksa değişen ticket dağılımının sonucu mu? Bu düşünce deneyinde, haftada altı saatlik insan emeğiyle PII içermeyen bir golden dataset kurmayı, LLM-as-judge sonuçlarını doğrulamayı ve offline değerlendirmeyi canary kararlarıyla birleştirmeyi ele alıyorum. Örnek eşiklerin ve sınırlı verinin hangi kararları destekleyebileceğini tartışıyorum."
tags: ["AI Native SWE", "AI", "LLM", "LLM-as-a-Judge", "Golden Dataset", "AI Reliability", "LLM Evaluation", "Data Privacy"]
image: "/images/design-golden-set-for-llm.png"
imageAlt: "Golden dataset, insan etiketleme, LLM-as-judge, canary deneyi ve metrik analizini Rollback, Hold ve Expand kararlarına bağlayan değerlendirme akışı."
toc: true
summaryForLLM: true
mathjax: false
---

*Bir kabul oranı düşüşünü gerçek model regresyonundan ayırmak ve sınırlı insan emeğiyle savunulabilir bir production kararı vermek.*

Bu yazıda bir soruyu adım adım ele alacağız. Anlattığım şey yaşanmış bir production hatası değil, çözdükçe yeni sorular doğuran bir düşünce deneyi. Soru şu:

> Çalıştığın şirketin destek ekibi, ticket’lara yanıt önermek için bir LLM kullanıyor. Daha ekonomik, daha hızlı veya kendi eğittiğiniz bir modele geçiyorsun. Yeni model, canary deployment ile production trafiğinin %5’ine açılmış durumda. Tech Lead senden “Model değişikliğinden sonra kalite düştü mü?” sorusunu cevaplamanı istiyor. Elinde yalnızca müşteri temsilcilerinin önerileri kabul/ret oranı ve ortalama yanıt süresi var. Kabul oranı %61’den %58’e düşmüş; ancak trafik dağılımı da değişmiş: Yeni bir ticket kategorisi eklenmiş.
>
> **Kısıtlar:**
>
> - Etiketleme bütçesi haftada toplam 6 saat insan emeği.
> - Golden dataset üretiminde gerçek müşterilere ait kişisel veriler (PII) kullanılamaz.
> - Golden dataset hem offline CI değerlendirmesinde hem de canary kararlarında kullanılacak.
>
> Bu soruyu cevaplayabilecek bir değerlendirme altyapısı tasarla. Golden dataset’i hangi kaynaklardan, nasıl örnekleyerek ve hangi boyutta oluşturursun? Kim, nasıl etiketler; etiket hatalarını nasıl kontrol edersin? Offline değerlendirmeyi canary’deki kabul oranıyla nasıl birleştirirsin? Hangi eşiği geçince “Kalite düştü” dersin? LLM-as-judge kullanacaksan insan etiketiyle uyumunu nasıl doğrularsın? Tercihlerinin getirilerini ve bedellerini açıkla.

İlk bakışta cevap kolay görünüyor: Müşteri temsilcilerinin önerileri kabul etme oranı **%61’den %58’e** gerilemiş. Üç yüzde puanlık bir düşüş var. Fakat aynı dönemde sisteme **yeni bir ticket kategorisi** de eklenmiş. Elimizde yalnızca kabul/ret davranışı ve ortalama yanıt süresi bulunuyor.

Dahası, haftalık insan etiketleme bütçemiz **6 saat**; golden dataset’te gerçek müşterilere ait kişisel verileri (**PII**) kullanamıyoruz; oluşturacağımız setin hem **offline CI** testlerinde hem de **canary kararlarında** işe yaraması gerekiyor.

Bu durumda iyi bir engineer’ın görevi yalnızca bir dashboard oluşturmak değil. Asıl görev, *hangi sinyale ne kadar güvenebileceğimizi* ve *hangi kanıtla release kararı vereceğimizi* tasarlamak.

## 1. İlk bakış: Kabul oranı, kalite midir?

Bir müşteri temsilcisi modelin önerisini neden reddeder?

- Öneri yanlış, eksik veya şirket politikasına aykırıdır.
- Öneri doğrudur; ancak temsilci farklı bir üslup tercih eder.
- Ticket karmaşıktır ve manuel inceleme gerektirir.
- Temsilci öneriyi tamamen reddetmemiş, düzenleyerek kullanmıştır.
- Öneri üretilmiştir ama temsilciye hiç gösterilmemiştir.

Bunların hepsi aynı olay değildir. Bu yüzden **acceptance rate**, modelin iş akışında ne kadar işe yaradığını gösteren değerli ama eksik bir *proxy metric*’tir.

Aynı dikkat ortalama yanıt süresi için de geçerli. Daha hızlı yanıt iyi bir deneyim anlamına gelebilir; ama özensiz yanıtlar da daha hızlı yazılabilir. Dahası, **model latency’si** ile **agent’ın yanıtı hazırlama süresi** ayrı tutulmalıdır.

İlk hedefimiz üç boyutu birbirinden ayırmak:

| Boyut | Esas soru | Örnek ölçümler |
|---|---|---|
| **Yanıt kalitesi** | Öneri doğru, güvenli ve kullanılabilir mi? | İnsan etiketi, politika ihlali, kritik hata |
| **Agent faydası** | Öneri temsilcinin işini kolaylaştırıyor mu? | Kabul, düzenleyerek kullanma, yanıt hazırlama süresi |
| **Sistem güvenilirliği** | Özellik production’da düzgün çalışıyor mu? | Hata oranı, timeout, p95 latency |

Kaliteyi tek bir birleşik skorda gizlemek yerine bu metrikleri ayrı raporlamak daha güvenli.

### Trafik kompozisyonu nasıl yanıltır?

Şu **tamamen temsili** senaryoya bakalım:

| Ticket kategorisi | Önceki trafik payı | Sonraki trafik payı | Kategori içi kabul oranı |
|---|---:|---:|---:|
| Kolay talepler | %55 | %40 | %70 |
| Zor talepler | %45 | %40 | %50 |
| Yeni kategori | %0 | %20 | %50 |

Önceki toplam kabul oranı:

> 0,55 * 0,70 + 0,45 * 0,50 = 0,61

Sonraki toplam kabul oranı:

> 0,40 * 0,70 + 0,40 * 0,50 + 0,20 * 0,50 = 0,58

Kabul oranı %61’den %58’e düşüyor; **ama kategori içi oranlardan hiçbiri değişmiyor**. Farkın tamamını trafik dağılımı açıklayabiliyor.

Bu örnek bize kritik bir ilkeyi hatırlatıyor:

> **Gözlenen metrik değişimi, tek başına model değişikliğinin nedensel etkisi değildir.**

## 2. Golden dataset: Modelin sınav kitapçığı

**Golden dataset**, test senaryoları ve beklenen doğru davranışları önceden tanımlanmış, uzmanlar tarafından doğrulanmış bir değerlendirme veri kümesidir.

Bir öğretmenin sınav hazırladığını düşün. Soruları ve cevap anahtarını önceden belirler; öğrencilerin yanıtlarını bu anahtarla karşılaştırır. Golden dataset de benzer bir işlev görür. Ancak açık uçlu LLM yanıtlarında tek bir cümleyi ezberletmek yerine *doğru davranışı* tarif etmek gerekir.

Örneğin sentetik bir müşteri mesajı:

> “Ürünüm hasarlı geldi. İade için ne yapmalıyım?”

**Beklenen davranış:** Geçerli iade politikasını referans almak, eksikse gerekli bilgileri istemek ve müşteriye doğru sonraki adımı açıklamak.

**Kritik hata:** Şirket politikasında dayanağı olmadığı hâlde kesin geri ödeme taahhüdü vermek.

Eski ve yeni model aynı senaryolarda değerlendirilince, gerçek trafik farklılaşsa bile **eşleştirilmiş (paired) karşılaştırma** yapabiliriz.

### Golden set’i nereden üretmeli?

Bu vakada gerçek müşteri PII’si golden set’e alınamaz. O nedenle üç kaynak kullanırım:

1. **Onaylı ve sürümlenmiş kaynaklar:** FAQ, knowledge base, iade/garanti politikaları.
2. **PII içermeyen agregat trafik istatistikleri:** Kategori frekansı, süreç tipi, zorluk dağılımı, risk işaretleri.
3. **Uzmanların hazırladığı sentetik vakalar:** Eksik bilgi, yanlış yazım, çelişkili talepler, çok adımlı süreçler ve kritik politika tuzakları.

Burada sentetik veri üretmenin de bedeli var: Yapay vakalar gerçek ticket’lardan fazla temiz ve tahmin edilebilir olabilir. Bu nedenle üretimden önce örnekleri support uzmanlarına kontrol ettiririm; ayrıca sentetik üretim sürecinin gerçek PII’yi kopyalamadığını taramalar ve insan denetimiyle doğrularım.

### Random sampling mi, stratified sampling mi?

**Random sampling**, vakaları rastgele seçer. Sık görülen talepleri iyi temsil edebilir; ancak nadir ama kritik sorunları ıskalayabilir.

**Stratified sampling**, önce vakaları anlamlı alt gruplara (*strata*) ayırır, ardından her gruptan belirlenmiş sayıda örnek alır. Örneğin:

- Ticket kategorisi: faturalama, iade, teknik destek, yeni kategori.
- Zorluk: kolay, orta, karmaşık.
- Risk: normal, yüksek, kritik.
- Gerekliyse dil, ürün veya agent segmenti.

**Risk-weighted sampling** ise ciddi sonuçlar doğurabilecek az sayıdaki vakaya daha fazla yer ayırır.

Başlangıçta **240 sentetik vaka** önerebilirim:

| Örnek grubu | Adet |
|---|---:|
| Mevcut kategorileri temsil eden vakalar | 160 |
| Yeni kategori | 40 |
| Kritik ve zorlayıcı vakalar | 40 |
| **Toplam** | **240** |

Bu rakamlar kanıtlanmış optimum değil; başlangıç tasarımıdır. 240 örnek, büyük regresyonları ve hata kalıplarını yakalamak için faydalı olabilir ama **2 yüzde puanlık küçük bir kalite farkını kesinlikle dışlamak için çoğu zaman yeterli değildir**.

Önemli bir ayrım daha var: Kritik vakaları bilerek fazla örneklediysek setin ham ortalaması production trafiğini temsil etmez. Bu nedenle raporda hem **stratum bazlı skorları** hem de güncel trafik ağırlıklarıyla hesaplanan **ağırlıklandırılmış skoru** gösteririm.

### Golden dataset için tarih aralığı: Son 6 ay yeterli mi?

Altı aylık referans pencere iyi bir başlangıç olabilir; fakat dogma hâline gelmemeli:

| Pencere | Avantajı | Riski |
|---|---|---|
| **Son 3 ay** | Yeni sorunlara duyarlı | Mevsimselliği ve nadir durumları kaçırabilir |
| **Son 6 ay** | Güncellik–kapsam dengesi | Yıllık örüntüler eksik kalabilir |
| **Son 12 ay** | Sezonluk değişimleri daha iyi kapsar | Eski, geçersiz iş kuralları karışabilir |

Pratik yaklaşım: Güncel trafik dağılımını belirlemek için **3, 6 ve 12 aylık pencereleri deneysel olarak karşılaştırmak**; artık geçerli olmayan politikaları dışlamak; hâlâ geçerli kritik tarihsel vakaları ise ayrıca korumak.

Bu süreçte **frozen regression set** (sabit karşılaştırma vakaları) ve **rolling/challenge set** (yenilenen ve zorlayıcı vakalar) ayrı sürümlenir. Böylece güncellik artarken geçmiş testlerin karşılaştırılabilirliği kaybolmaz.

## 3. Altı saatlik etiketleme bütçesiyle güvenilir sonuç üretmek

İnsan etiketi yüksek maliyetlidir. Ancak bütçeyi kısmak için etiket kalitesinden vazgeçersek, golden set yalnızca **güvenilir görünen** bir veri kümesine dönüşür.

İlk sorumuz “Kim etiketleyecek?” olmalı. Genel amaçlı *crowdsourcing* — yani işi geniş bir insan topluluğuna dağıtmak — birçok alanda işe yarayabilir. Fakat burada şirketin destek politikalarını bilen **deneyimli agent’lar** ve anlaşmazlıkları çözen **support QA/policy uzmanları** gerekir.

### Kullanılabilirlik rubriği

| Skor | Tanım | Kalite metriğinde |
|---|---|---|
| **3** | Doğru, eksiksiz, doğrudan kullanılabilir | Başarılı |
| **2** | Doğru, küçük düzenlemeyle kullanılabilir | Başarılı |
| **1** | Önemli eksik veya yanlış bilgi | Başarısız |
| **0** | Kritik gizlilik, güvenlik veya politika hatası | Kritik başarısız |

Ana metriklerden biri:

> Human-validated usability = Skor 2 veya 3 alan yanıtlar / Tüm değerlendirilen yanıtlar

Ek olarak eski/yeni yanıtlar **model adları gizlenerek ve sıraları karıştırılarak** karşılaştırılır: “Eski daha iyi / eşit / yeni daha iyi.”

### Örnek haftalık iş planı

| İş | Süre |
|---|---:|
| 60 farklı vakada birincil değerlendirme × 4 dk | 240 dk |
| 12 vakada ikinci bağımsız değerlendirme × 4 dk | 48 dk |
| Yaklaşık 6 anlaşmazlığın çözümü × 8 dk | 48 dk |
| Rubrik kalibrasyonu ve geri bildirim | 24 dk |
| **Toplam** | **360 dk / 6 saat** |

Bu süreler, her vakadaki eski ve yeni yanıtın birlikte incelenmesini varsayar; vaka yazımı, PII taraması ve veri hazırlığı için ayrıca kapasite gerekir.

Dört haftada 240 farklı vaka değerlendirmek **ancak dört dakika/vaka varsayımı tutuyorsa** mümkün. İlk hafta pilotta gerçek etiketleme süresini ölçer, gereken durumda vaka sayısını azaltırım. Kapsamı büyütmek uğruna etiketleme güvenilirliğini feda etmem.

### Label noise: İnsan etiketleri de hatalı olabilir

İki uzman aynı cevaba farklı skor verebilir. Sistematik ya da rastlantısal etiket hataları ise **label noise** oluşturur.

Kontrol için:

1. Vakalardan bir bölümünü **bağımsız çift etiketlerim**.
2. Yalnızca basit uyum yüzdesini değil, **Cohen’s kappa** gibi düzeltilmiş uyum ölçülerini ve güven aralıklarını raporlarım.
3. Bir sınıf çok baskınsa kappa’nın yanıltıcı olabileceğini bilerek **Gwet’s AC1** gibi alternatifleri de incelerim; bunları aynı ölçüymüş gibi yorumlamam.
4. Anlaşmazlıkları QA uzmanıyla çözüp rubrikte belirsiz kalan noktaları düzeltirim.
5. Etiketleyicilerin drift yaşayıp yaşamadığını **anchor örneklerle** takip ederim.

Örneğin yalnızca **12 vakanın çift etiketlendiği bir hafta**, kalıcı ve kesin bir insan uyum oranı çıkarmak için oldukça zayıf bir örneklemdir. Bu yüzden sonuçları haftalar arasında biriktirir, düşük sayıya uygun belirsizlik aralıkları gösteririm.

## 4. LLM-as-judge: Ölçeği büyütürken hatayı da büyütmemek

Her kod, prompt veya model değişiminde yüzlerce cevabı insanlara yeniden kontrol ettirmek gerçekçi değil. Bu yüzden **LLM-as-judge** kullanırım: Başka bir LLM, verilen politika referansı ve rubriğe göre önerilerin kalitesini değerlendirir.

Ama burada yeni bir problem doğar: **Yargıcın kendisi de önyargılı olabilir.**

- **Position bias:** A ve B cevaplarının sırası sonucu etkiler.
- **Verbosity bias:** Uzun cevap, daha doğruymuş gibi ödüllendirilebilir.
- **Style bias:** Profesyonel üslup, yanlış politika bilgisini maskeleyebilir.
- **Self-preference / model-family bias:** Yargıç bazı model ailelerinin çıktılarına eğilim gösterebilir.
- **Domain bias:** Yeni ticket kategorileri mevcut kalibrasyonun dışında kalabilir.

Bu riskler yalnızca teorik değil: Zheng ve arkadaşlarının **MT-Bench** çalışması ([NeurIPS 2023](https://papers.neurips.cc/paper_files/paper/2023/hash/91f18a1287b398d378ef22505bf41832-Abstract-Datasets_and_Benchmarks.html)) ile Ye ve arkadaşlarının **CALM** araştırması ([ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/fdca08d371e4b6c031397909e20043bd-Abstract-Conference.html)), LLM-as-judge yaklaşımındaki farklı önyargıları sistematik biçimde tartışıyor. Kaynaklar yazının sonunda.

Daha ince tehlike ise şu: **İnsanlar ve judge aynı yanlış cevabı beğenebilir.** Böylece yüksek insan–judge uyumu, otomatik olarak yüksek gerçek doğruluk anlamına gelmez.

### Judge nasıl doğrulanır?

İnsanların etiketlediği ve bağımsız tutulmuş bir doğrulama kümesinde şu testleri yaparım:

| Test | Ne gösterir? |
|---|---|
| Human–judge agreement | İnsan ve judge aynı kararı veriyor mu? |
| Kappa / AC1 + belirsizlik | Uyum ne kadar sağlam? |
| Critical failure recall | Kritik yanlışları ne sıklıkla yakalıyor? |
| False positive rate | Doğru cevapları haksız yere başarısız mı sayıyor? |
| Position swap | Cevapların yerini değiştirince karar değişiyor mu? |
| Kategori bazlı hata analizi | Judge bazı alt gruplarda sistematik hata yapıyor mu? |

Judge için sürümlenmiş prompt, model, referans politika ve yapılandırılmış çıktı tutulur. Judge prompt’unu ayarlamak için kullanılan vakaları son doğrulama kümesinden ayırırım; değerlendirme vakalarını da değerlendirilen modelin eğitim veya prompt optimizasyonuna taşımam. Aksi hâlde veri sızıntısı, ölçümü olduğundan iyi gösterebilir. İnsan–judge anlaşmazlığı yüksek olan ya da kritik hata şüphesi taşıyan vakalar insan incelemesine yönlendirilir.

**Kural:** Judge, insan etiketini ucuzlatan bir yardımcıdır; insanın ve referans politikanın yerine geçen mutlak otorite değildir. Özellikle doğruluğu kanıtlanmamış segmentlerde otomatik release kararı verdirmem.

## 5. Offline CI ve online canary birlikte nasıl çalışır?

Aynı sorunu iki farklı açıdan ölçmek gerekir.

**Offline CI:** Eski ve yeni sürümü aynı, PII içermeyen, versiyonlanmış senaryolarda çalıştırır. Politika ihlali, kullanılabilirlik regresyonu ve kritik hataları üretime çıkmadan yakalamaya çalışır.

**Online canary:** Gerçek ticket trafiğinde yeni sürümün ne kadar fayda sağladığını ölçer. Ancak bunun güvenilir olması için %5 yeni sürüm ile %95 eski sürüm **aynı dönemde ve aynı uygun trafik havuzunda rastgele atanmış** olmalıdır.

Karar akışı şöyle ilerler:

1. Onaylı politikalar ve PII içermeyen trafik istatistiklerinden, katmanlı örneklemeyle sentetik vakalar hazırlanır.
2. Uzman etiketleri ve anlaşmazlık çözümüyle sürümlenmiş golden dataset oluşturulur; judge ayrı bir doğrulama kümesiyle sınanır.
3. Offline CI’da eski ve yeni model aynı vakalarda, kalibre edilmiş judge ve güvenlik kontrolleriyle karşılaştırılır.
4. Gerçek trafik rastgele %95 control ve %5 canary olarak ayrılır; gösterim, kabul, düzenleme, süre ve hata sinyalleri toplanır.
5. Kategoriye göre normalize edilmiş online etki ile offline sonuçlar karar motoruna gider: Kritik hata veya kanıtlanmış maddi düşüşte **Rollback**, yetersiz kanıtta **Hold**, kabul edilebilir farkta **Expand**.

İki akış aynı **kalite tanımlarını** kullanır; ancak online gerçek müşteri içeriği doğrudan golden set’e kopyalanmaz. Canary’den gelen agregat istatistikler ve gizlilik kurallarına uygun uzman incelemeleri, sonraki sentetik senaryo üretimine bilgi sağlayabilir.

### Production telemetry’sinde hangi alanlar önemli?

- **Difficulty proxy:** Ticket’ın tahmini zorluğunu ifade eden dolaylı gösterge. Örneğin gerekli işlem sayısı veya geçmiş çözüm karmaşıklığı; kesin zorluk puanı değildir.
- **Agent cohort:** Deneyim seviyesi veya ekip gibi özelliklere göre oluşturulmuş temsilci grubu.
- **Model version:** Yanıtı üreten modelin sürümü; ayrıca prompt ve knowledge base sürümü.
- **Exposure:** Önerinin gerçekten agent’a gösterilip gösterilmediği. Görülmeyen öneri, otomatik olarak “ret” sayılmamalı.

Bu alanlar olmadan kabul oranı kolayca yanlış yorumlanır.

### Kategoriye göre normalize edilmiş etki

Her kategoride eski ve yeni modelin kabul oranını karşılaştırırım:

> Q_k = Q_yeni,k − Q_eski,k

Burada k ticket kategorisini, Q ise o kategorideki kabul oranını gösterir.

İki rapor sunarım:

1. **Like-for-like etki:** Sabit kategori dağılımında model değişikliğinin farkı.
2. **Güncel trafik etkisi:** Bugünkü ticket dağılımında beklenen operasyonel fark.

Yeni kategoride geçmiş dönem verisi yoksa onu önceki %61’e zorla bağlamam; mümkünse **eşzamanlı control** ile karşılaştırırım. Kontrol modelinin o kategoride geçerli bir yanıt üretme kabiliyeti yoksa bu sınırlamayı açıkça raporlarım.

## 6. Ne zaman “kalite düştü” diyeceğiz?

![Offline CI ve online canary sinyallerini Rollback, Hold veya Expand kararında birleştiren akış.](/images/rollback-hold-expand.svg)

Bence Tech Lead’e en baştan üç sonuçtan birini sunabilen bir sistem kurmalıyız: **Rollback, Hold veya Expand.**

Karar için iki katman gerekir:

**1. Güvenlik kapısı:** Doğrulanmış yeni ve ciddi bir gizlilik, güvenlik veya politika ihlali varsa rollback değerlendirilir; böyle bir riski yüksek ortalama skorla örtmeyiz.

**2. Kalite/fayda kapısı:** Önceden tanımlanmış kayıp toleransı ve istatistiksel belirsizlik üzerinden karar verilir.

Başlangıç tartışması için örneğin **−2 yüzde puanlık** kabul edilebilir kayıp sınırı seçilebilir. Ama bu evrensel bir sayı değildir: Ek retlerin temsilci emeğine maliyeti, müşteri zararı, beklenen fayda ve hata toleransıyla kalibre edilmelidir.

> ΔQ = Q_yeni − Q_eski

Burada ΔQ, değerlendirilen metriğin farkıdır: Offline için kullanılabilirlik, online için ortak trafik ağırlıklarıyla hesaplanan kabul oranı. Her metrik için tolerans ayrı belirlenir; pp, yüzde puanı ifade eder.

%95 güven aralığı kullanıldığında, önceden tanımlı doğru deney ve analiz varsayımları altında:

| Durum | Örnek karar kuralı |
|---|---|
| **Rollback — maddi regresyon kanıtı** | Kritik yeni hata veya ilgili farkın güven aralığı **üst sınırı < −2 pp** |
| **Hold — belirsizlik** | Güven aralığı −2 pp sınırını kesiyor; ya da örneklem/ölçüm yetersiz |
| **Expand — kayıp toleransı karşılandı** | Güven aralığı **alt sınırı > −2 pp**, güvenlik ve operasyonel guardrail’ler de uygun |

Bu kurallar, hem insan doğrulamalı offline kaliteye hem de online fayda metriğine kendi bağlamında uygulanır. Metriklerin birini diğerine ortalatıp başarısızlığı gizlemem.

Önemli bir nüans: **İstatistiksel olarak anlamlı düşüş** ile **iş açısından maddi düşüş** aynı kavram değil. “−2 pp” gibi sınır, hangi büyüklükteki zararı kabul edemediğimizi belirtir. Ayrıca bu tür güven aralığı kararları için analiz zamanı, örnekleme planı ve tekrarlı kontrol politikası önceden belirlenmelidir.

### %5 canary yeterli veri üretiyor mu?

Kabul oranı yaklaşık %60 iken; bağımsız gözlemler, iki oran testi, iki taraflı %5 anlamlılık, %80 güç ve 19:1 control/treatment oranı varsayımı altında **3 yüzde puanlık** farkı yakalamak için kabaca **2.200 treatment gözlemi** gerekebilir. %5 canary payında bu yaklaşık **44.000 uygun ticket** demektir.

**2 yüzde puanlık** fark için kabaca **5.000 treatment gözlemi** ve dolayısıyla **100.000 uygun ticket** gerekebilir.

Bu yuvarlatılmış değerler, `n_treatment ≈ (1,96 + 0,84)² × 0,60 × 0,40 × (1 + 1/19) / δ²` normal yaklaşımıyla hesaplanır; δ, yakalanmak istenen mutlak oran farkıdır. Bu, sıfır farkına karşı fark tespiti hesabıdır; −2 pp sınırına göre non-inferiority göstermek için ayrıca güç hesabı gerekir.

Bunlar yalnızca yaklaşık planlama sayılarıdır: Agent kümelenmesi, trafik dalgalanması, farklı metrik tanımları ve sequential testler örnek ihtiyacını değiştirir. Düşük trafikte birkaç günde kesin karar beklemek gerçekçi değildir.

Bu yüzden **“Henüz yeterli kanıt yok”**, kötü bir mühendislik cevabı değil; doğru tasarlanmış bir değerlendirme sisteminin gerekli çıktılarından biridir.

## 7. Bu tasarımın asıl trade-off’ları

| Tasarım seçimi | Kazancı | Bedeli |
|---|---|---|
| **Sentetik golden set** | PII koruması; tekrar üretilebilir testler | Gerçek dünyadaki ifade çeşitliliği eksik kalabilir |
| **Stratified/risk-weighted örnekleme** | Nadir, kritik hataları daha iyi kapsar | Ham sonuç üretim trafiğine doğrudan genellenemez |
| **Çift insan etiketi** | Label noise ve rubrik belirsizliğini görünür kılar | Aynı bütçeyle daha az yeni vaka etiketlenir |
| **LLM-as-judge** | CI değerlendirmesini ölçeklendirir | Kalibrasyon dışı bias ve yanlış güven oluşabilir |
| **%5 randomize canary** | Sınırlı müşteri riskiyle canlı ölçüm | Küçük etkiler için uzun gözlem gerekebilir |
| **Katı release gate** | Zararlı regresyonları engeller | Yanlış alarm ve gecikme maliyeti doğurabilir |

Sistemin başarılı olması, her zaman daha fazla veri veya daha karmaşık model kullanmasına bağlı değil. **Sınırlı kaynakla belirsizliği en dürüst şekilde yönetmesine** bağlı.

## 8. Tasarımın bütünü

![Golden dataset ve insan etiketlerinden offline CI, randomize canary ve sürüm karar motoruna uzanan sistem mimarisi.](/images/system-design-golden-set.png)

## 9. Bugün Tech Lead’e ne söylerdim?

Şunu:

> “Kabul oranı %61’den %58’e gerilemiş; fakat aynı dönemde ticket karışımı değişti. Bu nedenle henüz ‘model kalitesi düştü’ diyemeyiz. Yeni ve eski sürümü eşzamanlı, karşılaştırılabilir trafikte; ayrıca insan doğrulamalı golden set üzerinde ölçmemiz gerekiyor. Kritik regresyon bulunmadığı ve istatistiksel kanıt oluşmadığı sürece genişletmeyi durdurur, canary’yi güvenlik açısından izleyerek %5’te tutarız.”

Bu cevap gösterişli olmayabilir; ama production sorumluluğuna daha yakışır. Çünkü ortalama bir skorun arkasına saklanmaz, bilmediği şeyi biliyormuş gibi sunmaz ve **hangi kanıtın kararı değiştireceğini önceden tanımlar**.

Sonuçta iyi bir LLM eval sistemi yalnızca “Bu model kaç puan aldı?” sorusunu cevaplamaz. Daha zor bir soruyla yüzleşir:

**“Bu modele üretimde daha fazla sorumluluk vermek için gerçekten yeterli kanıtımız var mı?”**

## 10. Bu işi yapan başka biri var mı?

- [Langfuse](https://langfuse.com/docs/evaluation/overview): Dataset yönetimi, insan değerlendirmesi ve offline/online evaluation için.
- [Phoenix](https://github.com/arize-ai/phoenix): Model davranışlarını izleme, tracing ve deney karşılaştırma için.
- [Evidently](https://github.com/evidentlyai/evidently): Veri dağılımı değişiklikleri ve model performansının izlenmesi için.

Bu tasarımı bir düşünce deneyi olarak yazdım; ancak bir ürüne dönüşebilir. Belki ileride…

---

## Kavram sözlüğü

| Terim | Kısa açıklama |
|---|---|
| **Golden dataset** | Beklenen doğru davranışı uzman tarafından tanımlanmış değerlendirme vakaları |
| **Crowdsourcing** | İşin çok sayıda bağımsız katılımcıya dağıtılması |
| **Stratified sampling** | Örneklerin önceden belirlenmiş alt gruplardan seçilmesi |
| **Label noise** | Etiketlerdeki yanlışlık veya tutarsızlık |
| **Inter-annotator agreement** | Farklı etiketleyicilerin kararları arasındaki uyum |
| **LLM-as-judge** | LLM çıktılarının başka bir LLM tarafından değerlendirilmesi |
| **Difficulty proxy** | Ticket zorluğu için kullanılan dolaylı ölçü |
| **Agent cohort** | Ortak özelliğe sahip müşteri temsilcisi grubu |
| **Exposure** | Bir önerinin temsilciye gerçekten gösterilmesi |
| **Offline CI eval** | Canlıya çıkmadan önce sabit test kümesinde otomatik değerlendirme |
| **Traffic-mix adjustment** | Farklı kategori dağılımlarının etkisini normalize etme |
| **Non-inferiority** | Yeni sürümün belirlenen toleransın ötesinde kötü olmadığını test etme |
| **Rollback / Hold / Expand** | Eskiye dön / beklet / kontrollü genişlet kararları |

## İleri okuma

1. **Zheng ve diğerleri (NeurIPS 2023)** — [Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena](https://papers.neurips.cc/paper_files/paper/2023/hash/91f18a1287b398d378ef22505bf41832-Abstract-Datasets_and_Benchmarks.html). LLM yargıçlarında konum, uzunluk ve benzeri önyargılar.
2. **Ye ve diğerleri (ICLR 2025)** — [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://proceedings.iclr.cc/paper_files/paper/2025/hash/fdca08d371e4b6c031397909e20043bd-Abstract-Conference.html). CALM yaklaşımıyla LLM-as-judge önyargılarının analizi.
3. **Klie ve diğerleri (ACL 2024)** — [On Efficient and Statistical Quality Estimation for Data Annotation](https://aclanthology.org/2024.acl-long.837/). Küçük etiket kontrol örneklerinde istatistiksel belirsizlik ve maliyet.
4. **Gwet (2008)** — [Computing inter-rater reliability and its variance in the presence of high agreement](https://pubmed.ncbi.nlm.nih.gov/18482474/). Gwet’s AC1 ve etiketleyiciler arası güvenilirlik.
5. **Zec ve diğerleri (2017)** — [High Agreement and High Prevalence: The Paradox of Cohen’s Kappa](https://pmc.ncbi.nlm.nih.gov/articles/PMC5712640/). Cohen’s kappa’nın bazı sınıf dağılımlarında neden dikkatli yorumlanması gerektiği.

*Not: Bu yazı bir sistem tasarımı ve araştırma önerisidir. Golden set büyüklüğü, etiketleme hızı, kabul edilebilir kalite kaybı ve örneklem sayıları örnek mühendislik varsayımlarıdır; gerçek sonuç gibi sunulmamalıdır.*
