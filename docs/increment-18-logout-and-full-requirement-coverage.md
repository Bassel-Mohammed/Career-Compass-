# Increment 18 — Logout, Token Revocation, and Full Requirement Coverage

## What changed

Three things, in order of significance:

1. **Logout was implemented** for all five actors, backed by real token revocation. This is
   the only change in this increment that adds a capability the system did not have.
2. **Two application defects** found by the system test were fixed (error mapping and the
   authentication response code).
3. **The system test grew from 50 to 68 cases**, taking functional requirement coverage from
   53/75 fully covered to **72/75, with nothing left uncovered**.

---

## 1. Logout and token revocation

### The problem

A JWT is verified from its own signature, so the server holds nothing it can delete to end a
session. Before this increment, "logout" could only have meant the client discarding its
token — and a copy taken beforehand would keep working for the remainder of its 30-minute
lifetime. FR-JS-03, FR-CM-02 and FR-EMP-03 give every self-service actor the ability to log
out, so the system needed a way to refuse a token it had already issued.

### The implementation

| Component | Role |
|---|---|
| `JwtTokenProvider` | Stamps every issued token with a `jti` claim (random UUID). Adds `getTokenId()` and `getExpiry()`. |
| `RevokedToken` (entity) | One row per surrendered token: `token_id`, `expires_at`, `revoked_at`. |
| `RevokedTokenRepository` | Primary-key lookup plus `deleteByExpiresAtBefore` for housekeeping. |
| `TokenRevocationService` | `revoke()` records a token; `isRevoked()` answers the filter; expired rows are purged opportunistically on each logout. |
| `JwtAuthFilter` | Checks the denylist after signature validation, so one rule covers every protected route. |
| `AuthController` | `POST /api/auth/logout` → 204 NO CONTENT. |
| `SecurityConfig` | Declares `/api/auth/logout` as `authenticated()` **before** the `/api/auth/**` permitAll rule. |

### Design decisions worth defending

**Revocation is keyed on the token, not the user.** Logging out ends the session that was
actually surrendered and leaves the same user's other sessions alone. A per-user "valid from"
timestamp would have been cheaper — one column instead of a table — but it signs a user out of
every device at once, which is a different behaviour from the one the requirements describe.
ST-67 exists specifically to prove this: the Job Seeker's original journey token still works
after a *different* session for the same person is logged out.

**Only the token identifier is stored, never the token.** The `jti` names a token without
carrying its signature, so a leak of `revoked_tokens` cannot be replayed as credentials.

**One endpoint for all five actors.** Login and registration differ per actor because each
looks up a different table and accepts a different request body. Logout needs neither — the
token already identifies the caller — so five URLs would have meant five copies of one method.

**Rule ordering matters.** Spring Security applies the first matching rule, so
`/api/auth/logout` must be declared before `/api/auth/**` permitAll or logout would be public.

### The cost

A denylist lookup on every authenticated request. This is the price of making stateless tokens
revocable, and it is a conscious trade rather than an oversight. It is a primary-key lookup
against a table holding only the last 30 minutes of logouts, so it stays small; at production
scale it belongs in an in-memory cache such as Redis rather than the main database.

### Schema

`DB_Schema.sql` gains a `revoked_tokens` table. It deliberately has no foreign key to any actor
table: one denylist serves all five actors, and the token already identifies its owner. Under
the dev profile (`ddl-auto: update`) the table is created automatically from the entity.

---

## 2. Application defects fixed

Both were found by the system test, and neither would have been caught by unit tests, because
both arise in layers that unit tests replace with mocks.

**Unknown routes returned 500 instead of 404.** Spring raises `NoResourceFoundException` for an
unmatched path, and `GlobalExceptionHandler`'s catch-all clause was intercepting it — so every
mistyped URL in the API was reported as an internal server error. Now mapped to
`404 ENDPOINT_NOT_FOUND`, which remains distinct from `ResourceNotFoundException` → `404 NOT_FOUND`
for a missing entity.

**Unauthenticated requests returned 403 instead of 401.** No `AuthenticationEntryPoint` was
configured, so Spring Security used its default. For a token-based API this conflates "you are
not signed in, go to the login screen" with "you are signed in but this is not yours, do not
retry" — a distinction the frontend needs. Now 401 for unauthenticated, 403 reserved for
authenticated-but-forbidden, both returning the standard `ApiErrorResponse` shape.

---

## 3. System test: 50 → 68 cases

### Test defects fixed in the original 50

**Mock lifecycle.** `@MockBean` mocks are reset after every test method, so stubs declared
inside one test were gone by the next. Because this suite deliberately shares state across
methods, every later step that re-entered an AI-backed code path received `null` and failed
with a `NullPointerException`. All stubs now live in a `@BeforeEach`, giving the mocked Data
Analyses Layer one definition for the whole suite.

**Detached-entity access.** The quiz write-back assertion navigated a lazily loaded association
on an entity that had already been detached. Now reads the row by its composite primary key.

### Cases added

| Orders | Phase | Covers |
|---|---|---|
| 5–8 | 0 | Study field and career path created, renamed and deleted through the admin API (FR-SA-07 to FR-SA-10) |
| 18 | 1 | The 30-minute inactivity window: configured policy plus refusal of an expired token per actor (FR-JS-04, FR-CM-03, FR-EMP-04) |
| 26–28 | 2 | Employer login, company profile update, job deletion (FR-EMP-02, FR-EMP-06, FR-EMP-10) |
| 43–46 | 4B | **Logout for all five actors**, session isolation, authentication requirement, replay refusal (FR-JS-03, FR-CM-02, FR-EMP-03) |
| 78–79 | 7 | Expert availability schedule and consultation rejection (FR-EX-06, FR-EX-04) |
| 89, 94–96 | 9 | Content Manager update and reactivation, Expert deactivation (FR-SA-04, FR-SA-06, FR-EX-02) |

Phase 4B sits at orders 43–46 rather than beside the login tests because that is the first
point in the journey where all five actor types exist — the Content Manager and both Experts
are not created until Phase 3.

Disposable data is used wherever a test could damage the shared journey: a throwaway career
path for the delete test, a throwaway job for FR-EMP-10, a second appointment for the rejection
test, and freshly issued tokens for every logout, so the records later phases depend on survive.

### Coverage

| | Before | After |
|---|---|---|
| Test cases | 50 | 68 |
| Fully covered | 53 / 75 | **72 / 75** |
| Partial | 7 | 3 |
| Not covered | 15 | **0** |

Three requirements remain partial, none blocked by the test suite:

- **FR-JS-16** (recommendations tailored to career path) — the recommender is mocked, so the
  test can prove the career path is passed through but not that output genuinely varies by it.
  Becomes assertable once the Data Analyses Layer is live.
- **FR-EMP-13** (contact a candidate) — the system supplies the email address rather than
  providing a messaging channel; ST-45 asserts the address is present.
- **FR-EX-10** (readiness evaluation) — shares a column with FR-EX-09, so it cannot be asserted
  separately. Closing it means adding a `readiness_evaluation` field to `appointments`.

---

## Notes for the report

Two gaps in the requirements specification surfaced while building the traceability matrix:

1. **No requirement covers the creation of Expert accounts.** FR-SA-02 covers Content Managers;
   FR-EX-01 says an Expert logs in with credentials "assigned by the system administrator",
   which implies the capability without stating it. The system implements and tests it.
2. **No requirement gives Administrators or Experts the ability to log out**, though both can
   and must. The three logout requirements are stated per actor but describe identical
   behaviour. A single requirement — "The system shall allow any authenticated user to log out,
   ending that session" — would cover all five actors and replace the three near-duplicates.
