# CareerCompass Full Architecture Connection Report

## Executive Summary

This document provides a complete technical report on how the **Frontend (React/Vite)**, **Backend (Spring Boot)**, and **Database (H2/MySQL + PostgreSQL)** are interconnected in the CareerCompass system. The architecture follows a **three-tier microservices pattern** with an additional **AI/Data Analysis Service (FastAPI)** for NLP/ML workloads.

---

## 1. System Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            USER (Browser)                                        │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React + Vite)                                  │
│  Port: 5173 (dev) | URL: http://localhost:5173                                  │
│  └─ TypeScript + React 19 + React Router 7                                      │
│  └─ Communicates ONLY with Backend via REST API                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
                                         │
                    ┌────────────────────┴────────────────────┐
                    │         HTTP/REST + JWT Bearer Token    │
                    ▼                                         ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      BACKEND (Spring Boot 3.3.4 + Java 17)                      │
│  Port: 8080 | URL: http://localhost:8080                                        │
│  └─ Security Layer (JWT, BCrypt, Role-based Access Control)                     │
│  └─ Business Layer (Controllers → Services → Repositories)                      │
│  └─ Integration Layer (WebClient → AI Service)                                  │
│  └─ Data Access Layer (JPA/Hibernate + Flyway Migrations)                       │
└─────────────────────────────────────────────────────────────────────────────────┘
                    │                                         │
          ┌─────────┴─────────┐                     ┌─────────┴─────────┐
          ▼                   ▼                     ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  H2 Database     │ │  PostgreSQL      │ │  File Storage    │ │  AI Service      │
│  (dev profile)   │ │  (prod/AI svc)   │ │  (local volume)  │ │  (FastAPI)       │
│  Port: N/A       │ │  Port: 5433      │ │  Path: uploads/  │ │  Port: 8000      │
│  File: /app/data │ │  DB: careercompass│ │  learning-       │ │  Internal URL:   │
│  careercompass   │ │  _ai             │ │  outcomes        │ │  http://ai-      │
└──────────────────┘ └──────────────────┘ └──────────────────┘ │  service:8000    │
                                                              └──────────────────┘
```

---

## 2. Frontend ↔ Backend Connection

### 2.1 Network Configuration

| Environment | Frontend URL | Backend API URL | Communication |
|-------------|--------------|-----------------|---------------|
| **Development (Docker)** | `http://localhost:5173` | `http://localhost:8080` | `VITE_API_BASE_URL=http://localhost:8080` |
| **Development (Local)** | `http://localhost:5173` | `http://localhost:8080` | `.env.development` |
| **Production** | `https://app.careercompass.com` | `https://api.careercompass.com` | Configured via env |

### 2.2 Frontend API Client (`frontend/src/api/client.ts`)

**Base URL Resolution:**
```typescript
const BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';
```

**Key Features:**
- **Typed Error Handling**: Single `ApiError` class for all backend errors (400, 401, 403, 404, 500)
- **Network/Timeout Errors**: Distinct `NetworkError` and `TimeoutError` classes
- **Per-Operation Timeouts**: Configurable deadlines for AI-backed operations
  - Transcript: 45s (NFR-PERF-02)
  - Dashboard: 30s
  - Recommendations: 30s
  - Quiz: 45s (NFR-PERF-04)
  - Job Matches: 60s
  - Default CRUD: 15s

**Authentication Flow:**
```typescript
// Token sent via Authorization header
if (token) headers['Authorization'] = `Bearer ${token}`;
```

**CORS Handling:**
- Frontend makes direct browser requests to backend
- Backend CORS config allows `http://localhost:5173` and `http://localhost:3000`

### 2.3 Frontend Authentication (`frontend/src/auth/`)

**Session Management:**
- JWT stored in `localStorage` under key `careercompass.session`
- Session includes: `token`, `role`, `userId`, `email`, `expiresAt`
- Auto-expiry detection via `setTimeout` (max 32-bit ms delay)

**Auth Context (`AuthProvider.tsx`):**
```typescript
// Loads session on mount
const [session, setSession] = useState<Session | null>(() => loadSession());

// Sign in: stores token + sets state
const signIn = (auth: AuthResponse) => {
  const next = toSession(auth);
  saveSession(next);
  setSession(next);
};

// Sign out: clears local first, then calls backend logout
const signOut = async () => {
  clearSession();
  setSession(null);
  await authApi.logout(token); // Best effort
};
```

