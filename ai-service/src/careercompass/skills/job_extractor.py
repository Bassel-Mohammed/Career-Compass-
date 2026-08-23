"""
CareerCompass — Job Posting Skill Extractor

The job-market half of the skill join. Turns a scraped posting into the
same weighted, levelled skill records the syllabus extractor produces, so
both sides reach SkillMatcher through one interface and resolve onto one
taxonomy.

A posting is a much dirtier document than a syllabus. Three things in it
are not skills and would otherwise dominate the result, because they are
the most repeated text in the whole corpus:

    - section headings      "Responsibilities" appears in 960 postings and
                            is structure, not content
    - EEO boilerplate       the protected-class list in 21% of postings
                            reads as a skill vector of "religion", "age",
                            "sexual orientation"
    - scrape residue        some rows are a whole web page, navigation menu
                            included

So the zones are found first and the noise is cut before any phrase is
mined. Sections that carry no skills at all — benefits, company blurb,
perks — are dropped whole rather than filtered term by term.

Usage:
    from careercompass.skills.job_extractor import extract_job_skills

    skills = extract_job_skills(posting)   # a row from linkedin_jobs
"""

import re

from careercompass.skills.phrases import (
    LEAD_RE, NOISE_TERMS, add_mention, finalize, is_usable, phrases,
)

# ── Zones ──────────────────────────────────────────────────────
#
# What a mention is worth, by the section it was found in. A requirement
# is a direct statement of what the employer needs; a responsibility only
# implies the skills behind the task, so it is worth less.
SOURCE_WEIGHTS = {
    "title": 1.0,
    "requirements": 1.0,
    "qualifications": 0.9,
    "responsibilities": 0.7,
    "body": 0.5,
}

# Headings, as they are actually written. Frequencies from the 2,238
# scraped postings are in docs/; the long tail below ~50 occurrences is
# not worth enumerating, and falls through to "body".
SECTION_HEADINGS = {
    "requirements": (
        "requirements", "required skills", "required qualifications",
        "minimum qualifications", "must have", "what we're looking for",
        "what we are looking for", "who you are", "skills", "technical skills",
        "key skills", "required experience", "essential skills",
    ),
    "qualifications": (
        "qualifications", "preferred qualifications", "nice to have",
        "nice-to-have", "preferred", "preferred skills", "bonus points",
        "desired skills", "education", "good to have", "plus points",
    ),
    "responsibilities": (
        "responsibilities", "key responsibilities", "what you'll do",
        "what you will do", "what you’ll do", "duties", "the role",
        "role overview", "your role", "job description", "about the role",
        "job summary", "description", "your impact", "day to day",
        "what you'll be doing", "main duties", "job brief", "scope of work",
    ),
    # Carries no skills. Dropped whole: the terms inside are salary,
    # insurance and office perks, and they are stated repetitively enough
    # to outrank real skills if they survive.
    "_drop": (
        "benefits", "what we offer", "about us", "who we are", "why join",
        "why join us", "perks", "perks and benefits", "our culture",
        "compensation", "salary", "how to apply", "apply now",
        "company overview", "about the company", "equal opportunity",
        "eeo statement", "our values", "what we provide", "contact us",
        "disclaimer", "note", "location", "employment type",
    ),
}
ZONE_OF_HEADING = {
    heading: zone
    for zone, headings in SECTION_HEADINGS.items()
    for heading in headings
}

DROP_ZONE = "_drop"
DEFAULT_ZONE = "body"

# A heading is short, unpunctuated and on its own line. The length bound
# keeps a sentence that merely opens with "Requirements for this role
# include..." from being read as a section break.
MAX_HEADING_CHARS = 45
HEADING_TRIM_RE = re.compile(r"^[\s\W_]+|[\s:：.\-–—]+$")


# ── Boilerplate ────────────────────────────────────────────────

# The equal-opportunity statement. Present in 483 of 2,238 postings, and
# every protected class in it reads as a skill to a phrase miner.
EEO_RE = re.compile(
    r"equal opportunit|equal employment|regardless of race|without regard to|"
    r"protected veteran|affirmative action|all qualified applicants|"
    r"race,\s*(?:color|colour)|discriminat",
    re.IGNORECASE,
)

