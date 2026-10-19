---
title: "LLM’i Sisteme Aldık, Tapuyu Vermedik: Contract Testing"
date: "2026-10-19T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/ai-native-swe/ai-llm-contract-testing/"
series: "ai-native-swe"
description: "LLM yanıtlarını sözleşme testleriyle uygulama sınırında denetlemek: TypeScript demosunda şema doğrulama, timeout, retry, PII kontrolü ve circuit breaker."
summary: "AI Native SWE serisinin ilk yazısında, müşteri destek sistemine LLM yanıt önerisi ekleyen küçük bir TypeScript deneyini inceliyorum. Yerel mock servisle bozuk JSON, timeout, kişisel veri ve sağlayıcı hatalarını sınıyoruz. Sözleşme kontrollerinin neyi koruduğunu ve üretim kullanımı için hangi parçaların eksik olduğunu ayırıyoruz."
tags: ["AI Native SWE", "AI", "LLM", "Contract Testing", "Software Architecture", "AI Reliability", "Circuit Breaker", "Data Privacy", "Resilience"]
image: "/images/ai-native-swe-contract-testing.png"
imageAlt: "Düzensiz LLM çıktılarının doğrulama kapısından geçerek uygulamaya ulaştığı, hatalı parçaların ayrıldığı AI Native SWE Contract Testing kapağı."
toc: true
summaryForLLM: true
mathjax: false
---

Bir ara bir meslektaşımla “LLM sonrası yazılımcılar ne yapacak?” diye konuşuyorduk. Benim cevap pek vizyoner değildi: “Her zaman yaptığımız şeyi.”

Yine servis bağlayacağız, gelen veriye şüpheyle bakacağız, timeout koyacağız. Sonra o timeout'un neden çalışmadığını araştıracağız. Sadece bu sefer bağladığımız servis, yanlış cevap verirken bizden daha düzgün cümle kurabiliyor.

Ben de bu aralar kendime birtakım Zihni Sinir projeleri çıkarıyorum. Dönüşüme ayak uydurmak için, AI Native Software Engineer, AI Agent Architect, AI Reliability Engineer, Multi Agent Systems Engineer, Human AI Workflow Architect, AI Forward Engineer olmaya falan çalışıyorum... Unvanları arka arkaya yazınca bir insanın kariyer planından çok, altı kişilik departmanın işe alım ilanına benziyor. Hepsini LinkedIn başlığına sığdırmaya çalışmadan önce, bunların gerektirdiği işleri biraz yapayım dedim.

**AI Native SWE** serisinde küçük projeler kurup kurcalayacağım. Model nerede işe yarıyor, agent'a ne kadar yetki verilir, birden fazla agent birbirini onaylayınca gerçekten bir şey çözülmüş oluyor mu, insan hangi aşamada devreye girmeli? Bunları kod üzerinden düşünmek istiyorum. Bu bölümde henüz agent ordusu kurmuyoruz. Bir dış servisi düzgün bağlayarak başlayalım; ekip kalabalıklaşınca sorunlar zaten kendi gelir.

Senaryomuz bir müşteri destek sistemi. Temsilci bir talebi açıyor, sistem kategoriye göre hazır yanıt çıkarıyor. Buna bir de LLM destekli yanıt önerisi ekleyelim. Temsilci taslağa baksın, gerekirse düzenlesin, müşteriye kendisi göndersin.

“API'ye istek atıp cevabı ekrana basarız” kısmı kısa. Bu repo, cümlenin sonrasıyla ilgileniyor: Cevap bozuksa, geç gelirse, kişisel veri içerirse veya servis bütün gün 500 dönerse ne yapacağız?

Baştan netleştireyim: Burada gerçek bir LLM sağlayıcısı yok; yerel bir mock HTTP servisi var. Bu yazı production ortamında başarıyla devreye aldığım bir sistemin hikâyesi değil, entegrasyon sınırlarını denediğim küçük bir çalışma. Henüz token ücreti ödemeden kendi hatalarımı bulabiliyorum. Gayet ekonomik.

## Hazır yanıtın bir suçu yok

Mevcut akışta `refund`, `shipping` veya `general` kategorisine göre deterministik bir yanıt üretiyoruz. Aynı kategori, aynı şablon. Edebi değeri tartışılır ama ne yapacağı belli.

LLM önerisi bunun üzerine geliyor. Kullanılabilir bir öneri gelirse onu alıyoruz; gelmezse hazır yanıt elimizde duruyor. Temsilcinin müşteriye vereceği son yanıt yine insanın kararı.

