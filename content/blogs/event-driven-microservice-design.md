---
title: "Event-Driven Mikroservislerde 3 Kritik Çözüm: Fat Event, Outbox Pattern ve Cluster Yönetimi"
date: 2026-01-31T02:23:55+03:44
draft: false
author: "Onur Özkır"
tags:
  - System Design
  - Scalability
  - Architecture
  - Microservices
  - Outbox Pattern
  - RabbitMQ
image: /images/event-driven-design.png
description: "Senkron REST çağrılarından kaynaklanan performans darboğazlarını nasıl aştım? Event-Driven Design, Fat Event ve Outbox Pattern kullanarak mikroservisler arası bağımlılığı azaltma ve finansal veri tutarlılığını sağlama yolculuğumuzu teknik detaylarıyla keşfedin."
toc: true
summaryForLLM: true
summary: "This technical blog post explores the transition from synchronous REST-based communication to an asynchronous Event-Driven Architecture (EDA) within a high-growth environment. It details real-world challenges like 'Distributed Monolith' traps and API choking. The author discusses three key solutions: implementing Fat Events (Event-Carried State Transfer) to eliminate redundant API calls, using the Outbox Pattern to ensure 100% financial data consistency and atomicity, and managing RabbitMQ Clusters for high availability. Ideal for engineers interested in fintech scalability, reliability, and loosely coupled microservice design."
mathjax: true
---

Öncelikle, **event-driven design mikroservis mimarisinde**, servisler birbirleriyle event messages üzerinden haberleşir. Bir business event gerçekleştiğinde, producer servisler bu durumu mesajlarla yayınlar. Aynı anda diğer servisler de bu mesajları event-listener aracılığıyla tüketir.

Bu sayede,  event driven sistemlerin temel kazanımları asenkron davranış ve loosely coupled yapılardır. Örneğin; uygulamalar veriye ihtiyaç duydukları anda talep göndermek yerine, veriyi henüz ihtiyaç oluşmadan olaylar aracılığıyla alıp işlerler. Böylece uygulamanın genel performansı artar. Diğer taraftan, bağlamı gevşek tutmak, mikroservis ekosisteminin en kritik noktalarından biridir.

Özellikle finansal sistemlerde bu mimari, 'Audit Log'  oluşturmayı doğal bir süreç haline getirir. Her event aslında finansal bir hareketin kaydı olduğundan, sistemin geçmişe dönük izlenebilirliği maksimum seviyeye çıkar.

## Bir Çözüm Olarak Event Driven Mimari (EDA)

---

Sistemlerinizi en baştan event driven yapılarla inşa edebileceğiniz gibi, bu yaklaşımı halihazırda highly coupled olan mevcut ortamlarınız için bir çözüm olarak da kullanabilirsiniz. Şimdi, olay güdümlü yaklaşımı bir çözüm olarak nasıl uygulayabileceğimizi tartışalım.

## Temel REST Odaklı Yaklaşım

---