# The tail of an EEO statement, when the scrape broke it across lines and
# only the protected-class list is left on its own.
PROTECTED_CLASSES = (
    "race", "color", "colour", "religion", "sex", "gender", "gender identity",
    "sexual orientation", "national origin", "age", "disability", "genetics",
    "veteran status", "marital status", "pregnancy", "creed", "ancestry",
    "citizenship", "ethnicity", "nationality", "protected veteran",
)
PROTECTED_LIST_RE = re.compile(
    r"^\W*(?:(?:%s)\b\W*(?:,|and|or)?\W*)+$" % "|".join(
        re.escape(term) for term in PROTECTED_CLASSES
    ),
    re.IGNORECASE,
)

# Application and listing chrome the scraper pulled in with the body.
CHROME_RE = re.compile(
    r"^\s*(?:apply now|apply here|submit your (?:cv|resume|application)|"
    r"send your (?:cv|resume)|click here|read more|share this job|"
    r"back to (?:jobs|careers)|view all jobs|follow us|book a consultation|"
    r"job type|posted on|seniority level|employment type|job function|"
    r"industries|referrals?|get notified|sign in|log in)\b",
    re.IGNORECASE,
)

# Site navigation. Shape alone cannot separate a nav menu from a list of
# one-word skills — "Home / Services / Careers" and "Docker / Redis /
# Kafka" are identically shaped — so the run is identified by vocabulary
# instead. A closed list of chrome words has essentially no overlap with
# any skill, where a shape rule would silently eat real requirement
# bullets.
NAV_WORDS = frozenset({
    "home", "about", "about us", "services", "service", "products",
    "product", "solutions", "industries", "methodology", "blog", "news",
    "events", "careers", "career", "jobs", "contact", "contact us",
    "portfolio", "pricing", "resources", "team", "our team", "clients",
    "case studies", "testimonials", "faq", "faqs", "support", "login",
    "log in", "sign in", "sign up", "register", "search", "menu",
    "privacy", "privacy policy", "terms", "terms of use", "cookies",
    "sitemap", "gallery", "partners", "insights", "company", "who we are",
    "what we do", "get in touch", "book a consultation", "follow us",
    "newsletter", "subscribe", "download", "language", "english",
})
MIN_MENU_RUN = 3

