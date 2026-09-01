#!/usr/bin/env python3
"""
Seed a CareerCompass deployment with a Jordanian demo dataset.

Why this exists
---------------
`DevDataSeeder` is `@Profile("dev & !test")` and deliberately never runs in production, so a
freshly migrated prod database has schema and nothing else. Everything below is therefore
created the way a real operator would create it — through the public REST API, honouring the
same authorisation and validation rules the UI is bound by. Nothing is written straight to a
table, so anything this script produces is by definition reachable through the product.

The one thing it cannot bootstrap is the first administrator: there is no
`/api/auth/admins/register` endpoint, by design (an open "create an admin" route is a privilege
escalation hole). Insert that row by hand first — see deployplan.md section 5.5 — then give this
script those credentials.

Names that are not free text
----------------------------
Career path titles must match `ai-service/data/extracted/jobs/career_path_skills.json` exactly
and study field names must match the keys of `data/mapping/study_field_career_paths.json`,
otherwise Java accepts the row and the Python side then matches nothing — an empty skill gap
that looks like a bug rather than a typo. The constants below are copied from those two files.

Re-running is safe
------------------
Every step checks for the row before creating it, and treats "already exists" as success, so an
interrupted run can simply be repeated.

Usage
-----
    python3 scripts/seed_jordan_demo.py \
        --base-url https://your-host \
        --admin-email admin@example.com \
        --admin-password '...'

Add --skip-transcripts to leave students at the "career path chosen, nothing uploaded" stage,
which is much faster because it does not wait on the AI service.
"""

from __future__ import annotations

import argparse
import getpass
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TRANSCRIPT_DIR = REPO_ROOT / "ai-service" / "data" / "plans"


# --------------------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------------------

# Real Jordanian institutions, in no particular order of preference.
UNIVERSITIES = [
    "University of Jordan",
    "Jordan University of Science and Technology",
    "Princess Sumaya University for Technology",
    "Yarmouk University",
    "German Jordanian University",
    "Al-Balqa Applied University",
    "The Hashemite University",
    "Mutah University",
    "Al al-Bayt University",
    "Applied Science Private University",
]

# Exactly the keys the AI service recognises. A field spelled any other way is silently
# unmapped there and the mentor is then ranked on seniority alone.
STUDY_FIELDS = [
    "Computer Science",
    "Computer Engineering",
    "Software Engineering",
    "Information Technology",
    "Information Systems",
    "Cybersecurity",
    "Data Science",
    "Artificial Intelligence",
    "Multimedia",
    "Mobile Development",
]

# The nine canonical paths, with the study fields that may select them. This is
# study_field_career_paths.json inverted, so the two directions cannot drift apart.
CAREER_PATHS = [
    {
        "title": "Backend Development",
        "code": "career:backend-development",
        "description": "Server-side services, APIs and the data stores behind them.",
        "fields": ["Computer Science", "Computer Engineering", "Software Engineering"],
    },
    {
        "title": "Full Stack Development",
        "code": "career:full-stack-development",
        "description": "Both the browser interface and the services powering it.",
        "fields": ["Computer Science", "Software Engineering", "Information Systems"],
    },
    {
        "title": "Data Science & Analytics",
        "code": "career:data-science-analytics",
        "description": "Turning raw data into models, dashboards and decisions.",
        "fields": [
            "Computer Science",
            "Information Systems",
            "Data Science",
            "Artificial Intelligence",
        ],
    },
    {
        "title": "AI & Machine Learning",
        "code": "career:ai-machine-learning",
        "description": "Training, evaluating and deploying machine-learning systems.",
        "fields": ["Data Science", "Artificial Intelligence"],
    },
    {
        "title": "DevOps & Cloud",
        "code": "career:devops-cloud",
        "description": "Build pipelines, infrastructure and running systems in production.",
        "fields": ["Computer Engineering", "Information Technology"],
    },
    {
        "title": "Cybersecurity",
        "code": "career:cybersecurity",
        "description": "Protecting systems and data from compromise.",
        "fields": ["Information Technology", "Cybersecurity"],
    },
    {
        "title": "QA & Testing",
        "code": "career:qa-testing",
        "description": "Automated and exploratory testing, and the quality of a release.",
        "fields": ["Software Engineering"],
    },
    {
        "title": "Mobile Development",
        "code": "career:mobile-development",
        "description": "Native and cross-platform applications for phones and tablets.",
        "fields": ["Mobile Development"],
    },
    {
        "title": "UI/UX Design",
        "code": "career:ui-ux-design",
        "description": "Interface design, interaction and usability research.",
        "fields": ["Multimedia"],
    },
]

