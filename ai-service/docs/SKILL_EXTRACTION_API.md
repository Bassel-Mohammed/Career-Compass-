# CareerCompass Skill Extraction API

HTTP interface specification for the syllabus skill pipeline.

This is the skills subsystem. For the platform-wide interface — authentication,
the five actors, and the other AI modules — see [API_DESIGN.md](API_DESIGN.md).
For how the pipeline itself works — parsing, extraction, retrieval, reranking
and the matching thresholds — see
[SYLLABUS_SKILL_EXTRACTION.md](SYLLABUS_SKILL_EXTRACTION.md).

## Conventions

| Item | Value |
|---|---|
| Base path | `/api/v1` |
| Request bodies | `application/json`, except uploads |
| Uploads | `multipart/form-data` |
| Responses | `application/json` |
| Errors | `application/problem+json` (RFC 9457) |
| Timestamps | ISO 8601, UTC, e.g. `2026-08-14T19:04:11Z` |
| Interactive docs | `/docs` |
| OpenAPI schema | `/openapi.json` |

Two modes are exposed. Synchronous endpoints return their result directly.
`POST /api/v1/extractions` is asynchronous: it returns a job resource that the
client polls, because a full extraction takes about ninety seconds.

## Endpoint index

| Method | Path | Mode |
|---|---|---|
| `POST` | `/api/v1/syllabi/preview` | synchronous |
| `POST` | `/api/v1/extractions` | asynchronous |
| `GET` | `/api/v1/extractions/{extraction_id}` | synchronous |
| `DELETE` | `/api/v1/extractions/{extraction_id}` | synchronous |
| `GET` | `/api/v1/courses` | synchronous |
| `GET` | `/api/v1/courses/{course_code}/skills` | synchronous |
| `POST` | `/api/v1/skills/match` | synchronous |
| `GET` | `/api/v1/review-queue` | synchronous |
| `POST` | `/api/v1/review-queue/decisions` | synchronous |
| `GET` | `/api/v1/health/live` | synchronous |
| `GET` | `/api/v1/health/ready` | synchronous |

---

## Extraction

### POST /api/v1/syllabi/preview

Parses a syllabus and returns candidate terms without taxonomy matching.
Persists nothing.

**Request** — `multipart/form-data`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | PDF | yes | — | Course syllabus document |
| `min_weight` | float `0.0`–`1.0` | no | `0.0` | Return only terms at or above this weight |

**Responses**

| Status | Body |
|---|---|
| `200` | Preview document |
| `400` | `invalid-file-type` |
| `413` | `payload-too-large` |
| `422` | `unparseable-syllabus` |

```json
{
  "course_code": "0443501",
  "course_title": "Software Architecture",
  "content_sha256": "cae488bc9eb06ce731aed825c4a4fc5f...",
  "total_terms": 80,
  "terms": [
    {
      "term": "Layered Architecture",
      "level": "intermediate",
      "weight": 1.0,
      "evidence_count": 2,
      "sources": ["topic"]
    }
  ],
  "warnings": []
}
```

### POST /api/v1/extractions

Queues a full extraction: extract, match and store.

**Request** — `multipart/form-data`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | PDF | yes | — | Course syllabus document |
| `use_llm` | bool | no | unset | Overrides `CC_MATCH_LLM` for this job |
| `force` | bool | no | `false` | Bypass the idempotency cache |
| `store` | bool | no | `true` | Write results to PostgreSQL as well as disk |

**Responses**

| Status | Meaning |
|---|---|
| `202` | Job accepted. `Location` header holds the job URL |
| `200` | A completed job already exists for this document and taxonomy version |
| `400` | `invalid-file-type` |
| `413` | `payload-too-large` |
| `422` | `unparseable-syllabus` or `missing-course-code` |
| `503` | `matcher-unavailable` |
| `507` | `queue-full` |

Idempotency is keyed on `content_sha256` plus the taxonomy fingerprint.
Re-submitting the same document returns the existing job rather than repeating
the work; `force=true` overrides this.

```json
{
  "extraction_id": "ext_8aace3af0412",
  "status": "queued",
  "course_code": "0443501",
  "content_sha256": "cae488bc9eb06ce731aed825c4a4fc5f...",
  "degraded": false,
  "progress": {
    "stage": "queued",
    "terms_total": 0,
    "terms_resolved": 0,
    "elapsed_seconds": 0.0
  },
  "result": null,
  "warnings": [],
  "error": null,
  "created_at": "2026-08-14T19:04:11Z",
  "finished_at": null
}
```

