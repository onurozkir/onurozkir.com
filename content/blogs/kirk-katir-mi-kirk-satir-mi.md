---
title: "Kırk Katır mı Kırk Satır mı?"
date: 2026-01-25T01:22:33+05:30
draft: false
author: "Onur Özkır"
tags:
  - Race Condition
  - System Design
  - CAP Theorem
  - NET Core
  - Redis
  - Architecture
  - Microservices
  - Zero Downtime Deployment
  - BlueGreen Deployment
image: /images/kirk-katir-mi-kirk-satir-mi.png
description: "Saatler 23:59'u gösterdiğinde sisteminiz veri tutarlılığını koruyabilir mi? Basit bir faiz güncelleme işinin arkasında yatan Race Condition ve Stale Data canavarlarını, Redis Pointer Swapping tekniğiyle nasıl alt ettiğimizi anlatıyorum. Dağıtık sistemlerdeki 'Kırk Katır mı, Kırk Satır mı' ikilemini yönetmek isteyenler için mimari bir vaka analizi."
toc: true
summaryForLLM: true
summary: "This technical case study analyzes a Redis-based 'Pointer Swapping' architecture designed to resolve Race Conditions, Stale Data, and Clock Skew in distributed fintech systems using .NET Core. It provides a comprehensive guide on achieving Zero Downtime Deployment and Atomic Consistency via Data Versioning, effectively mitigating Cache Stampede risks without relying on traditional RDBMS locking. Additionally, the article explores resilience strategies, including Smart Retries and Blue-Green Data Deployment, to manage integration latencies within the constraints of the CAP Theorem."
mathjax: true
---


Eski firmamın hibrit çalışma modeline geçeceğini duyurmasıyla, yavaştan iş aramaya başlamam gerektiğini hissetmiştim. Ama yeni yerim hakkında biraz seçici olmak istiyordum. Bu arayış içinde bir fintech şirketi ile görüşme ayarlayabildim. Mülakat aşamasında bir case vereceklerini ve onun üstüne konuşacağımızı söylediler. Case, kağıt üzerinde basit bir istekten ibaretti. Bir adet Rest API ve bir adet job oluşturmamı istediler. Ama soruda bence büyük bir felsefe yatıyordu -soranlar bunun farkında mıydı bilmiyorum tabi - hoşuma gitmişti. Felsefesi şuydu "**Kırk katır mı kırk satır mı?**"

Soru basit anlamda şu şekilde " saat 23:59'da bir endpoint ertesi gün kullanılacak yeni faiz oranlarını veriyor ve artık 23:59'dan itibaren yeni faiz oranları geçerli olmakta. Ayrıca bir Rest API ile bu faiz oranlarını parametrelere göre filtreleyerek belirledikleri sırada request sahibine verilmesi isteniliyor. tabi rest apinin monitor edilebilmesi SOLID'e uygun olması ve resilience bir yapıda olması gerekiyor.

Case'in kodlama tarafı bir senior için aslında basit kalıyor bir adet job yarat bir adet web api oluştur, rate limiting, circuit breaker kur ve logla. ama bence soru 23:59 detayında. günün çoğunda işler sıkıntısız ve istenilen gibi geçecek ama asıl problem buradaki 1 saniye içinde olacak. Case’e bir bakış attığımda kafamdaki olası senaryolar şunlardı:

- 23:59:00 da job başlar ve 23:59:02'de biter. 23:59:01'de bir request DB call yapar. Bu kişi aslında Stale Data (bayat veri) görecek.
- 23:59:00'da başlar ancak entegrasyon sahibi henüz yeni faiz oranlarını vermemiştir. 23:59:02'de tekrar bir istek yapılır ve o zaman yeni faiz oranları gelmiştir.
- 23:59:00'da başlar dataları da alır Ancak DB güncellenirken o sırada biri tüm listeyi talep eder. request sahibi yarısı güncel, yarısı eski data mı görür?
- Faiz oranları alınıp kaydedildiğinde o sırada cache’den istekte bulunan değerler ne olacak?
- Job sunucusu ile API sunucusunun saati arasında 500ms fark varsa ne olacak? Job "saat şu an 00:00" deyip işi bitirdiğinde, API sunucusu hala "23:59:59" sanıyorsa eski veriyi mi cacheleyecek?

bu gibi bir çok case düşünülür. Bir problemi çözmek için önce teşhis koymak, sonra da ona doğru ismi vermek gerekir. İşte asıl mesela burada bu bir **Race Condition** mı yoksa **Stale Data** problemi mi? Yoksa daha derinlerde bir **Consistency** problemi mi?

