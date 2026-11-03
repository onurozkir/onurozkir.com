---
title: 'When All AI Agents Agree on an Error, Who Verifies the Truth?'
date: "2026-11-04T00:00:00+03:00"
draft: false
author: "Onur Özkır"
url: "/ai-native-swe/when-all-ai-agents-agree-on-an-error/"
series: "ai-native-swe"
translationKey: "when-all-ai-agents-agree-on-an-error"
description: "AI agent'larla geliştirilen yazılımlarda testler yeşilken iş kuralları nasıl yanlış olabilir? TDD, test oracle, context isolation ve bağımsız doğrulama üzerine bir system design incelemesi."
summary: "Multi-agent TDD süreçlerinde bütün agentlar aynı yanlış iş kuralını doğrulayabilir. Bu yazıda test duyarlılığı, oracle doğruluğu ve doğrulama bağımsızlığı kavramlarını ayırıyor; iki hatlı bağımsız doğrulama mimarisi ile Independent Oracle Gateway demo sonuçlarını inceliyorum."
tags: ["AI Native SWE", "AI", "LLM", "TDD", "AI Verification", "AI Software Quality", "Multi-Agent Systems", "Oracle"]
image: "/images/oracle-verification.png"
imageAlt: "When All AI Agents Agree on an Error, Who Verifies the Truth?"
toc: true
summaryForLLM: true
mathjax: false
---
*Bütün AI agent'lar aynı hatada uzlaşırsa doğruyu kim doğrular?*

> Demo: https://github.com/onurozkir/oracle-gateway

> Bir B2B SaaS şirketinde yazılım geliştirme sürecini tamamen AI agent'larla otomatikleştirdiniz. Planner, Product Owner, Developer, Tester, QA ve DevOps rollerinden oluşan agent workflow'unuz var.
Sistem TDD (Test-Driven Development) yaklaşımıyla çalışıyor. Planner görevleri tanımlıyor, Tester önce testleri yazıyor, Developer implementasyonu gerçekleştiriyor, QA doğruluyor ve DevOps production'a çıkarıyor.
Her şey mükemmel görünüyor: Unit testler başarılı, code coverage %98, CI/CD pipeline yeşil. İnsan müdahalesi minimum seviyede.
Ancak production'a çıktıktan iki hafta sonra kritik bir iş kuralının yanlış uygulandığını fark ediyorsunuz. İncelediğinizde testlerin de aynı yanlış iş kuralını doğruladığını görüyorsunuz.
Daha önemlisi, bütün agent'lar aynı temel LLM'i kullanıyor ve birbirlerinin ürettiği çıktılardan besleniyor. Planner'ın doğru yorumladığı gereksinim, Tester tarafından yanlış anlaşılıyor ve beklenen davranışa, Developer tarafından çalışan koda, QA tarafından da başarı kriterine dönüştürülmüş.
Yani :
> - A modeli ile beslenen Planner isteği belirler:  "100 TL üzerindeki siparişlere %10 indirim uygulanacak."
> - A modeli ile beslenen Tester bunu yanlış yorumlayıp "100 TL ve üzerindeki indirimlere %10 indirim uygulanacak" düşünür ve TDD testi yazar:
> - A Modeli kod yazar.
> - A Reviewer modeli kodu ve testi karşılaştırır doğru der.
> 
> Soru:
> Bu sistemde tüm testlerin başarılı olması gerçekten yazılımın doğru çalıştığını mı kanıtlıyor, yoksa agent'ların aynı hatalı varsayım üzerinde tutarlı biçimde uzlaştığını mı?
> 
> Peki gerçekten doğru yazılım mı ürettik? Yoksa aynı modelin yanlış anladığı bir gereksinimi, yine aynı modele defalarca doğrulatıp **tutarlı bir hata** mı ürettik?
> 1. Testler kod değişikliklerine gerçekten duyarlı mı?
> 2. Testler doğru iş gereksinimini mi temsil ediyor?
> 3. Birbirini onaylayan agent'lar gerçekten bağımsız bir doğrulama mekanizması mı oluşturuyor?
 