### GET /api/v1/extractions/{extraction_id}

Returns the current state of a job.

**Responses**

| Status | Body |
|---|---|
| `200` | Job document |
| `404` | `extraction-not-found` |

```json
{
  "extraction_id": "ext_8aace3af0412",
  "status": "running",
  "course_code": "0443501",
  "content_sha256": "cae488bc9eb06ce731aed825c4a4fc5f...",
  "degraded": false,
  "progress": {
    "stage": "matching",
    "terms_total": 79,
    "terms_resolved": 47,
    "elapsed_seconds": 58.4
  },
  "result": null,
  "warnings": [],
  "error": null,
  "created_at": "2026-08-14T19:04:11Z",
  "finished_at": null
}
```

**Job fields**

| Field | Type | Description |
|---|---|---|
| `status` | enum | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `progress.stage` | enum | `queued`, `extracting`, `matching`, `storing`, `done` |
| `progress.terms_total` | int | Candidate terms found; `0` until extraction completes |
| `progress.terms_resolved` | int | Terms matched so far; advances during `matching` |
| `progress.elapsed_seconds` | float | Wall time; stops advancing at a terminal status |
| `degraded` | bool | `true` only when the LLM stage was requested and unreachable |
| `result` | object \| null | The result document; populated when `status` is `succeeded` |
| `error` | string \| null | Failure description when `status` is `failed` |
| `warnings` | string[] | Non-fatal problems, e.g. a failed database write |

Parsing is not a job stage. It runs inside the submit request, so a malformed
document is reported as a `4xx` on `POST /api/v1/extractions`; after a job is
accepted, failures appear as `status: "failed"` rather than an HTTP status.

### DELETE /api/v1/extractions/{extraction_id}

Cancels a `queued` or `running` job. Partial results are discarded.

**Responses**

| Status | Body |
|---|---|
| `200` | Job document with `cancel_requested` honoured |
| `404` | `extraction-not-found` |
| `409` | `extraction-not-cancellable` — the job already finished |

---

## Results

### GET /api/v1/courses

Lists every course that has been extracted.

**Responses** — `200`

```json
{
  "total": 1,
  "courses": [
    {
      "course_code": "0443501",
      "total_skills": 79,
      "taxonomy_version": "1.0",
      "by_status": { "accepted": 8, "needs_review": 39, "no_match": 32 }
    }
  ]
}
```

### GET /api/v1/courses/{course_code}/skills

Returns a course's matched skills.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `status` | `accepted` \| `needs_review` \| `no_match` \| `all` | `accepted` | Which review statuses to return |
| `min_weight` | float `0.0`–`1.0` | `0.0` | Evidence-strength floor |
| `include` | comma-separated: `evidence`, `candidates` | none | Adds the audit fields, which are large |

**Responses**

| Status | Body |
|---|---|
| `200` | Result document, filtered |
| `404` | `course-not-found` |
| `422` | `invalid-request` — a query parameter failed validation |

```json
{
  "course_code": "0443501",
  "taxonomy_version": "1.0",
  "match_summary": {
    "by_status": { "accepted": 8, "needs_review": 39, "no_match": 32 },
    "by_method": { "embedding_reranker": 77, "exact_alias": 2 }
  },
  "total_skills": 8,
  "skills": []
}
```

`total_skills` is the count *after* filtering; `match_summary` describes the
whole course.

---

## Matching

### POST /api/v1/skills/match

Matches free-text terms against the taxonomy without a PDF. Accepts at most
**25 terms** per request.

**Request** — `application/json`

| Field | Type | Required | Description |
|---|---|---|---|
| `terms` | array, 1–25 items | yes | Terms to resolve |
| `terms[].term` | string, 1–200 chars | yes | The phrase to match |
| `terms[].evidence` | string, ≤ 2000 chars | no | Surrounding context |
| `use_llm` | bool | no | Overrides `CC_MATCH_LLM` for this request |

**Responses**

| Status | Body |
|---|---|
| `200` | Match results |
| `413` | `payload-too-large` — more than 25 terms |
| `422` | `invalid-request` |
| `503` | `matcher-unavailable` |