# Sunday-to-Thursday, the Jordanian working week. dayOfWeek is 1=Monday .. 7=Sunday, matching
# the availability editor and the frontend's day names.
SCHEDULE_MORNINGS = [
    (7, "09:00:00", "13:00:00"),  # Sunday
    (1, "09:00:00", "13:00:00"),  # Monday
    (3, "09:00:00", "12:00:00"),  # Wednesday
]
SCHEDULE_AFTERNOONS = [
    (7, "13:00:00", "17:00:00"),
    (2, "14:00:00", "18:00:00"),  # Tuesday
    (4, "13:00:00", "17:00:00"),  # Thursday
]
SCHEDULE_MIXED = [
    (1, "10:00:00", "14:00:00"),
    (3, "13:00:00", "17:00:00"),
    (4, "09:00:00", "12:00:00"),
]

MENTORS = [
    ("Tareq", "Al-Rousan", "Computer Science", 2010, SCHEDULE_MORNINGS),
    ("Dana", "Al-Khatib", "Software Engineering", 2013, SCHEDULE_AFTERNOONS),
    ("Firas", "Bani-Hani", "Cybersecurity", 2011, SCHEDULE_MIXED),
    ("Lujain", "Al-Adwan", "Data Science", 2016, SCHEDULE_MORNINGS),
    ("Bashar", "Al-Zoubi", "Information Systems", 2009, SCHEDULE_AFTERNOONS),
    ("Alaa", "Al-Momani", "Computer Engineering", 2012, SCHEDULE_MIXED),
    ("Rasha", "Al-Tamimi", "Artificial Intelligence", 2015, SCHEDULE_MORNINGS),
    ("Zaid", "Al-Hyari", "Information Technology", 2008, SCHEDULE_AFTERNOONS),
    ("Maha", "Al-Sharif", "Multimedia", 2014, SCHEDULE_MIXED),
    ("Hamza", "Al-Dabbas", "Mobile Development", 2017, SCHEDULE_MORNINGS),
]

CONTENT_MANAGERS = [
    ("Noor", "Al-Qudah", "University of Jordan", "Computer Science"),
    ("Hamza", "Al-Nabulsi", "Jordan University of Science and Technology", "Software Engineering"),
    ("Sundus", "Al-Btoush", "Princess Sumaya University for Technology", "Cybersecurity"),
    ("Mohannad", "Al-Refai", "Yarmouk University", "Information Technology"),
]

# (first, last, university, study field, career path, transcript file or None)
#
# Deliberately at three different stages, so the reviewer can see how the product behaves at
# each one without having to construct the states by hand.
STUDENTS = [
    (
        "Ahmad", "Al-Obeidat", "University of Jordan",
        "Computer Science", "Backend Development", "202310442_old_plan_CS.pdf",
    ),
    (
        "Rania", "Al-Tarawneh", "Princess Sumaya University for Technology",
        "Software Engineering", "Full Stack Development", "202410100_software_enineering.pdf",
    ),
    (
        "Yousef", "Al-Masri", "Jordan University of Science and Technology",
        "Cybersecurity", "Cybersecurity", "202410709_old_plan_cyber_security.pdf",
    ),
    (
        "Layan", "Al-Hasan", "Yarmouk University",
        "Artificial Intelligence", "AI & Machine Learning", "202411766_CS_AI_plan.pdf",
    ),
    (
        "Omar", "Al-Sakran", "The Hashemite University",
        "Cybersecurity", "Cybersecurity", "202510446_new_paln_cyber_security.pdf",
    ),
    # Career path chosen, nothing uploaded — lands on "upload and confirm your transcript first".
    ("Yazan", "Al-Majali", "Mutah University", "Computer Science", "Data Science & Analytics", None),
    ("Salma", "Al-Nsour", "German Jordanian University", "Computer Engineering", "DevOps & Cloud", None),
    ("Karam", "Al-Dweik", "Applied Science Private University", "Mobile Development", "Mobile Development", None),
    # Nothing set at all — walks the whole onboarding from zero.
    ("Tala", "Al-Saqqa", None, None, None, None),
    ("Mohammad", "Al-Jabari", None, None, None, None),
]