> **Temel tez:** *Multi-agent olmak, bağımsız doğrulama yapmak anlamına gelmez.*

---

## System Design Interview: Production'da her şey yeşil, ama sonuç yanlış

Sisteminiz TDD (Test-Driven Development) yaklaşımını izliyor: Planner görevi tanımlıyor, Tester önce testleri yazıyor, Developer kodu geliştiriyor, QA doğruluyor ve DevOps production'a çıkarıyor.

İki hafta sonra kritik bir iş kuralının yanlış uygulandığı fark ediliyor. İnceleme sırasında daha çarpıcı bir şey ortaya çıkıyor: **Testler de aynı yanlış iş kuralını doğruluyor.**

Örneği basitleştirelim.

**Orijinal gereksinim:**

> 100 TL üzerindeki siparişlere %10 indirim uygulanacaktır.

Türkçedeki “üzerindeki” ifadesi burada *100 TL hariç* anlamına geliyor. Beklenen koşul `amount > 100`.

Ancak Tester agent bunu “100 TL ve üzerindeki” olarak yorumluyor. Developer da aynı sınırı uyguluyor. Gateway demosundaki hatalı aday tam bu beklentiyi kuruş cinsinden test ediyor.

```js
assert.equal(calculateTotal(10000), 9000);
```

