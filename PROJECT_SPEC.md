# RAGProof

## Production-Ready RAG Verification Platform

RAGProof; kullanıcıların URL üzerinden dokümanları sisteme aktarmasını, dokümanları otomatik olarak analiz edip anlamlı parçalara (chunk) ayırmasını, embedding'lerini oluşturup OpenSearch üzerinde indekslemesini ve LLM tarafından oluşturulan cevapların kaynak dokümanlarla doğrulanmasını sağlayan uçtan uca bir RAG platformudur.

Proje özellikle **Türkçe mevzuat ve hukuki dokümanlar** üzerinde çalışacak şekilde tasarlanacaktır.

---

# 1. Projenin Amacı

Sistem üç temel problemi çözecek:

1. Web üzerindeki dokümanları otomatik olarak RAG sistemine aktarmak.
2. Dokümanları RAG için kaliteli ve anlamlı chunk'lara dönüştürmek.
3. LLM'in ürettiği cevapların gerçekten kaynak doküman tarafından desteklenip desteklenmediğini kontrol etmek.

Örnek:

```text
URL
 ↓
Web Scraper
 ↓
Document Parser
 ↓
Text Cleaner
 ↓
Legal Chunker
 ↓
Embedding
 ↓
OpenSearch
 ↓
Hybrid Retrieval
 ↓
LLM
 ↓
Answer
 ↓
Claim Extraction
 ↓
RAG Verifier
 ↓
Evidence / Confidence
```

---

# 2. Örnek Kullanım

Kullanıcı arayüzden aşağıdaki URL'yi girer:

```text
https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7068&MevzuatTur=1&MevzuatTertip=5
```

Sistem:

* URL'yi indirir.
* HTML içeriğini parse eder.
* Gereksiz HTML, menü, footer vb. alanları temizler.
* Mevzuat yapısını algılar.
* MADDE bazlı chunk'lar oluşturur.
* Her chunk için embedding üretir.
* OpenSearch'e kaydeder.
* Dokümanın indeksleme durumunu UI üzerinden gösterir.

---

# 3. Temel Özellikler

## 3.1 URL ile Doküman Ekleme

UI üzerinde kullanıcı:

```text
URL:
[ https://www.mevzuat.gov.tr/... ]

Chunk Strategy:
[ Legal ]

Embedding Model:
[ BGE-M3 ]

[ Ingest Document ]
```

şeklinde doküman ekleyebilmelidir.

Sistem aynı URL'nin daha önce indekslenip indekslenmediğini kontrol etmelidir.

---

# 4. Document Ingestion

Ingestion işlemi API request'i içerisinde uzun süre çalıştırılmamalıdır.

Önerilen yapı:

```text
Frontend
   ↓
API
   ↓
RabbitMQ
   ↓
Ingestion Worker
   ↓
Fetcher
   ↓
Parser
   ↓
Cleaner
   ↓
Chunker
   ↓
Embedding
   ↓
OpenSearch
```

API sadece ingestion job oluşturmalıdır.

Örnek:

```http
POST /api/v1/documents/ingest
```

Request:

```json
{
  "url": "https://www.mevzuat.gov.tr/...",
  "chunk_strategy": "legal",
  "embedding_model": "bge-m3"
}
```

Response:

```json
{
  "job_id": "job_123",
  "status": "queued"
}
```

---

# 5. Document Fetcher

Fetcher URL'den içeriği almalıdır.

Desteklenmesi gereken içerikler:

* HTML
* PDF
* Plain text

İlk versiyonda HTML desteği yeterlidir.

Fetcher:

* timeout kullanmalı
* retry mekanizmasına sahip olmalı
* HTTP status kontrolü yapmalı
* Content-Type kontrolü yapmalı
* maximum response size belirlemeli
* User-Agent göndermeli

Örnek:

```text
URL
 ↓
HTTP GET
 ↓
200 OK
 ↓
HTML
```