# Fictional companies. Real Jordanian employers are deliberately not used: these are demo
# accounts with a published password, and attaching them to a real company's name would put
# words in that company's mouth.
EMPLOYERS = [
    {
        "company": "Petra Digital Solutions",
        "email": "hr@petra-digital.local",
        "industry": "Software Development",
        "description": (
            "An Amman software house building web platforms for banking and logistics clients "
            "across Jordan and the Gulf. Around 60 engineers, offices in Shmeisani."
        ),
        "jobs": [
            {
                "title": "Junior Backend Engineer",
                "field": "Computer Science",
                "description": (
                    "Amman (Shmeisani), hybrid — 2 days on site.\n\n"
                    "Join the platform team building REST services behind our clients' banking "
                    "portals. You will own small features end to end, from schema change to "
                    "deployment, with a senior engineer reviewing your work.\n\n"
                    "Fresh graduates welcome. Salary 700-950 JOD depending on interview outcome."
                ),
                "skills": "Java, Spring Boot, REST APIs, SQL, MySQL, Git, unit testing",
            },
            {
                "title": "Frontend Developer (React)",
                "field": "Software Engineering",
                "description": (
                    "Amman (Shmeisani), hybrid.\n\n"
                    "Build the customer-facing dashboards our banking clients put in front of "
                    "their own users. Strong emphasis on accessibility and on getting the "
                    "Arabic right-to-left layouts genuinely correct, not merely mirrored.\n\n"
                    "1-3 years experience. Salary 750-1100 JOD."
                ),
                "skills": "React, TypeScript, HTML, CSS, REST APIs, Git, responsive design",
            },
            {
                "title": "QA Automation Engineer",
                "field": "Software Engineering",
                "description": (
                    "Amman, on site.\n\n"
                    "Own the regression suite for three client platforms. You will decide what "
                    "is worth automating and what is not, and you will be listened to when you "
                    "say a release is not ready.\n\n"
                    "Salary 800-1200 JOD."
                ),
                "skills": "Selenium, Playwright, test automation, CI/CD, Java, SQL",
            },
        ],
    },
    {
        "company": "Wadi Rum Analytics",
        "email": "careers@wadirum-analytics.local",
        "industry": "Data & Analytics Consulting",
        "description": (
            "An Irbid data consultancy working with telecoms, retail chains and two "
            "universities. Small team, unusually broad exposure — analysts here see the whole "
            "pipeline rather than one slice of it."
        ),
        "jobs": [
            {
                "title": "Data Analyst",
                "field": "Data Science",
                "description": (
                    "Irbid, on site with one remote day.\n\n"
                    "Turn messy client exports into dashboards their executives actually read. "
                    "Expect to spend real time on data cleaning; we would rather you say a "
                    "dataset cannot support a conclusion than produce a confident wrong chart.\n\n"
                    "Salary 650-900 JOD."
                ),
                "skills": "Python, pandas, SQL, data visualization, Power BI, statistics, Excel",
            },
            {
                "title": "Machine Learning Engineer",
                "field": "Artificial Intelligence",
                "description": (
                    "Irbid or remote within Jordan.\n\n"
                    "Take models from a notebook to something that survives contact with "
                    "production traffic — evaluation, monitoring, retraining, the parts that are "
                    "not the model.\n\n"
                    "2+ years. Salary 1000-1600 JOD."
                ),
                "skills": "Python, scikit-learn, PyTorch, MLOps, Docker, SQL, model evaluation",
            },
            {
                "title": "Business Intelligence Developer",
                "field": "Information Systems",
                "description": (
                    "Irbid, hybrid.\n\n"
                    "Build and maintain the warehouse layer feeding client reporting. Heavy SQL, "
                    "some dbt, and a lot of conversations about what a metric actually means.\n\n"
                    "Salary 700-1000 JOD."
                ),
                "skills": "SQL, data warehousing, ETL, dbt, Power BI, dimensional modeling",
            },
        ],
    },
    {
        "company": "Jerash Cloud Systems",
        "email": "jobs@jerash-cloud.local",
        "industry": "Cloud Infrastructure",
        "description": (
            "Managed cloud and platform engineering for mid-size Jordanian businesses moving off "
            "their own server rooms. On-call is real but properly compensated and properly staffed."
        ),
        "jobs": [
            {
                "title": "Cloud & DevOps Engineer",
                "field": "Information Technology",
                "description": (
                    "Amman (Abdali), hybrid.\n\n"
                    "Own client infrastructure end to end: Terraform, pipelines, and the "
                    "monitoring that tells us before the client does. You will be handed the "
                    "pager and also the authority to fix what keeps waking you up.\n\n"
                    "Salary 1100-1700 JOD."
                ),
                "skills": "AWS, Docker, Kubernetes, Terraform, CI/CD, Linux, Bash, monitoring",
            },
            {
                "title": "Site Reliability Engineer",
                "field": "Computer Engineering",
                "description": (
                    "Amman, hybrid.\n\n"
                    "Reliability work for platforms serving a few hundred thousand users. Error "
                    "budgets are used as intended here — as a reason to stop shipping, not as a "
                    "dashboard nobody reads.\n\n"
                    "3+ years. Salary 1400-2000 JOD."
                ),
                "skills": "Linux, Kubernetes, Prometheus, Grafana, Go, Python, incident response",
            },
            {
                "title": "Junior Systems Administrator",
                "field": "Information Technology",
                "description": (
                    "Amman, on site.\n\n"
                    "First line for client infrastructure — access requests, backups, patching, "
                    "and escalating what you cannot yet solve. A genuine entry point into "
                    "infrastructure work.\n\n"
                    "Graduates welcome. Salary 550-750 JOD."
                ),
                "skills": "Linux, Windows Server, networking, Bash, Active Directory, backups",
            },
        ],
    },
    {
        "company": "Aqaba FinTech Labs",
        "email": "talent@aqaba-fintech.local",
        "industry": "Financial Technology",
        "description": (
            "Payments and lending products built in Aqaba's special economic zone. Regulated "
            "environment, so expect code review, audit trails and a genuinely slow release "
            "process — which is the point."
        ),
        "jobs": [
            {
                "title": "Mobile Developer (Flutter)",
                "field": "Mobile Development",
                "description": (
                    "Aqaba, on site — relocation support available from Amman.\n\n"
                    "Build the consumer wallet app used across the south. Offline behaviour and "
                    "Arabic localisation are first-class requirements, not a later phase.\n\n"
                    "Salary 900-1400 JOD."
                ),
                "skills": "Flutter, Dart, REST APIs, mobile UI, state management, Git",
            },
            {
                "title": "Backend Engineer (Payments)",
                "field": "Computer Science",
                "description": (
                    "Aqaba or Amman, hybrid.\n\n"
                    "Ledger and settlement services. Correctness beats throughput here — every "
                    "movement of money must reconcile, and the audit log is not optional.\n\n"
                    "2+ years. Salary 1200-1800 JOD."
                ),
                "skills": "Java, Spring Boot, PostgreSQL, REST APIs, message queues, testing",
            },
            {
                "title": "UI/UX Designer",
                "field": "Multimedia",
                "description": (
                    "Aqaba, hybrid.\n\n"
                    "Design flows for customers who are often using a financial app for the "
                    "first time. Research with real users in Aqaba and Amman is part of the "
                    "role, not an afterthought.\n\n"
                    "Salary 800-1200 JOD."
                ),
                "skills": "Figma, user research, prototyping, wireframing, accessibility, RTL design",
            },
        ],
    },
    {
        "company": "Zarqa Cyber Defense",
        "email": "recruit@zarqa-cyber.local",
        "industry": "Information Security",
        "description": (
            "A security consultancy running assessments and a small managed SOC for industrial "
            "and public-sector clients in Zarqa and Amman."
        ),
        "jobs": [
            {
                "title": "SOC Analyst (Tier 1)",
                "field": "Cybersecurity",
                "description": (
                    "Zarqa, on site, rotating shifts.\n\n"
                    "Triage alerts, escalate what matters, and write the incident notes the next "
                    "shift depends on. Structured mentoring for the first six months.\n\n"
                    "Graduates welcome. Salary 600-850 JOD."
                ),
                "skills": "SIEM, log analysis, incident response, networking, Linux, threat detection",
            },
            {
                "title": "Penetration Tester",
                "field": "Cybersecurity",
                "description": (
                    "Zarqa or Amman, hybrid, some client travel.\n\n"
                    "Web and network assessments under signed scope. Report writing is half the "
                    "job — a finding a client cannot act on has not been delivered.\n\n"
                    "2+ years. Salary 1100-1700 JOD."
                ),
                "skills": (
                    "penetration testing, Burp Suite, network security, OWASP, Python, "
                    "vulnerability assessment, report writing"
                ),
            },
        ],
    },
]