Çünkü:

- **Race Condition mı?** Evet, çünkü Job'ın yazma hızı ile User'ın okuma hızı yarışıyor.
- **Stale Data mı?** Evet, sonuç "bayat veri" oluyor.
- Bu bir **Consistency** problemidir. Özellikle ACID prensiplerindeki **Isolation** ilkesiyle ilgilidir.

gelin bu sorunları teker teker çözmeye çalışalım.

İşte burada sorunun adını koyup çözüme gidemiyorsak, sorunları teker teker ortadan kaldırıp bir dumanı dağıtalım. Senaryomuzda 5 adet soru işareti tespit etmiştik. karalama defterimize teker teker üstten bakarak çözümleri sıralayalım ve temize çekmeye başlarken problemleri sıralayalım.

## Case 1: 2 Saniyelik Gecikme

Öncelikle; 1. Maddemiz olan  “**23:59:00 da job başlar ve 23:59:02'de biter. 23:59:01'de bir request DB call yapar. Bu kişi aslında bayat veri görecek**” sorununa bir bakış atalım. Normal şartlarda bankalar, yeni oranları yürürlüğe gireceği tarihten çok önce yayınlar. Böylece entegratörler hazırlıklı olur. Ancak bizim senaryomuzda işler biraz daha zorlayıcı: Oranlar, geçerli olacağı saniyede yayınlanıyor. Şşte burada  benim “**kırk katır mı kırk satır mı**” diyeceğim ama endüstride [**CAP teoremi**](https://en.wikipedia.org/wiki/CAP_theorem) olarak geçen duruma geliyoruz. **Consistency** mi yoksa **Availability** mi? seçeneklerinden birini seçeceğiz. Şöyle ki bu sorunda o 2 saniyelik alanda gelen istekleri “**503 Service Unavailable**” ‘a mı düşürmeli yoksa “**Availability**” ön planda tutup o 2 saniye de gelen kişilere eski verileri ver ama sistemi açık tut mu demeliyiz? Bence buradaki çözüm “**Retroactive Correction/Reporting**” yani geri dönük düzeltme/raporlama. Peki nasıl?

```csharp
namespace NewRation.Jobs.Jobs
{
    public class RatiosJobs : IJob
    {
        private readonly IRatiosApiClient _apiClient;
        private readonly IRatios _repository;

        public RatiosJobs (
            IRatiosApiClient apiClient,
            IPosRatios repository)
        {
             
            _apiClient = apiClient;
            _repository = repository;
        }
         
        public async Task Execute(IJobExecutionContext context)
        {  
            try
             {
                // fetch ration
                List<RatioDTO> ratios = await _apiClient.FetchRatios(ct);
                
                // some logic response  
                
                // tüm logicler işletildi
                 // ve artık 23:59:00 - DateTimeOffset.UtcNow arasındak kimler
                // eski dataları kullandı transaction tablosundan görebiliriz.
                var posReceiveFinishDate = DateTimeOffset.UtcNow;
                
                // write DB
                var dbResult = await _repository.Insert(ratiosJson, posReceiveFinishDate, ct);
                
                // some result logic
                
                _logger.LogInformation("Fetched {Count} ratios from external API.", ratios.Count);
            }
            catch (Exception e)
            {
                _logger.LogError(e, "Error occurred while fetching ratios.");
            }
            _logger.LogInformations("RatiosSyncJob finished at {time}", DateTimeOffset.Now);
        }
    }
}
```

İşte şimdi biz 2 saniye’de işlemleri bitirmiş olsak ve o 2 saniye’de eski istek ile gelmiş olsalar biz artık geriye dönük işlemleri yapabilir durumdayız. Burada düzeltme veya raporlama kişinin isteğine bağlı.

## Case 2: Entegrasyon Gecikmesi

Şimdi gelelim 2. soruya "23:59:00'da başlar ancak entegrasyon sahibi henüz yeni faiz oranlarını vermemiştir. 23:59:02'de tekrar bir istek yapılır ve o zaman yeni faiz oranları gelmiştir.”

Bu sorun literatürde “**Producer-Consumer Time Discrepancy**” olarak geçiyor. Veriyi veren ile alan arasında zaman uyuşmazlığı. Tabi gerçek hayatta Entegrasyon sahibi işi bitince bize haber vermeli (**Event-Driven / Webhook**) bizde böylece gerçek verileri almalıyız ama şuanda bile böyle bir akış olduğunu sanmıyorum ve biz senaryomuza devam ediyoruz. Burada aklımıza ilk gelen ve sağlam olan plan Check Fresh Data & Retry olurdu. Yani gelen verinin tazeliğini kontrol et eğer değil ise bir süre sonra tekrar job ateşle. Tabi burada trade-off maliyetimiz çıkmakta Kaynak israfı önümüzde duruyor. Son tahlilde kodumuz şuna dönüyor.

```csharp
namespace NewRation.Jobs.Jobs
{
    [DisallowConcurrentExecution] // Bir retry çalışırken diğeri başlamasın.
    public class RatiosJobs : IJob
    {
        private readonly IRatiosApiClient _apiClient;
        private readonly IPosRatios _repository;
        private readonly ILogger<RatiosJobs> _logger;

        public RatiosJobs(
            IRatiosApiClient apiClient,
            IPosRatios repository,
            ILogger<RatiosJobs> logger)
        {
            _apiClient = apiClient;
            _repository = repository;
            _logger = logger;
        }

        public async Task Execute(IJobExecutionContext context)
        {
            var ct = context.CancellationToken; 
            
            try
            {
                _logger.LogInformation("RatiosSyncJob started checks at {time}", DateTimeOffset.Now);

                // fetch ratios 1.case
                List<RatioDTO> ratios = await _apiClient.FetchRatios(ct);

                // Data Freshness Check
                // SORUN ÇÖZÜMÜ: Entegrasyon sahibi eski datayı dönüyor mu?
                var isDataStale = ratios.Any(r => r.RateDate < DateTime.Today); 

                if (isDataStale || ratios.Count == 0)
                {
                    _logger.LogWarning("Entegrasyon servisinden henüz yeni faiz oranları gelmedi. Retry tetikleniyor...");
                    
                    // Quartz'a özel Exception fırlatarak Job'ın hata aldığını 
                    // ve tekrar çalışması gerektiğini söylüyoruz.
                    // Not: Quartz config'de exponential backoff ayarlı olmalı.
                    var retryException = new JobExecutionException("Stale Data Detected");
                    
                    // Eğer hemen denemesini istemiyorsak Trigger update yapılabilir 
                    // ama basitlik adına Refire diyoruz.
                    retryException.RefireImmediately = true; 
                    throw retryException; 
                }

                // Reconciliation Window process
                // SORUN ÇÖZÜMÜ: Job 23:59:00'da başladı ama şu an saat 23:59:05.
                // Bu 5 saniyede eski kurdan işlem yapanları bulmak için time alıyoruz.
                var effectiveTime = DateTimeOffset.UtcNow;
                
                // Insert
                // Burada "Insert" metoduna 'effectiveTime' gönderiyoruz.
                // Veritabanına bu kayıt "Bu oranlar şu andan itibaren geçerlidir" diye işleniyor.
                await _repository.Insert(ratios, effectiveTime, ct);
                
                // Event sonrası (Post-Action)
                if (context.ScheduledFireTimeUtc.HasValue)
                {
                    var latency = effectiveTime - context.ScheduledFireTimeUtc.Value;
                    if (latency.TotalSeconds > 1)
                    {
                         _logger.LogWarning("Job gecikmeli tamamlandı ({Latency} sn). Bu aralıktaki işlemler incelenmeli.", latency.TotalSeconds); 
                    }
                }

                _logger.LogInformation("Fetched and saved {Count} ratios. Effective from: {Date}", ratios.Count, effectiveTime);
            }
            catch (JobExecutionException)
            {
                // Retry için fırlattığımız hatayı tutma, yukarı fırlat ki Quartz bilsin.
                throw; 
            }
            catch (Exception e)
            {
                _logger.LogError(e, "Unexpected error occurred while fetching ratios.");
                // Beklenmedik hatalarda da retry mekanizması calıştıralım.
                var rex = new JobExecutionException(e);
                rex.RefireImmediately = true;
                throw rex; 
            }
        }
    }
}
```

2. sorunumuz da halloldu sayılır. Artık entegrasyon sahibi datayı geç verirse biz taze data gelene kadar istekte bulunmaya devam edeceğiz. Tabiki burada “**EffectiveTime**” uzayacak geriye doğru düzeltme/raporlama süreleri artacak ancak elimizde sihirli bir değnek yok ve sorun bizden kaynaklanmıyor.

## Case 3: Yarım Data ve Deployment

gelelim 3. case’imizi çözmeye : “**23:59:00'da başlar dataları da alır Ancak DB güncellenirken o sırada biri tüm listeyi talep eder. request sahibi yarısı güncel, yarısı eski data mı görür?**” Aslında görmez. Geleneksel RDBMS databaseler “`Commit;`” komutunu görene kadar yarım yamalak data göstermez “ACID” gereği tabloda şuanda olanı verirler. Ancak burada gizli bir sorun RDBMS database’in Yüksek trafik altında veritabanı darboğazı ve milisaniyelik tutarlılık ihtiyacı var. O zaman bu sorunu da çözecek olan başka bir katmana, Redis’e gidelim. Bu konumuzda birazda DevOps yaklaşımından yardım alır ve **Zero Downtime Deployment** mantığına uygun bir kod yazalım. Çözüm Senaryomuz şu olsun:

- Bir adet version yarat. Örneğin: **v2**
- Entegrasyon sahibinin verdiği datayı v2 keyine ata
- ration:current = v1 olan keyi bir anda “ration:current = v2” olarak değiştir.
- web tarafından bundan sonra v2 olan kaydı göster.

Bu sıralama ile tüm kullanıcıların ruhu bile duymadan artık dataları “deploy” aldık ve “Pointer Swapping” ile DB güncelleme veya insert sürelerini sıfıra düşürdük. Bu akışa göre kodumuzu tekrar yazalım.

Job tarafı:

```csharp
namespace NewRation.Jobs.Jobs
{
    [DisallowConcurrentExecution]
    public class RatiosJobs : IJob
    {
        private readonly IRatiosApiClient _apiClient;
        private readonly IPosRatios _repository;
        private readonly ILogger<RatiosJobs> _logger;

        public RatiosJobs(
            IRatiosApiClient apiClient,
            IPosRatios repository,
            ILogger<RatiosJobs> logger)
        {
            _apiClient = apiClient;
            _repository = repository;
            _logger = logger;
        }

        public async Task Execute(IJobExecutionContext context)
        {
            var ct = context.CancellationToken; 
            
            try
            {
                _logger.LogInformation("RatiosSyncJob started checks at {time}", DateTimeOffset.Now);

                // fetch ratios 1.case
                List<RatioDTO> ratios = await _apiClient.FetchRatios(ct);

                var isDataStale = ratios.Any(r => r.RateDate < today); 

                if (isDataStale || ratios.Count == 0)
                {
                    _logger.LogWarning("Entegrasyon servisinden henüz yeni faiz oranları gelmedi. Retry tetikleniyor...");
                    
                    var retryException = new JobExecutionException("Stale Data Detected");
                  
                    retryException.RefireImmediately = true; 
                    throw retryException; 
                }
                
                // Yeni gelen veriyi serialize et
                var ratiosJson = JsonSerializer.Serialize(ratios);
                
                // Yeni veriyi, benzersiz bir key ile kaydet
                var versionId = Guid.NewGuid().ToString();
                
                // Veriye makul bir TTL (Ömür) ver. (Örn: 48 saat)
								// Neden? Redis hem dolmasın diye, hemde veri hemen de silinmesin.
                await _redis.StringSetAsync(dataKey, ratiosJson, TimeSpan.FromHours(48));

                // Pointer'ı güncelle (Atomic Switch)
							  await _redis.StringSetAsync("ratios:current_version", versionId);
                
                var effectiveTime = DateTimeOffset.UtcNow;
                
                // database artık bir history tablosuna dönecek
                // bir önceki koddan farklı olarak verionId'yi de kaydedeceğiz
                // Aslında bu geliştirme bize L1 + L2 veri katmanları sağlamakta
                // redis'in beklenmedik hataları karşısında elimizde
                // database'de bulunacak bir data da olacak
                await _repository.Insert(versionId, ratios, effectiveTime, ct);
              
                if (context.ScheduledFireTimeUtc.HasValue)
                {
                    var latency = effectiveTime - context.ScheduledFireTimeUtc.Value;
                    if (latency.TotalSeconds > 1)
                    {
                         _logger.LogWarning("Job gecikmeli tamamlandı ({Latency} sn). Bu aralıktaki işlemler incelenmeli.", latency.TotalSeconds); 
                    }
                }

                _logger.LogInformation("Fetched and saved {Count} ratios. Effective from: {Date}", ratios.Count, effectiveTime);
            }
            catch (JobExecutionException)
            {
                throw; 
            }
            catch (Exception e)
            {
                _logger.LogError(e, "Unexpected error occurred while fetching ratios.");
                var rex = new JobExecutionException(e);
                rex.RefireImmediately = true;
                throw rex; 
            }
        }
    }
}
```

API Tarafı :

```csharp
public async Task<List<Ratio>> GetRatiosAsync()
{
    // 1. Pointer'ı bul
    var versionId = await _redis.StringGetAsync("ratios:current_version");
    
    if (!versionId.IsNullOrEmpty)
    {
        var dataKey = $"ratios:data:{versionId}";
        var json = await _redis.StringGetAsync(dataKey);
        
        if (!json.IsNullOrEmpty)
        {
            return JsonSerializer.Deserialize<List<Ratio>>(json);
        }
    }

    // Redis patladıysa veya veri yoksa DB'den al (Fallback)
    return await _db.GetLatestRatiosFromDb();
}
```

Kırk katır mı Kırk satır mı sorusu işte burada da karşımıza çıktı. Aslında bakarsanız “Tek bir gümüş kurşun yok” sadece trade-off’lar var. Deyimi çok gerçekçi. Biz bir trade-off problemi çözerken çözdüğümüz sorun da bir adet trade-off çıkarıyor. “Pointer Swapping” ile ne kadar “Zero Downtime Deployment” yapıyor olsakta artık Web tarafında bizden istenen “Order ve Parametreler ile sorgulama” yeteğini database’den alarak artık kod (LinQ) tarafıma taşıdık. Json String olarak kaydettiğimiz datayı önce JSON parse etmeli ardından gelen parametrelere göre filtrelememiz gerekecek.

## Case 4: Cache ve Race Condition

Madem web tarafına giriş yaptık hadi gelin 4. sorumuz olan “Faiz oranları alınıp kaydedildiğinde o sırada cache’den istekte bulunan değerler ne olacak?” sorusuna da cevap verelim. Bir de soralım kim demiş versionlı cache-response-key kullanılamaz diye. Bir önceki sorundaki gibi versionlu bir key kullanabiliriz.

API:

```csharp
public async Task<List<Ratio>> GetRatiosAsync()
{
   
    var versionId = await _redis.StringGetAsync("ratios:current_version");
    
    // Cache Key'i oluştururken bu versiyonu KULLAN
		// Eskisi: "ratios-response:{filter_params}"
		// Yenisi: "ratios-response:{v2}:{filter_params}"
		var cacheKey = $"ratios-response:{currentVersion}:{request.GetHash()}";
    
    // Cache'e bak
		var cachedJson = await _redis.Get(cacheKey);
		if (!string.IsNullOrWhiteSpace(cachedJson))
		{
	    return Deserialize(cachedJson);
		}
    
    if (!versionId.IsNullOrEmpty)
    {
        var dataKey = $"ratios:data:{versionId}";
        var json = await _redis.StringGetAsync(dataKey);
        
        if (!json.IsNullOrEmpty)
        {
            return JsonSerializer.Deserialize<List<Ratio>>(json);
        }
    }

    
    // Cache Miss -> Hesapla -> Yaz
    // artık redisValue == null ise DB'ye bak kısmını buraya taşıdık
    // ve Database'de version alanı oluşturduk. SQL sorgumuz
    // EffectiveDate <= NOW()8 yerine Version = {versionId} olacak.
		var response = Calculate(currentVersion, request);
		
		// Cache'e yaz
		// Biz şu an "v2" key'ine yazıyoruz.
		// Job çalışıp versiyonu "v3" yapsa bile, biz "v2"ye yazmış olacağız.
		// Yeni gelen istekler "v3" arayacağı için bizim yazdığımız bu eski veri
		// kimseyi zehirlemeyecek. Sadece Redis'te fazladan yer kaplayıp ölecek.
		await _redis.Set(
	    cacheKey, 
	    Serialize(response), 
	    TimeSpan.FromMinutes(5));
    
    
    return response;
}
```

Artık hem cache’de hem ratios result için **Zero Downtime Deployment** yapabiliyoruz. Aslında ismini koyamadığımız sorunlardan eleme yaptık ve bu sorunun bir Race Condition sorunu olsa bile artık ortada bir sorun kalmadı.

## Case 5: Time Skew (Saat Farkı)

En son kafamızdaki soru ise şuydu : “**Job sunucusu ile API sunucusunun saati arasında 500ms fark varsa ne olacak? Job "saat şu an 00:00" deyip işi bitirdiğinde, API sunucusu hala "23:59:59" sanıyorsa eski veriyi mi cacheleyecek?**” Bu noktaya gelene kadar bu sorun çözülmüş olabilir mi?  Evet olabilir. bir üstte yazdığımız kodları tekrar hatırlayalım:

API.cs

```csharp
		// Cache Miss -> Hesapla -> Yaz
    // artık redisValue == null ise DB'ye bak kısmını buraya taşıdık
    // ve Database'de version alanı oluşturduk. SQL sorgumuz
    // EffectiveDate <= NOW()8 yerine Version = {versionId} olacak.
		var response = Calculate(currentVersion, request);
```

Job.cs:

```csharp
// database artık bir history tablosuna dönecek
// bir önceki koddan farklı olarak verionId'yi de kaydedeceğiz
// Aslında bu geliştirme bize L1 + L2 veri katmanları sağlamakta
// redis'in beklenmedik hataları karşısında elimizde
// database'de bulunacak bir data da olacak
await _repository.Insert(versionId, ratios, effectiveTime, ct);
```

Bu noktada artık hangi sunucunun hangi saate ait olduğu beni ilgilendirmiyor. Amazon, Google gibi firmaların bile yakalandığı **Time Skew** sorunu **Redis Pointer** ile bizim için tarihe gömüldü.

## Sonuç: Kodun Ötesine

Başlarken sorduğumuz o meşhur "**Kırk katır mı, kırk satır mı?**" sorusuna geri dönelim. Mülakatı yapanların veya projeyi bizden isteyenlerin asıl aradığı cevap, aslında ne katırdı ne de satır. Onların aradığı şey, **bu ikilemle karşılaştığında donup kalmayan, masaya üçüncü bir seçenek koyabilen bir vizyondu.**

Bu vaka çalışmasında gördük ki;
Basit bir "Job yaz, API ver" isteği; **Time Skew (Zaman Kayması)**, **Race Condition**, **Stale Data** ve **Cache Stampede** gibi dağıtık sistem canavarlarına dönüşebiliyor.

Eğer biz sadece Her şeyin yolunda gittiği senaryoyu kodlasaydık, sistemimiz günün %99'unda harika çalışacak ama o kritik %1'lik dilimde, yani tam da 23:59:00'da veri tutarsızlığı yüzünden şirkete zarar ettirecekti.

Biz ne yaptık?

1. **Zamanı Durdurduk:** Saate güvenmek yerine, veriyi **versiyonladık** (Pointer Swapping).
2. **Körü Körüne Beklemedik:** Entegrasyon gecikmelerine karşı **akıllı retry** mekanizmaları kurduk.
3. **Kullanıcıyı Yarı Yolda Bırakmadık:** Cache stratejimizi versiyonlara bağlayarak **Zero Downtime** sağladık.
4. **Maliyetini Kabullendik:** Veritabanı yükünü azalttık ama Redis bağımlılığını ve kod karmaşıklığını (Complexity) artırdık. Yani bir "Trade-off" yaptık.
5. **Stale Data:** Yönetilebilir gecikme sistemi kurduk, kullanıcı eski veriyi görse bile düzeltilebilir bir kayıt attık.

Bir Developer’ın görevi sadece temiz kod yazmak değildir. Asıl görev; sistemin kırılacağı anları öngörmek, kaos anında sistemin nasıl davranacağını tasarlamak ve işletmenin ihtiyaçlarına en uygun trade-off seçmektir.

Bir sonraki "basit" istek geldiğinde, o 1 saniyelik detayın peşine düşmeyi ihmal etmeyin. Çünkü şeytan ayrıntıda, kalite ise o ayrıntıyı yönetmekte gizlidir.

## Kaynaklar

- [Quartz.NET - Job Scheduling Library](https://www.quartz-scheduler.net/)
- [Redis Official Documentation - Data Types & Atomic Operations](https://redis.io/docs/latest/develop/data-types/)
- [Polly - .NET Resilience & Transient-Fault-Handling Library](https://github.com/App-vNext/Polly)
- [CAP Theorem - Brewer's Conjecture](https://people.eecs.berkeley.edu/~brewer/cs262b-2004/PODC-keynote.pdf)
- [Blue-Green Deployment - Martin Fowler](https://martinfowler.com/bliki/BlueGreenDeployment.html)
- [Distributed Locking with Redis (Redlock)](https://redis.io/docs/manual/patterns/distributed-locks/)
- [Google Spanner: TrueTime & External Consistency](https://research.google/pubs/pub39966/)
- [Microsoft .NET Microservices Architecture E-book](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/)
