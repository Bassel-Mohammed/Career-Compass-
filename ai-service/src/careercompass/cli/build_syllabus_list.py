"""Build data/plans/required_syllabi.md from the study plans.

Reads the plan PDFs directly rather than through parsing.transcript, because
that parser rejects letter-prefixed course codes (COURSE_CODE_RE = ^0\\d{6}$)
and returns zero courses for the newer plan editions.

Collection status is derived from disk on every run:
  extracted  - a JSON in data/extracted/syllabi/
  collected  - a syllabus PDF in data/syllabi/, not yet extracted
  needed     - neither

Adding a plan means one line in PLAN_FILES; dropping a course means one line
in EXCLUDED_CODES.

    python -m careercompass.cli.build_syllabus_list
"""
import collections
import json
import re
import sys
from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[3]
PLANS = ROOT / "data" / "plans"
FIXTURES = ROOT / "data" / "syllabi"
EXTRACTED_DIR = ROOT / "data" / "extracted" / "syllabi"
OUT = PLANS / "required_syllabi.md"

# The older Cyber Security edition is superseded by edition 2 and describes a
# plan no current student is on. Its PDF stays in data/plans/ deliberately: for
# several courses it is the only document linking the old and new code schemes.
PLAN_FILES = [
    ("CS/AI", "Computer Science \\ Artificial Intelligence", "202411766_CS_AI_plan.pdf"),
    ("CS", "Computer Science (edition 7)", "202310442_old_plan_CS.pdf"),
    ("CYBER", "Cyber Security (edition 2)", "202510446_new_paln_cyber_security.pdf"),
    ("SE", "Software Engineering (edition 1)", "202410100_software_enineering.pdf"),
]
RETIRED = [("Cyber Security (older edition)", "202410709_old_plan_cyber_security.pdf")]

# Courses dropped by hand, on top of the category scope below. Each sits in an
# in-scope category but contributes nothing the skill map can use.
EXCLUDED_CODES = {
    "0181201": "science requirement, no IT skill content",
    "0181202": "science requirement, no IT skill content",
    "0181301": "science requirement, no IT skill content",
    "0414406": "content varies by term; no fixed syllabus",
    "A0434407": "content varies by term; no fixed syllabus",
    "0414501": "content is student-specific; no fixed syllabus",
    "0434501": "content is student-specific; no fixed syllabus",
    "A0434501": "content is student-specific; no fixed syllabus",
    "0414502": "content is student-specific; no fixed syllabus",
    "0434502": "content is student-specific; no fixed syllabus",
    "A0434502": "content is student-specific; no fixed syllabus",
    "0414503": "content is student-specific; no fixed syllabus",
    "A0434503": "content is student-specific; no fixed syllabus",
    "0444601": "content is student-specific; no fixed syllabus",
    "0444602": "content is student-specific; no fixed syllabus",
    "0444603": "content is student-specific; no fixed syllabus",
}
excluded_seen = {}   # code -> (course name, plan tag)

SCOPE = [
    "Faculty Requirement Compulsory",
    "Major Requirement Compulsory",
    "Major Requirement Optional",
    "Supportive Requirement Compulsory",
]
SCOPE_KEYS = {s.replace(" ", "").lower() for s in SCOPE}

HEADER_RE = re.compile(
    r"^(University|Faculty|Major|Supportive|Orientation)\s*Requirement\s*(Compulsory|Optional)", re.I
)
CODE_RE = re.compile(r"^([A-Z]?\d{7})$")
NO_SYLLABUS = re.compile(r"graduation project|field training|special topics|practical training", re.I)

# Some syllabi print both numbering schemes: "A0413301 (0433301)". Both are real
# codes for the same course, so both must be matched against the plans.
CODE_IN_TEXT = re.compile(r"\b([A-Z]?\d{7})\b")
EQUIV_RE = re.compile(r"\b(A\d{7})\s*\(\s*(\d{7})\s*\)")

ST_EXTRACTED, ST_COLLECTED, ST_NEEDED, ST_NONE = "extracted", "collected", "needed", "none"