Hedeflediğim ekran davranışı şu: Temsilci hazır yanıtı hemen görsün, modelin önerisi sonradan ve kontrollerden geçerek gelsin. “Yapay zeka düşünüyor” diye çalışan ekranı bekleme salonuna çevirmeyelim.

**Demo bu ekran davranışının tamamını uygulamıyor.** CLI, önce fallback'i hesaplıyor, ardından LLM denemesini çalıştırıyor; satırları senaryo tamamlanınca yazdırıyor. Postman için kullanılan HTTP endpoint'i de fallback'i önce üretmesine rağmen `suggest()` sonucunu bekleyip tek response dönüyor. Gerçek arayüzde anında fallback göstermek için ayrı bir çağrı, polling veya streaming gibi bir teslim akışı kurmak gerekir.

Bu ayrım önemli. “Önce hesapladım” ile “kullanıcıya önce gösterdim” aynı şey değil. Backend'in kendi içinde hızlı olması, kullanıcıya henüz haber verilmediyse biraz aile içinde övünmek oluyor.

## “JSON dön lütfen” sözleşme sayılmıyor

Prompt'a “sadece JSON dön” yazabiliriz. Hatta rica dozunu artırabiliriz. Yine de uygulamanın sınırında gelen veriyi parse edip kontrol etmek gerekiyor.

`src/contract.ts` içindeki sözleşmenin kabul ettiği örnek bir yanıt şöyle:

```json
{
  "contract_version": 1,
  "suggestion_id": "123e4567-e89b-42d3-a456-426614174000",
  "status": "suggestion",
  "reply": {
    "subject": "İade talebiniz hakkında",
    "body": "Merhaba, iade talebinizi aldık. İnceleme sonrası bilgi vereceğiz."
  },
  "confidence": 0.72,
  "metadata": {
    "model": "mock-gpt-1",
    "generated_at": "2026-10-19T09:30:00.000Z",
    "latency_ms": 42
  }
}
```

Başlık 1–200, gövde 1–4000 karakter. `confidence`, 0 ile 1 arasında sayı veya `null`. `suggestion_id` UUID, tarih alanı da şemanın beklediği ISO tarih formatında olmalı.

Buradaki `0.72`, cevabın yüzde 72 ihtimalle doğru olduğuna dair elimizde bir kanıt olduğu anlamına gelmiyor. Demo bu değerin kalibrasyonunu ölçmüyor, kabul kararını da buna göre vermiyor. Sayı ondalıklı diye bilimsel ciddiyete kapılmayalım.

Bir de `status: "unavailable"` var. Bu durumda `reply: null` olmalı. Sağlayıcının “öneri yok” diyebilmesi geçerli bir sonuç. Bunu bozuk JSON ile aynı sepete atmıyoruz; sözleşme ihlali oranının paydasına da katmıyoruz. Elbette mock'un bu cevabı verebilmesi, gerçek bir modelin ne zaman susması gerektiğini bildiğini kanıtlamıyor.

Üst seviye nesnede Zod `.strict()` kullanıyorum. Sağlayıcı fazladan `sentiment` alanı gönderirse reddediliyor. Bunun bedeli, zararsız bir alan eklemesinin de entegrasyonu bozabilmesi. Bu örnekte sürüm değişimini açıkça yönetmeyi tercih ettim. Ayrıca `.strict()` burada yalnızca üst seviyede; iç nesneler için aynı katılığı tanımlamış değilim.

## Dış servisin DTO'su içeride ev sahibi olmasın

Veri içeri şu yoldan giriyor:

```text
Ham HTTP gövdesi
  → JSON.parse          → parse_error
  → contract_version    → version_mismatch
  → Zod şeması          → schema_violation
  → toDomain()          → Suggestion veya null
```

`parseContract()` ham metni alıyor, ya doğrulanmış payload ya da sınıflandırılmış bir ihlal döndürüyor. Ardından `toDomain()` dış servisin alanlarını bizim modelimize çeviriyor:

```ts
export type Suggestion = {
  suggestionId: string;
  subject: string;
  body: string;
  confidence: number | null;
};
```

`src/domain.ts`, Zod'u veya sağlayıcının DTO'sunu bilmiyor. `suggestion_id` dışarıda kalıyor, içeride `suggestionId` ile çalışıyoruz. Bu sınırın adı anti-corruption layer. İsmi biraz belediye soruşturması gibi ama yaptığı iş gayet sade: Dış servisin tercihleri bütün uygulamaya yayılmasın.