**Protected Routes:**
- `ProtectedRoute.tsx` wraps pages requiring authentication
- Role-based access via `roles.ts` and `useAuth.ts` hook

### 2.4 API Endpoints Consumed by Frontend

| Domain | Endpoint Prefix | Auth Required | Roles |
|--------|-----------------|---------------|-------|
| Auth | `/api/auth/**` | No (except logout) | All |
| Reference Data | `/api/reference/**` | Yes | All authenticated |
| Job Seeker | `/api/job-seekers/**` | Yes | JOB_SEEKER |
| Content Manager | `/api/content-managers/**` | Yes | CONTENT_MANAGER |
| Employer | `/api/employers/**` | Yes | EMPLOYER |
| Expert | `/api/experts/**` | Yes | EXPERT |
| Admin | `/api/admin/**` | Yes | ADMIN |

---

## 3. Backend ↔ Database Connection

### 3.1 Database Configuration

#### Development Profile (H2)
```yaml
# application.yml
spring:
  datasource:
    url: "jdbc:h2:file:/app/data/careercompass;MODE=MySQL;DB_CLOSE_ON_EXIT=FALSE"
  profiles:
    active: dev
```
- **File-based H2** persisted in Docker volume `backend_h2`
- **Mode: MySQL** compatibility for Flyway migrations
- **Flyway** manages schema from `src/main/resources/db/migration/`

#### Production Profile (MySQL)
```yaml
# Requires environment variables
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
  profiles:
    active: prod
```

#### AI Service Database (PostgreSQL)
```yaml
# compose.yaml - separate PostgreSQL for AI service
postgres:
  image: postgres:16-alpine
  environment:
    POSTGRES_DB: ${AI_POSTGRES_DB:-careercompass_ai}
    POSTGRES_USER: ${AI_POSTGRES_USER:-careercompass}
    POSTGRES_PASSWORD: ${AI_POSTGRES_PASSWORD:-careercompass-local-dev-only}
  ports:
    - "127.0.0.1:5433:5432"  # Exposed on 5433 to avoid local pg conflict
```

### 3.2 Database Schema (from `backend/db/schema.sql`)

**38 Tables** organized by domain:

| Domain | Tables | Key Entities |
|--------|--------|--------------|
| **Core Users** | 6 | administrators, job_seekers, content_managers, employers, experts, universities |
| **Academic** | 5 | study_fields, career_paths, university_study_fields, learning_outcomes, academic_records |
| **Skills & Matching** | 6 | skills, levels, jobseeker_skills, courses_recommendations, quizzes, quiz_questions |
| **Jobs & Matching** | 4 | jobs, job_skills, job_matches, career_path_study_fields |
| **Appointments** | 4 | expert_availability, appointments, appointment_statuses, expert_statuses |
| **Security** | 1 | revoked_tokens |

**Key Relationships:**
- `job_seekers` → `universities`, `study_fields`, `career_paths` (nullable FKs)
- `jobseeker_skills` composite PK (`jobseeker_id`, `skill_id`) with `level_id` FK
- `job_matches` composite PK (`job_id`, `jobseeker_id`) with score 0-100
- `learning_outcomes` → `university_study_fields` → `universities` + `study_fields`

### 3.3 Data Access Layer

**JPA Repositories** (Spring Data JPA):
```java
// Example: JobSeekerRepository.java
public interface JobSeekerRepository extends JpaRepository<JobSeeker, Integer> {
    Optional<JobSeeker> findByEmail(String email);
    List<JobSeeker> findByUniversityId(Integer universityId);
}
```

**MapStruct Mappers** for Entity ↔ DTO conversion:
```java
@Mapper(componentModel = "spring")
public interface JobSeekerMapper {
    JobSeekerResponse toResponse(JobSeeker entity);
    JobSeeker toEntity(JobSeekerRequest request);
}
```

**Flyway Migrations** (versioned, repeatable):
```
src/main/resources/db/migration/
├── V1__initial_schema.sql
├── V2__add_quiz_skill_identity.java
├── V3__align_quiz_option_column_types.java
└── ...
```

---

## 4. Backend ↔ AI Service Connection

### 4.1 Architecture Pattern: Anti-Corruption Layer