Başarısız durumda:

```text
FETCH_FAILED
```

job status'u oluşturulmalıdır.

---

# 6. HTML Cleaning

Ham HTML doğrudan embedding'e gönderilmemelidir.

Temizlenmesi gereken alanlar:

* navigation
* header
* footer
* menu
* script
* style
* reklam
* cookie banner
* gereksiz linkler

Sonuç:

```text
HAM HTML
   ↓
HTML Parser
   ↓
Main Content Extraction
   ↓
Clean Text
```

---

# 7. Legal Chunking

Projenin en önemli bölümlerinden biri legal-aware chunking'dir.

Normal karakter bazlı chunking yerine hukuki dokümanın yapısı korunmalıdır.

Örneğin:

```text
MADDE 1- ...

MADDE 2- ...

MADDE 3- ...
```

her madde mümkün olduğunca ayrı chunk olmalıdır.

Örnek:

```json
{
  "chunk_id": "7068-madde-8",
  "document_id": "7068",
  "article_number": 8,
  "content": "MADDE 8- ..."
}
```

Bir madde çok uzunsa:

```text
MADDE 8
   ↓
MADDE 8 / PART 1
MADDE 8 / PART 2
MADDE 8 / PART 3
```

şeklinde bölünebilir.

Ancak her alt chunk metadata içerisinde aynı madde numarasını taşımalıdır.

---

# 8. Chunk Metadata

Her chunk aşağıdaki metadata'ları mümkün olduğunca içermelidir:

```json
{
  "document_id": "7068",
  "chunk_id": "7068-madde-8",
  "source_url": "https://www.mevzuat.gov.tr/...",
  "title": "7068 Sayılı Kanun",
  "document_type": "kanun",
  "law_number": 7068,
  "article_number": 8,
  "chapter": null,
  "chunk_index": 8,
  "content": "MADDE 8- ..."
}
```

Metadata RAG retrieval ve citation için kullanılacaktır.

---

# 9. Embedding

Chunk'ların embedding'i oluşturulacaktır.

Örnek:

```text
Chunk
 ↓
Embedding Model
 ↓
Vector
 ↓
OpenSearch
```

Embedding model configurable olmalıdır.

Örneğin:

```text
BGE-M3
```

Ancak sistem tek bir modele bağımlı tasarlanmamalıdır.

---

# 10. OpenSearch

OpenSearch ana retrieval katmanı olacaktır.

Index:

```text
rag_documents
```

Örnek document:

```json
{
  "document_id": "7068",
  "chunk_id": "7068-madde-8",
  "source_url": "https://www.mevzuat.gov.tr/...",
  "title": "7068 Sayılı Kanun",
  "article_number": 8,
  "content": "MADDE 8- ...",
  "embedding": []
}
```

Vector alanı OpenSearch vector/k-NN desteği ile indekslenmelidir.

---

# 11. Hybrid Search

Sistem sadece vector search kullanmamalıdır.

İki retrieval yöntemi kullanılmalıdır:

```text
User Query
    │
    ├───────────────┐
    ▼               ▼
Vector Search    BM25 Search
    │               │
    └───────┬───────┘
            ▼
           RRF
            │
            ▼
      Ranked Results
```

Vector search:

* semantic similarity

BM25:

* exact terms
* kanun numarası
* madde numarası
* özel hukuk terimleri

için kullanılacaktır.

Sonuçlar RRF veya benzer bir ranking yöntemiyle birleştirilecektir.

---

# 12. RAG Question Answering

Kullanıcı UI üzerinden soru sorabilmelidir.

Örnek:

```text
7068 sayılı Kanuna göre meslekten çıkarma cezası
hangi durumlarda uygulanır?
```

Pipeline:

```text
Question
 ↓
Embedding
 ↓
Hybrid Search
 ↓
Top K Chunks
 ↓
Context
 ↓
LLM
 ↓
Answer
```