Servis katmanı da çağırana ya öneri ya da `timeout`, `contract_violation`, `pii_detected` gibi bir sebep dönüyor. Her çağıran yeniden JSON yorumlamıyor.

## Modelin düşünme süresi benim mesaimden gitmesin

`src/config.ts` içinde iki bütçe var:

```ts
export const BUDGETS = { TOTAL_MS: 3000, LLM_CALL_MS: 2200 } as const;
```

3000 ms, servis akışında denemeler için takip ettiğimiz toplam bütçe. 2200 ms ise tek HTTP denemesinin varsayılan tavanı. `src/llmClient.ts`, `AbortController` ile isteği bu sürede iptal ediyor. Gerçek kesilme zamanı event loop'un çalışmasına da bağlı; JavaScript'e kronometre bağlayınca gerçek zamanlı işletim sistemine terfi etmiyoruz.

İlk deneme 5xx ile biterse ve toplam bütçeden süre kalmışsa bir kez daha deneyebiliyoruz. İkinci denemenin tavanı, 2200 ms ile kalan bütçenin küçüğü. Dolayısıyla 2200 ms bütün retry zincirinin ortak tavanı değil. Parse ve PII taraması da sonrasında çalışıyor; burada uçtan uca tarayıcı çizim süresini ölçen bir mekanizma yok.

Retry kararları da şöyle:

| Sonuç | Retry | Neden? |
|---|---|---|
| HTTP 5xx | En fazla 1, süre kaldıysa | Geçici bir sunucu hatası olabilir. |
| Timeout | Yok | Bu öneri için daha fazla beklemiyoruz. |
| Bozuk JSON / şema / sürüm | Yok | Bu denemede sözleşme dışı veri geldi. |
| Çıktıda PII | Yok | Öneriyi reddedip fallback'e dönüyoruz. |
| `unavailable` | Yok | Sağlayıcı geçerli biçimde öneri vermedi. |
| HTTP 4xx / ağ hatası | Yok | Bu örneğin politikası burada durmak. |

Bozuk JSON için retry yapmamak, modelin ikinci sefer de kesin aynı hatayı yapacağı anlamına gelmiyor. Yalnızca bu özellikte süreyi ve çağrı sayısını sınırlamayı seçiyorum. “Bir daha dene” yazması kolay; o sırada bekleyen insanı ikna etmek biraz daha zor.

## Telefon numarasını prompt'a koyunca teknik borç sayılmıyor

Modele yalnızca talebin konusu, gövdesi ve kategorisi gönderiliyor. Konu ve gövde önce `maskPii()` içinden geçiyor. Tanınan telefon, e-posta ve 11 haneli kimlik numarası örüntüleri `[masked-phone]`, `[masked-email]`, `[masked-national_id]` etiketlerine çevriliyor.

Dönen önerinin de **hem başlığı hem gövdesi** `detectPii()` ile taranıyor. Eşleşme varsa öneri `pii_detected` sebebiyle reddediliyor. Girişte maskeledik diye çıkışta gözümüzü kapatmıyoruz.

Ama bu katman regex kullanıyor. İsim, adres, yazıyla yazılmış telefon numarası, farklı ülke formatları gibi pek çok şey kapsam dışında kalabilir. Bir eşleşme de verinin başka müşteriden geldiğini kanıtlamaz. Bu örnek yalnızca belirli örüntüleri bulup reddediyor; regex'e hukuk müşavirliği ve veri kökeni analizi de yaptırmayalım.

Öneriler için kalıcı veritabanı yok, sayaçlar ve breaker bellekte. Bu tercihler tek başına KVKK/GDPR uyumu iddiası taşımıyor. Gerçek entegrasyonda sağlayıcının veriyi nerede işlediği, ne tuttuğu ve erişimlerin nasıl yönetildiği ayrıca ele alınmalı.

Log konusunda da demoyu olduğundan temiz anlatmayayım: Servisin metrikleri içerik yerine sonuç kodlarıyla çalışıyor, fakat CLI kabul edilen mock önerinin başlığını yazdırıyor. HTTP demo yanıtı da test kolaylığı için ticket ve öneri içeriklerini gösteriyor. Gerçek müşteri verisiyle çalışacak bir ürüne bunları aynen taşımamak gerekir.

## Gerektiğinde kapatacağımız bir düğme de olsun

Her başarısız isteği tek başına yönetmek yetmiyor. Sağlayıcı sürekli bozuk cevap dönüyorsa aynı kapıyı çalmayı bırakabilmeliyiz.