The Spring Boot backend **never exposes the AI service directly to the frontend**. All AI calls go through the backend's Integration Layer.

```
Frontend → Backend (Spring) → AI Service (FastAPI)
              │
              ▼
    HttpDataAnalysisClient
    (Integration Layer)
```

### 4.2 Configuration (`application.yml`)

```yaml
careercompass:
  ai-service:
    base-url: ${AI_SERVICE_BASE_URL:http://localhost:8000}
    use-mock: true  # false = real HTTP client
    token: ${AI_SERVICE_TOKEN:}  # Bearer token for service-to-service auth
    timeout-seconds: 30
    timeouts:
      transcript-seconds: 30
      skill-vector-seconds: 10
      skill-gap-seconds: 10
      recommendations-seconds: 5
      quiz-seconds: 15
      syllabus-seconds: 30
      taxonomy-seconds: 10
      publication-seconds: 30
```

### 4.3 WebClient Configuration (`WebClientConfig.java`)

**Two Filters Applied to Every Request:**

1. **Service Token Filter** - Adds `Authorization: Bearer <service_token>`
2. **Correlation ID Filter** - Adds `X-Correlation-ID` header (from MDC or generated)

```java
@Bean
public WebClient aiServiceWebClient() {
    WebClient.Builder builder = WebClient.builder()
            .baseUrl(aiServiceProperties.getBaseUrl())
            .filter(correlationIdFilter());

    if (StringUtils.hasText(aiServiceProperties.getToken())) {
        builder.filter(serviceTokenFilter(aiServiceProperties.getToken()));
    }
    return builder.build();
}
```

### 4.4 HTTP Client Implementation (`HttpDataAnalysisClient.java`)

**Key Responsibilities:**
- **Contract Translation**: Snake_case (wire) ↔ CamelCase (Java domain)
- **Scale Conversion**: 0.0-1.0 (wire) ↔ 0-100 (Java percentages)
- **Enum Mapping**: `weak`/`moderate`/`strong` ↔ `Weak`/`Moderate`/`Strong`
- **Answer Key**: Zero-based index → A/B/C/D letter
- **Error Translation**: RFC 9457 ProblemDetails → `AiServiceException` with proper HTTP status

**Operations Implemented:**
| Operation | AI Endpoint | Java Method |
|-----------|-------------|-------------|
| Transcript Parse | `POST /api/v1/transcripts/parse` | `extractTranscript()` |
| Skill Vector | `POST /api/v1/skill-vector` | `buildSkillVector()` |
| Skill Gap | `POST /api/v1/skill-gap` | `analyzeSkillGap()` |
| Recommendations | `POST /api/v1/recommendations` | `recommendCourses()` |
| Quiz Generation | `POST /api/v1/quizzes` | `generateQuiz()` |
| Syllabus Extraction | `POST /api/v1/extractions` | `submitSyllabusExtraction()` |
| Taxonomy Search | `GET /api/v1/taxonomy/skills` | `searchTaxonomySkills()` |
| Course Map Publish | `PUT /api/v1/course-maps/{version}` | `publishCourseMap()` |

**Error Handling:**
- 400/422 → 502 BAD_GATEWAY (backend bug)
- 401/403 → 502 BAD_GATEWAY (service auth failure)
- 404 → 502 BAD_GATEWAY (unknown reference)
- 503 → 503 SERVICE_UNAVAILABLE (AI service down)
- Timeout → 504 GATEWAY_TIMEOUT

### 4.5 Mock Implementation (`MockDataAnalysisClient`)

When `careercompass.ai-service.use-mock=true`:
- Returns deterministic placeholder data
- Enables frontend development without AI service
- Used in `BACKEND_USE_AI_MOCK=true docker compose up`

---

## 5. AI Service ↔ PostgreSQL Connection

### 5.1 Configuration (`ai-service/src/careercompass/config.py`)

```python
DB_CONFIG = {
    "host": os.getenv("CC_DB_HOST"),
    "port": int(os.getenv("CC_DB_PORT", "5432")),
    "dbname": os.getenv("CC_DB_NAME"),
    "user": os.getenv("CC_DB_USER"),
    "password": os.getenv("CC_DB_PASSWORD"),
    "connect_timeout": max(1, int(os.getenv("CC_DB_CONNECT_TIMEOUT", "5"))),
    "application_name": "careercompass-ai",
}
```

