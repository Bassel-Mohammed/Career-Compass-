"""Generate mock course -> skill rows for courses whose syllabus is missing.

M2 (skill vector) and M3 (skill gap) are deterministic arithmetic over a join
of two tables. Only one side exists today: 18 of 114 courses have a syllabus.
This fills the other 96 so the arithmetic can be built and verified now, while
the real syllabi are still being collected.

Two stages, and the second one is the real pipeline:

  1. An LLM writes a plausible syllabus for each course - description, CLOs
     with Bloom verbs, and a 15-week topic plan - into data/mock/syllabi/.
     Same shape parse_syllabus produces, so nothing downstream can tell the
     difference.
  2. extract_skills() and SkillMatcher run over it unchanged, exactly as they
     do for a real syllabus, writing data/mock/skills/.

Stage 2 is deliberately not simulated. Running the real extractor and the real
matcher means the mock rows carry real taxonomy ids, real match statuses and
real confidence scores, so M2/M3 built against them will behave the same way
against real syllabi.

*** These rows must never be loaded into the production course_skills table. ***

Everything is written under data/mock/, every record carries "mock": true, and
nothing here is read by the real pipeline. Mixing mock and real rows destroys
the one property that makes a gap number trustworthy: that you can tell a code
fault from a coverage gap.

    python -m careercompass.cli.generate_mock_skills            # both stages
    python -m careercompass.cli.generate_mock_skills --stage 1  # syllabi only
    python -m careercompass.cli.generate_mock_skills --stage 2  # match only

Both stages skip work already on disk, so an interrupted run resumes.
"""
import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
CHECKLIST = ROOT / "data" / "plans" / "required_syllabi.md"
OUT_DIR = ROOT / "data" / "mock"
SYLLABI_DIR = OUT_DIR / "syllabi"
SKILLS_DIR = OUT_DIR / "skills"

OLLAMA_URL = os.getenv("CC_OLLAMA_URL", "http://127.0.0.1:11434")
MODEL = os.getenv("CC_MOCK_MODEL", "qwen3:8b")
TIMEOUT = int(os.getenv("CC_MOCK_TIMEOUT", "300"))

# "- [ ] `0413403` `A0412401` · 2/3 hr · **Database Systems** · CS, CS/AI, SE"
ENTRY_RE = re.compile(
    r"^- \[( |x)\] ((?:`[A-Z]?\d{7}`\s*)+)· ([\d/?]+) hr · \*\*(.+?)\*\* · (.+?)(?: — \*.*)?$"
)
CODE_RE = re.compile(r"`([A-Z]?\d{7})`")

PROMPT = """You are writing the official course syllabus for a Bachelor of \
Information Technology course at a Jordanian university.

Course title: {title}
Credit hours: {hours}
Required by these majors: {plans}

Write the syllabus content as JSON with exactly these keys:

"description": one paragraph, 500-800 characters, listing the concrete topics \
the course covers, separated by semicolons. Name specific technologies, \
methods, algorithms and standards - not generic phrases like "students will \
learn". Write it the way a real course catalogue entry reads.

"clos": exactly 5 course learning outcomes. Each is an object with "number" \
(1-5) and "text". Each text must start with a Bloom's taxonomy verb (Define, \
Describe, Explain, Apply, Implement, Analyze, Design, Evaluate, Construct) \
and name specific technical content.

"weeks": exactly 15 objects, each with "week" (1-15), "topics" (a list of 1-3 \
short topic strings for that week) and "labs" (a list of 0-2 lab titles; use \
an empty list if this course has no practical component).

The topics must progress sensibly from foundations in week 1 to advanced \
material by week 15, and must be specific to {title} - a reader should be able \
to identify the course from the topic list alone.

Return only the JSON object. No commentary, no markdown fences."""


def parse_checklist():
    """Return the courses under '### Still to obtain' in required_syllabi.md."""
    if not CHECKLIST.exists():
        raise SystemExit(
            f"missing {CHECKLIST}\nRun: python -m careercompass.cli.build_syllabus_list"
        )
    courses, in_section = [], False
    for line in CHECKLIST.read_text(encoding="utf-8").splitlines():
        if line.startswith("### Still to obtain"):
            in_section = True
            continue
        if in_section and line.startswith("#"):
            break
        if not in_section:
            continue
        m = ENTRY_RE.match(line.strip())
        if not m:
            continue
        _box, codes_raw, hrs, name, plans = m.groups()
        courses.append(
            {
                "codes": CODE_RE.findall(codes_raw),
                "credit_hours": hrs,
                "course_title": name.strip(),
                "plans": [p.strip() for p in plans.split(",")],
            }
        )
    return courses


