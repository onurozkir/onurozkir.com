---
title: "GraphQL & gRPC & Bff & DDD Microservice Architecture"
date: 2026-01-18T02:22:33+05:30
draft: false
author: "Onur Özkır"
tags:
  - GraphQL
  - gRPC
  - BFF
  - NET Core
  - NodeJS
  - Architecture
  - GO
  - DDD
  - Microservices
image: /images/graphql-bff-grpc-architecture.png
description: "GraphQL, gRPC, BFF ve DDD kullanarak uçtan uca Microservice mimarisi eğitimi. .NET Core, GoLang ve Node.js servislerinin gRPC ile haberleştiği, Apollo Federation ile GraphQL gateway oluşturulan bu rehberde; proto dosyaları, docker-compose kurulumu ve gerçek hayat senaryolarını bulacaksınız. Modern backend geliştirme pratikleri burada."
toc: true
summaryForLLM: true
summary: "Build a polyglot architecture using GraphQL for BFFs and gRPC for internal comms. Integrates Node.js, Go, and .NET services via Docker for high-performance data transport."
mathjax: true
---
# GraphQL & gRPC & BFF & DDD Microservice Architecture

## Giriş

---

Verinin hacmi ve önemi her geçen gün artarken, genel konuşulanlar 'Bu veriyi nerede tutacağız?' oluyor. Bu sorunlar konuşulurken biz farklı bir şey konuşalım bugün : '**Bu veriyi A noktasından B noktasına en verimli nasıl taşıyacağız?**'. Klasik yöntemler hantallaşırken; Server-to-Server iletişimde hızın tanımı gRPC ile, Client-to-Server iletişimde esnekliğin tanımı ise GraphQL ile yeniden yazılıyor.

Bu yazıda, sadece teoride kalmayıp ellerimizi koda bulayacağız. Oluşturduğumuz mikroservisleri, BFF (Backend for Frontend) deseni altında nasıl topladığımızı inceleyeceğiz. Amacımız net: Client tarafında yükü azaltan, Server tarafında ise performansı maksimize eden, her domainin kendi işine baktığı, clientlerin data yüklerini azalttığı, scability yeteneği yüksek temiz bir mimari kurgulamak.

“**Ne Nedir?**” sorusuna geçmeden önce bir “**Mimari Felesefemizi**” bir konuşalım. İyi Okumalar.

## Mimari Felsefe

---

### **"Magnas inter opes inops",** Horace - **GraphQL, BFF ve gRPC Üçlemesi**

Horace’nin sözü buraya güzel gitti. Büyük zenginlik içinde fakirlik çekmemek gerek.

Bugün herkes "Data büyüyor, Big Data, bunu nereye sığdıracağız?" konuşuyor. Onlar onu konuşup çözüm üretirken biz burada "E biz bu veriyi oradan oraya nasıl taşıyacağız?" diye konuşalım. Bu işler biraz imece usulü birileri başka iş yaparken diğerler farklı “angaryaları” yapmalı.

İstatistiklere bakarsak web isteklerinin neredeyse **%90’ı hala REST** ile dönüyor. Yani sektörün büyük çoğunluğu HTTP üzerinden JSON paslaşmaca oynuyor. Hatta işin mutfağında servisler, cevapları "Event Streaming" ile önceden hazırlayıp tepside bekletiyor ama servis anı gelince işler karışıyor. Gelin şu akışa bir "Mimarın Dokunuşu"nu yapalım ve felsefemizi savunalım.

### 1. REST’ten GraphQL’e Geçiş

İlk durağımız istemci (client) tarafı. Yıllardır REST ile şöyle bir diyaloğumuz var:
**Client:** "Bana kullanıcının adını ver."
**REST API:** "Al sana kullanıcının adı, soyadı, annesinin kızlık soyadı, kan grubu, son giriş tarihi ve favori rengi."
**Client:** "Sağ ol ama bana sadece kullanıcı adı lazımdı..."