### 5.2 Database Usage

**PostgreSQL used for:**
- Course map publication metadata (immutable versions)
- Human review decisions (term → skill_id mappings)
- Career path ontology (skills required per path)
- Job corpus data (for future job matching)

**File-based Storage (JSON):**
- Taxonomy: `data/taxonomy/taxonomy.jsonl`
- Course-skill maps: `data/extracted/skills/*.json`
- Career path skills: `data/extracted/jobs/career_path_skills.json`

### 5.3 Migrations (`ai-service/src/careercompass/db/migrate.py`)

```python
# Applied automatically on startup if CC_DB_AUTO_MIGRATE=1
async def apply_migrations():
    # Creates tables: course_maps, review_decisions, etc.
```

---

## 6. Docker Compose Orchestration (`compose.yaml`)

### 6.1 Service Definitions

| Service | Image/Build | Ports | Depends On | Health Check |
|---------|-------------|-------|------------|--------------|
| **postgres** | `postgres:16-alpine` | 5433→5432 | - | `pg_isready` |
| **ai-service** | `./ai-service/Dockerfile` | 8000→8000 | postgres (healthy) | `GET /api/v1/health/ready` |
| **backend** | `./backend/Dockerfile` | 8080→8080 | ai-service (healthy) | `GET /v3/api-docs` |
| **frontend** | `./frontend/Dockerfile` | 5173→5173 | backend (healthy) | `fetch(http://localhost:5173)` |
| **adminer** | `adminer:latest` | 8081→8080 | postgres | - |

### 6.2 Network Communication

```
Frontend (localhost:5173)
    │
    ▼ HTTP: VITE_API_BASE_URL=http://localhost:8080
Backend (localhost:8080)
    │
    ▼ HTTP: AI_SERVICE_BASE_URL=http://ai-service:8000 (Docker DNS)
AI Service (internal:8000)
    │
    ▼ TCP: CC_DB_HOST=postgres:5432
PostgreSQL (internal:5432)
```

### 6.3 Volume Persistence

```yaml
volumes:
  backend_h2:           # H2 database files
  learning_outcomes:    # Uploaded PDF files
  ai_postgres:          # PostgreSQL data
```

---

## 7. Security Architecture

### 7.1 JWT Authentication (Backend)

**Token Generation** (`JwtTokenProvider`):
- HS256 algorithm with secret from `JWT_SECRET` env var
- 30-minute expiration (configurable)
- Claims: `sub` (email), `role`, `userId`

**Token Validation** (`JwtAuthFilter`):
- Extracts Bearer token from Authorization header
- Validates signature, expiration, revocation check
- Sets `SecurityContext` with `Authentication` principal

### 7.2 Role-Based Access Control

| Role | Endpoint Access |
|------|-----------------|
| ADMIN | `/api/admin/**` |
| CONTENT_MANAGER | `/api/content-managers/**` |
| EMPLOYER | `/api/employers/**` |
| EXPERT | `/api/experts/**` |
| JOB_SEEKER | `/api/job-seekers/**` |
| ALL (authenticated) | `/api/reference/**` (GET) |

### 7.3 CORS Configuration

**Backend (`SecurityConfig.java`):**
```java
configuration.setAllowedOrigins(List.of("http://localhost:3000", "http://localhost:5173"));
configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
configuration.setAllowedHeaders(List.of("*"));
configuration.setAllowCredentials(true);
```

**AI Service (`app.py`):**
```python
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
               "http://localhost:8080", "http://127.0.0.1:8080"]
allow_credentials=False  # No cookies, service-to-service only
```

### 7.4 Service-to-Service Authentication

- **Backend → AI Service**: Bearer token via `AI_SERVICE_TOKEN`
- **Token validated** by AI service middleware (`service_token_middleware`)
- **No user identity** crosses this boundary (ADR-008)

---

## 8. Data Flow Examples

### 8.1 Student Transcript Upload → Skill Dashboard