`src/metrics.ts` içinde son 20 kayıtlı sonucu tutan bir pencere ve circuit breaker var. `unavailable`, ihlal hesabının dışında; timeout ve PII oranlarında toplam kayıt sayısı kullanılıyor.

| Ölçüm | Eşik |
|---|---|
| Sözleşme ihlali oranı | %10'dan büyük |
| Timeout oranı | %50'den büyük |
| PII tespit oranı | %10'dan büyük |
| Kabul edilen çağrıların breaker içindeki p99'u | 2200 ms üstünde, iki ayrı yüksek p99 değeriyle ilerleyen takip |

Son satır biraz dolambaçlı, çünkü kodun davranışı da “her iki yavaş çağrıda aç” kadar basit değil. Breaker, yüksek p99 değeri değişince sayacı ilerletiyor. Timeout'lar gecikme örneği olarak eklenmiyor. Bu küçük pencerede p99 da pratikte en yüksek gecikme örneğine denk geliyor. Dashboard'a p99 yazınca elimizde birden geniş ölçekli performans araştırması olmuyor.

Devre açılınca 60 saniye yeni LLM çağrısı yapılmıyor. Sonra `half_open` durumunda bir deneme hakkı var. Kabul edilen öneri devreyi kapatıyor; bu denemede timeout, sözleşme ihlali veya PII görülürse devre yeniden açılıyor. İstenirse `flagEnabled = false` ile de ağ çağrısını baştan kesebiliyoruz.

Bu eşikler deney için seçilmiş değerler. Minimum örnek sayısı kontrolü yok; ilk çağrı ihlalse oran yüzde 100, devre açılabilir. Ayrıca `provider_error` sonuçları bu metrik pencerelerine kaydedilmiyor; half-open denemesi `provider_error` veya `unavailable` ile biterse toparlanma akışı da eksik kalıyor. Gerçek kullanıma taşımadan önce buraları tamamlamak gerekir. Sigortayı taktık diye elektrik tesisatının tamamına kefil olmayalım.

## Contract testing'de neyi test ediyoruz?

Burada “modelin cevabı güzel mi?” sorusunu test etmiyorum. Sağlayıcının sınırda farklı davranışlar göstermesi durumunda **bizim uygulamamızın ne yaptığını** test ediyorum.

`src/provider.ts`, yerel HTTP sunucusunda 10 mod sunuyor:

| Mod | Deney |
|---|---|
| `valid` | Geçerli fixture kabul ediliyor mu? |
| `unavailable` | Öneri olmaması geçerli sonuç olarak ele alınıyor mu? |
| `malformed_json` | JSON olmayan metin reddediliyor mu? |
| `wrong_type` | `confidence: "high"` şemadan geçiyor mu? Geçmemeli. |
| `unknown_field` | Fazladan üst seviye alan reddediliyor mu? |
| `version_2` | Desteklenmeyen sürüm kapıda durduruluyor mu? |
| `pii_body` | Telefon içeren öneri reddediliyor mu? |
| `slow` | 2600 ms bekleyen sağlayıcıya karşı timeout çalışıyor mu? |
| `flaky_500` | İlk 500 sonrası izin verilen tek retry işe yarıyor mu? |
| `always_500` | Sürekli 500 dönen servis karşısında denemeyi bırakıyor muyuz? |

Bu, gerçek sağlayıcıyla karşılıklı sözleşme doğrulaması yapan bir test düzeni değil; tüketici tarafında, kontrol edebildiğimiz mock yanıtlarla sınırı zorluyoruz. Sağlayıcının gerçekte bu sözleşmeye uyduğunu ayrıca doğrulamak gerekir.

Daha önemlisi, şemadan geçen cevap doğru cevap demek değil. Müşteri iade istiyor, model düzgün JSON içinde kargo tavsiyesi veriyor olabilir. Contract testi bunu yakalamaz. Gerçek modelle ayrıca içerik değerlendirmesi, görev doğruluğu, prompt injection denemeleri ve insan incelemesi gerekir. JSON'un süslü parantezleri yerinde diye müşteri sorununu çözmüş sayılmıyoruz.

## Dün dün, bugün bugün; ticket da değişiyor

Bir de zaman aşımından farklı bir sorun var. Model talebin birinci sürümü için çalışırken müşteri yeni mesaj yazabilir. Cevap zamanında gelir ama artık eski soruya aittir.

