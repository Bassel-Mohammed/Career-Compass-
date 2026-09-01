#!/usr/bin/env python3
"""
Create a Middle East University content manager and publish its course maps from the syllabi
in ai-service/data/syllabi/.

What it does
------------
For every syllabus PDF it walks the whole FR-CM-04 workflow the way a content manager would:
scan the PDF to pre-fill the form, upload it, wait for extraction, review every proposed skill,
then publish the reviewed map. Nothing is written straight to a table.

The review step is where judgement would normally go, so it is worth being explicit about the
rule this script applies. Publication refuses a draft that still has pending rows, rows with no
canonical skill, or two rows claiming the same canonical skill. This script therefore:

  * accepts every proposal that resolved to a canonical taxonomy skill;
  * removes proposals that resolved to nothing, because picking a replacement is a judgement
    call and a wrong one silently corrupts every downstream skill gap;
  * removes the weaker duplicate when two proposals land on the same canonical skill, keeping
    whichever has more evidence behind it.

That is a defensible automatic pass, not a substitute for review. Anything removed is soft
deleted with a note saying this script did it, so a human can see exactly what was skipped.

Two syllabi are excluded by default so they stay available to demonstrate the upload and review
flow by hand — see EXCLUDED.

Usage
-----
    python3 scripts/seed_meu_course_maps.py \
        --base-url http://localhost \
        --admin-email admin@careercompass.jo \
        --password demo12345

Re-running is safe: an already-published course is left alone, and an upload interrupted
part-way is picked up where it stopped.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from seed_jordan_demo import Api, ApiError, email_for, is_conflict, ok, skip, step, warn  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SYLLABI_DIR = REPO_ROOT / "ai-service" / "data" / "syllabi"

UNIVERSITY = "Middle East University"
STUDY_FIELD = "Computer Science"
MANAGER = ("Rami", "Al-Kilani")
MANAGER_DOMAIN = "meu.content.local"

# Left unpublished on purpose, so the upload → extract → review → publish flow can still be
# demonstrated live against a course that has never been seen before.
EXCLUDED = {
    "object_oriented_programming_in_java.pdf",
    "computer_vision.pdf",
}

# Statuses that mean extraction is over, one way or another.
TERMINAL = {"READY_FOR_REVIEW", "FAILED", "CANCELLED", "PUBLISHED", "PUBLISHING"}


def course_name_from(filename: str) -> str:
    """internet_of_things.pdf -> "Internet Of Things", with the usual acronyms fixed up."""
    words = Path(filename).stem.replace("_", " ").split()
    small = {"of", "and", "in", "the", "for", "to"}
    titled = [
        w.upper() if w.lower() in {"ai", "iot", "oop"} else
        w.lower() if i and w.lower() in small else
        w.capitalize()
        for i, w in enumerate(words)
    ]
    return " ".join(titled)


def wait_for_extraction(api: Api, token, outcome_id, label, timeout_s):
    """Poll until extraction reaches a terminal state. Returns the final outcome, or None."""
    started = time.monotonic()
    last = None
    while time.monotonic() - started < timeout_s:
        outcome = api.get(f"/api/content-managers/me/learning-outcomes/{outcome_id}/extraction",
                          token=token, timeout=60)
        status = outcome.get("extractionStatus")
        if status != last:
            print(f"      {status.lower()}…", flush=True)
            last = status
        if status in TERMINAL:
            return outcome
        time.sleep(5)
    warn(f"{label}: extraction still running after {timeout_s}s — left for manual review")
    return None


def plan_review(drafts):
    """
    Decide a target decision for every draft, applying the rule described in the module docstring.

    Returns (targets, kept, dropped_unresolved, dropped_duplicate) where targets maps
    draftSkillId -> "ACCEPTED" | "REMOVED".
    """
    live = [d for d in drafts if d.get("decision") != "REMOVED"]

    resolved, unresolved = [], []
    for d in live:
        (resolved if d.get("canonicalSkillId") else unresolved).append(d)

    # More evidence wins; the match score breaks ties. Both are already the extractor's own
    # confidence signals, so this keeps the row a reviewer would most likely have kept.
    def strength(d):
        return (d.get("evidenceCount") or 0, float(d.get("matchScore") or 0))

    best_per_skill = {}
    for d in sorted(resolved, key=strength, reverse=True):
        best_per_skill.setdefault(d["canonicalSkillId"], d)

    keep_ids = {d["draftSkillId"] for d in best_per_skill.values()}

    targets = {}
    for d in live:
        targets[d["draftSkillId"]] = "ACCEPTED" if d["draftSkillId"] in keep_ids else "REMOVED"

    duplicates = len(resolved) - len(best_per_skill)
    return targets, len(keep_ids), len(unresolved), duplicates


def review_and_publish(api: Api, token, outcome, label, note):
    outcome_id = outcome["outcomeId"]
    revision = outcome.get("draftRevision") or 0

    drafts = api.get(f"/api/content-managers/me/learning-outcomes/{outcome_id}/skills",
                     token=token, timeout=60)
    if not drafts:
        warn(f"{label}: extraction produced no skills — nothing to publish")
        return False

    targets, kept, unresolved, duplicates = plan_review(drafts)
    if kept == 0:
        warn(f"{label}: nothing resolved to a canonical skill — left unpublished")
        return False

    by_id = {d["draftSkillId"]: d for d in drafts}
    changed = 0

    for draft_id, target in targets.items():
        draft = by_id[draft_id]
        if draft.get("decision") == target:
            continue

        body = {
            "decision": target,
            "expectedRowVersion": draft.get("rowVersion") or 0,
            "expectedDraftRevision": revision,
        }
        if target == "REMOVED":
            body["note"] = note

        try:
            api.patch(
                f"/api/content-managers/me/learning-outcomes/{outcome_id}/skills/{draft_id}",
                body, token, timeout=60)
        except ApiError as exc:
            if exc.status != 409:
                raise
            # Someone (or a previous interrupted run) moved the draft on. Re-read both halves
            # of the compare-and-swap and try once more before giving up on this row.
            fresh = api.get(f"/api/content-managers/me/learning-outcomes/{outcome_id}",
                            token=token, timeout=60)
            revision = fresh.get("draftRevision") or 0
            current = api.get(
                f"/api/content-managers/me/learning-outcomes/{outcome_id}/skills",
                token=token, timeout=60)
            match = next((d for d in current if d["draftSkillId"] == draft_id), None)
            if not match or match.get("decision") == target:
                continue
            body["expectedRowVersion"] = match.get("rowVersion") or 0
            body["expectedDraftRevision"] = revision
            api.patch(
                f"/api/content-managers/me/learning-outcomes/{outcome_id}/skills/{draft_id}",
                body, token, timeout=60)

        revision += 1  # every accepted edit advances the aggregate's revision
        changed += 1

    detail = f"{kept} accepted"
    if unresolved:
        detail += f", {unresolved} unresolved removed"
    if duplicates:
        detail += f", {duplicates} duplicate removed"
    print(f"      reviewed: {detail} ({changed} edits)", flush=True)

    try:
        published = api.post(f"/api/content-managers/me/learning-outcomes/{outcome_id}/publish",
                             {"expectedDraftRevision": revision}, token, timeout=300)
    except ApiError as exc:
        if exc.status == 409:
            fresh = api.get(f"/api/content-managers/me/learning-outcomes/{outcome_id}",
                            token=token, timeout=60)
            published = api.post(
                f"/api/content-managers/me/learning-outcomes/{outcome_id}/publish",
                {"expectedDraftRevision": fresh.get("draftRevision") or 0}, token, timeout=300)
        else:
            warn(f"{label}: publish refused ({exc.status}) — {exc.body[:200]}")
            return False

    ok(f"{label} — published, course map v{published.get('courseMapVersion')}, "
       f"{published.get('totalSkills')} skills")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-password", default=None)
    parser.add_argument("--password", default=None,
                        help="password for the MEU content manager (env CC_SEED_PASSWORD)")
    parser.add_argument("--syllabi-dir", default=str(DEFAULT_SYLLABI_DIR))
    parser.add_argument("--catalog-version", default="2024-2025")
    parser.add_argument("--limit", type=int, default=None,
                        help="publish at most N courses this run, to stay inside the "
                             "OpenRouter free daily quota; re-run to continue")
    parser.add_argument("--extraction-timeout", type=int, default=900,
                        help="seconds to wait for one extraction (default 900)")
    args = parser.parse_args()

    admin_password = args.admin_password or os.environ.get("CC_ADMIN_PASSWORD") \
        or getpass.getpass("Administrator password: ")
    password = args.password or os.environ.get("CC_SEED_PASSWORD") \
        or getpass.getpass("Password for the MEU content manager: ")
    if len(password) < 8:
        sys.exit("Password must be at least 8 characters — the API rejects anything shorter.")

    syllabi_dir = Path(args.syllabi_dir)
    if not syllabi_dir.is_dir():
        sys.exit(f"No syllabi directory at {syllabi_dir}")

    pdfs = sorted(p for p in syllabi_dir.glob("*.pdf") if p.name not in EXCLUDED)
    held_back = sorted(EXCLUDED & {p.name for p in syllabi_dir.glob("*.pdf")})
    if not pdfs:
        sys.exit(f"No syllabi to publish in {syllabi_dir}")

    api = Api(args.base_url)
    print(f"Target: {api.base_url}")

    admin_token = api.post("/api/auth/admins/login",
                           {"email": args.admin_email, "password": admin_password})["token"]
    print(f"Signed in as {args.admin_email}")

    step(f"{UNIVERSITY}")
    universities = {u["universityName"]: u["universityId"]
                    for u in api.get("/api/admin/universities", admin_token)}
    if UNIVERSITY in universities:
        skip(UNIVERSITY)
        university_id = universities[UNIVERSITY]
    else:
        university_id = api.post("/api/admin/universities",
                                 {"universityName": UNIVERSITY}, admin_token)["universityId"]
        ok(UNIVERSITY)

    fields = {f["fieldName"]: f["studyFieldId"]
              for f in api.get("/api/admin/study-fields", admin_token)}
    if STUDY_FIELD not in fields:
        fields[STUDY_FIELD] = api.post("/api/admin/study-fields",
                                       {"fieldName": STUDY_FIELD}, admin_token)["studyFieldId"]
        ok(STUDY_FIELD)

    step("Content manager")
    first, last = MANAGER
    manager_email = email_for(first, last, MANAGER_DOMAIN)
    existing = {c["email"] for c in api.get("/api/admin/content-managers", admin_token)}
    if manager_email in existing:
        skip(manager_email)
    else:
        try:
            api.post("/api/admin/content-managers", {
                "firstName": first, "lastName": last, "email": manager_email,
                "initialPassword": password,
                "universityId": university_id,
                "studyFieldId": fields[STUDY_FIELD],
            }, admin_token)
            ok(f"{first} {last} — {UNIVERSITY} · {STUDY_FIELD} · {manager_email}")
        except ApiError as exc:
            if is_conflict(exc):
                skip(manager_email)
            else:
                raise

    token = api.post("/api/auth/content-managers/login",
                     {"email": manager_email, "password": password})["token"]

    step(f"Course maps — {len(pdfs)} syllabi")
    if held_back:
        print(f"  holding back for manual testing: {', '.join(held_back)}")

    done = {(o.get("courseCode") or "").lower(): o
            for o in (api.get("/api/content-managers/me/learning-outcomes", token) or [])}
    by_filename = {(o.get("originalFilename") or ""): o for o in done.values()}

    note = "Removed automatically by seed_meu_course_maps.py — not individually reviewed."
    published = 0
    processed = 0

    for pdf in pdfs:
        label = course_name_from(pdf.name)

        prior = by_filename.get(pdf.name)
        if prior and prior.get("extractionStatus") == "PUBLISHED":
            skip(f"{label} — published")
            continue

        if args.limit is not None and processed >= args.limit:
            print(f"  … stopping at --limit {args.limit}; re-run to continue")
            break
        processed += 1

        print(f"  → {label}  ({pdf.name})", flush=True)

        outcome = prior
        if outcome is None:
            # The form's own auto-fill decides the qualified identity wherever it can read one,
            # exactly as it would for a person filling the form in.
            course_code, course_name = None, label
            try:
                preview = api.post_file("/api/content-managers/me/learning-outcomes/preview",
                                        "file", pdf, token=token, timeout=300)
                course_code = (preview.get("courseCode") or "").strip() or None
                course_name = (preview.get("courseName") or "").strip() or label
            except ApiError as exc:
                warn(f"{label}: scan failed ({exc.status}) — falling back to the filename")

            if not course_code:
                course_code = "MEU-" + pdf.stem.upper().replace("_", "-")[:70]

            try:
                outcome = api.post_file(
                    f"/api/content-managers/me/learning-outcomes"
                    f"?courseCode={urlquote(course_code)}"
                    f"&catalogVersion={urlquote(args.catalog_version)}"
                    f"&courseName={urlquote(course_name)}",
                    "file", pdf, token=token, timeout=600)
                print(f"      uploaded as {course_code} — {course_name}", flush=True)
            except ApiError as exc:
                if is_conflict(exc):
                    warn(f"{label}: already uploaded — {exc.body[:160]}")
                    continue
                warn(f"{label}: upload failed ({exc.status}) — {exc.body[:200]}")
                continue

        if outcome.get("extractionStatus") not in ("READY_FOR_REVIEW",):
            outcome = wait_for_extraction(api, token, outcome["outcomeId"], label,
                                          args.extraction_timeout)
            if outcome is None:
                continue

        if outcome.get("extractionStatus") == "FAILED":
            warn(f"{label}: extraction failed — {outcome.get('extractionError') or 'no detail'}")
            continue
        if outcome.get("extractionStatus") == "PUBLISHED":
            skip(f"{label} — published")
            continue

        if review_and_publish(api, token, outcome, label, note):
            published += 1

    step("Summary")
    print(f"  content manager   {manager_email}")
    print(f"  university        {UNIVERSITY}")
    print(f"  published now     {published}")
    print(f"  held back         {', '.join(held_back) or 'none'}")
    print("\nRe-running is safe — published courses are left alone.")


def urlquote(value: str) -> str:
    from urllib.parse import quote
    return quote(value, safe="")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nInterrupted. Re-running picks up where this stopped.")