LLM cevabında mümkün olduğunca kaynak gösterilmelidir.

Örneğin:

```text
Meslekten çıkarma cezası ... durumlarda uygulanır.

Kaynak:
7068 Sayılı Kanun - Madde 8
```

---

# 13. RAG Verifier

Projenin ana özelliği RAG Verifier'dır.

LLM'in ürettiği cevap doğrudan güvenilir kabul edilmemelidir.

Cevap claim'lere ayrılır.

Örnek:

```text
Answer

"X davranışı meslekten çıkarma cezasını gerektirir.
Bu ceza Madde 8 kapsamında düzenlenmiştir.
Ayrıca ilgili personelin görevine son verilir."
```

Sistem:

```text
Answer
 ↓
Claim Extraction
 ↓
Claim 1
Claim 2
Claim 3
```

Her claim için kaynak aranır.

---

# 14. Claim Verification

Örnek sonuç:

```json
{
  "claim": "X davranışı meslekten çıkarma cezasını gerektirir.",
  "supported": true,
  "confidence": 0.94,
  "evidence": [
    {
      "document_id": "7068",
      "article_number": 8,
      "score": 0.94
    }
  ]
}
```

Desteklenmeyen claim:

```json
{
  "claim": "Personelin görevine otomatik olarak son verilir.",
  "supported": false,
  "confidence": 0.31,
  "evidence": []
}
```

UI'da:

```text
✓ Supported
⚠ Weak Evidence
✕ Unsupported
```

olarak gösterilmelidir.

---

# 15. Verifier Score

Cevap için genel bir verification score hesaplanmalıdır.

Örneğin:

```text
Verified Claims: 8
Unsupported Claims: 1

Verification Score: 88.9%
```

Bu skor kullanıcıya gösterilmelidir.

Skorun nasıl hesaplandığı backend'de deterministik ve dokümante edilmiş olmalıdır.

---

# 16. UI

Frontend modern bir dashboard yapısına sahip olmalıdır.

Ana sayfalar:

```text
Dashboard
Documents
Ingestion Jobs
Search
RAG Chat
Verifier
Settings
```

---

# 17. Dashboard

Dashboard'da:

```text
Documents
1,284

Chunks
248,921

Embeddings
248,921

Queries
8,421

Verified Answers
7,932

Average Verification Score
94.2%
```

gibi metrikler gösterilmelidir.

Ayrıca son ingestion job'ları gösterilmelidir.

---

# 18. Documents Page

Doküman listesi:

```text
Document
Type
Chunks
Status
Created
Actions
```

Örnek:

```text
7068 Sayılı Kanun
KANUN
184 chunks
INDEXED
2026-08-29
[View]
```

Dokümana tıklandığında:

* URL
* başlık
* metadata
* chunk sayısı
* embedding durumu
* ingestion status

gösterilmelidir.

---

# 19. Ingestion Job Page

Her ingestion işleminin durumu izlenmelidir.

Status:

```text
QUEUED
FETCHING
PARSING
CLEANING
CHUNKING
EMBEDDING
INDEXING
COMPLETED
FAILED
```

Progress bar:

```text
Fetching       ✓
Parsing        ✓
Cleaning       ✓
Chunking       ✓
Embedding      ███████░░░ 70%
Indexing       -
```

---

# 20. Search UI

Kullanıcı OpenSearch üzerinde arama yapabilmelidir.

```text
Search:
[ meslekten çıkarma cezası ]

[ Hybrid Search ]
```

Sonuç:

```text
MADDE 8
Score: 0.94

...

Source:
7068 Sayılı Kanun
```

Kullanıcı chunk'ın tamamını görebilmelidir.

---

# 21. RAG Chat UI

Chat ekranında:

