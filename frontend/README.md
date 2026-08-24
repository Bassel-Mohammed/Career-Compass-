# CareerCompass Frontend

The browser UI. React 19 + TypeScript, built with Vite.

It calls the **Spring Boot API** at `http://localhost:8080` and must never call the
internal FastAPI service directly — Spring is the only caller allowed there, and it
holds the service token. Spring Security already permits this app's dev origin,
`http://localhost:5173`.

## Running it

```bash
npm ci
npm run dev      # http://localhost:5173
npm run build    # type-check, then bundle to dist/
npm run lint
```

The API base URL comes from `VITE_API_BASE_URL` (see `.env.development`). Point it
elsewhere to run against a deployed backend.

## What is built

Authentication, the student journey, the content-manager upload workflow, and the employer
workspace are implemented. Every actor route is protected by role as well as by authentication.
Mentor and administrator home routes still use `PlaceholderHome`; their deeper navigation entries
describe the intended workspace but do not have registered routes yet.

| Route | Actor | Capability / state |
|---|---|---|
| `/login` | all five actors | Sign in through the endpoint for the selected actor |
| `/signup` | student, employer | Self-registration for the two roles the backend permits |
| `/setup` | student | Select university, study field, and a compatible career path |
| `/dashboard` | student | Skill readiness, classifications, gaps, and calculation disclosure |
| `/transcript` | student | Upload a PDF, review/edit extracted rows, then confirm |
| `/courses` | student | Generate and revisit course recommendations |
| `/quizzes` | student | Generate, attempt, and submit a skill quiz; show the updated dashboard score |
| `/jobs` | student | List job matches, explicitly labelling mock scores or the descoped 501 response |
| `/mentors` | student | List same-field mentors, request a session, and view appointments |
| `/profile` | student | Update account/study choices or permanently delete the account |
| `/employer` | employer | List postings and delete one after confirmation |
| `/employer/jobs/new` | employer | Create a posting, optionally scoped to a study field |
| `/employer/jobs/:jobId/edit` | employer | Edit an existing posting |
| `/employer/jobs/:jobId/candidates` | employer | Ranked candidates, with explicit 501/mock-score disclosure |
| `/employer/profile` | employer | View and update the company profile |
| `/content` | content manager | Upload/list learning-outcome PDFs and remove a stored file while retaining its record |
| `/content/profile` | content manager | View account details and select the study field used for new uploads |
| `/expert` | mentor | Guarded placeholder landing page |
| `/admin` | administrator | Guarded placeholder landing page |

`/expert/availability`, `/expert/profile`, `/admin/mentors`, and `/admin/reference` appear in the
role navigation but are not implemented routes. The catch-all page reports them as not found.

## Two things about auth that shape the UI

**Sign-in is per actor.** `LoginRequest` carries only an email and a password — no role
field — so the *URL* is what decides which table is searched. There are five login
endpoints, and the role picker on the sign-in form chooses between them. Picking the
wrong one for a real account returns 401, indistinguishable from a wrong password, which
is why the failure message names the account type the user selected.

**Only two actors can register themselves.** `AuthController` exposes `/register` for
job seekers and employers and for nobody else. Mentors, content managers and
administrators are created by an administrator, so the sign-up form offers two options,
not five, and says so.

## Layout

```
src/
  api/
    client.ts          fetch wrapper; turns ApiErrorResponse into a typed ApiError
    auth.ts            the seven /api/auth routes
    employer.ts        company profile, posting CRUD, and candidate ranking
    contentManager.ts  study-field profile and learning-outcome storage
    transcript.ts      transcript review/confirmation and skill dashboard
    recommendations.ts, quizzes.ts, consultations.ts, jobMatches.ts
  auth/
    session.ts         token persistence; resolves expiresInSeconds to an absolute instant
    AuthProvider.tsx   session state, sign-in, sign-out, expiry timer
    ProtectedRoute.tsx role guard and wrong-role redirect
    nav.ts, roles.ts   per-actor navigation, labels, hints, and home routes
    validate.ts        client-side mirror of Java Bean Validation rules
  components/          responsive AppShell plus shared fields, feedback, and status UI
  hooks/useAsync.ts    shared loading/action state for API-backed screens
  pages/
    student/           setup, transcript, dashboard, courses, quizzes, jobs, mentors, profile
    employer/          posting list/form/candidates and company profile
    content/           learning outcomes and study-field profile
    LoginPage.tsx, SignupPage.tsx, PlaceholderHome.tsx, NotFoundPage.tsx
  App.tsx              complete route table and role guards
  types.ts             Java request/response DTOs represented in TypeScript
```

`types.ts` and `auth/validate.ts` mirror
`backend/src/main/java/com/careercompass/dto/`. When a DTO changes, those change with it.

## Errors

Every backend failure — from the security filter chain and from `GlobalExceptionHandler`
alike — arrives as the same `ApiErrorResponse`, so there is one shape to parse. The codes
the auth screens act on:

| Code | Status | Handling |
|---|---|---|
| `VALIDATION_ERROR` | 400 | `fieldErrors` are attached to the matching inputs |
| `INVALID_CREDENTIALS` | 401 | banner naming the selected account type |
| `EMAIL_ALREADY_EXISTS` | 409 | attached to the email field, with a link to sign in |
| anything else | — | the server's own `message`, shown as-is |

An unreachable server is a `NetworkError`, not an `ApiError`, and says which URL it tried.

## Verification

CI uses Node 22 and runs `npm ci`, `npm run build`, and `npm run lint` for every pull request and
push to `main`. Both frontend quality commands pass on the current tree. There is not yet a
browser-level automated test suite.

### Authentication checked against the running backend

Checked on 24 August 2026 against the Spring Boot API on the `dev` profile (in-memory H2),
with the frontend's own origin. Every request and error shape below is confirmed, not inferred.

| Check | Result |
|---|---|
| Register job seeker | 201 + `AuthResponse`, `expiresInSeconds: 1800` |
| Register employer, optional fields omitted | 201 |
| Register employer, optional fields sent | 201 |
| Duplicate email | 409 `EMAIL_ALREADY_EXISTS` |
| Blank name, bad email, 5-char password | 400 `VALIDATION_ERROR`, `fieldErrors` naming `firstName`, `email`, `password` |
| Login | 200 + `AuthResponse` |
| Wrong password | 401 `INVALID_CREDENTIALS` |
| Correct credentials, wrong role endpoint | 401 `INVALID_CREDENTIALS` — byte-identical to a wrong password |
| Logout | 204 |
| Reusing the logged-out token | 401 `UNAUTHENTICATED` — the denylist works |
| CORS preflight from `localhost:5173` | 200, `Authorization` and `Content-Type` allowed |
| CORS preflight from an unknown origin | 403, no allow-origin header |

The `fieldErrors[].field` values match the form state keys exactly, so server-side validation
messages land on the right inputs with no mapping layer.

**The wrong-role case is why the sign-in error names the account type.** Signing in with a
student's real credentials at the employer endpoint returns exactly the same 401 and the same
`"Invalid email or password."` as a genuinely wrong password. Nothing in the response can tell
the two apart, so the UI has to raise the possibility itself — otherwise a user with a correct
password and the wrong radio button selected has no way to work out what is wrong.

## Running the backend for local work

The pom targets Java 17 and will not compile on a newer JDK. If `java -version` reports
anything else, point Maven at 17 explicitly:

```bash
cd ../backend
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 SPRING_PROFILES_ACTIVE=dev mvn spring-boot:run
```

The `dev` profile uses in-memory H2, so no database setup is needed — but the data is gone
on restart, and accounts must be registered again.