İşte bu "over-fetching" bu. Bu beladan kurtulmak için düşüncemizde **GraphQL** var. GraphQL, network tabındaki o "Content Download" sürelerini alıyor, her client’in ihtiyacı duyduğu veriyi, o koca responselar içerisinde ayıklayarak kendine lazım olan verileri kullanmamızı sağlayabilir. Başlangıç olarak güzel, **GraphQL.**

### 2. Kapıları Ayıralım: BFF (Backend for Frontend)

Şimdi elimizde güzel bir GraphQL yapısı var ama hala arkada tek bir devasa API Gateway var. Endüstrinin %80’i gibi biz de tüm trafiği (Web, Mobil, Desktop, 3. rd) aynı kapıya yığıyoruz. Buradan bir "trade-off" doğuyor. Herkesi aynı kapıdan sokmaya çalışmak, izdiham demektir.

Çözümümüz? **BFF (Backend for Frontend).**

Kısaca; Her client kendi API Gateway’ı olmasını önceleyen bir patterndir. Yani her client’in kendi kapıcısı olsun diyoruz. Mobil için `m.api.ornek.com`, web için [`w.api.ornek.com`](http://w.api.ornek.com) vs. Burada hemen şu aklıma geldi: *"E  GraphQL zaten veriyi filtreliyor, ben web endpoint'ine mobilden query atsam, az data isterim olur biter? Niye ekstra katman çıkardık?"* Olmaz bro. Çünkü olay sadece veri boyutu değil.  **Network Traffic, Business Domain, Accessibility ve Client Talent**. Bu yeteneklerin hepsi veri taşıma işleri ile doğrudan bağımlı.

**Bir Gerçek Hayat Senaryosu şöyle olsun:**
Şu an çalıştığım Kanada’nın dev bir telekomünikasyon firması, mobil trafik neredeyse "yok" hükmünde diye mobil uygulamasını komple kapattı. Herkes web'de. Ama dönelim Türkiye'ye... Türk Telekom’un web sitesine en son ne zaman girdiniz? İşlemlerin %85’i mobilden akıyor.

Şimdi BFF olmazsa; o %15’lik web trafiğini, %85’lik mobil trafiğinin olduğu otobana sokmak zorundasınız. Halbuki ayır gatewayleri; web trafiği kendi şeridinden, mobil kendi şeridinden aksın. Mobil Gateway yanarken, Web Gateway "Buralar çok sakin" diyerek ultra hızlı cevap dönsün.

**Trade-off:** Kod tekrarı. Evet, web için yazdığın endpoint’i bazen mobil için de yazacaksın. Sunucu maliyeti de cabası. Ekstradan bir sunucu daha açacaksın.

### 3. Backendsel İşler: Microservices ve gRPC

Geldik backend tarafına. Elimizde hayali bir "Rüya Takımı" var. Çok hevesli Junior’lar ve olayı yemiş bitirmiş Senior’lar... Ekip diyor ki: *"Abi her servisi farklı dilde yazalım!"*
Profesyonel hayatta genellikle *"Saçmalamayın, her yer Java/C# olacak"* denir ama biz bu senaryoda kendi kafamızda kurduğumuz bir düşünce deneyi biz öyle yapalım. Database normalize edilmiş, indexler havada uçuşuyor, kodlar optimize, resilience kurulmuş ,scability tam takır her şey harika. Peki bu servisler kendi aralarında nasıl konuşacak? REST ile mi? hayalimizde her yeri değiştirmek vardı

Hayır. Burada sahneye "Server-to-Server" ilişkilerin ağababası **gRPC** çıkıyor.

gRPC öyle bir şey ki; sanki uzaktaki sunucuda değil de, senin kendi kodunun içindeki bir fonksiyonu çağırıyormuşsun gibi hissettirir. Network trafiğiymiş, JSON parse etmekmiş... Bunlarla uğraşmazsın. Binary formatta veri taşır, REST'e göre 3 kata kadar daha hızlıdır.

**Trade-off:**

- Tarayıcılar (Browser) gRPC'yi doğrudan sevmez (Gerçi bizim BFF var, o halledecek).
- Proto dosyası yönetimi biraz can sıkabilir.
- Implementasyonu REST kadar "tak-çalıştır" değildir.

### Geri çekilip büyük resme bakmak:

Ve işte o yapı:

1. Client istekleri tek bir endpoint üzerinden **GraphQL** ile geliyor.
2. İstekleri karşılayan, trafiği izole eden **BFF API Gateway**'lerimiz var.
3. BFF arkada, işi yapan **Microservice**'lerle **gRPC** üzerinden jet hızıyla konuşuyor.
4. Her Microservice, **DDD (Domain Driven Design)** mantığıyla kendi çöplüğünde ötüyor.

Bonus olarak; madem ekip yenilikçi, ben de şu sıralar **Go** öğreniyorum. O zaman stack şöyle olsun:

- Bir servis **.NET Core** (Kurumsal hafıza için),
- Bir servis **NodeJS** (Hızlı prototip için),
- Bir servis **Go** (Yüksek performans ve benim öğrenme hevesim için).

Sonuç? Bakımı zor, öğrenme eğrisi yüksek ama performansı ve felsefesiyle *taş* gibi bir mimari.

Hadi şimdi **“Ne nedir?”** hızlıca bitirp demomuza geçelim.

## GraphQL

---

GraphQL, birden çok endpointi bir araya getirerek ve her cliente yalnızca ihtiyaç duyduğu verileri getirmesi için bir interface sağlayarak bu sorunların bazılarının çözülmesine yardımcı olur. Client sahibinin neye ihtiyaç duyduklarını tanımlamasına ve tam olarak ve yalnızca bunu almasına olanak tanır. Kısaca **verileri istemeye yarayan bir syntaxtır**.

### Schema

API'mızın iskeleti; hangi verilerin var olduğunu, tiplerini ve bunların birbirleriyle nasıl ilişkilendiğini tanımlayan ana sözleşmedir.

### Queries

Sunucudan veri çekerken kullandığımız, "bana tüm menüyü değil, sadece tatlıları getir" diyebildiğimiz okuma (read) işlemidir.

### Mutation

Veritabanında ekleme, güncelleme veya silme gibi bir değişiklik yapacağımız zaman devreye giren ve sunucunun durumunu değiştiren operasyondur.

### Resolver

Şemada tanımladığımız her bir alanın verisinin veritabanından mı yoksa başka bir servisten mi geleceğini belirleyen, işin mutfağındaki fonksiyondur.

### Subscribers

Sunucu ile istemci arasında sürekli açık bir hat (WebSocket) kurarak, veri değiştiği anda (örneğin gol olduğunda) canlı bildirim almamızı sağlayan yapıdır.

## BFF (Backend-for-frontend)

---

BFF, yukarıda bahsedilen over-fetching ve under-fetching problemlerine kalkan olması, her platformunun kendine ait service endpointin oluşturması, stateless çalışabilen ve microserviceler ile iletişime geçerek her microservice’nin kendi sorumluluğunu almasını sağlayan bir mimaridir.

| Pros | Cons |
| --- | --- |
| her microservice yalnızca kendi sorumluluğuna odaklanabilir | Kod tekrar yaratıyor. |
| her client için ağ protokolünü özelleştirebiliriz. | Sunucu maliyetini çoğaltıyor. |
| client ve server arasındaki ağ trafiğini azaltabiliriz. |  |
| Frontend için özelleşmiş basit ve tek endpoint bir servis sağlanabilir. |  |

## gRPC

---

Google’ın geliştirdiği Remote Procedure Call, yani başka bir servis ya da uzak sunucudaki bir metodu sanki kendi servisimizin metoduymuş gibi kullanabilmemizi sağlayan, server-to-server ilişkisindeki iletişimi kolay ve hızlıca sunan bir frameworktür. gRPC, HTTP/2 kullanan  bir haberleşme protokolüdür. Servisler kendi aralarında dataları binary olarak taşımaktadır.

### Protocol Buffer

protocol Buffer, gRPC servisleri arasında taşınan binary datayı serialization yapan haberleşme protokolüdür. Dil bağımsızdır. Streaming ile büyük data alış-verişi yapar. Multiplexingdir. - HTTP/1 de bir seferde bir istek, 1 response var iken HTTP/2 ile beraber protocol buffer dosyalar için tüm istekler tek seferde toplu olarak yapılabilmektedir. Böylece açılış hızı artmakta, süresi düşürülmektedir.

![1_HrdL83EKgzW7_Zj2pZ6Emw (1).png](https://onurozkir.com/images/1_HrdL83EKgzW7_Zj2pZ6Emw_(1).png)

Proto Buffer, compile için .`proto` dosyalarına ihtiyaç duyar. Proto dosyaları dil bağımsız olup kullanılacak methodları ve mesajları generate eder

- **Unary**: Client’ın servera tek bir istek gönderdiği ve tek bir yanıt aldığı en basit RPC türüdür.

  ![gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-2-300x149.png](https://onurozkir.com/images/gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-2-300x149.png)

- **Server’dan Client’a Streaming**: Bir client’ın istek attıktan sonra isteğine yanıt olarak server’ın stream başlatması ve istek atılan tüm mesajların client’a aktarılmasını içermektedir.

  ![gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-3.png](https://onurozkir.com/images/gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-3.png)

- **Client‘dan Server’a Streaming**: Client bir stream açarak tüm mesajları server’a gönderir, mesaj gönderimi bitince server tek bir mesaj halinde cevap döner.

  ![gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-4.png](https://onurozkir.com/images/gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-4.png)

- **Bi-directional streaming**: Çift yönlü streaming özelliği; client ve server birbirlerine tek bir mesaj ya da stream açabilir. İki streamde birbirinden bağımsız işler. Client ve server mesajları herhangi bir sırayla okuyabilir ve yazabilir.

  ![gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-5-300x152.png](https://onurozkir.com/images/gRPC-Nedir-Ne-Amacla-ve-Nasil-Kullanilir-5-300x152.png)


| Pros(gRPC) | Cons(Rest) |
| --- | --- |
| HTTP/2 | HTTP/1 |
| Protobuf | JSON/XML/Text |
| Browser desteği az. farklı browser’lar ve cihazlarda sorunlu | Tüm browser ve cihazları destekliyor |
| Rest isteklerine göre 3 kat daha hızlı |  |
| encoding ve decoding client tarafında gerçekleşir. sunucu maliyetini düşürür | sunucu ve taşıma maliyeti yüksek |
| Implemantation daha zor | implemantation kolay |

## Microservice Architecture & Demo

---

Demomuzu aşağıdaki görsele göre oluşturacağız

- BFF’ler NodeJS
- Microservisler .Net Core & Go & NodeJS olacak
- tüm projeyi dockerize edecek ve tüm değişiklikleri aynı anda ayağa kaldıracağız

### Mimari Görsel

![mermaid-diagram-2026-01-19-165458.png](https://onurozkir.com/images/mermaid-diagram-2026-01-19-165458.png)

### File System

Öncelikle dosya sistemimizi oluşuralım:

![Screenshot 2026-01-18 171000.png](https://onurozkir.com/images/Screenshot_2026-01-19_171000.png)

- **_shared**: Trade-off’larımızdan bir tanesidir. Yönetmesi zor birden fazla proto dosyası idi. Bunu şuan local’de ve _shared dosyası içerisinde tutalım. Profesyonel bir senaryoda bu proto dosyaları ayrı bir git submodule reposunda tutulmalı ve dockerize edilmiş uygulama publish anında bu repodan alarak uygulama içerisinde barındırmalı.

### Dockerize

Uygulamayı şuan monolith ve local deneme olduğu için tek bir docker-compose dosyası ile yöneteceğiz. Tüm env bilgileri ve container ilgileri bu docker-compose’de bulunacak

```yaml
version: '3.8'

services:
  # Users Service (.NET 9)
  users-service:
    build:
      context: .
      dockerfile: users-service/Dockerfile
    container_name: users-service
    ports:
      - "50051:50051"
    environment:
      - ASPNETCORE_URLS=http://+:50051

  # Posts Service (Go)
  # i am getting error when i provide the context as ., i dont understand why.
  posts-service:
    build:
      context: ./posts-service
      dockerfile: Dockerfile
    container_name: posts-service
    ports:
      - "50052:50052"

  # Comments Service (Node.js)
  comments-service:
    build:
      context: .
      dockerfile: comments-service/Dockerfile
    container_name: comments-service
    ports:
      - "50053:50053"

  # Web BFF (Node.js + Apollo)
  web-bff:
    build:
      context: .
      dockerfile: web-bff/Dockerfile
    container_name: web-bff
    ports:
      - "4000:4000"
    environment:
      - USERS_SERVICE_URL=users-service:50051
      - POSTS_SERVICE_URL=posts-service:50052
      - COMMENTS_SERVICE_URL=comments-service:50053
    depends_on:
      - users-service
      - posts-service
      - comments-service

  # Mobile BFF (Node.js - Apollo)
  mobile-bff:
    build:
      context: .
      dockerfile: mobile-bff/Dockerfile
    container_name: mobile-bff
    ports:
      - "4001:4001"
    environment:
      - USERS_SERVICE_URL=users-service:50051
      - POSTS_SERVICE_URL=posts-service:50052
      - COMMENTS_SERVICE_URL=comments-service:50053
    depends_on:
      - users-service
      - posts-service
      - comments-service

```

- USERS_SERVICE_URL için 50051, POSTS_SERVICE_URL için 50052, COMMENTS_SERVICE_URL için 50053 postlarını açtık ayrıca web-bff için 4000, mobile-bff için 4001 portunu kullanacağız.

*Not: yazının çok uzamaması için BFF configurationları web-bff ile anlatacağım sadece farklarından bahsedeceğim:*

### Web BFF & Mobile BFF

Öncelikle ihtiyacımız olan paketler:

```jsx
  "@apollo/server": "^4.11.0",
  "@grpc/grpc-js": "^1.14.3",
  "@grpc/proto-loader": "^0.8.0",
  "graphql": "^16.8.1"
```

`index.js` içerisinde [localhost](http://localhost):4000  üzerinde Apollo Server’ı ayağa kaldıralım:

```jsx
const { ApolloServer } = require('@apollo/server');
const typeDefs = require('./schema');
const resolvers = require('./resolvers');
const { startStandaloneServer } = require('@apollo/server/standalone');

async function startServer() {
    // Web BFF for Apollo Server
    const server = new ApolloServer({
        typeDefs,
        resolvers,
    });

    const { url } = await startStandaloneServer(server, {
        listen: { port: 4000 },
    });

    console.log(`Web BFF app listening on port: ${url}`);
}

startServer(); 

```

İşin buraya kadar kısmı AI vey documentation sayesinde yapılabilir. İhtiyaca yönelik değişim aşağıda `resolvers.js, schema.js ve grpc-client.js` ile başlıyor kod içeriisnde hepsini anlamaya çalışalım:

```jsx
// schema.js 

// burası graphQL'in kullanacağı query ve mutaion kısımlarını yapılandırıyor
// Her request & response değerleri için TypeDefinition belirlenmeli
// Ancak bu söz diziminde herşey type ile başlıyor. Bunları ayrıştıran pre-defined tanımlamalar
// Örnekte User, Comment, Post bir response&request typelarıdır Comment bu dönmeli, User bu gelmeli vs
// Ancak Query ve Mutation pre-defined tır ve 
// Query, GET endpointlerini
// Muration, PUT/POST/DELETE methodlarını temsil ediyor
// Örneğimizde post?id=[id] ve posts GET Endpointleri var iken
// createUser ve createPost ile POST methodları ile CRUD işlemler vardır
const typeDefs = `#graphql
  type User {
    id: ID!
    name: String
    email: String
  }

  type Comment {
    id: ID!
    text: String
    author_name: String
    post_id: String
  }

  type Post {
    id: ID!
    title: String
    content: String
    author: User
    comments: [Comment]
  }

  type Query {
    post(id: ID!): Post
    posts: [Post]
  }

  type Mutation {
    createUser(name: String!, email: String!): User
    createPost(title: String!, content: String!, authorId: ID!): Post
  }
`;
module.exports = typeDefs;

```

```jsx
// resolvers.js
// bir önceki schema.js'de belirlenen Query ve Mutation kısımları
// aggregate ve business logicleri işte buraya yapıyoruz. 
// Örneğin post(id: ID!): Post query'si kullanılacağında verilen id ile
// postClient.GetPost({ id } ...) kodunu çalıştır logici işte buraya yapılacak. 
const { userClient, postClient, commentClient } = require('./grpc-client');

const resolvers = {
    Query: {
        post: async (_, { id }) => {
            return new Promise((resolve, reject) => {
                postClient.GetPost({ id }, (err, response) => {
                    if (err) return reject(err);
                    resolve(response);
                });
            });
        },
        posts: async () => {
            return new Promise((resolve, reject) => {
                postClient.GetPosts({}, (err, response) => {
                    if (err) return reject(err);
                    resolve(response.posts);
                });
            });
        }
    },
    Mutation: {
        createUser: async (_, { name, email }) => {
            return new Promise((resolve, reject) => {
                userClient.CreateUser({ name, email }, (err, response) => {
                    if (err) return reject(err);
                    resolve(response);
                });
            });
        },
        createPost: async (_, { title, content, authorId }) => {
            return new Promise((resolve, reject) => {
                // Post service
                postClient.CreatePost({ title, content, author_id: authorId }, (err, response) => {
                    if (err) return reject(err);
                    resolve(response);
                });
            });
        }
    },
    // Burada daha önce schema.js' de belirtilmeyen Post diye bir şey var bu da nesi?
    // Burası İç içe sorguları yapmamızı sağlıyor
    // Buradaki örnekte post(id: ID!): Post query'si Post dönüyor beki bakalım Post ne dönüyor
    //   type Post {
    //      id: ID!
    //      title: String
    //      content: String
    //      author: User
    //      comments: [Comment]
    //    }
    // görüldüğü üzere comment ve author gibi hem comment-service'in yönettiği
    // hem de user-servisin yönettiği dtaları dönmesi lazım
    // işte gRPC burada devreye giriyor ve Post değerinden gelen id ile hem userClient ile
    // user microservice'e, hem de id  ile comment-service giderek bir bütünleşik data oluşturuyor.
    Post: {
        author: async (parent) => {

            console.log("Post Parent:", parent);

            if (!parent.author_id) return null;

            return new Promise((resolve, reject) => {
                userClient.GetUser({ id: parent.author_id }, (err, response) => {
                    if (err) {
                        console.error("Error fetching user:", err);
                        resolve(null); // error de  null return et
                    }
                    resolve(response);
                });
            });
        },
        comments: async (parent) => {
            return new Promise((resolve, reject) => {
                commentClient.GetCommentsByPostId({ id: parent.id }, (err, response) => {
                    if (err) {
                        console.error("Error fetching comments:", err);
                        resolve([]);
                    }
                    resolve(response.comments || []);
                });
            });
        }
    }
};
module.exports = resolvers;

```

```jsx
**// grpc-client.js

const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const path = require('path');

// Download proto file
// https://grpc.io/docs/languages/node/basics/#loading-service-descriptors-from-proto-files
const loadProto = (filename) => {
    const packageDefinition = protoLoader.loadSync(
        path.join(__dirname, 'protos', filename),
        { keepCase: true, longs: String, enums: String, defaults: true, oneofs: true }
    );
    return grpc.loadPackageDefinition(packageDefinition);
};

// Proto define
const userProto = loadProto('user.proto').user;
const postProto = loadProto('post.proto').post;
const commentProto = loadProto('comment.proto').comment;

// create gRPC client
// we get service url from the environment within docker-compose
// octopus can be used in configuration management
const userClient = new userProto.UserService(
    process.env.USERS_SERVICE_URL || 'users-service:50051',
    grpc.credentials.createInsecure()
);

const postClient = new postProto.PostService(
    process.env.POSTS_SERVICE_URL || 'posts-service:50052',
    grpc.credentials.createInsecure()
);

const commentClient = new commentProto.CommentService(
    process.env.COMMENTS_SERVICE_URL || 'comments-service:50053',
    grpc.credentials.createInsecure()
);

module.exports = { userClient, postClient, commentClient };**

```

## Hegelci Diyalekti: Tez, Antitez ve Sentez

---

Her mimari karar bir takastır (trade-off). Horace’nin dediği gibi "Büyük zenginlik içinde fakirlik çekmemek" için, kurduğumuz bu yapıyı masaya yatıralım. Neden bu kadar zahmete girdik?

### 1. Tez: "İletişim, Verinin Şekline Göre Eğilip Bükülmelidir"

**Argüman:** Tek bir iletişim yöntemi (REST/JSON) evrensel bir çözüm olamaz. Verinin yolculuğu, geçtiği tünelin yapısına uygun olmalıdır.

- **Protokol :** Client ile Server arasındaki ilişki "Talepkar ve Seçici"dir; burada GraphQL'in esnekliği kraldır. Server-toServer arasındaki ilişki ise "Emir-Komuta ve Hız" odaklıdır; burada gRPC'nin binary disiplini gereklidir.
- **Network Isolation (BFF):** Bir otobanda kamyonları, motosikletleri ve yayaları aynı şeritten götüremezsiniz. BFF, dijital trafiği şeritlerine ayırır. Mobilin kısıtlı bant genişliği ile Web'in geniş ekran iştahını aynı API Gateway'de çarpıştırmak, mimari bir tembelliktir. Biz bu tembelliği reddedip, her istemciye özel "şerit" hizmeti sunuyoruz.

### 2. Antitez: "Dağıtık Yapılar, Yönetilemez Bir Kaos Yaratır"

**Argüman:** "Basitlik en büyük erdemdir" ilkesinden uzaklaşıyoruz. Bu kadar katman, başımızı ağrıtmaz mı?

- **Operasyonel "Angarya":** BFF deseninde bahsettiğimiz kod tekrarı bir gerçektir. Web için yazdığımız bir "business logic" veya veri birleştirme işini, bazen mobil BFF için de kopyalamak zorunda kalacağız.
- **Contract Testing:** gRPC harika ama her servis güncellemesinde `.proto` dosyalarını güncellemek, versiyonlamak ve tüm servislere dağıtmak, REST'in "yazdım-oldu" rahatlığının yanında tam bir bürokrasidir.
- **Network Latency:** Eskiden tek bir monolith uygulamanın içinde, RAM üzerinden milisaniyeden kısa sürede dönen fonksiyonlar, şimdi ağ üzerinden birbirini çağırıyor. Her ne kadar gRPC hızlı desek de, fizik kuralları gereği bir "network hop" maliyeti ekliyoruz.

### 3. Sentez: "Büyük Zenginliği Yönetmek İçin Kontrollü Zahmet"

**Sonuç:** Horace'nin korktuğu o "zenginlik içinde fakirliği" yaşamamak için bu zahmete değer.

- **Manage Chaos:** Evet, BFF kod tekrarı yaratır ama **Dependency Hell** kurtarır.
- **Hızın Bedeli:** Evet, gRPC için proto dosyalarıyla uğraşıyoruz ama bunun karşılığında JSON parse etmekle harcanan CPU gücünü geri kazanıyoruz ve veri boyutunu küçültüyoruz. "Angarya" dediğimiz o proto yönetimi, aslında servisler arası **Type Safety** sağlayarak, runtime’da patlayacak hataları derleme zamanında yakalamamızı sağlıyor.
- **Nihai Denge:** Client, GraphQL ile "Sana özel hissettiren" bir deneyim sunarken, Backend gRPC ile askeri bir disiplin kurduk.
- **Strict Contracts:** Proto dosyaları sayesinde, Go ve .NET gibi farklı diller birbirleriyle konuşurken "Acaba şu alan string mi geldi, int mi?" endişesi yaşamaz. Bu, monolith sistemlerdeki "Type Safety" konforunu dağıtık yapıya taşır.

---

### Bu Mimariyi Ne Zaman Seçmelisin?

Bu yapı her proje için değildir. Aşağıdaki kontrol listesi "Evet" ise bu mimari sizin ilacınızdır:

1. **Çoklu Vitrin:** Sistemin hem Web, hem Mobil, hem de 3. parti entegrasyonları gibi çok farklı karakterde istemcileri varsa (BFF Şart).
2. **Yüksek Trafik ve İç İletişim:** Mikroservisleriniz kendi aralarında çok sık konuşuyorsa ve "JSON Serilization/Deserialization" maliyeti sunucularınızı yoruyorsa (gRPC Şart).
3. **Veri Zenginliği:** İstemcileriniz (Client), her ekranda çok farklı veri kombinasyonlarına ihtiyaç duyuyor ve sürekli "Backendçilere yeni endpoint açtırmak" için ticket açıyorsa (GraphQL Şart).
4. **Geniş Takımlar:** Backend ekibiniz büyüdüyse ve farklı dillerde uzmanlaşmış alt ekipleriniz varsa.

Eğer tek bir web siteniz varsa ve günde 500 kişi giriyorsa; Horace’yi rahat bırakın ve REST ile devam edin. Ama amacınız veriyi bir sanat gibi işlemek ve taşımaksa, mimarinin dokunuşu budur.

## Demo

---

[https://github.com/onurozkir/graphql-grpc-bff-microservice-architecture](https://github.com/onurozkir/graphql-grpc-bff-microservice-architecture)

## Sample request:

web-bff

```graphql
query PostsQuery() {
  posts {
    author {
      email
      id
      name
    }
    comments {
      post_id
      author_name
      text
      id
    }
    content
    title
    id
  }
}

query PostQuery($postId: ID!) {
  post(id: "101") {
    id
    title
    content
    author {
      email
      name
      id
    }
    comments {
      post_id
      author_name
      text
      id
    }
  }
}

mutation CreateUser($name: String!, $email: String!) {
  createUser(name: "onur", email: "onur@temp.com") {
    id
    name
    email
  }
}

mutation CreatePost($title: String!, $content: String!, $authorId: ID!) {
  createPost(title: "test title-1", content: "lorem ipsum dolar sit amet-1", authorId: "1") {
    id
    title
    content
    author {
      email
      name
      id
    }
  }
}

```

mobile-bff

```graphql
query PostQuery($postId: ID!) {
  post(id: "102") {
    title
    content
  }
  posts {
    title
    author {
      name
    }
    comments {
      author_name
      text
    }
    content
    id
  }
}

query AuthorDetails($authorDetailsAuthorId2: ID!) {
  authorDetails(authorId: "1") {
    user {
      name
      id
    }
    commentHistory {
      post_id
      author_name
      text
      id
    }
  }
}

mutation CreatePost($title: String!, $content: String!, $authorId: ID!) {
  createPost(title: "test", content: "test content", authorId: "1") {
    id
    title
    content
    author {
      name
      id
    }
  }
}

```

## Kaynaklar

---

[So what's this GraphQL thing I keep hearing about?](https://www.freecodecamp.org/news/so-whats-this-graphql-thing-i-keep-hearing-about-baf4d36c20cf)

[gRPC](https://grpc.io/)

[A query language for your API](https://graphql.org/)

[Introduction to Apollo Server](https://www.apollographql.com/docs/apollo-server/)

[Some thoughts on GraphQL vs. BFF](https://philcalcado.com/2019/07/12/some_thoughts_graphql_bff.html)

[When GraphQL meets gRPC... 😍](https://medium.com/@svengau/when-graphql-meets-grpc-3e9729d32e05)

[Introducing gRPC, a new open source HTTP/2 RPC Framework](https://opensource.googleblog.com/2015/02/introducing-grpc-new-open-source-http2.html)

[gRPC Nedir? Ne Amaçla ve Nasıl Kullanılır?](https://www.gencayyildiz.com/blog/grpc-nedir-ne-amacla-ve-nasil-kullanilir/)