```text
User:
7068 sayılı Kanuna göre hangi durumlarda
meslekten çıkarma cezası uygulanır?

Assistant:
...

Sources:

[ MADDE 8 ]
[ MADDE 9 ]
[ MADDE 10 ]
```

Source'a tıklanınca ilgili chunk açılmalıdır.

---

# 22. Verifier UI

Verifier ekranı:

```text
Question
────────────────────────

Answer
────────────────────────

Verification Score
94%

Claims

✓ Claim 1
  Evidence: MADDE 8
  Score: 0.94

✓ Claim 2
  Evidence: MADDE 9
  Score: 0.91

⚠ Claim 3
  Evidence: MADDE 10
  Score: 0.61

✕ Claim 4
  No supporting evidence
```

Bu ekran projenin en önemli UI ekranlarından biri olacaktır.

---

# 23. Backend API

Temel endpoint'ler:

```text
POST   /api/v1/documents/ingest
GET    /api/v1/documents
GET    /api/v1/documents/{id}
DELETE /api/v1/documents/{id}

GET    /api/v1/jobs
GET    /api/v1/jobs/{id}

POST   /api/v1/search

POST   /api/v1/rag/query

POST   /api/v1/verifier/check
```

---

# 24. Önerilen Teknoloji Stack

## Frontend

```text
Next.js
TypeScript
TailwindCSS
shadcn/ui
```

## Backend

```text
Python
FastAPI
Pydantic
```

## Async Processing

```text
RabbitMQ
Workers
```

## Search

```text
OpenSearch
```

## Cache

```text
Redis
```

## Database

```text
PostgreSQL
```

PostgreSQL:

* users
* documents
* ingestion jobs
* configurations
* verifier results

için kullanılabilir.

OpenSearch:

* chunks
* embeddings
* retrieval

için kullanılmalıdır.

---

# 25. Docker

Tüm servisler Docker Compose ile ayağa kaldırılabilmelidir.

Örnek:

```text
docker compose up -d
```

Servisler:

```text
frontend
backend
worker
postgres
redis
rabbitmq
opensearch
```

---

# 26. Proje Klasör Yapısı

Önerilen yapı:

```text
ragproof/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   └── types/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   ├── rag/
│   │   ├── verifier/
│   │   └── ingestion/
│   │
│   └── tests/
│
├── worker/
│   ├── fetcher/
│   ├── parser/
│   ├── chunker/
│   ├── embedding/
│   └── indexing/
│
├── infrastructure/
│   ├── docker/
│   └── opensearch/
│
├── docker-compose.yml
├── README.md
└── PROJECT_SPEC.md
```

---

# 27. Production Gereksinimleri

Sistem production mantığıyla tasarlanmalıdır.

Dikkat edilmesi gerekenler:

* retry
* timeout
* idempotency
* logging
* structured logging
* error handling
* health checks
* rate limiting
* job status tracking
* duplicate document detection
* configurable chunk size
* configurable embedding model
* OpenSearch index management
* RabbitMQ dead-letter queue
* monitoring

---

# 28. Idempotency

Aynı URL ikinci kez gönderildiğinde sistem aynı dokümanı tekrar indekslememelidir.

Örneğin:

```text
URL
 ↓
SHA256
 ↓
document_hash
```

oluşturulabilir.

Aynı hash varsa:

```text
DOCUMENT_ALREADY_EXISTS
```

dönmelidir.

---

# 29. Observability

Sistem log üretmelidir.

Örnek:

```text
INGESTION_STARTED
DOCUMENT_FETCHED
DOCUMENT_PARSED
CHUNKS_CREATED
EMBEDDING_STARTED
INDEXING_STARTED
INGESTION_COMPLETED
```

Her işlemde:

```text
request_id
job_id
document_id
duration
status
error
```

gibi bilgiler tutulmalıdır.

---

# 30. Testler

Test edilmesi gereken bölümler:

### Unit Tests

```text
HTML Cleaner
Legal Chunker
Metadata Extractor
Claim Extractor
Verifier
```