![](https://miro.medium.com/v2/resize:fit:476/1*mUyGHyXYF3-MPoAld-2I2w.png)

Uygulamanız düzgün çalışıyor olsa bile, senkron (REST) API çağrılarının bazı dezavantajları vardır:

- **Modül 1 cevabı bekler:** İşlem bloke olur
- **Modül 2 devre dışı olabilir:** Sistemde single point of failure riski artar.
- **Ağ gecikmeleri performansı düşürür:** Her "hop" süreyi uzatır.
- **Büyük veri setleri pagination gerektirir:** Bu da daha fazla ağ trafiği ve gecikme demektir.
- **Modül 2 ağır yük altında olabilir:** Cevap süresi öngörülemez hale gelir.
- **Zayıf Hata Toleransı (Resiliency):** Senkron yapılarda, hedef servis o an ayakta değilse işlem genellikle başarısız olur ve kullanıcıya hata döner. EDA'da ise mesaj kuyrukta -broker da - bekler ve servis ayağa kalktığında işlem kaldığı yerden devam eder.

Sisteminiz senkron bağlantılar nedeniyle verimsizleşmeye başladığında, event driven çözümü uygulamanın vakti gelmiş demektir.

## Gerçek Dünya Senaryosu

---

GİB API ile entegre çalışan bir raporlama uygulamamız vardı. Bu uygulama, tüm satış raporlarını resmi kurumlara iletiyordu. Dolayısıyla, bu uygulamanın tüm satış verilerini başka bir API'den çekmesi gerekiyordu. Başlangıçta işlem hacmi (transaction volume) oldukça düşüktü; bu yüzden biz de hızlıca REST tabanlı bir yaklaşım kurguladık.

![](https://miro.medium.com/v2/resize:fit:1250/1*Vqc4J7kmYNROSpHn9JA4sw.png)

Özellikle finansal raporlama ve regülasyon süreçlerinde (GİB, BDDK vb.), senkron bağlantıların kopması veri tutarsızlığına yol açabilir. Mesaj kuyrukları kullanarak, satış verilerinin asenkron ama 'garantili teslimat' (guaranteed delivery) prensibiyle işlenmesini sağladık.

Başlarda veri miktarının az olmasına rağmen, hacim bir anda çok ciddi bir artış gösterdi. Hızla büyüyen bir şirkette bu tarz ölçeklenme sorunlarıyla sıkça karşılaşıyoruz. Öte yandan, çözüm basit: Yapıyı olay tabanlı mesajlaşmaya (event messaging) dönüştürmek.

### **Çözüm 1: Event Messaging Sisteme Geçiş**

Raporların verimli bir şekilde oluşturulamadığını fark eder etmez, event driven çözümü uygulamaya koyduk. Her şeyden önce, planımız oldukça basitti:

- Bir işlem kalemi (transaction item) oluşturulduğunda bir "event" yayınla.
- Event alındığında ilgili veriyi çek.
- Veriyi bir rapor metni parçasına dönüştür.
- İlişkisel veri tabanına (PostgreSQL) kaydet.
- Rapor oluşturma aşamasında veriyi sorgula.
- Metin verilerini birleştir ve diskte bir dosya olarak sakla.

![](https://miro.medium.com/v2/resize:fit:664/1*bSOYF16WUrgUuC0Kg6MUkQ.png)

##### **Asenkron Mesajlaşma Yoluyla Veri Toplama**

Bu yaklaşımın bir sonucu olarak, ihtiyaç duyulan işlem kalemleri Raporlama API'sinde önceden depolanmış olur. Rapor oluşturma süreci başladığında, sistem sadece PostgreSQL üzerindeki verileri sorgular ve birleştirir.

![](https://miro.medium.com/v2/resize:fit:501/1*rhLoIJDOGQ_qcKBoCkIpQA.png)

Bu mimari sayesinde 'Read-Heavy'  olan raporlama yükünü, 'Write-Heavy' olan ana sistemden tamamen izole ettik. Bu durum, finansal sistemlerin en büyük kabusu olan **DB locks** tamamen ortadan kaldırdı.

#### **Başarı Kolay Gelmez**

Senkron süreci asenkron bir mimariye dönüştürdüğümüzde, bu kez **Transaction API**'si başka bir performans sorunuyla karşı karşıya kaldı. Raporlama (GİB) API'si, her bir **transaction item** oluşturulduğunda detay verisini tekrar tekrar talep ettiği için, **Transaction API**'si ağır bir yük altında kaldı. Bunun temel nedeni; Satılan her bir ürün için ayrı bir işlem kaydı oluşturulmasıydı. Dolayısıyla, devasa boyutlardaki "transaction detail" talepleri API'yi adeta boğdu.

Bu durum bize gösterdi ki; sadece mesajlaşmaya geçmek yeterli değil. Mesajın içeriği (payload) zenginleştirilmediği sürece, asenkron sistemler bile 'senkron bir bağımlılık' yaratabiliyor. Bu tarz bir yük, sadece API'yi değil, aynı zamanda veri tabanı bağlantı havuzlarını (connection pools) da tüketerek tüm sistemi durma noktasına getirebilir.

### **Çözüm 2: Fat Event**

Açıklamak gerekirse; **"Fat Event"** yaklaşımı, mesajın sadece bir **ID** değil, o **entity’ye** ait tüm detayları da içermesi anlamına gelir.

![](https://miro.medium.com/v2/resize:fit:380/1*nCTWqcJQctJ7wAzIauHk7Q.png)

**Zengin İçerikli Olay (Fat Event) Mesaj Örneği**

Mesaj yapısını "Fat Event" modeline dönüştürdükten sonra, ek bir REST çağrısı yapmamıza gerek kalmadı. Bunun sonucunda mimarimiz, tamamen asenkron ve olay güdümlü (event-driven) bir sisteme dönüştü.

![](https://miro.medium.com/v2/resize:fit:788/1*-0Auy2uQld_oLhNhbpVDKg.png)

**Complete Event-Driven Architecture**

Fat Event kullanımı sayesinde, sistemler arasındaki 'Temporal Coupling' (**Zamansal Bağlılık**) tamamen ortadan kalktı. İşlem API'si bakımda veya kapalı olsa bile, Raporlama API'si mesaj kuyruğundaki zengin içerikli veriyi işleyerek finansal raporları üretmeye devam edebildi. Bu, özellikle regülatif raporlama süreçlerinde sistem kesintilerine karşı muazzam bir direnç sağladı.

### Çözüm 3: Outbox Pattern

Satış işlemlerinden bahsettiğimize göre, bu verilerin ne kadar kritik olduğu zaten ortadadır. Finansal bir iş süreci söz konusu olduğunda, hesaplamalar %100 doğru olmalıdır.

Bu doğruluğa ulaşabilmek için, sistemimizin hiçbir event mesajını kaybetmediğinden emin olmalıyız. Bu amaçla, **"Outbox Pattern"** uygulamasını hayata geçirdik.

**Outbox Pattern Nedir?** En basit haliyle; API'niz olay mesajlarını yayınlarken onları doğrudan göndermez. Bunun yerine mesajlar, veri tabanındaki bir tabloya kaydedilir. Ardından bir işleyici job, birikmiş mesajları önceden tanımlanmış zaman aralıklarında gönderir.

![](https://miro.medium.com/v2/resize:fit:875/1*4m4_-08loz6MNmNNqm6zKA.png)

**Şemanın Açıklaması:**

- Business module bir olay yayınlar.
- Event servisi, mesajı ilişkisel veri tabanına (RDBMS) kaydeder.
- Scheduler, "Send Event Message" görevini tetikler.
- Event servisi, bekleyen mesajları sorgular.
- Event servisi, mesajları RabbitMQ üzerinden yayınlar.

#### **Pros**

- **Guaranteed Delivery:** Mesaj asla kaybolmaz.
- **Strong Consistency:** Business datası ile event datası her zaman senkrondur.
- **Two-Phase Commit:** Karmaşık dağıtık işlemlere gerek kalmadan local transaction ile iş çözülür.

#### **Cons**

- **Latency:** Scheduler'ın çalışma aralığı kadar bir gecikme eklenir (Real-time değildir).
- **Veri Tabanı Yükü:** Sürekli outbox tablosunu sorgulamak ve yazmak ek yük getirir.
- **Yönetim Zorluğu:** Mesajların gönderilip gönderilmediğini takip eden ek bir mekanizma gerektirir.

## **Event-Driven Microservice Architecture Avantajları**

---

- **Loosely Coupled Yapı:** Servislerin birbirine olan bağımlılığının azalması.
- **Mikroservislerin Tam İzolasyonu:** Her servisin kendi sorumluluk alanında bağımsız çalışması.
- **Senkron REST Çağrılarının Ortadan Kalkması:** Servisler arası iletişimde bloklanmaların önlenmesi.
- **Asenkron Event Driven İşlevsellik:** İşlemlerin gerçek zamanlı ama bağımsız akışı.
- **Performans Kazanımı:** Sistem kaynaklarının daha verimli kullanılması

Tüm bu avantajlar arasında en önemlisi birincisidir. Mikroservis mimarisi ile bileşenleri birbirinden ayırmak istediğimizde, tüm birimlerin yeterince ayrıştırılmış (loosely-coupled) olması gerekir. Aksi takdirde, mikroservis mimarisi işlevini yitirir ve sisteminiz "**distrubuted-monolith**" yapısına dönüşür.

Sonuç olarak; Çeviklik ve yüksek erişilebilirlik bir tercih değil, zorunluluktur. Olay güdümlü mimari, sistemlerimize sadece performans katmakla kalmaz; aynı zamanda finansal regülasyonlara uyum, veri tutarlılığı ve ölçeklenebilir bir büyüme için gereken sağlam temeli sağlar.

## Dezavantajlar ve Risk Yönetimi

---

### ***Single point of failure***

Eğer RabbitMQ (veya Kafka) canlı ortamda bir sorunla karşılaşırsa, tüm sisteminiz aksayabilir.

![](https://miro.medium.com/v2/resize:fit:788/1*QFVSFEVGbxY8mn8UonxDTw.png)

Hataların Üstesinden Gelmek İçin:

- **RabbitMQ'yu cluster yapısında kurgulayın:** Yedekli bir yapı oluşturun.
- **Kuyrukları durable hale getirin:** Kuyruk tanımlarının kaybolmasını engelleyin.
- **Mesajları persisted olarak yayınlayın:** Mesajların diskte saklandığından emin olun.

Bu sayede, olası bir arızadan hızla kurtulabilirsiniz. Bir hata oluştuğunda, kümedeki diğer instances işi devralır ve dayanıklı kuyrukları yeniden oluşturur. Ayrıca, kalıcı mesajlarınız diskten geri yüklenir.

### ***Duplicated event messages***

Bir publisher  hata alıp aynı mesajı tekrar gönderebilir. Sistemdeki bu mükerrerlik sorununu çözmek için, her consumer noktası **idempotent** olmalıdır. Yani, mesajı işlemeden önce bu olayın daha önce işlenip işlenmediğini mutlaka kontrol etmelisiniz

Finansal sistemlerde '**At-least-once delivery**'  garantisiyle çalışırken, dublike kayıtların (double-spending vb.) önüne geçmek için tüm servislerimizi '**idempotent**' tasarladık. Bu, sistemin hem dayanıklı hem de her zaman tutarlı kalmasını sağlayan en kritik savunma hattımızdır.

## Özetle

---

- **Mikroservis mimarilerinde** servisler arası bağımlılığı (coupling) düşük tutmak zorundayız. Bunun en etkili yollarından biri **event-driven** yaklaşımları benimsemektir.
- **Doğrudan yapılan REST çağrıları maliyetlidir.** Hedef API o an hizmet dışı olabilir ve kaynak API cevap gelene kadar block zorunda kalır.
- Sağlam bir yapı için, mesajları kalıcı olarak saklayan bir **RabbitMQ cluster** kurulabilir. Sorumlu servisler olayları yayınlar; diğer servisler ise bu olayları dinleyerek kendi işlemlerini yürütür.
- Sistemleri inşa ederken **"Fat Event"**  yaklaşımı değerlendirilmelidir. Bu model, ihtiyaç duyulan tüm veriyi olay anında sunduğu için API'lerin ek dış çağrılar yapma zorunluluğunu ortadan kaldırır.
- Diğer taraftan, sistem veya ağ hataları nedeniyle **kayıp mesajlar** oluşabilir. Tüm mesajların başarıyla yayınlandığından emin olmak için **Outbox Pattern** uygulanabilir. Mesajlar doğrudan yayınlanmak yerine bir veritabanında saklanır ve yapılandırılmış bir "job" aracılığıyla belirli aralıklarla gönderilir. Bu sayede olası kayıplar kolayca telafi edilir.
- **Observability:** Bir mesaj kuyrukta takıldığında bunu anında bilmen gerekir. Bu yüzden tüm sistem baştan sona gözlemlenebilir ve SLO message ile herkesi uyarabilir olmalıdır.
- **Strict Ordering -Sıralama Garantisi-:** Bazı finansal işlemlerde (örneğin önce para yatırma, sonra çekme) mesajların sırası hayati önem taşır. Kullanılan message mimarisinin partitioning ve ordering özellikleri aktif kullanılmalıdır. (Kafka, burada RabbitMQ yerine seçilebilir.)

## Sonuç

---

Özetlemek gerekirse; mikroservis mimarisi nispeten daha iyi bir yaklaşım ve biz yazılım geliştiriciler olarak her geçen gün bu konuda daha fazla deneyim kazanıyoruz. Dikkatli davranmadığımız her an sistemimiz **distributed monolith** yapısına dönüşebilir ki bu, karşılaşılabilecek en kötü senaryodur. Çünkü bu durumda mimarinin hiçbir avantajından yararlanamadığınız gibi, bir de üstüne dağıtık sistemlerin getirdiği karmaşıklıkla boğuşmak zorunda kalırsınız. Hepsinden önemlisi, event driven mimari (EDA) kullanarak servisler arası bağımlılığı düşük tutmak, bu mimarinin başarısı için en kritik unsurdur. Sistemleri sadece 'çalışsın' diye değil, finansal verinin güvenliği ve tutarlılığı için **fault-tolerant** tasarlamayı önemsiyorum. Yaşadığım bu ölçeklenme tecrübeleri, bana bir Finansal işlemleri sisteminde işlemlerin asenkron akarken bile nasıl güvenli tutulacağını öğretti.

## Kaynaklar

---

[Enterprise Integration Patterns (EIP) - Gregor Hohpe & Bobby Woolf](https://www.enterpriseintegrationpatterns.com/)

[Designing Data-Intensive Applications (DDIA) - Martin Kleppmann](https://unidel.edu.ng/focelibrary/books/Designing%20Data-Intensive%20Applications%20The%20Big%20Ideas%20Behind%20Reliable,%20Scalable,%20and%20Maintainable%20Systems%20by%20Martin%20Kleppmann%20(z-lib.org).pdf)

[Microservices.io - Chris Richardson](https://microservices.io/patterns/data/transactional-outbox.html)

[Confluent Blog](https://www.confluent.io/blog/)

[RabbitMQ Official Documentation & Blog](https://www.rabbitmq.com/blog)

[Martin Fowler - Event-Driven Architecture](https://martinfowler.com/articles/201701-event-driven.html)