# ── Terms ──────────────────────────────────────────────────────
#
# Filler that survives phrase mining because it is grammatically a noun
# phrase. Every entry here was measured in the top terms of a full corpus
# run; they are the difference between an ontology of skills and an
# ontology of recruiting prose.
JOB_NOISE_TERMS = NOISE_TERMS | {
    # Posting scaffolding
    "responsibilities", "key responsibilities", "requirements", "qualifications",
    "preferred qualifications", "required qualifications", "job description",
    "about the role", "the role", "role", "job summary", "job brief",
    "benefits", "what we offer", "about us", "who we are", "why join us",
    "location", "employment type", "job type", "full-time", "part-time",
    "remote", "hybrid", "on-site", "onsite", "contract", "internship",
    "salary", "compensation", "apply now", "how to apply", "company",
    "team", "teams", "role overview", "position", "opportunity", "candidate",
    "candidates", "applicants", "employer", "employees", "employee",
    # Recruiting prose
    "experience", "experiences", "years", "years of experience", "skills",
    "skill", "abilities", "ability", "knowledge", "understanding", "education",
    "degree", "bachelor", "bachelors", "master", "masters", "phd",
    "related field", "relevant field", "similar field", "equivalent",
    "we are looking", "you will", "we offer", "you have", "we are",
    "e.g", "i.e", "etc.", "plus", "strong", "excellent", "good", "solid",
    "proven", "demonstrated", "hands on", "hands-on", "familiarity",
    "proficiency", "expertise", "background", "track record", "passion",
    "willingness", "attention", "attention to detail", "detail",
    "environment", "environments", "industry", "business", "clients",
    "client", "customers", "customer", "stakeholders", "stakeholder",
    "requirement", "responsibility", "duties", "duty", "tasks",
    "work", "working", "job", "jobs", "career", "careers", "growth",
    "quality", "best practices", "standards", "processes", "process",
    "solutions", "solution", "products", "product", "services", "service",
    "technologies", "technology", "platforms", "platform", "features",
    "feature", "issues", "issue", "needs", "need", "goals", "goal",
    "objectives", "objective", "results", "result", "impact", "value",
    # Benefits vocabulary. Some postings list perks without a heading to
    # drop, and "dental" was the 102nd most common term in the corpus
    # before this set existed.
    "dental", "medical", "vision", "insurance", "health insurance",
    "life insurance", "pto", "paid time off", "annual leave", "sick leave",
    "parental leave", "maternity leave", "401k", "pension", "gym",
    "wellness", "bonus", "bonuses", "equity", "stock options", "rsus",
    "flexible hours", "flexible working", "work life balance", "relocation",
    "visa", "sponsorship", "meal", "transportation", "allowance",
    # Bare verbs. A verb alone names an activity, not a competency, and
    # the noun form is already in the taxonomy where one exists
    # ("monitoring" is a skill, "monitor" is prose).
    "monitor", "maintain", "manage", "deploy", "configure", "debug",
    "plan", "prepare", "support", "deliver", "drive", "ensure", "provide",
    "participate", "collaborate", "contribute", "assist", "coordinate",
    "execute", "operate", "handle", "conduct", "produce", "report",
    "designing", "developing", "building", "writing", "creating",
    "managing", "working", "leading", "supporting", "ensuring",
    "responsible", "lead", "own", "help",
    # Prose residue that survives as a grammatical noun phrase.
    "you", "we", "us", "here", "more", "this role", "the role", "our team",
    "the team", "the ideal candidate", "ideal candidate", "similar",
    "we're looking", "we’re looking", "you will be responsible",
    "preferred", "required", "desired", "essential", "mandatory",
    "opportunities", "trends", "patterns", "competencies", "certifications",
    # People, not skills.
    "designers", "designer", "engineers", "engineer", "developers",
    "developer", "product managers", "product manager", "team members",
    "colleagues", "peers", "management", "leadership team", "users", "user",
    # Bare category nouns. These name an area of work, not a competency,
    # and they are dangerous rather than merely useless: retrieval always
    # finds *some* entry for them, so "development" resolves confidently
    # to "REST API development" and "automation" to "test automation".
    # A wrong canonical id is invisible once stored, and these terms are
    # frequent enough to outrank the real skills they displace.
    "development", "implementation", "deployment", "delivery", "operations",
    "maintenance", "innovation", "administration", "configuration",
    "migration", "optimization", "validation", "execution", "adoption",
    "transformation", "enablement", "excellence", "efficiency",
    "productivity", "alignment", "ownership", "accountability",
    "visibility", "consistency", "availability", "maintainability",
    "scalability", "reliability", "performance", "integration",
    "integrations", "reporting", "engineering", "operations support",
    "improvement", "continuous improvement", "enhancement", "initiatives",
    "initiative", "capabilities", "capability", "functionality",
    "deliverables", "milestones", "roadmap", "strategy", "vision",
    # Fields of study, which appear only as degree requirements.
    "related discipline", "similar discipline", "information systems",
    "information technology", "related area", "relevant discipline",
    # EEO vocabulary, as a backstop for statements the block cut missed
    *PROTECTED_CLASSES,
    "protected class", "protected status", "veteran", "veterans",
    "equal opportunity", "equal opportunity employer", "discrimination",
    "diversity", "inclusion", "belonging", "harassment",
}

# ── Term Refinement ────────────────────────────────────────────
#
# Postings wrap the same skill in evaluative padding: "strong
# communication skills", "excellent communication", "communication
# skills" and "communication" are one requirement written four ways. The
# strips below fold them together rather than dropping them, which is
# what turns four weak signals into one strong one.

# "5+ years of experience in Kubernetes" -> "Kubernetes"
YEARS_RE = re.compile(
    r"^\W*\d+\s*\+?\s*(?:-\s*\d+\s*)?years?\b(?:\s+of)?"
    r"(?:\s+(?:hands[-\s]?on\s+)?(?:professional\s+|relevant\s+|prior\s+)?"
    r"(?:experience|work)\b)?(?:\s+(?:in|with|using|as))?\s*",
    re.IGNORECASE,
)

# Evaluative adjectives that grade a skill without naming one.
EVALUATIVE_LEAD_RE = re.compile(
    r"^(?:strong|excellent|good|solid|great|deep|extensive|broad|proven|"
    r"demonstrated|hands[-\s]?on|working|practical|thorough|sound|superior|"
    r"exceptional|outstanding|relevant|prior|previous|significant|"
    r"substantial|comprehensive|familiar(?:ity)?\s+with|proficien(?:t|cy)\s+"
    r"(?:in|with)|expertise\s+in|experience\s+(?:in|with|using)|"
    r"knowledge\s+of|understanding\s+of|ability\s+to|able\s+to)\s+",
    re.IGNORECASE,
)

