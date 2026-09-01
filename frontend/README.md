# CareerCompass Frontend

The CareerCompass browser application is built with React 19, TypeScript, and Vite. It provides
responsive, role-protected workspaces for students, employers, mentors, content managers, and
administrators.

The frontend calls only the Spring Boot public API. It must never call the internal FastAPI service
or receive the AI service token.

## Requirements

- Node.js 22
- npm 10+
- Spring Boot API running locally or at a configured URL

## Install and run

```bash
cd frontend
npm ci
npm run dev
```

Open `http://localhost:5173`.

The API URL defaults to `http://localhost:8080`. Override it in a local `.env` file when needed:

```dotenv
VITE_API_BASE_URL=https://api.example.com
```

Only variables prefixed with `VITE_` are compiled into browser code. Never place secrets or
service tokens in a frontend environment file.

## Available commands

| Command | Purpose |
|---|---|
| `npm run dev` | Start the Vite development server |
| `npm run build` | Type-check and produce the optimized `dist/` bundle |
| `npm run preview` | Serve the production bundle locally |
| `npm run lint` | Run Oxlint |
| `npm run test` | Run Vitest in watch mode |
| `npm run test -- --run` | Run the test suite once |
| `npm run test:ui` | Open the Vitest UI |

## User workspaces

### Student

- Account setup with university, study field, and career path
- Transcript upload, extraction review, editing, and confirmation
- Skill dashboard with proficiency, demand, gaps, and data-source disclosure
- Course recommendations, quizzes, job matching, mentor appointments, and profile management

### Employer

- Company profile management
- Job posting creation, editing, listing, and deletion
- Ranked candidate view with AI/mock-result disclosure

### Mentor

- Scheduled and historical sessions
- Availability and profile management
- Appointment acceptance, rejection, and outcome recording
- Student skill-dashboard and course-recommendation views

### Content manager

- Learning-outcome upload and extraction status
- AI-extracted skill review, replacement, deletion, retry, and publication
- Study-field profile management

### Administrator

- Content-manager and mentor account management
- University, study-field, and career-path reference-data management
- Administrator account profile and password management

Only students and employers can self-register. Mentor and content-manager accounts are created by
an administrator. Sign-in is role-specific: choosing the wrong account type produces the same safe
credential error as a wrong password.

## Routes

| Route | Role | Purpose |
|---|---|---|
| `/login`, `/signup` | Public | Role-specific sign-in and allowed self-registration |
| `/setup`, `/dashboard`, `/transcript` | Student | Onboarding and skill analysis |
| `/courses`, `/quizzes`, `/jobs`, `/mentors`, `/profile` | Student | Recommendations and student workflows |
| `/employer` | Employer | Job postings |
| `/employer/jobs/new`, `/employer/jobs/:jobId/edit` | Employer | Job-posting form |
| `/employer/jobs/:jobId/candidates` | Employer | Ranked candidates |
| `/employer/profile` | Employer | Company profile |
| `/expert` | Mentor | Sessions |
| `/expert/job-seekers/:jobseekerId` | Mentor | Student progress |
| `/expert/availability`, `/expert/profile` | Mentor | Availability and profile |
| `/content` | Content manager | Learning outcomes |
| `/content/learning-outcomes/:outcomeId/review` | Content manager | Extracted-skill review |
| `/content/study-field` | Content manager | Study field |
| `/admin`, `/admin/mentors` | Administrator | Managed accounts |
| `/admin/reference`, `/admin/profile` | Administrator | Reference data and profile |

`ProtectedRoute` validates both authentication and role before rendering a workspace. Unknown URLs
render the not-found page.

## Source layout

```text
src/
├── api/          Typed API modules and the shared HTTP/error client
├── auth/         Session persistence, role guards, validation, and navigation
├── components/   Shared layout, form, feedback, and visualization components
├── hooks/        Reusable async behavior
├── pages/        Role-specific pages and public authentication pages
├── test/         Vitest setup and shared test support
├── App.tsx       Route table and providers
└── types.ts      TypeScript representations of backend DTOs
```

`types.ts` and `auth/validate.ts` mirror backend DTOs and validation rules. Update them whenever the
corresponding Java contract changes.

## API errors and sessions

Backend errors use one `ApiErrorResponse` shape. Field-validation errors attach to matching form
fields; authentication and conflict errors are displayed with role-aware messages. Network and
timeout failures have separate client-side error types, and AI operations receive longer deadlines
than ordinary CRUD requests.

The browser stores the authenticated session, converts `expiresInSeconds` into an absolute expiry,
automatically signs out at expiration, and includes the bearer token only on protected Spring API
requests.

## Test and build

```bash
npm run test -- --run
npm run build
npm run lint
```

CI uses Node 22 and runs the build and linter for every pull request and every push to `main`.

## Docker

From the repository root:

```bash
docker compose up --build frontend
```

For production, `Dockerfile.prod` builds the static site and serves it through the production web
stack. `VITE_API_BASE_URL` is a build-time value, so set it before building the image; it cannot be
changed in an already-built bundle.