```json
{
  "total": 2,
  "degraded": false,
  "matches": [
    {
      "original_term": "REST API",
      "canonical_id": "custom:rest-api",
      "canonical_label": "REST API development",
      "taxonomy": "custom",
      "taxonomy_version": "1.0",
      "match_method": "embedding_reranker",
      "match_score": 0.83,
      "review_status": "accepted",
      "reason": "alias match above threshold",
      "candidates": []
    }
  ]
}
```

---

## Review

### GET /api/v1/review-queue

Returns terms awaiting a human decision, lowest match score first.

**Query parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int `1`–`500` | `100` | Maximum items to return |
| `course_code` | string | none | Restrict to one course |

**Responses**

| Status | Body |
|---|---|
| `200` | Queue page |
| `422` | `invalid-request` |
| `503` | `database-unavailable` |

```json
{
  "total": 3,
  "items": [
    {
      "course_code": "0432405",
      "term": "Drones",
      "review_status": "no_match",
      "match_score": 0.102,
      "candidates": []
    }
  ]
}
```

### POST /api/v1/review-queue/decisions

Records reviewer decisions in a batch.

**Request** — `application/json`

| Field | Type | Required | Description |
|---|---|---|---|
| `reviewer` | string, ≤ 100 chars | no | Who made the decisions |
| `decisions` | array, 1–200 items | yes | The decisions |
| `decisions[].term` | string, 1–200 chars | yes | Term being decided |
| `decisions[].decision` | `confirmed` \| `corrected` \| `rejected` | yes | The verdict |
| `decisions[].skill_id` | string \| null | no | Canonical id; `null` on a rejection means no taxonomy entry covers the term |
| `decisions[].note` | string, ≤ 500 chars | no | Free-text justification |

Decisions are stored against the **normalised term**, not the course, so one
correction applies to every course containing that term.

**Responses**

| Status | Body |
|---|---|
| `200` | `{ "recorded": 2, "errors": [] }` |
| `422` | `invalid-request` |
| `503` | `database-unavailable` |

```json
{
  "reviewer": "mohammed",
  "decisions": [
    {
      "term": "Layered Architecture",
      "decision": "corrected",
      "skill_id": "esco:2450c3b3-e78e-435b-b84d-e05d984e71dc",
      "note": "architecture style, not robotics"
    },
    { "term": "techniques", "decision": "rejected", "skill_id": null }
  ]
}
```

---

## Health

### GET /api/v1/health/live

Liveness. Always `200` while the process is running; touches no dependency.

```json
{ "status": "ok", "service": "CareerCompass API" }
```

### GET /api/v1/health/ready

Readiness. `200` when the instance can serve matches, `503` otherwise with a
`Retry-After` header.

`ready` reflects the `taxonomy` and `vector_index` checks only. The `llm` and
`database` checks are reported but do not gate readiness.

```json
{
  "ready": true,
  "checks": {
    "taxonomy":     { "ok": true, "version": "1.0", "skills": 906 },
    "vector_index": { "ok": true, "backend": "st:BAAI/bge-m3", "entries": 906,
                      "warm_seconds": 16.69 },
    "llm":          { "ok": true, "model": "ollama:qwen3:8b" },
    "database":     { "ok": true }
  }
}
```

---

## Result document

Returned as `result` on a succeeded job, and by
`GET /api/v1/courses/{course_code}/skills`. Identical to the file written to
`data/extracted/skills/<course_code>.json`.

```json
{
  "course_code": "0443501",
  "total_skills": 79,
  "taxonomy_version": "1.0",
  "match_summary": {
    "by_status": { "accepted": 8, "needs_review": 39, "no_match": 32 },
    "by_method": { "embedding_reranker": 77, "exact_alias": 2 }
  },
  "skills": [
    {
      "term": "Layered Architecture",
      "canonical": null,
      "level": "intermediate",
      "weight": 1.0,
      "evidence_count": 2,
      "sources": ["topic"],
      "evidence": [
        { "source": "topic", "week": 5, "text": "5. Layered Architecture" }
      ],
      "match": {
        "original_term": "Layered Architecture",
        "canonical_id": null,
        "canonical_label": null,
        "taxonomy": null,
        "taxonomy_version": "1.0",
        "match_method": "embedding_reranker",
        "match_score": 0.5,
        "review_status": "needs_review",
        "reason": "best candidate below the accept threshold",
        "candidates": [
          {
            "id": "custom:robotics-system-architecture",
            "label": "robotics system architecture",
            "score": 0.5
          }
        ]
      }
    }
  ]
}
```