# Head nouns that add nothing once the skill itself is named.
TRAILING_NOUN_RE = re.compile(
    r"\s+(?:skills?|abilit(?:y|ies)|knowledge|experience|expertise|"
    r"proficiency|background|competenc(?:y|ies)|capabilit(?:y|ies)|"
    r"fundamentals|principles|techniques|practices|methodologies)$",
    re.IGNORECASE,
)

# Action verbs a posting opens a bullet with. The Bloom vocabulary in
# phrases.py covers the ones a syllabus uses; postings chain a wider set,
# and chain several at once — "Design, develop, and maintain ..." leaves
# "maintain" heading the phrase once Bloom's "design" is stripped.
JOB_LEAD_VERB_RE = re.compile(
    r"^(?:maintain|manage|monitor|deploy|configure|debug|support|deliver|"
    r"drive|ensure|provide|participate|collaborate|contribute|assist|"
    r"coordinate|execute|operate|handle|conduct|produce|report|own|lead|"
    r"help|work|write|ship|scale|automate|test|document|refactor|migrate|"
    r"translate|partner|mentor|guide|champion|own|oversee|track|"
    r"maintaining|managing|monitoring|deploying|configuring|debugging|"
    r"supporting|delivering|ensuring|providing|participating|collaborating|"
    r"contributing|coordinating|executing|operating|handling|conducting|"
    r"writing|shipping|scaling|automating|documenting|refactoring|migrating)"
    r"(?:\s+(?:and|or|&)\s*)?\s+",
    re.IGNORECASE,
)

# An education requirement, not a skill.
DEGREE_RE = re.compile(
    r"^(?:a\s+)?(?:bachelor|master|bachelors|masters|bsc|b\.sc|msc|m\.sc|"
    r"ba|bs|ms|phd|doctorate|university|college|academic)\b|"
    r"\bdegree\b|\bdiploma\b",
    re.IGNORECASE,
)


def refine(term: str) -> str:
    """
    Strip recruiting padding from a candidate so variants collapse.

    Applied after phrase splitting rather than inside it, because the
    padding is specific to how postings are written — a syllabus does not
    say "strong Python skills".
    """
    previous = None
    while term and term != previous:
        previous = term
        term = YEARS_RE.sub("", term)
        term = JOB_LEAD_VERB_RE.sub("", term)
        term = EVALUATIVE_LEAD_RE.sub("", term)
        term = LEAD_RE.sub("", term)
        term = TRAILING_NOUN_RE.sub("", term)
        term = term.strip(" \t-–—,;:&")
    return term


# ── Levels ─────────────────────────────────────────────────────
#
# What the posting is asking for, not what it teaches. LinkedIn's own
# field is authoritative but present on only 43% of the corpus, so the
# title carries the rest.
SENIORITY_LEVELS = {
    "internship": "beginner",
    "entry level": "beginner",
    "associate": "intermediate",
    "mid-senior level": "advanced",
    "director": "advanced",
    "executive": "advanced",
}
SENIOR_TITLE_RE = re.compile(
    r"\b(?:senior|sr\.?|lead|principal|staff|head|chief|architect|manager|"
    r"director|expert|specialist)\b",
    re.IGNORECASE,
)
JUNIOR_TITLE_RE = re.compile(
    r"\b(?:junior|jr\.?|intern|internship|trainee|graduate|entry[-\s]?level|"
    r"apprentice|fresher)\b",
    re.IGNORECASE,
)


# Grade, location and contract markers a title carries around the role
# itself: "Senior Backend Engineer II (Remote)" is a backend engineer.
TITLE_MODIFIER_RE = re.compile(
    r"\b(?:senior|sr\.?|junior|jr\.?|lead|principal|staff|entry[-\s]?level|"
    r"mid[-\s]?level|graduate|trainee|intern(?:ship)?|apprentice|fresher|"
    r"remote|hybrid|onsite|on[-\s]?site|full[-\s]?time|part[-\s]?time|"
    r"contract|freelance|permanent|temporary|urgent|hiring|"
    r"[ivx]+|[1-5])\b",
    re.IGNORECASE,
)