Bu repoda ticket versiyonu ve `bumpVersion()` var. Deterministik önerinin ID'si de `${ticket.id}-d${ticket.version}` biçiminde. **LLM önerisi ise sağlayıcının UUID'sini taşıyor; bu ID bir tazelik kontrolü sağlamıyor.** İstek sürümüyle güncel ticket sürümünü karşılaştırıp eski LLM önerisini reddeden bir akış henüz yok.

Üründe, çağrı başladığında ticket ID'sini ve sürümünü tutup öneri uygulanacağı anda tekrar karşılaştırmak gerekir. Bu yarışı otomatik testle de kanıtlamak isterim. Müşteri “sorunu çözdüm” dedikten sonra “cihazı kapatıp açmayı denediniz mi?” önerisini yetiştirmek için 2200 ms uğraşmış olmayalım.

## Local'de biraz bozalım

Node.js 20 veya üstüyle:

```bash
npm install
npm test
npm run typecheck
npm run demo
```

CLI demosu altı senaryoyu çalıştırıyor: `valid`, `unavailable`, `malformed_json`, `pii_body`, `slow`, `flaky_500`. Bütün modları HTTP üzerinden denemek için:

```bash
npm run server
```

Ardından `postman_collection.json` dosyasını Postman'e import edebilirsiniz. Örneğin `POST http://127.0.0.1:3000/api/suggest` adresine:

```json
{
  "ticketId": "t-refund",
  "mode": "malformed_json"
}
```

gönderince `llmResult.reason` alanında `contract_violation`, `finalDisplayedSuggestion` alanında fallback görürsünüz. Demo endpoint'i bu alanı böyle adlandırıyor; ortada henüz öneriyi gösteren bir frontend yok.

HTTP demosunda breaker istekler arasında ortak. Bir senaryoda devreyi açıp sonra başka modu denediğinizde `circuit_open` alabilirsiniz. Yeni senaryo için `POST /api/breaker/reset` ile sıfırlayabilirsiniz. CLI'da ise her senaryo kendi temiz breaker'ıyla başlıyor. İkinci istekte “valid de bozukmuş” diye mock servise haksızlık etmeyelim.

## Bunu gerçek sisteme nasıl yaklaştırırım?

Önce gerçek sağlayıcı adaptörü, tazelik kontrolü ve fallback'i gerçekten erken teslim eden arayüz akışı gerekir. Çok instance varsa bellekteki metriklerin ve breaker kararlarının nerede yerel, nerede ortak olacağını da kararlaştırmak lazım. Şimdilik her process kendi dünyasında yaşıyor.

Sonra öneriyi temsilciye göstermeden çağrı yapıp sonuçları ölçtüğümüz bir shadow aşaması düşünebilirim. Bu da bedelsiz veya risksiz değil: Sağlayıcıya veri gönderiliyor, çağrı maliyeti oluşuyor. Sonrasında küçük bir gönüllü temsilci grubu ve ölçümlerle kademeli açılış. Bunlar bu repoda uygulanmış rollout özellikleri değil, devamında yapacağım işler.

Bu bölümde çalıştığım kas, AI Reliability Engineer tarafına daha yakın: bozuk cevabı tanımak, beklemeyi sınırlamak, gerektiğinde özelliği kapatmak. Temsilcinin taslağı kontrol edip göndermesi de Human AI Workflow Architect tarafına açılan kapı. Agent'lara araç ve yetki vermeye geçtiğimde aynı sözleşme işini bu kez aksiyonlar için düşünmem gerekecek. Birden fazla agent ekleyince de aralarındaki mesajlar için. Şimdilik bir HTTP servisine sınır çizmeyi deniyoruz.

Meslektaşıma verdiğim cevaba dönersek: Evet, hâlâ her zamanki işi yapıyoruz. Dışarıdan gelen veriyi kontrol ediyor, servisin ne zaman vazgeçeceğine karar veriyor, kullanıcıya çalışır bir yol bırakıyoruz.

Bu sefer servis, hatalı yanıtın başına “Elbette, memnuniyetle yardımcı olayım” yazabiliyor. Biz yine teste bakalım.

## Kaynak kod ve başvuru

- [Demo deposu ve çalıştırma adımları](https://github.com/onurozkir/ai-llm-contract-testing)
- [Sözleşme şeması ve domain dönüşümü](https://github.com/onurozkir/ai-llm-contract-testing/blob/main/src/contract.ts)
- [Timeout, retry ve PII kontrol akışı](https://github.com/onurozkir/ai-llm-contract-testing/blob/main/src/suggestionService.ts)
- [Metrikler ve circuit breaker](https://github.com/onurozkir/ai-llm-contract-testing/blob/main/src/metrics.ts)