### Integration Tests

```text
PostgreSQL
RabbitMQ
OpenSearch
Embedding
```

### End-to-End

```text
URL
 ↓
Ingestion
 ↓
OpenSearch
 ↓
Question
 ↓
RAG
 ↓
Verifier
```

pipeline'ı uçtan uca test edilmelidir.

---

# 31. MVP

İlk versiyonda aşağıdaki özellikler yeterlidir:

### Backend

* URL ingestion
* HTML parser
* legal chunker
* embedding
* OpenSearch indexing
* hybrid search
* RAG endpoint
* verifier endpoint

### Frontend

* Dashboard
* Documents
* Add URL
* Ingestion status
* RAG Chat
* Verifier

### Infrastructure

* Docker Compose
* PostgreSQL
* Redis
* RabbitMQ
* OpenSearch

---

# 32. İlk Demo Senaryosu

Demo sırasında:

### 1.

UI'dan URL gir:

```text
https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=7068&MevzuatTur=1&MevzuatTertip=5
```

### 2.

Sistem:

```text
Fetching ✓
Parsing ✓
Cleaning ✓
Chunking ✓
Embedding ✓
Indexing ✓
```

### 3.

Documents ekranında:

```text
7068 Sayılı Kanun
184 Chunks
INDEXED ✓
```

### 4.

Chat ekranında soru sor:

```text
7068 sayılı Kanuna göre meslekten çıkarma cezası
hangi durumlarda uygulanır?
```

### 5.

RAG cevap üretir.

### 6.

Verifier cevabı claim'lere böler.

### 7.

Her claim için:

```text
Supported
Confidence
Evidence
Source
Article
```

gösterilir.

Bu demo, projenin **URL ingestion + RAG + OpenSearch + LLM + verification + UI** özelliklerinin tamamını tek akışta göstermelidir.

---

# 33. Geliştirme Prensibi

Kod geliştirilirken öncelik:

```text
Correctness
>
Maintainability
>
Observability
>
Performance
>
UI Polish
```

olmalıdır.

Kod mümkün olduğunca modüler tasarlanmalı ve ingestion, retrieval ve verification birbirinden bağımsız servis/modül olarak geliştirilebilmelidir.

LLM veya embedding sağlayıcısı değiştirilmek istendiğinde tüm sistemi değiştirmek gerekmemelidir.

Örneğin:

```text
EmbeddingProvider
    ├── BGE
    ├── OpenAI
    └── LocalModel
```

şeklinde abstraction kullanılabilir.

Aynı yaklaşım LLM provider için de uygulanmalıdır.

---

# 34. Başarı Kriterleri

MVP başarılı sayılabilmesi için:

* URL'den doküman alınabilmeli.
* Doküman temizlenebilmeli.
* Legal-aware chunk oluşturulabilmeli.
* Chunk embedding oluşturulabilmeli.
* OpenSearch'e indekslenebilmeli.
* Hybrid search çalışmalı.
* RAG cevap oluşturabilmeli.
* Cevap claim'lere ayrılabilmeli.
* Claim'ler kaynaklarla doğrulanabilmeli.
* UI üzerinden tüm süreç izlenebilmeli.
* Sistem Docker Compose ile çalıştırılabilmeli.

---

# 35. Projenin Nihai Hedefi

RAGProof yalnızca bir chatbot değildir.

Amaç:

> **Kaynak dokümanları otomatik olarak indeksleyen, RAG üzerinden cevap üreten ve üretilen cevabın kaynaklar tarafından desteklenip desteklenmediğini ölçen production-ready bir RAG verification platformu oluşturmak.**

Sistem ileride:

* mevzuat
* şirket dokümanları
* teknik dokümantasyon
* akademik makaleler
* kurum içi bilgi tabanları

gibi farklı veri kaynaklarını destekleyecek şekilde genişletilebilir.