def strip_title_modifiers(title: str) -> str:
    """Reduce a job title to the role it names."""
    cleaned = TITLE_MODIFIER_RE.sub(" ", title)
    cleaned = re.sub(r"[(\[][^)\]]*[)\]]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" .-–—/|,:")


def job_level(job: dict) -> str:
    """
    Resolve what depth of skill a posting is asking for.

    Prefers LinkedIn's `seniority_level`; falls back to the title, which
    is the only signal on the 57% of postings where the field is null.
    """
    seniority = (job.get("seniority_level") or "").strip().lower()
    if seniority in SENIORITY_LEVELS:
        return SENIORITY_LEVELS[seniority]

    title = job.get("title") or ""
    if JUNIOR_TITLE_RE.search(title):
        return "beginner"
    if SENIOR_TITLE_RE.search(title):
        return "advanced"
    return "intermediate"


# ── Sectioning ─────────────────────────────────────────────────
def _heading_zone(line: str):
    """The zone a line opens, or None when it is not a heading."""
    if len(line) > MAX_HEADING_CHARS:
        return None
    key = HEADING_TRIM_RE.sub("", line).lower()
    return ZONE_OF_HEADING.get(key)


def _is_nav_line(line: str) -> bool:
    """Whether a line is a site-navigation link rather than content."""
    return HEADING_TRIM_RE.sub("", line).lower() in NAV_WORDS


def _drop_menu_runs(lines: list) -> list:
    """
    Remove runs of consecutive navigation links.

    A single nav word is left alone — "Support" can head a real section,
    and "Company" can open a sentence. Three in a row is a menu the
    scraper captured along with the posting, and dropping the run rather
    than each word keeps a lone legitimate use intact.
    """
    kept = []
    run = []
    for line in lines:
        if _is_nav_line(line):
            run.append(line)
            continue
        if len(run) < MIN_MENU_RUN:
            kept.extend(run)
        run = []
        kept.append(line)
    if len(run) < MIN_MENU_RUN:
        kept.extend(run)
    return kept


def _clean_lines(description: str) -> list:
    """Strip boilerplate before any structure is read off the text."""
    lines = []
    for raw in (description or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if EEO_RE.search(line) or PROTECTED_LIST_RE.fullmatch(line):
            continue
        if CHROME_RE.match(line):
            continue
        lines.append(line)
    return _drop_menu_runs(lines)


def sections(description: str) -> list:
    """
    Split a description into (zone, line) pairs.

    Everything before the first recognised heading is `body`: many
    postings open with an unlabelled summary paragraph, and it carries
    real skills even though nothing announces it.

    Lines under a `_drop` heading are excluded here rather than filtered
    later, because a benefits list is uniform prose that no term-level
    rule reliably separates from a requirements list.
    """
    zone = DEFAULT_ZONE
    result = []
    for line in _clean_lines(description):
        heading = _heading_zone(line)
        if heading is not None:
            zone = heading
            continue
        if zone != DROP_ZONE:
            result.append((zone, line))
    return result


# ── Extraction ─────────────────────────────────────────────────
def extract_job_skills(job: dict) -> list:
    """
    Extract candidate skills from one job posting.

    Args:
        job: A posting with `title`, `description` and optionally
            `seniority_level` — a row of linkedin_jobs, or an entry of
            data/clean/all_jobs.json.

    Returns:
        Skill dictionaries in the shape SkillMatcher expects, strongest
        first: term, canonical (None), level, weight, evidence_count,
        sources, evidence.
    """
    found = {}
    level = job_level(job)

    title = (job.get("title") or "").strip()
    for term in _job_phrases(strip_title_modifiers(title)):
        add_mention(found, term, "title", level,
                    {"source": "title", "text": title})

    for zone, line in sections(job.get("description", "")):
        for term in _job_phrases(line):
            add_mention(found, term, zone, level,
                        {"source": zone, "text": line})

    return finalize(found, SOURCE_WEIGHTS)


def _job_phrases(text: str) -> list:
    """
    Split a line of posting text into candidate skill phrases.

    Refinement runs after the split and the result is re-tested, because
    stripping padding can turn a usable phrase into filler: "strong
    analytical skills" refines to "analytical", and "excellent
    communication skills" to "communication".
    """
    terms = []
    seen = set()
    for candidate in phrases(text, noise_terms=JOB_NOISE_TERMS):
        if DEGREE_RE.search(candidate):
            continue
        term = refine(candidate)
        key = term.lower()
        if key in seen:
            continue
        if is_usable(term, noise_terms=JOB_NOISE_TERMS):
            seen.add(key)
            terms.append(term)
    return terms