### Skill object

| Field | Type | Description |
|---|---|---|
| `term` | string | The phrase as it appears in the syllabus |
| `canonical` | object \| null | `{id, label, taxonomy}`; non-null only when `review_status` is `accepted` |
| `level` | enum | `beginner`, `intermediate`, `advanced` |
| `weight` | float | Rule-based evidence strength, not a probability |
| `evidence_count` | int | How many syllabus mentions backed the term |
| `sources` | string[] | Any of `clo`, `lab`, `topic`, `description` |
| `evidence` | object[] | Every mention; omitted unless `include=evidence` |
| `match` | object | The matching audit trail |

### Match object

| Field | Type | Description |
|---|---|---|
| `original_term` | string | Term submitted to the matcher |
| `canonical_id` | string \| null | Taxonomy id of the chosen skill |
| `canonical_label` | string \| null | Human-readable label |
| `taxonomy` | enum \| null | `esco`, `onet`, `custom` |
| `taxonomy_version` | string | Vocabulary version this result is valid against |
| `match_method` | enum | `exact_alias`, `embedding_reranker`, `llm` |
| `match_score` | float | Score or LLM confidence |
| `review_status` | enum | `accepted`, `needs_review`, `no_match` |
| `reason` | string | Why the stage decided as it did |
| `candidates` | object[] | Retrieved alternatives; omitted unless `include=candidates` |

### Review status

| Value | Meaning | Downstream treatment |
|---|---|---|
| `accepted` | Score cleared the threshold, or the LLM chose a candidate at confidence ≥ 0.70 | Safe to consume |
| `needs_review` | Plausible but under threshold; appears in the review queue | Exclude until a human decides |
| `no_match` | Below the review floor, or the LLM returned no match | Exclude |

---

## Errors

All errors use `application/problem+json`.

```json
{
  "type": "unparseable-syllabus",
  "title": "Syllabus could not be parsed",
  "status": 422,
  "detail": "No text layer found in scan.pdf; the file is likely a scan and needs OCR before it can be parsed.",
  "warnings": []
}
```

| Field | Type | Description |
|---|---|---|
| `type` | string | Stable machine-readable identifier |
| `title` | string | Short human-readable summary |
| `status` | int | Repeats the HTTP status code |
| `detail` | string | Specific explanation; may be absent |

Some types add fields: `unparseable-syllabus` and `missing-course-code` carry
`warnings`, and `invalid-request` carries `errors`.

| Status | `type` | Raised when |
|---|---|---|
| 400 | `invalid-file-type` | Upload is not a PDF |
| 404 | `course-not-found` | No stored skills for that course code |
| 404 | `extraction-not-found` | Unknown or evicted job id |
| 409 | `extraction-not-cancellable` | Cancel arrived after the job finished |
| 413 | `payload-too-large` | PDF over 20 MB, or match request over 25 terms |
| 422 | `invalid-request` | Request failed schema validation; carries `errors` |
| 422 | `unparseable-syllabus` | No text layer or no recognisable tables in the PDF |
| 422 | `missing-course-code` | Parsed, but no course code to store the result under |
| 500 | `internal-error` | Unexpected failure; detail is logged, not returned |
| 503 | `matcher-unavailable` | Vector index still building or failed to load; sets `Retry-After` |
| 503 | `database-unavailable` | PostgreSQL unreachable on an endpoint that requires it |
| 507 | `queue-full` | Worker queue at capacity; sets `Retry-After` |

An unreachable LLM is not an error. The matcher degrades by sending ambiguous
terms to the review queue, and the response is `200` with `"degraded": true` and
a warning.

---

## Legacy endpoints

Unversioned, retained for the existing frontend. New clients should not use
them.

| Method | Path | Replacement |
|---|---|---|
| `GET` | `/api/health` | `/api/v1/health/live` |
| `POST` | `/api/transcript/upload` | none yet; will move under `/api/v1` |

These return FastAPI's default `{"detail": "..."}` error shape rather than
`problem+json`.