```
1. Frontend: Student uploads PDF via /api/job-seekers/me/transcript
2. Backend: Multipart upload → FileStorageService saves to /app/uploads
3. Backend: Calls AI Service POST /api/v1/transcripts/parse (multipart)
4. AI Service: Parses PDF → returns extracted courses (regex-based, fast)
5. Backend: Persists AcademicRecord entities (JPA)
6. Frontend: Calls GET /api/job-seekers/me/dashboard
7. Backend: Builds SkillVectorRequest from stored courses + quiz scores
8. Backend: Calls AI Service POST /api/v1/skill-vector
9. AI Service: Joins courses to course-skill maps → returns skill vector (0-100)
10. Backend: Persists JobseekerSkill entities
11. Backend: Calls AI Service POST /api/v1/skill-gap with career path
12. AI Service: Computes gap → returns prioritized skill gaps
13. Frontend: Renders dashboard with gaps, recommendations, quiz suggestions
```

### 8.2 Content Manager Syllabus Review Workflow

```
1. Frontend: CM uploads syllabus PDF → POST /api/content-managers/extractions
2. Backend: Forwards to AI Service POST /api/v1/extractions (async, returns 202)
3. AI Service: Queues extraction job (parsing + LLM matching)
4. Frontend: Polls GET /api/content-managers/extractions/{id}
5. AI Service: Returns progress → when done, returns matched skills with review_status
6. Frontend: CM reviews/accepts/rejects matches → POST /api/content-managers/review-queue/decisions
7. Backend: Forwards to AI Service POST /api/v1/review-queue/decisions
8. AI Service: Stores decisions in PostgreSQL + updates in-memory overlay
9. CM publishes → PUT /api/content-managers/course-maps/{version}
10. AI Service: Writes canonical course map JSON + PostgreSQL metadata
```

### 8.3 Employer Job Posting → Candidate Matching

```
1. Frontend: Employer creates job → POST /api/employers/jobs
2. Backend: Persists Job + JobSkill entities
3. Frontend: Employer views candidates → GET /api/employers/jobs/{id}/candidates
4. Backend: For each jobseeker, calls AI Service (when implemented)
5. AI Service: Would score job match → returns match_score 0-100
6. Backend: Persists JobMatch entities
7. Frontend: Renders ranked candidate list
```

---

## 9. Environment Variables Reference

### 9.1 Backend (Spring Boot)

| Variable | Default | Description |
|----------|---------|-------------|
| `SPRING_PROFILES_ACTIVE` | `dev` | `dev` (H2) or `prod` (MySQL) |
| `SPRING_DATASOURCE_URL` | H2 file URL | JDBC URL for database |
| `JWT_SECRET` | *required* | HS256 signing key (min 32 chars) |
| `AI_SERVICE_BASE_URL` | `http://localhost:8000` | AI service URL |
| `AI_SERVICE_TOKEN` | *(empty)* | Service-to-service Bearer token |
| `BACKEND_USE_AI_MOCK` | `false` | `true` = use mock client |
| `LEARNING_OUTCOMES_DIR` | `./uploads/learning-outcomes` | PDF storage path |

### 9.2 AI Service (FastAPI)

| Variable | Default | Description |
|----------|---------|-------------|
| `CC_DATA_DIR` | `./data` | Root data directory |
| `CC_DB_HOST` | *required* | PostgreSQL host |
| `CC_DB_PORT` | `5432` | PostgreSQL port |
| `CC_DB_NAME` | *required* | Database name |
| `CC_DB_USER` | *required* | Database user |
| `CC_DB_PASSWORD` | *required* | Database password |
| `CC_DB_AUTO_MIGRATE` | `0` | `1` = auto-apply migrations |
| `CC_SERVICE_TOKEN` | *required* | Expected Bearer token |
| `CC_API_CORS_ORIGINS` | `localhost:3000,localhost:8080` | Allowed CORS origins |
| `CC_MATCH_LLM` | `0` | `1` = enable LLM matcher |
| `CC_EMBEDDING_BACKEND` | `lexical` | `lexical` or `bge` |
| `CC_RERANKER` | `lexical` | `lexical` or `cross-encoder` |