def respace(name):
    """Re-insert spaces in names from plans whose PDF text layer has none."""
    if " " in name.strip():
        return name.strip()
    s = re.sub(r"(?<=[a-z)])(?=[A-Z])", " ", name)
    s = re.sub(r"(?<=[A-Za-z])(?=\()", " ", s)
    s = re.sub(r"(?<=[a-z])(?=\d)", " ", s)
    return s.strip()


def namekey(name):
    """Normalised course name, used to group the same course across plans."""
    s = name.lower()
    s = re.sub(r"\(\s*(\d)\s*\)", r"\1", s)
    s = re.sub(r"\b(i|ii|iii)\b", lambda m: str(len(m.group(1))), s)
    return re.sub(r"[^a-z0-9+#]", "", s)


def canonical(code):
    return code.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def clean_title(raw):
    """Syllabus titles bleed the next table cell and the Arabic subtitle."""
    t = re.split(r"Course\s*No\.?", raw or "")[0]
    t = re.sub(r"[^\x00-\x7F]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_plan(path, tag):
    """Return {category: {code: (name, credit_hours)}} for in-scope categories."""
    with pdfplumber.open(path) as pdf:
        tables = [t for p in pdf.pages for t in p.extract_tables()]

    cats, current = collections.OrderedDict(), None
    for table in tables:
        for row in table:
            if not row:
                continue
            cell0 = str(row[0]).strip() if row[0] else ""
            # Some plans' text layer carries no spaces, so try both forms.
            if HEADER_RE.match(cell0) or HEADER_RE.match(cell0.replace(" ", "")):
                canon = re.sub(r"\s*:.*$", "", cell0).replace(" ", "").lower()
                current = canon if canon in SCOPE_KEYS else None
                continue
            m = CODE_RE.match(cell0)
            if not m or current is None:
                continue
            name = str(row[1]).replace("\n", " ").strip() if len(row) > 1 and row[1] else ""
            hrs = ""
            if len(row) > 3 and row[3]:
                h = re.search(r"\d+", str(row[3]))
                hrs = h.group(0) if h else ""
            code = m.group(1)
            if code in EXCLUDED_CODES:
                excluded_seen.setdefault(code, (respace(name), tag))
                continue
            cats.setdefault(current, {})[code] = (respace(name), hrs)
    return cats


# ── what is already on disk ────────────────────────────────────────────
extracted_codes, extracted_titles = set(), {}
for p in EXTRACTED_DIR.glob("*.json"):
    if not re.fullmatch(r"[A-Z]?\d{7}", p.stem):
        continue
    extracted_codes.add(p.stem)
    # A syllabus is keyed on the code it prints, which is often the edition the
    # document was written for, not the one the current plan uses: Application
    # Security is 0454302 on the document and A0433301 in the plan. Without the
    # title as a second key those courses never show as extracted.
    try:
        title = (json.loads(p.read_text(encoding="utf-8")).get("course_title") or "").strip()
    except Exception:
        title = ""
    if title:
        extracted_titles[namekey(title)] = p.stem

collected, collected_titles, fixture_errors, equivalences = {}, {}, [], {}
sys.path.insert(0, str(ROOT / "src"))
from careercompass.parsing.syllabus import parse_syllabus  # noqa: E402

for pdf in sorted(FIXTURES.glob("*.pdf")):
    try:
        r = parse_syllabus(str(pdf))
        codes = CODE_IN_TEXT.findall(r.get("course_code") or "")
        title = clean_title(r.get("course_title") or "")
        if title:
            collected_titles[namekey(title)] = pdf.name
        for c in codes:
            collected[c] = pdf.name
        if not codes and not title:
            fixture_errors.append((pdf.name, "no course code or title found"))
    except Exception as e:
        fixture_errors.append((pdf.name, f"{type(e).__name__}: {str(e)[:60]}"))
        continue
    # Harvest every "Anew (old)" pairing anywhere in the document - the course
    # code line and the prerequisite lines both carry them.
    try:
        with pdfplumber.open(str(pdf)) as doc:
            text = "\n".join((pg.extract_text() or "") for pg in doc.pages)
        for line in text.split("\n"):
            for new_c, old_c in EQUIV_RE.findall(line):
                equivalences.setdefault(new_c, (old_c, pdf.name, line.strip()[:64]))
    except Exception:
        pass

# ── the plans ──────────────────────────────────────────────────────────
parsed = {}
for tag, _title, fname in PLAN_FILES:
    path = PLANS / fname
    if path.exists():
        parsed[tag] = parse_plan(path, tag)
    else:
        print(f"missing plan: {fname}", file=sys.stderr)

# Grouping is keyed on the normalised course NAME, not on the course code.
# Stripping the letter prefix does not work: the newer plan editions renumbered,
# so A0181503 is Digital Logic while 0181503 is Programming Fundamentals. Name
# grouping over-splits at worst; code grouping merges unrelated courses.
master, collisions = {}, {}
for tag, cats in parsed.items():
    for _cat, courses in cats.items():
        for code, (name, hrs) in courses.items():
            if not name:
                continue
            e = master.setdefault(
                namekey(name), {"names": set(), "plans": set(), "codes": set(), "hrs": set()}
            )
            e["names"].add(name)
            e["plans"].add(tag)
            e["codes"].add(code)
            if hrs:
                e["hrs"].add(hrs)
            collisions.setdefault(canonical(code), set()).add((name, code, tag))

BAD = {c: v for c, v in collisions.items() if len({namekey(n) for n, _, _ in v}) > 1}

all_plan_codes = {c for e in master.values() for c in e["codes"]}
_by_file = collections.defaultdict(set)
for c, f in collected.items():
    _by_file[f].add(c)
_matched_by_title = {f for k, f in collected_titles.items() if k in master}
orphan_fixtures = {
    sorted(cs)[0]: f
    for f, cs in _by_file.items()
    if not (cs & all_plan_codes) and f not in _matched_by_title
}
_extracted_by_title = set(extracted_titles[k] for k in extracted_titles if k in master)
orphan_extracted = {c for c in extracted_codes
                    if c not in all_plan_codes and c not in _extracted_by_title}


def status(key):
    # Exact code match only. Canonicalising first would mark Database Systems
    # extracted because A0412401 strips to 0412401, which is System Analysis and
    # Design in the other plans - the collision this file documents.
    codes = master[key]["codes"]
    if codes & extracted_codes or key in extracted_titles:
        return ST_EXTRACTED
    # Match on code first, then on course name. A syllabus written against a
    # retired plan edition carries a code no current plan uses, but the course
    # name still identifies it.
    if codes & set(collected) or key in collected_titles:
        return ST_COLLECTED
    if NO_SYLLABUS.search(" ".join(master[key]["names"])):
        return ST_NONE
    return ST_NEEDED


def display_name(key):
    names = master[key]["names"]
    return sorted(names, key=len)[-1] if names else "(name not extracted)"


def entry(key):
    """One task-list line for a course."""
    e = master[key]
    st = status(key)
    box = "[x]" if st in (ST_EXTRACTED, ST_COLLECTED) else "[ ]"
    codes = "`" + "` `".join(sorted(e["codes"])) + "`"
    hrs = "/".join(sorted(e["hrs"])) if e["hrs"] else "?"
    line = f"- {box} {codes} · {hrs} hr · **{display_name(key)}** · {', '.join(sorted(e['plans']))}"
    if st == ST_EXTRACTED:
        line += " — *extracted*"
    elif st == ST_COLLECTED:
        line += " — *PDF collected, not yet extracted*"
    return line


by_status = collections.defaultdict(list)
for k in master:
    by_status[status(k)].append(k)


def order(keys):
    return sorted(keys, key=lambda k: sorted(master[k]["codes"])[0])


needed = order(by_status[ST_NEEDED])
have = order(by_status[ST_EXTRACTED] + by_status[ST_COLLECTED])
none = order(by_status[ST_NONE])
labs = [k for k in needed if re.search(r"\blab\b|\(lab\)", display_name(k), re.I)]

L = []
A = L.append

A("# Required Course Syllabi")
A("")
A("Courses whose syllabus must be collected and run through the syllabus")
A("skill-extraction pipeline, to build the **course → skill map** that M2 joins")
A("against a student's transcript.")
A("")
A("> Regenerated by `python -m careercompass.cli.build_syllabus_list`. Every")
A("> checkbox is set from disk — `data/extracted/syllabi/` and `data/syllabi/`")
A("> — so ticking one by hand will not survive a rebuild. Drop the PDF into")
A("> `data/syllabi/` and the box ticks itself.")
A("")

A("## Status")
A("")
A("| | Courses |")
A("|---|---:|")
A(f"| Extracted into the skill map | {len(by_status[ST_EXTRACTED])} |")
A(f"| PDF collected, not yet extracted | {len(by_status[ST_COLLECTED])} |")
A(f"| **Still to obtain** | **{len(needed)}** |")
if none:
    A(f"| No fixed syllabus (student-specific) | {len(none)} |")
A(f"| **Total unique courses** | **{len(master)}** |")
A("")
A(f"Of the {len(needed)} still to obtain, **{len(labs)} are Lab courses**, which usually share")
A("their parent course's syllabus — so the real number of distinct documents to")
A(f"chase is closer to **{len(needed) - len(labs)}**.")
A("")

A("## Scope")
A("")
A("Only these four requirement categories are included:")
A("")
for s in SCOPE:
    A(f"- {s}")
A("")
A("**Excluded, and why.** *University Requirement* (Compulsory and Optional) is")
A("Arabic, English, National Education, Military Science, Islamic Education and")
A("similar — no IT skill content. *Orientation Requirement* is three remedial")
A("courses, marked `Exempted` for every student seen so far.")
A("")

if excluded_seen:
    by_course = {}
    for code, (name, _tag) in excluded_seen.items():
        k = namekey(name)
        by_course.setdefault(k, {"name": name, "codes": set(), "why": EXCLUDED_CODES[code]})
        by_course[k]["codes"].add(code)
    A(f"**Also dropped by hand** — {len(by_course)} courses that sit inside the four")
    A("categories above but contribute nothing the skill map can use:")
    A("")
    A("| Code(s) | Course | Why |")
    A("|---|---|---|")
    for k in sorted(by_course, key=lambda k: sorted(by_course[k]["codes"])[0]):
        e = by_course[k]
        codes = "`" + "` `".join(sorted(e["codes"])) + "`"
        A(f"| {codes} | {e['name']} | {e['why']} |")
    A("")

A("## Source plans")
A("")
A("| Tag | Major | In-scope courses | File |")
A("|---|---|---:|---|")
for tag, title, fname in PLAN_FILES:
    n = sum(len(v) for v in parsed.get(tag, {}).values())
    A(f"| `{tag}` | {title} | {n} | `{fname}` |")
A("")
if RETIRED:
    A("Not used:")
    A("")
    for title, fname in RETIRED:
        A(f"- {title} — `{fname}` · superseded, excluded from every count below")
    A("")
A("Plan PDFs are git-ignored: they carry a student's name, ID, advisor and full")
A("grade history. This file carries only course codes and names, so it is tracked.")
A("")

A("## Courses")
A("")
A("Deduplicated across all plans — a course shared by several plans needs its")
A("syllabus extracted **once**.")
A("")
A("Grouped by course **name**, not by code. The newer plan editions renumbered")
A("their courses, so a code alone cannot identify a course across plans — see")
A("[Code collisions](#code-collisions). Every code a course is known by is listed.")
A("")

A(f"### Still to obtain ({len(needed)})")
A("")
for k in needed:
    A(entry(k))
A("")

A(f"### In hand ({len(have)})")
A("")
for k in have:
    A(entry(k))
A("")

if none:
    A(f"### No fixed syllabus ({len(none)})")
    A("")
    A("Content is student-specific; skip these or handle them as a separate")
    A("evidence type. There is no syllabus to extract.")
    A("")
    for k in none:
        e = master[k]
        codes = "`" + "` `".join(sorted(e["codes"])) + "`"
        A(f"- {codes} · **{display_name(k)}** · {', '.join(sorted(e['plans']))}")
    A("")

A("## By plan")
A("")
for tag, title, fname in PLAN_FILES:
    cats = parsed.get(tag)
    A(f"### {tag} — {title}")
    A("")
    if not cats:
        A("*(no courses extracted)*")
        A("")
        continue
    total = 0
    for cat_name in SCOPE:
        courses = cats.get(cat_name.replace(" ", "").lower())
        if not courses:
            continue
        A(f"**{cat_name}** — {len(courses)} courses")
        A("")
        for code in sorted(courses):
            name, hrs = courses[code]
            st = status(namekey(name))
            if st == ST_NONE:
                A(f"- `{code}` · {hrs or '?'} hr · {name} — *no fixed syllabus*")
            else:
                box = "[x]" if st in (ST_EXTRACTED, ST_COLLECTED) else "[ ]"
                A(f"- {box} `{code}` · {hrs or '?'} hr · {name}")
            total += 1
        A("")
    A(f"**In-scope total: {total}**")
    A("")

if equivalences:
    A("## Code equivalences published by the syllabi")
    A("")
    A("Several syllabus documents print both numbering schemes side by side, in the")
    A("course-code line and in prerequisites. This is the old → new mapping stated")
    A("by the department itself, so the canonical course id does not have to be")
    A("guessed from course names — it can be harvested as more syllabi arrive.")
    A("")
    A("| New code | Old code | Seen in | Line |")
    A("|---|---|---|---|")
    for new_c in sorted(equivalences):
        old_c, src, ctx = equivalences[new_c]
        A(f"| `{new_c}` | `{old_c}` | `{src}` | {ctx} |")
    A("")

A("## Code collisions")
A("")
if BAD:
    A("The same course number means **different courses** in different plans. Any")
    A("course → skill map keyed on a plan's course code will join a student to the")
    A("wrong skills for every entry below.")
    A("")
    for c in sorted(BAD):
        A(f"**`{c}`**")
        A("")
        A("| Code | Plan | Course |")
        A("|---|---|---|")
        for name, code, tag in sorted(BAD[c], key=lambda x: x[1]):
            A(f"| `{code}` | {tag} | {name} |")
        A("")
    A(f"**{len(BAD)} colliding course numbers.**")
else:
    A("None across the plans currently in scope.")
A("")

if orphan_fixtures or orphan_extracted or fixture_errors:
    A("## Loose ends")
    A("")
    if orphan_fixtures:
        A("### Syllabus PDFs whose code is in no plan")
        A("")
        A("| Code | File |")
        A("|---|---|")
        for c, f in sorted(orphan_fixtures.items()):
            A(f"| `{c}` | `data/syllabi/{f}` |")
        A("")
        A("Either from a plan edition not collected, or the code in the syllabus")
        A("document does not match the code the plan uses for that course.")
        A("")
    if orphan_extracted:
        A("### Extracted syllabi whose code is in no plan")
        A("")
        for c in sorted(orphan_extracted):
            A(f"- `{c}`")
        A("")
    if fixture_errors:
        A("### Files in data/syllabi that are not readable syllabi")
        A("")
        A("| File | Problem |")
        A("|---|---|")
        for f, err in fixture_errors:
            A(f"| `{f}` | {err} |")
        A("")

A("## Notes")
A("")
A("1. **Course codes are per-plan, not per-course.** The same course carries")
A("   different codes across editions, *and* the same code can mean different")
A("   courses. Stripping the letter prefix is **not** enough — `0433301` is")
A("   Operating Systems but `A0433301` is Application Security. The course →")
A("   skill map needs a canonical course id assigned deliberately, with each")
A("   plan's code mapped onto it. Some syllabi state the mapping outright — see")
A("   [Code equivalences](#code-equivalences-published-by-the-syllabi).")
A("")
A("2. **Professional Ethics and the mathematics courses** sit inside the in-scope")
A("   categories and will match few or no market skills. That is correct")
A("   behaviour, not a pipeline failure. Physics and Chemistry were dropped")
A("   outright — see Scope.")
A("")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({len(L)} lines)")
print(f"total={len(master)} needed={len(needed)} have={len(have)} none={len(none)} labs={len(labs)}")
print(f"collisions={len(BAD)} equivalences={len(equivalences)}")
print(f"orphan fixtures: {orphan_fixtures}")
print(f"orphan extracted: {orphan_extracted}")
print(f"fixture errors: {fixture_errors}")
