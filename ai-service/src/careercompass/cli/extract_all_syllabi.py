"""
CareerCompass — batch syllabus extraction

Runs the parse → extract → match pipeline over every syllabus PDF in
data/syllabi/, writing the parsed syllabus to data/extracted/syllabi/ and the
matched skills to data/extracted/skills/.

The single-PDF CLI builds a SkillMatcher per invocation. Doing that in a loop
loads bge-m3 once per course, which is slow and, alongside Ollama on an 8 GB
card, will OOM. This builds one matcher and reuses it.

Already-extracted courses are skipped, so an interrupted run resumes and newly
collected syllabi can be added without redoing the rest.

    CUDA_VISIBLE_DEVICES="" python -m careercompass.cli.extract_all_syllabi

The CUDA_VISIBLE_DEVICES="" is not optional on a card that also hosts Ollama:
without it the LLM stage dies with a CUDA OOM that the run reports as success.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from careercompass.config import SKILLS_DIR, SYLLABI_DIR
from careercompass.parsing.syllabus import parse_syllabus
from careercompass.skills.extractor import extract_skills, save_skills

ROOT = Path(__file__).resolve().parents[3]
PDF_DIR = ROOT / "data" / "syllabi"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--source", default=str(PDF_DIR), help="directory of syllabus PDFs")
    ap.add_argument("--llm", action=argparse.BooleanOptionalAction, default=None,
                    help="enable or disable the matcher's LLM (default: CC_MATCH_LLM)")
    ap.add_argument("--force", action="store_true", help="re-extract courses already done")
    args = ap.parse_args()

    pdfs = sorted(Path(args.source).glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"no PDFs in {args.source}")

    Path(SYLLABI_DIR).mkdir(parents=True, exist_ok=True)
    Path(SKILLS_DIR).mkdir(parents=True, exist_ok=True)

    # Parse first so the skip check knows each course code without paying for
    # the matcher on a run that turns out to have nothing to do.
    pending = []
    parse_failures = []
    for pdf in pdfs:
        try:
            syllabus = parse_syllabus(str(pdf))
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not stop the batch
            parse_failures.append((pdf.name, f"{type(exc).__name__}: {exc}"))
            continue
        code = (syllabus.get("course_code") or "").strip()
        if not code:
            parse_failures.append((pdf.name, "no course code"))
            continue
        # "A0413301 (0433301)" - the document states both numbering schemes.
        code = code.split()[0]
        if not args.force and (Path(SKILLS_DIR) / f"{code}.json").exists():
            continue
        pending.append((pdf, code, syllabus))

    print(f"{len(pdfs)} PDFs, {len(pending)} to extract, "
          f"{len(pdfs) - len(pending) - len(parse_failures)} already done")
    for name, why in parse_failures:
        print(f"  unreadable: {name} - {why}")
    if not pending:
        return

    from careercompass.skills.matcher import SkillMatcher
    from careercompass.skills.taxonomy import TAXONOMY_VERSION

    matcher = SkillMatcher.build(use_llm=args.llm)

    failures = []
    for n, (pdf, code, syllabus) in enumerate(pending, start=1):
        started = time.time()
        try:
            (Path(SYLLABI_DIR) / f"{code}.json").write_text(
                json.dumps(syllabus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            skills = extract_skills(syllabus)
            matches = matcher.match_skills(skills)
            matcher.attach(skills, matches)
            summary = matcher.summary(matches)

            save_skills(code, skills, str(Path(SKILLS_DIR) / f"{code}.json"), extra={
                "course_title": syllabus.get("course_title"),
                "source_file": pdf.name,
                "taxonomy_version": TAXONOMY_VERSION,
                "match_summary": {"by_status": summary["by_status"],
                                  "by_method": summary["by_method"]},
            })
            accepted = summary["by_status"].get("accepted", 0)
            print(f"  [{n}/{len(pending)}] {code:<10}{str(syllabus.get('course_title'))[:34]:<36}"
                  f"{len(skills):>3} terms {accepted:>3} accepted  {time.time() - started:.0f}s",
                  flush=True)
        except Exception as exc:  # noqa: BLE001
            failures.append((pdf.name, f"{type(exc).__name__}: {exc}"))
            print(f"  [{n}/{len(pending)}] {code} FAILED: {exc}", flush=True)

    print(f"\ndone: {len(pending) - len(failures)} extracted, {len(failures)} failed")
    for name, why in failures + parse_failures:
        print(f"  {name}: {why}", file=sys.stderr)


if __name__ == "__main__":
    main()