### 9.3 Frontend (Vite)

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8080` | Backend API URL |

---

## 10. Development Workflow

### 10.1 Local Development (All Services)

```bash
# From project root
docker compose up --build
# Frontend: http://localhost:5173
# Backend API: http://localhost:8080
# AI Service: http://localhost:8000
# Adminer (DB UI): http://localhost:8081
```

### 10.2 Local Development (Individual Services)

**Backend Only:**
```bash
cd backend
mvn spring-boot:run
# Uses H2, mock AI client by default
```

**AI Service Only:**
```bash
cd ai-service
pip install -e .
uvicorn careercompass.api.app:app --reload
# Requires PostgreSQL + data files
```

**Frontend Only:**
```bash
cd frontend
npm install
npm run dev
# Proxies to localhost:8080 via VITE_API_BASE_URL
```

### 10.3 Testing Commands

```bash
# Backend tests
cd backend && mvn test

# AI Service tests
cd ai-service && pytest

# Frontend lint
cd frontend && npm run lint

# Cross-runtime contract tests
cd backend && mvn test -Dtest=*ContractTest
```

---

## 11. Key Architectural Decisions (ADRs)

| ADR | Title | Impact on Connections |
|-----|-------|----------------------|
| ADR-001 | Service and Data Ownership | Backend owns user data; AI service owns taxonomy/skills |
| ADR-002 | Wire Protocol and Identifiers | Snake_case wire, canonical IDs for skills/career paths |
| ADR-003 | Score and Skill Vector Semantics | 0-100 in Java, 0.0-1.0 on wire |
| ADR-004 | Execution Errors and Service Security | RFC 9457 problems, service token auth |
| ADR-005/008 | Mentor Matching Scope | Descoped for v1; mock used for demo |
| ADR-007 | Database Migration Framework | Flyway (Java) + custom (Python) |

---

## 12. Troubleshooting Common Connection Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Frontend "NetworkError" | Backend not running or wrong port | Check `VITE_API_BASE_URL`, ensure backend on 8080 |
| Backend "AI_SERVICE_UNAVAILABLE" | AI service not healthy | `docker compose logs ai-service`, check health endpoint |
| Backend "AI_SERVICE_TIMEOUT" | AI operation exceeded deadline | Increase timeout in `application.yml` or check AI service load |
| CORS errors | Origin not in allowed list | Add frontend URL to `SecurityConfig.java` and `app.py` |
| JWT 401 on valid token | Token expired or revoked | Check `expiresAt` in session, `revoked_tokens` table |
| Flyway migration fails | Schema drift | Baseline existing DB or reset H2 volume |

---

## 13. Production Deployment Considerations

### 13.1 Required Changes for Production

1. **Database**: Switch to MySQL (backend) + PostgreSQL (AI) with managed instances
2. **Secrets**: Use secret manager for `JWT_SECRET`, `AI_SERVICE_TOKEN`, DB passwords
3. **CORS**: Restrict to production frontend domain only
4. **TLS**: Terminate at load balancer; services communicate over internal network
5. **File Storage**: Replace local volume with S3-compatible object storage
6. **AI Service**: Enable `CC_MATCH_LLM=1`, configure BGE embeddings + cross-encoder reranker
7. **Scaling**: Backend stateless (scale horizontally); AI service single-writer for course maps

### 13.2 Health Checks & Monitoring

| Service | Liveness | Readiness |
|---------|----------|-----------|
| Backend | `GET /actuator/health/liveness` | `GET /actuator/health/readiness` |
| AI Service | `GET /api/v1/health/live` | `GET /api/v1/health/ready` |
| Frontend | N/A (static) | `GET /` (Vite dev server) |

---

## 14. Summary: Connection Matrix

| From → To | Protocol | Auth | Data Format | Purpose |
|-----------|----------|------|-------------|---------|
| Browser → Frontend | HTTPS | Session/Cookie | HTML/JS/CSS | Serve SPA |
| Frontend → Backend | HTTPS/REST | JWT Bearer | JSON | All user-facing operations |
| Backend → H2/MySQL | JDBC | DB User/Pass | SQL | Primary persistence |
| Backend → AI Service | HTTP/REST | Service Token | JSON (snake_case) | NLP/ML operations |
| AI Service → PostgreSQL | psycopg2 | DB User/Pass | SQL | Course maps, reviews, ontology |
| Backend → File System | Local FS | OS Permissions | Binary (PDF) | Learning outcome uploads |

---

*Report generated from codebase analysis as of 2026-08-25*
*Project: CareerCompass - AI-powered Skills Enhancement and Job Matching System*
*MEU Graduation Project — Basil Mohammad & Mohammed Al-Madhoun*