# --------------------------------------------------------------------------------------
# HTTP plumbing
# --------------------------------------------------------------------------------------

class ApiError(RuntimeError):
    def __init__(self, status: int, body: str, method: str, path: str):
        super().__init__(f"{method} {path} -> HTTP {status}: {body[:400]}")
        self.status = status
        self.body = body


class Api:
    """Thin JSON/multipart client. Standard library only, so it runs anywhere the repo does."""

    def __init__(self, base_url: str, timeout: int = 60, verbose: bool = False):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.verbose = verbose

    def request(self, method, path, *, token=None, body=None, raw=None,
                content_type=None, timeout=None):
        url = f"{self.base_url}{path}"
        data = None
        headers = {
            "Accept": "application/json",
            # Free ngrok tunnels serve an interstitial to anything that looks like a browser.
            "ngrok-skip-browser-warning": "true",
            "User-Agent": "careercompass-seed/1.0",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif raw is not None:
            data = raw
            headers["Content-Type"] = content_type
        if token:
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as resp:
                payload = resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", "replace")
            raise ApiError(exc.code, payload, method, path) from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"{method} {path} failed to connect: {exc.reason}") from None

        if not payload.strip():
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return payload

    def get(self, path, token=None, timeout=None):
        return self.request("GET", path, token=token, timeout=timeout)

    def post(self, path, body=None, token=None, timeout=None):
        return self.request("POST", path, body=body or {}, token=token, timeout=timeout)

    def put(self, path, body=None, token=None, timeout=None):
        return self.request("PUT", path, body=body or {}, token=token, timeout=timeout)

    def patch(self, path, body=None, token=None, timeout=None):
        return self.request("PATCH", path, body=body or {}, token=token, timeout=timeout)

    def post_file(self, path, field, file_path: Path, token=None, timeout=None):
        boundary = f"----CareerCompassSeed{uuid.uuid4().hex}"
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        head = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{field}"; filename="{file_path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        tail = f"\r\n--{boundary}--\r\n".encode()
        payload = head + file_path.read_bytes() + tail
        return self.request(
            "POST", path, token=token, raw=payload,
            content_type=f"multipart/form-data; boundary={boundary}", timeout=timeout,
        )


# --------------------------------------------------------------------------------------
# Output helpers
# --------------------------------------------------------------------------------------

_created = 0
_reused = 0


def step(msg):
    print(f"\n=== {msg}", flush=True)


def ok(msg):
    global _created
    _created += 1
    print(f"  + {msg}", flush=True)


def skip(msg):
    global _reused
    _reused += 1
    print(f"  = {msg} (already present)", flush=True)


def warn(msg):
    print(f"  ! {msg}", flush=True)


def email_for(first: str, last: str, domain: str) -> str:
    """
    firstname.lastname@domain, with the hyphens dropped out of names like "Al-Rousan".

    Every domain here is `.local`, which RFC 6762 reserves and no mail system will ever route.
    These are demo accounts with a shared, written-down password; a typo that turned one into a
    deliverable address would be a nuisance to a real stranger.
    """
    slug = f"{first}.{last}".lower().replace("'", "").replace("-", "").replace(" ", "")
    return f"{slug}@{domain}"


def is_conflict(exc: ApiError) -> bool:
    """A duplicate, however this deployment phrases it."""
    if exc.status == 409:
        return True
    if exc.status in (400, 422):
        lowered = exc.body.lower()
        return any(w in lowered for w in ("already", "exists", "duplicate", "taken", "in use"))
    return False


# --------------------------------------------------------------------------------------
# Seeding phases
# --------------------------------------------------------------------------------------

def seed_reference_data(api: Api, admin_token: str):
    """Universities, study fields and career paths — everything an admin alone can create."""

    step("Universities")
    existing = {u["universityName"]: u["universityId"]
                for u in api.get("/api/admin/universities", admin_token)}
    universities = dict(existing)
    for name in UNIVERSITIES:
        if name in universities:
            skip(name)
            continue
        created = api.post("/api/admin/universities", {"universityName": name}, admin_token)
        universities[name] = created["universityId"]
        ok(name)

    step("Study fields")
    existing = {f["fieldName"]: f["studyFieldId"]
                for f in api.get("/api/admin/study-fields", admin_token)}
    fields = dict(existing)
    for name in STUDY_FIELDS:
        if name in fields:
            skip(name)
            continue
        created = api.post("/api/admin/study-fields", {"fieldName": name}, admin_token)
        fields[name] = created["studyFieldId"]
        ok(name)

    step("Career paths")
    existing = {p["title"]: p["careerPathId"]
                for p in api.get("/api/admin/career-paths", admin_token)}
    paths = dict(existing)
    for spec in CAREER_PATHS:
        if spec["title"] in paths:
            skip(spec["title"])
            continue
        created = api.post("/api/admin/career-paths", {
            "title": spec["title"],
            "careerPathCode": spec["code"],
            "description": spec["description"],
            "studyFieldIds": [fields[f] for f in spec["fields"]],
        }, admin_token)
        paths[spec["title"]] = created["careerPathId"]
        ok(f"{spec['title']}  ({', '.join(spec['fields'])})")

    return universities, fields, paths


def seed_content_managers(api: Api, admin_token: str, universities, fields, password):
    step("Content managers")
    existing = {c["email"] for c in api.get("/api/admin/content-managers", admin_token)}
    accounts = []
    for first, last, university, field in CONTENT_MANAGERS:
        email = email_for(first, last, "content.local")
        accounts.append((f"{first} {last}", email, university, field))
        if email in existing:
            skip(email)
            continue
        try:
            api.post("/api/admin/content-managers", {
                "firstName": first,
                "lastName": last,
                "email": email,
                "initialPassword": password,
                "universityId": universities[university],
                "studyFieldId": fields[field],
            }, admin_token)
            ok(f"{first} {last} — {university} · {field}")
        except ApiError as exc:
            if is_conflict(exc):
                skip(email)
            else:
                raise
    return accounts


def seed_mentors(api: Api, admin_token: str, fields, password):
    """
    Create each mentor, then sign in as them to activate and publish a schedule.

    Both of those are the mentor's own decisions (FR-EX-02), so there is no admin route for
    them. A mentor left inactive never appears in a student's mentor list, and one with no
    published slots cannot be booked at all — either would look like a broken screen rather
    than an unfinished account.
    """
    step("Mentors")
    existing = {e["email"] for e in api.get("/api/admin/experts", admin_token)}
    accounts = []

    for first, last, field, since, schedule in MENTORS:
        email = email_for(first, last, "mentors.local")
        accounts.append((f"{first} {last}", email, field, since, schedule))

        if email in existing:
            skip(f"{email} — account")
        else:
            try:
                api.post("/api/admin/experts", {
                    "firstName": first,
                    "lastName": last,
                    "email": email,
                    "initialPassword": password,
                    "studyFieldId": fields[field],
                    "fieldStartingYear": since,
                }, admin_token)
                ok(f"{first} {last} — {field}, since {since}")
            except ApiError as exc:
                if is_conflict(exc):
                    skip(f"{email} — account")
                else:
                    raise

        try:
            token = api.post("/api/auth/experts/login",
                             {"email": email, "password": password})["token"]
        except ApiError as exc:
            warn(f"{email}: cannot sign in to activate ({exc.status}) — "
                 f"password may differ from the one given to this script")
            continue

        api.patch("/api/experts/me/status/activate", {}, token)
        api.put("/api/experts/me/availability", {
            "slots": [
                {"dayOfWeek": day, "startTime": start, "endTime": end}
                for day, start, end in schedule
            ]
        }, token)
        ok(f"{first} {last} — activated, {len(schedule)} weekly slots published")

    return accounts


def seed_employers(api: Api, password, fields):
    step("Employers and job postings")
    accounts = []
    for spec in EMPLOYERS:
        email = spec["email"]
        try:
            auth = api.post("/api/auth/employers/register", {
                "companyName": spec["company"],
                "industry": spec["industry"],
                "email": email,
                "password": password,
                "companyDescription": spec["description"],
            })
            ok(f"{spec['company']} — {email}")
        except ApiError as exc:
            if not is_conflict(exc):
                raise
            skip(email)
            auth = api.post("/api/auth/employers/login", {"email": email, "password": password})

        token = auth["token"]
        posted = {j["title"] for j in (api.get("/api/employers/me/jobs", token) or [])}
        titles = []
        for job in spec["jobs"]:
            titles.append(job["title"])
            if job["title"] in posted:
                skip(f"{spec['company']} · {job['title']}")
                continue
            api.post("/api/employers/me/jobs", {
                "title": job["title"],
                "description": job["description"],
                "requiredSkills": job["skills"],
                "studyFieldId": fields[job["field"]],
            }, token)
            ok(f"{spec['company']} · {job['title']}")

        accounts.append((spec["company"], email, titles))
    return accounts


def seed_students(api: Api, universities, fields, paths, password,
                  transcript_dir: Path, do_transcripts: bool):
    step("Students")
    accounts = []

    for first, last, university, field, path, transcript in STUDENTS:
        email = email_for(first, last, "student.local")
        stage = "new"

        try:
            auth = api.post("/api/auth/job-seekers/register", {
                "firstName": first, "lastName": last, "email": email, "password": password,
            })
            ok(f"{first} {last} — {email}")
        except ApiError as exc:
            if not is_conflict(exc):
                raise
            skip(email)
            auth = api.post("/api/auth/job-seekers/login", {"email": email, "password": password})

        token = auth["token"]

        if university and field and path:
            api.put("/api/job-seekers/me", {
                "universityId": universities[university],
                "studyFieldId": fields[field],
                "careerPathId": paths[path],
            }, token)
            ok(f"{first} {last} — {university} · {field} → {path}")
            stage = "path"

        if transcript and do_transcripts:
            pdf = transcript_dir / transcript
            if not pdf.is_file():
                warn(f"{first} {last}: transcript not found at {pdf} — left without one")
            else:
                stage = seed_transcript(api, token, first, last, pdf) or stage

        accounts.append((f"{first} {last}", email, university, field, path, stage))

    return accounts


def seed_transcript(api: Api, token, first, last, pdf: Path):
    """
    Upload, then confirm. Extraction runs through the AI service and is slow — several minutes
    on a cold index — so this uses a much longer timeout than everything else.
    """
    # No transcript yet is an error here, not an empty dashboard — that is the signal to proceed.
    try:
        dashboard = api.get("/api/job-seekers/me/skill-dashboard", token=token, timeout=120)
        if isinstance(dashboard, dict) and dashboard.get("skills"):
            skip(f"{first} {last} — transcript already confirmed")
            return "transcript"
    except ApiError:
        pass

    print(f"  … {first} {last}: extracting {pdf.name} (this can take a few minutes)", flush=True)
    started = time.monotonic()
    try:
        review = api.post_file("/api/job-seekers/me/transcript", "file", pdf,
                               token=token, timeout=600)
    except ApiError as exc:
        warn(f"{first} {last}: transcript upload failed ({exc.status}) — {exc.body[:200]}")
        return None

    # Confirm rejects a blank name or grade, and extraction legitimately produces some of both
    # for rows that are not graded courses at all (headers, GPA lines, transfer credit).
    courses = [
        {
            "courseCode": c.get("courseCode"),
            "courseName": (c.get("courseName") or "").strip(),
            "grade": (c.get("grade") or "").strip(),
        }
        for c in (review.get("courses") or [])
    ]
    courses = [c for c in courses if c["courseName"] and c["grade"]]

    if not courses:
        warn(f"{first} {last}: nothing usable extracted from {pdf.name} — left without a transcript")
        return None

    try:
        dashboard = api.post("/api/job-seekers/me/transcript/confirm",
                             {"courses": courses}, token=token, timeout=600)
    except ApiError as exc:
        warn(f"{first} {last}: confirm failed ({exc.status}) — {exc.body[:200]}")
        return None

    elapsed = time.monotonic() - started
    if isinstance(dashboard, dict):
        skills = len(dashboard.get("skills") or [])
        readiness = dashboard.get("overallReadinessPercent")
        counted = dashboard.get("coursesCounted")
        ok(f"{first} {last} — {len(courses)} courses confirmed ({counted} readable), "
           f"{skills} skills, {readiness}% ready, {elapsed:.0f}s")
    else:
        ok(f"{first} {last} — {len(courses)} courses confirmed, {elapsed:.0f}s")
    return "transcript"


# --------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Seed CareerCompass with a Jordanian demo dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--base-url", required=True,
                        help="e.g. https://your-host or http://localhost")
    parser.add_argument("--admin-email", required=True,
                        help="an administrator that already exists in the database")
    parser.add_argument("--admin-password", default=None,
                        help="omit to be prompted without echo")
    parser.add_argument("--password", default=None,
                        help="shared password for every seeded demo account "
                             "(env CC_SEED_PASSWORD; prompted if neither is given)")
    parser.add_argument("--skip-transcripts", action="store_true",
                        help="do not upload transcripts — much faster, students stop at "
                             "'career path chosen'")
    parser.add_argument("--transcript-dir", default=str(DEFAULT_TRANSCRIPT_DIR),
                        help=f"default: {DEFAULT_TRANSCRIPT_DIR}")
    args = parser.parse_args()

    admin_password = args.admin_password or os.environ.get("CC_ADMIN_PASSWORD")
    if not admin_password:
        admin_password = getpass.getpass("Administrator password: ")

    demo_password = args.password or os.environ.get("CC_SEED_PASSWORD")
    if not demo_password:
        demo_password = getpass.getpass("Shared password for seeded demo accounts: ")
    if len(demo_password) < 8:
        sys.exit("Demo password must be at least 8 characters — the API rejects anything shorter.")

    api = Api(args.base_url)

    print(f"Target: {api.base_url}")
    health = api.get("/actuator/health")
    print(f"Health: {health}")

    try:
        admin_token = api.post("/api/auth/admins/login",
                               {"email": args.admin_email, "password": admin_password})["token"]
    except ApiError as exc:
        if exc.status == 401:
            sys.exit(f"Administrator sign-in rejected for {args.admin_email}. Create the first "
                     f"administrator first — see deployplan.md section 5.5.")
        raise
    print(f"Signed in as {args.admin_email}")

    universities, fields, paths = seed_reference_data(api, admin_token)
    managers = seed_content_managers(api, admin_token, universities, fields, demo_password)
    mentors = seed_mentors(api, admin_token, fields, demo_password)
    employers = seed_employers(api, demo_password, fields)
    students = seed_students(api, universities, fields, paths, demo_password,
                             Path(args.transcript_dir), not args.skip_transcripts)

    step("Summary")
    print(f"  universities      {len(universities)}")
    print(f"  study fields      {len(fields)}")
    print(f"  career paths      {len(paths)}")
    print(f"  content managers  {len(managers)}")
    print(f"  mentors           {len(mentors)}")
    print(f"  employers         {len(employers)} "
          f"({sum(len(e[2]) for e in employers)} job postings)")
    print(f"  students          {len(students)}")
    print(f"\n  {_created} created, {_reused} already present")
    print("\nDone. Update ACCOUNTS.txt if the shared password changed.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted. Re-running is safe — every step checks before it creates.")