Hatalı implementasyon `>= 10000` kullandığı için bu test geçiyor. QA da kodla testin aynı sonucu beklediğini görüyor. Test yeşil. Review olumlu. Pipeline başarılı. [Demo adayı ve testleri](https://github.com/onurozkir/oracle-gateway/blob/main/tests/fixture.ts)

Ama iş kuralı ihlal ediliyor.

| Sipariş tutarı | Gerçekte beklenen | Hatalı implementasyon |
|---:|---:|---:|
| 99 TL | 99 TL | 99 TL |
| **100 TL** | **100 TL** | **90 TL** |
| 101 TL | 90,90 TL | 90,90 TL |

Bu küçük sınır hatası, gerçek bir fiyatlandırma sisteminde binlerce siparişi etkileyebilir.

Dikkat edelim: Buradaki problem, testlerin hiç yazılmamış veya çalıştırılmamış olması değil. **Test edilen beklentinin yanlış olması.**

> **The problem is not that our tests failed. The problem is that our tests successfully verified the wrong behavior.**

Üstelik örnek, sorunu sadece `>=` ve `>` operatörlerine indirgemek için seçildi. Gerçek sistemlerde aynı hata; indirimlerin hangi ücret kalemlerine uygulandığı, rol bazlı yetkilendirme, tenant izolasyonu, iade koşulları veya veri saklama kuralları gibi çok daha zor yorumlanan gereksinimlerde ortaya çıkabilir.

Demo, parasal değerleri kuruş cinsinden tam sayı olarak taşır. Yüzde hesabını `BigInt` ile yapar ve sonucu en yakın kuruşa yuvarlar. Tam 100 TL vakasında asıl fark, yuvarlama başlamadan önce hangi dalın seçildiğidir.

## Sorunun adı: İç tutarlılık, doğruluk değildir

Bu tür bir hata üç kavramla ilişkilidir.

**Common-mode failure:** Birden fazla bileşen ortak bir hata kaynağından etkilenir. Tester'ın yanlış yorumu, Developer'ın implementasyonuna ve QA'nın değerlendirmesine taşınır.

**Correlated errors:** Agent'ların hataları birbirinden bağımsız değildir. Aynı temel model, aynı konuşma geçmişi veya aynı ara çıktılar hata korelasyonunu artırabilir.

**Test oracle problem:** Bir testin beklenen sonucunun doğru olduğunu hangi güvenilir kaynaktan biliyoruz?

Burada kritik bir nüans var: Aynı LLM'in kullanılması, bütün agent'ların mutlaka aynı hatayı yapacağı anlamına gelmez. Farklı LLM'ler de aynı yanlış yoruma ulaşabilir. Sorun sadece model kimliği değil; **bilgi akışının, varsayımların ve onay yetkisinin nasıl tasarlandığıdır.**

Bir Tester'ın `100 >= 100` varsayımını üretmesi ayrı bir olaydır. Developer'ın bu varsayımı doğru kabul etmesi ikinci olaydır. Reviewer'ın, orijinal gereksinime geri dönmeden yalnızca kodu ve testi karşılaştırıp “doğru” demesi ise üçüncü olaydır.

Bu üç rolü farklı agent isimleriyle çağırmak, üç bağımsız kanıt üretmiş olmaz.

---

## Birbirine karıştırmamamız gereken üç problem

### 1. Test Sensitivity — Testler gerçekten hata yakalayabiliyor mu?

İlk soru, testlerin kod davranışındaki değişikliklere duyarlı olup olmadığıdır.

Bir test her koşulda geçiyorsa, doğrudan production kodunu çalıştırmıyorsa veya aşırı mock kullanımı yüzünden gerçek davranışı gözlemlemiyorsa güvenilir bir kontrol değildir.

Bu soruya **mutation testing** ve **negative control** teknikleriyle yaklaşabiliriz.

Mutation testing, koda kontrollü değişiklikler yapar ve testlerin bunları yakalayıp yakalamadığını inceler. Negative control yaklaşımında ise örneğin yeni yazılan testler korunurken implementasyon değişikliği geri alınabilir: Testler hâlâ geçiyorsa, yapılan değişikliğe karşı yeterli kanıt üretmemiş olabiliriz.

Önemli sınır şu: Bir test, **yanlış davranışı çok iyi test ediyor** olabilir.

Örneğimizde `amount >= 100` bekleyen test, kod `amount > 100` olarak değiştirildiğinde başarısız olabilir. Bu, testin duyarlı olduğunu gösterir; fakat testteki beklentinin doğru olduğunu göstermez.

Dolayısıyla:

> **Test sensitivity, oracle correctness değildir.**

### 2. Oracle Correctness — Beklenen davranış doğru mu?

İkinci soru daha zor: Testteki `expected` değerini nereden aldık?

Tester bunu kendi yorumundan üretmişse ve Reviewer yalnızca Tester'ın yazdığı assertion'ı referans alıyorsa, işin doğruluğunu dışarıdan doğrulayan bir mekanizmamız yoktur.

Böyle bir sistem için **onaylı, implementasyondan bağımsız bir business oracle** gerekir.

Gateway demosunda kabul vakası `exact-threshold`, adayın testinden ayrı hazırlanır. Adaya `{"amountCents":10000}` gönderir ve `{"totalCents":10000}` bekler. Aday kendi testinde 9000 beklemeye devam etse de oracle'ın beklediği değer 10000 olarak kalır. Bu ayrımı sürdürebilmek, **beklenen sonucun kaynağını ve onu değiştirme yetkisini** görünür kılmaya bağlıdır. [Kabul vakaları](https://github.com/onurozkir/oracle-gateway/tree/main/tests/helpers.ts) · [Demo bundle'ı](https://github.com/onurozkir/oracle-gateway/tree/main/tests/authority.ts)

Bir LLM bu dosyayı hazırlayabilir. Ama aynı LLM'in hazırladığı dosyayı yine aynı LLM'e otomatik olarak onaylatırsak problemi yalnızca başka bir yere taşırız.

Kritik iş kurallarında oracle'ın kaynağı; onaylı ürün politikası, sözleşme, düzenleyici kural, domain owner kararı veya bağımsız biçimde doğrulanmış kabul senaryoları olmalıdır. Aksi hâlde elimizde yalnızca daha düzenli yazılmış bir varsayım vardır.

### 3. Verification Independence — Reviewer gerçekten bağımsız mı?

Üçüncü soru, kodu doğrulayan agent'ın nasıl bilgi edindiğiyle ilgilidir.

Reviewer'a şunları birlikte verdiğimizi düşünelim:

- Tester'ın yanlış assertion'ı,
- Developer'ın bu assertion'a göre yazdığı kod,
- Tester'ın “tüm testler başarılı” özeti,
- Developer'ın “görev tamamlandı” açıklaması.

Reviewer, değerlendirmeye başlamadan önce aynı yanlış yorumun birçok kez tekrarlandığı bir bağlama maruz kalır.

Benim tercih edeceğim yöntem iki aşamalı bir değerlendirmedir:

**Aşama 1 — Blind interpretation:** Reviewer yalnızca orijinal gereksinimi ve yetkili kaynakları görür. Henüz kodu veya Tester'ın beklediği sonucu görmeden sınır koşullarını ve beklenen davranışı kaydeder.

**Aşama 2 — Candidate comparison:** Reviewer'a kod ve testler açılır. Kendi önceden kaydettiği beklentilerle implementasyonu karşılaştırır; semantik uyuşmazlıkları somut örneklerle raporlar.

Bu tasarım, önceki agent'ın gerekçesinin reviewer'a doğrudan taşınmasını azaltır. İstenirse farklı model ailesi de kullanılabilir.

Ancak şunu özellikle vurgulamak gerekir:

> **Fresh context, bağımsız doğruluk garantisi değildir. Farklı model kullanmak da tek başına garanti değildir.**

İki reviewer aynı yanlış yoruma ulaşabilir. Bu nedenle özellikle kritik kararlarda bağımsız model görüşünü, **onaylı oracle ve çalıştırılabilir kanıtların yerine** koymam.

---

## Önerdiğim mimari: Independent Verification by Design

Burada geliştirme workflow'unu baştan yazmak yerine iki ayrı hat oluştururdum: **Development Lane** ve **Independent Validation Lane**.

![Orijinal iş gereksinimi geliştirme ve bağımsız doğrulama hatlarına ayrılır. Test duyarlılığı ve onaylı iş kurallarına göre yürütülen kabul testleri, kabul, ret veya açıklama isteme kararını besler.](/images/independent-verification-flow.svg)

Bu diyagramda üç teknik karar belirleyici:

**Bir:** Development Lane kendi testlerini üretebilir, ancak onaylı business oracle'ı tek taraflı değiştiremez.

**İki:** Independent Validation Lane, Developer'ın testlerini başlangıç otoritesi kabul etmez. Orijinal gereksinimden ve onaylı kaynaklardan hareket eder.

**Üç:** Nihai release kararı, agent'ın “bence doğru” ifadesine değil; kayıtlı kanıtlara ve deterministik policy'ye dayanır.

### Adım 1 — Gereksinimi dondurmak değil, sürümlemek

İş kuralları değişebilir. Asıl ihtiyacım, **hangi kural sürümüne göre hangi kodun doğrulandığını** izleyebilmektir.

Gateway'in yerel görev akışında `task start`, düzenlemeden önce proje dosyalarının başlangıç kopyasını alır ve orijinal istekle sözleşme taslağını kaydeder. Kullanıcı sözleşmenin hash'ini onaylar. Ajan kabul kriterini değiştirdiğinde yeni bir hash ve yeni onay gerekir. İş sonunda `verify` kaydedilmiş dosyaların yeni bir kopyasını sabitler. Rapor, sonucu bu kopyaya bağlar ve hangi dosyaların eklendiğini, değiştiğini veya silindiğini gösterir. Açık commit seçeneği de aynı soruyu Git üzerinden yanıtlar. [Yerel görev akışı](https://github.com/onurozkir/oracle-gateway/tree/main/README.md#verify-a-local-task)

### Adım 2 — Sınır değerlerini sistematik üretmek

`100 TL üzeri` gereksinimi tek bir mutlu yol testinden ibaret olmamalıdır.

En azından 99, 100 ve 101 TL senaryoları sınanmalıdır. Gerektiğinde property-based testing ve metamorphic testing ile daha genel değişmezler de kontrol edilir.

Örneğin bu kuralda tam 100 TL için indirim uygulanmaması, tek başına güçlü bir karşı örnektir.

### Adım 3 — Agent'ın testlerini ayrıca zorlamak

TDD testlerini kaldırmam. Onları mutation testing veya negative control ile ayrıca sınarım.

Bu katmanın görevi şudur: *“Bu testler gerçekten davranış değişikliğini fark edebiliyor mu?”*

Bu sorunun cevabını business correctness ile aynı metrikte birleştirmem.

### Adım 4 — Reviewer'ın yorumunu önce üretmek

Reviewer, kodu gördükten sonra gereksinimi yorumlamamalı. Önce kendi beklenen senaryolarını kaydetmeli; sonra kodu değerlendirmelidir.

Eğer Reviewer `amount > 100`, Tester ise `amount >= 100` diyorsa bu bir **semantic disagreement** olarak kaydedilir. Sistem tartışmayı saklamaz veya çoğunluk oylamasıyla otomatik kapatmaz.

Anlaşmazlık onaylı iş kuralıyla çözülebiliyorsa düzeltme istenir. Kuralın kendisi belirsizse domain owner'a eskale edilir.

Gateway'de bu ayrımı iki yerde kullanıyorum. Onaydan önce reviewer orijinal isteği okuyor, yorumunu kaydediyor ve ardından YAML taslağını görüyor. İş bitince ayrı bir inceleme aynı sırayla başlıyor ve bu kez sabitlenen aday kodunu görüyor. Reviewer, örneğin `>` ile `>=` arasındaki farkı bildirebiliyor. Sınır vakasının sonucu ise aday gerçekten çalıştırılarak elde ediliyor. [Reviewer akışı](https://github.com/onurozkir/oracle-gateway/blob/main/docs/reviewers.md)

### Adım 5 — Deterministik completion gate

Release için şu üç kanıt birbirinden ayrı tutulmalıdır:

| Sinyal | Kanıtladığı şey | Tek başına kanıtlamadığı şey |
|---|---|---|
| Test sensitivity | Testlerin ilgili davranış değişimini fark edebildiği | Beklenen davranışın doğru olduğu |
| Approved oracle checks | Candidate'ın onaylı iş örneklerine uyduğu | Tüm olası durumlarda doğru olduğu |
| Independent review | Farklı yorumların ve uyuşmazlıkların değerlendirildiği | Reviewer'ın hatasız olduğu |

Gateway'deki yerel karar politikası bu fikrin bir bölümünü uyguluyor. Kanıtın aday ve sözleşme kimlikleriyle eşleşmesini ve güncelliğini denetliyor. Onaylı sınır vakası başarısızsa `REJECT` veriyor. Gerekli bağımsız inceleme kanıtı yetersizse `INCONCLUSIVE`, gerekli bir kontrol çalıştırma hatası verdiyse `INFRASTRUCTURE_ERROR` üretiyor. `ACCEPT`, belirli bir adayın tanımlı politikayı karşıladığını ifade ediyor. [Karar politikası](https://github.com/onurozkir/oracle-gateway/blob/main/packages/core/src/policy.ts)

---

## Production'da iki hafta sonra bu hatayı bulursam ne yaparım?

System Design Interview'da mimari çizmek yetmez. Production'dan sorumlu engineer olarak ilk önceliğim yeni bir framework geliştirmek değil, müşteri etkisini sınırlandırmaktır.

**Önce etkiyi durdururum.** Hatalı indirim kuralını feature flag ile kapatır veya güvenli sürüme geri dönerim. Yanlış fiyat hesaplanmasını önlerim.

**Sonra etkilenen işlemleri çıkarırım.** Hangi siparişlerin 100 TL sınırında yanlış hesaplandığını belirler; finans ve ürün ekipleriyle düzeltme veya iade sürecini yönetirim.

**Ardından kök nedeni araştırırım.** Hata yalnızca `>=` operatöründe mi, yoksa Tester'ın yanlış yorumunun Reviewer tarafından da sorgulanmadan kabul edilmesinde mi? Yanlış assertion nasıl onaylı başarı kriterine dönüştü? CI neden bu konuda bağımsız kanıt istemedi?

**Son olarak karşı örneği kalıcı hâle getiririm.** `100 TL → 100 TL` senaryosu, agent'ın yazma yetkisi dışında tutulan acceptance corpus'a eklenir. Aynı hata sınıfı için başka sınır değerleri de araştırılır.

Production izlemesini de yalnızca HTTP 200, latency ve exception oranıyla sınırlandırmam. Fiyatlandırma, yetki veya finans gibi alanlarda bağımsız business reconciliation gerekir. Teknik açıdan sağlıklı görünen bir servis, her istekte yanlış iş kararı veriyor olabilir.

---

## Son soru: TDD bizi hangi risklerden korur, hangilerinden korumaz?

TDD'yi bu nedenle terk etmem. Tam tersine, TDD'nin hangi sorunu çözdüğünü doğru konumlandırırım.

| Risk | TDD'nin katkısı |
|---|---|
| Kodun testlerde tanımlanan davranıştan sapması | Güçlü koruma sağlayabilir |
| Önceden test edilmiş davranışların bozulması | Regresyonu yakalamaya yardımcı olur |
| Kontrolsüz implementasyon ve geç test yazımı | Test-first disiplinini destekler |
| Test beklentisinin yanlış iş kuralına dayanması | Tek başına korumaz |
| Agent'ların ortak yanlış varsayımı | Tek başına korumaz |
| Reviewer'ın yanlış testi doğru kabul etmesi | Tek başına korumaz |
| Test edilmemiş production davranışı | Tek başına korumaz |

Bunu iki kavramla ayırabiliriz:

- **Verification:** Kodu tanımladığımız davranışa uygun geliştirdik mi?
- **Validation:** Başta doğru davranışı mı tanımladık?

TDD, verification sürecinde son derece faydalıdır. Fakat testlerin kaynaklandığı iş gereksiniminin doğruluğunu otomatik olarak tesis etmez.

> **TDD helps verify that the implementation follows the expected behavior. It does not independently establish that the expected behavior is correct.**

Sorun TDD'nin yetersiz bir teknik olması değil; TDD'ye tasarlanmadığı bir sorumluluğun yüklenmesidir.

---

## Bu problemden doğan proje: Independent Oracle Gateway

Buraya kadar anlattıklarım bizi daha pratik bir soruya götürüyor:

*Bu güven sınırlarını yalnızca mimari prensip olarak anlatmak yerine, mevcut coding agent workflow'larının önüne konumlandırabileceğimiz çalıştırılabilir bir doğrulama aracı hâline getirebilir miyiz?*

**Independent Oracle Gateway** bu sorudan doğdu. TypeScript tabanlı CLI, mevcut coding agent akışına eklenebilen oracle adımını uyguluyor. Adayın kendi testini ve ayrı hazırlanmış kabul vakalarını çalıştırıyor, iki sonucu da aynı rapora yazıyor.

### İlk demoda ne oldu?

Kaynak depoda Node.js 24 ve Git ile iki demoyu çalıştırdım.

```sh
npm ci
npm run demo:wrong
npm run demo:correct
```

| Aday ve politika | Adayın testi | Oracle | Karar |
|---|---|---|---|
| `>= 10000`, yerel standart | PASS | FAIL. 10000 beklenirken 9000 döndü. | `REJECT` |
| `> 10000`, yerel standart | PASS | PASS | `ACCEPT` |
| `> 10000`, kritik | PASS | PASS | `INCONCLUSIVE` |

İlk satır yazının çıkış noktası. Aday, kendi testinin istediği davranışı doğru uyguluyor. Aynı aday, orijinal iş kuralından gelen sınır vakasında kalıyor. Son satır da güvence sınırını gösteriyor. Kritik politika korumalı yürütme ve bağımsız inceleme kanıtı istiyor. Bugünkü çalıştırma yerel ve `UNPROTECTED`. Test duyarlılığı ve production release onayı, yukarıdaki daha geniş mimarinin ayrı katmanları. [Demo kaynağı](https://github.com/onurozkir/oracle-gateway/blob/main/scripts/demo.ts) · [Çalıştırma ve raporlar](https://github.com/onurozkir/oracle-gateway/blob/main/README.md#quick-start) · [Bilinen sınırlar](https://github.com/onurozkir/oracle-gateway/blob/main/docs/known-limitations.md)

Aynı hata sınıfını parasal hesapların dışında da görüyorum. “Sayfaya **Siparişiniz alındı** yaz” isteği, sözleşmeye **Siparişiniz verildi** diye aktarılırsa taslakta yorum hatası vardır. Sözleşme doğruysa ama ekranda yanlış metin görünüyorsa hata uygulamadadır. Bugünkü demo kuruş cinsinden sayısal sonuçları karşılaştırıyor. Metin, boolean ve liste alanlarını sınayabilmek, aynı ayrımın genel veri protokolüne taşınmasını gerektiriyor.

### Ürünün değerini nasıl ölçeceğiz?

Bir doğrulama aracının kendisini de yalnızca kendi başarı raporuyla değerlendiremeyiz.

Depoda 42 sentetik vakalık bir başlangıç ölçümü var. Sınır, yuvarlama, rol erişimi ve tenant izolasyonu gibi vakalarda karşılaştırma mantığını sınayan bu çalışma, gerçek agent performansı hakkında veri üretmiyor. Bunu ölçmek için aynı gereksinimleri şu dört yaklaşıma verip sonuçları karşılaştırmak gerekir. [Benchmark metodolojisi](https://github.com/onurozkir/oracle-gateway/blob/main/docs/benchmark-methodology.md)

1. Tek model: Kod + test + self-review, ortak context.
2. Aynı model: Ayrı roller ve izole context.
3. Farklı modeller: Bağımsız reviewer, fakat aynı gereksinim kaynağı.
4. Onaylı oracle: İzole reviewer + bağımsız acceptance tests + policy gate.

Ölçümler yalnızca kaç hata bulunduğuyla sınırlı kalmamalı. Yanlış alarm oranı, tespit edilmeyen hatalar, insan eskalasyon ihtiyacı, doğrulama gecikmesi ve token/altyapı maliyeti de raporlanmalıdır.

Böylece “farklı model kullanmak gerçekten ne kadar yardımcı oluyor?”, “context izolasyonu ne kadar katkı sağlıyor?” ve “onaylı oracle hangi hata sınıflarında fark yaratıyor?” sorularına varsayımla değil, deneyle cevap verebiliriz.

---

## Sonuç: Consensus is not correctness

Bu senaryodan çıkardığım ders, AI agent'larla geliştirilen yazılımlara güvenilemeyeceği değil. Güvenin, rol isimleri veya başarılı test ekranları üzerinden kurulamayacağı.

Bir Planner gereksinimi doğru tanımlamış olabilir. Bir Tester yanlış anlayabilir. Developer yanlış testi başarıyla geçebilir. Reviewer da kodla testi karşılaştırıp aynı yanlışı onaylayabilir.

Bu zinciri kırmak için daha fazla agent eklemek tek başına yeterli değildir.

İhtiyacımız olan şey:

- Testlerin gerçekten hataları algılayabildiğine dair kanıt,
- Test beklentilerinin onaylı iş kurallarına dayandığına dair kanıt,
- Reviewer'ın önceki agent'ların varsayımlarını yalnızca tekrar etmediğine dair kontrollü bir değerlendirme,
- Ve bütün bunları güvenilir release politikasına bağlayan bir mekanizma.

**Amaç, bütün agent'ların aynı fikirde olmasını sağlamak değil; hepsi aynı yanlış fikre sahip olsa bile sistemin bunu bağımsız bir kanıt olmadan doğru kabul etmesini engellemek.**

> **Consensus is not correctness. Passing tests are not proof of valid requirements. And multiple agents are not independent reviewers unless independence is designed into the system.**

AI-native software engineering'de bir sonraki olgunluk adımının yalnızca daha iyi kod üreten agent'lar değil, *üretilen kod hakkında kimin hangi kanıta dayanarak hüküm verebildiğini* doğru tasarlayan sistemler olduğuna inanıyorum.

---

### Kaynaklar ve proje referansları

- [Harnessed — Independent QA for AI coding agents](https://github.com/tt-a1i/harnessed)
- [Stryker — Mutation testing](https://stryker-mutator.io/)
- [GitHub Spec Kit — Specification-driven development](https://github.com/github/spec-kit)
- [Independent Oracle Gateway — Kurulum, demo ve yerel görev akışı](https://github.com/onurozkir/oracle-gateway/blob/main/README.md)