def ollama(prompt):
    body = json.dumps(
        {
            "model": MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.7, "num_predict": 3000},
        }
    ).encode()
    req = Request(
        f"{OLLAMA_URL}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    with urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())["response"]


def strip_thinking(text):
    """qwen3 emits <think> blocks even in JSON mode."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


def coerce(raw, course):
    """Validate the model's JSON into the shape parse_syllabus produces."""
    data = json.loads(strip_thinking(raw))

    clos = []
    for i, c in enumerate(data.get("clos") or [], start=1):
        text = (c.get("text") if isinstance(c, dict) else str(c)) or ""
        if not text.strip():
            continue
        clos.append(
            {
                "number": (c.get("number") if isinstance(c, dict) else None) or i,
                "text": text.strip(),
                "jnqf_descriptor": "knowledge",
                "bloom_verb": text.strip().split()[0],
            }
        )

    weeks = []
    for i, w in enumerate(data.get("weeks") or [], start=1):
        if not isinstance(w, dict):
            continue
        topics = [str(t).strip() for t in (w.get("topics") or []) if str(t).strip()]
        labs = [str(t).strip() for t in (w.get("labs") or []) if str(t).strip()]
        if not topics and not labs:
            continue
        weeks.append({"week": w.get("week") or i, "topics": topics, "labs": labs, "clos": []})

    description = str(data.get("description") or "").strip()
    if not description or len(clos) < 3 or len(weeks) < 8:
        raise ValueError(
            f"thin response: desc={len(description)} clos={len(clos)} weeks={len(weeks)}"
        )

    hrs = course["credit_hours"].split("/")[0]
    return {
        "source_file": f"MOCK::{course['course_title']}",
        "course_code": course["codes"][0],
        "course_codes": course["codes"],
        "course_title": course["course_title"],
        "credit_hours": int(hrs) if hrs.isdigit() else 3,
        "theoretical_hours": None,
        "practical_hours": None,
        "jnqf_level": None,
        "prerequisites": [],
        "description": description,
        "clos": clos,
        "weeks": weeks,
        "warnings": [],
        "plans": course["plans"],
        "mock": True,
        "mock_model": MODEL,
        "WARNING": "Synthetic syllabus written by an LLM. Not a real MEU document.",
    }


def stage_one(courses, retries=2):
    SYLLABI_DIR.mkdir(parents=True, exist_ok=True)
    todo = [c for c in courses if not (SYLLABI_DIR / f"{c['codes'][0]}.json").exists()]
    done = len(courses) - len(todo)
    print(f"stage 1: {len(todo)} syllabi to write ({done} already on disk), model={MODEL}")

    failures = []
    for n, course in enumerate(todo, start=1):
        code = course["codes"][0]
        prompt = PROMPT.format(
            title=course["course_title"],
            hours=course["credit_hours"],
            plans=", ".join(course["plans"]),
        )
        started = time.time()
        for attempt in range(retries + 1):
            try:
                syllabus = coerce(ollama(prompt), course)
                (SYLLABI_DIR / f"{code}.json").write_text(
                    json.dumps(syllabus, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                print(
                    f"  [{n}/{len(todo)}] {code} {course['course_title'][:44]:<45}"
                    f"{len(syllabus['clos'])} clos {len(syllabus['weeks'])} wks "
                    f"{time.time() - started:.0f}s",
                    flush=True,
                )
                break
            except (ValueError, json.JSONDecodeError) as exc:
                if attempt == retries:
                    failures.append((code, course["course_title"], str(exc)[:60]))
                    print(f"  [{n}/{len(todo)}] {code} FAILED: {exc}", flush=True)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                failures.append((code, course["course_title"], f"{type(exc).__name__}: {exc}"))
                print(f"  [{n}/{len(todo)}] {code} FAILED: {exc}", flush=True)
                break
    return failures


def stage_two(use_llm=None, shard=None):
    from careercompass.skills.extractor import extract_skills
    from careercompass.skills.matcher import SkillMatcher
    from careercompass.skills.taxonomy import TAXONOMY_VERSION

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(SYLLABI_DIR.glob("*.json"))
    todo = [p for p in sources if not (SKILLS_DIR / p.name).exists()]
    if shard:
        # Disjoint slices so parallel workers never race on the same course.
        # The LLM disambiguation is ~85% of this stage and Ollama serves
        # concurrent requests against one loaded model, so sharding converts
        # that wait into throughput.
        i, n = shard
        todo = [p for k, p in enumerate(todo) if k % n == i]
        tag = f" [shard {i + 1}/{n}]"
    else:
        tag = ""
    print(f"stage 2{tag}: {len(todo)} to match ({len(sources) - len(todo)} already on disk)")
    if not todo:
        return []

    # One matcher for the whole run. Building a second loads a second bge-m3
    # into the same process, which OOMs a 7.6 GB card while Ollama holds 4.3.
    matcher = SkillMatcher.build(use_llm=use_llm)

    failures = []
    for n, path in enumerate(todo, start=1):
        syllabus = json.loads(path.read_text(encoding="utf-8"))
        started = time.time()
        try:
            skills = extract_skills(syllabus)
            matches = matcher.match_skills(skills)
            matcher.attach(skills, matches)
            summary = matcher.summary(matches)
            record = {
                "course_code": syllabus["course_code"],
                "course_codes": syllabus.get("course_codes", [syllabus["course_code"]]),
                "course_title": syllabus["course_title"],
                "credit_hours": syllabus.get("credit_hours"),
                "plans": syllabus.get("plans", []),
                "taxonomy_version": TAXONOMY_VERSION,
                "mock": True,
                "mock_model": syllabus.get("mock_model"),
                "WARNING": "Synthetic. Never load into the production course_skills table.",
                "match_summary": {
                    "by_status": summary["by_status"],
                    "by_method": summary["by_method"],
                },
                "total_skills": len(skills),
                "skills": skills,
            }
            (SKILLS_DIR / path.name).write_text(
                json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            acc = summary["by_status"].get("accepted", 0)
            print(
                f"  [{n}/{len(todo)}] {syllabus['course_code']} "
                f"{syllabus['course_title'][:40]:<41}{len(skills):>3} terms "
                f"{acc:>3} accepted  {time.time() - started:.0f}s",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - one bad course must not stop the run
            failures.append((path.stem, f"{type(exc).__name__}: {exc}"))
            print(f"  [{n}/{len(todo)}] {path.stem} FAILED: {exc}", flush=True)
    return failures


GRADES = ["A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D"]


def build_transcript(plan_tag):
    """A synthetic student who took every mocked course of one plan."""
    rng = random.Random(f"transcript:{plan_tag}")
    courses = []
    for path in sorted(SKILLS_DIR.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        if plan_tag not in rec.get("plans", []):
            continue
        courses.append(
            {
                "course_code": rec["course_code"],
                "course_name": rec["course_title"],
                "credit_hours": rec.get("credit_hours") or 3,
                "grade": rng.choices(GRADES, weights=[8, 10, 12, 14, 12, 10, 8, 6, 4, 3])[0],
                "status": "Pass",
            }
        )
    return {
        "mock": True,
        "WARNING": "Synthetic transcript. For testing M2/M3 only.",
        "student": {"id": "mock_000001", "name": "Mock Student", "plan": plan_tag},
        "total_courses": len(courses),
        "courses": courses,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--stage", type=int, choices=(1, 2), default=None,
                    help="run only one stage (default: both)")
    ap.add_argument("--plan", default="CS/AI", help="plan tag for the mock transcript")
    ap.add_argument("--llm", action=argparse.BooleanOptionalAction, default=None,
                    help="stage 2: enable or disable the matcher's LLM")
    ap.add_argument("--limit", type=int, default=None, help="only process the first N courses")
    ap.add_argument("--shard", default=None, metavar="I/N",
                    help="stage 2: process only slice I of N, for parallel workers")
    args = ap.parse_args()
    if args.shard:
        i, n = (int(x) for x in args.shard.split("/"))
        if not 0 < n or not 0 <= i - 1 < n:
            raise SystemExit(f"bad --shard {args.shard}; expected I/N with 1 <= I <= N")
        args.shard = (i - 1, n)

    failures = []
    if args.stage in (None, 1):
        courses = parse_checklist()
        if not courses:
            raise SystemExit("no courses parsed from the checklist - has its format changed?")
        if args.limit:
            courses = courses[: args.limit]
        failures += [("stage1", *f) for f in stage_one(courses)]

    if args.stage in (None, 2):
        failures += [("stage2", *f) for f in stage_two(use_llm=args.llm, shard=args.shard)]

    if args.stage in (None, 2) and not args.shard:
        transcript = build_transcript(args.plan)
        (OUT_DIR / "transcript.json").write_text(
            json.dumps(transcript, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        records = [json.loads(p.read_text(encoding="utf-8")) for p in SKILLS_DIR.glob("*.json")]
        if records:
            total = sum(r["total_skills"] for r in records)
            ids = {
                s["canonical"]["id"]
                for r in records
                for s in r["skills"]
                if s.get("canonical")
            }
            print()
            print(f"{len(records)} mock courses in {SKILLS_DIR}")
            print(f"  {total} skill rows, {len(ids)} distinct taxonomy ids")
            print(f"  avg {total / len(records):.1f} terms per course")
            print(f"transcript: {transcript['total_courses']} courses -> {OUT_DIR / 'transcript.json'}")

    if failures:
        print(f"\n{len(failures)} failures:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)


if __name__ == "__main__":
    main()
