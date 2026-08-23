"""
CareerCompass — Bring extracted skill artefacts back in line with current rules

The JSON counterpart of `db.skills.remap_retired_skills`, and it exists because
that function only ever repaired half the system.

Merging two taxonomy records for one skill retires the loser's id. Rows already
written still carry it, and the two sides of the join drift apart silently: a
course matched to `custom:java` and a career-path requirement keyed on
`esco:19a8293b…` describe the same skill and compare as different ones. The 18
August merge was repaired in PostgreSQL and left untouched in
`data/extracted/skills/*.json` — which is what every API path actually reads. A
student graded A in Object Oriented Programming in Java was therefore reported
as having a complete Java gap.

The successor is found the same way the database repair finds it: resolve the
retired *label* through the current alias index, which works because a merge
keeps the loser's label as an alias. An id whose label no longer resolves is
left in place and reported rather than guessed at.

Run this after any taxonomy merge, alongside the database repair.

**The second pass does the same job for the auto-accept guards.** Tightening a
matching rule only changes what the matcher decides next time; rows already
written keep the verdict they were given under the old rule. Re-running the
matcher would fix them, but that is ~90 s per course of LLM time to recompute
decisions that a pure function can re-evaluate in milliseconds — the guards
depend only on the term, its evidence and the chosen skill, all three of which
are already on the stored row. A row the guards now refuse is demoted to
needs_review and its `canonical` cleared, exactly as `SkillMatcher.attach`
would have written it.

Usage:
    python -m careercompass.cli.remap_extracted_skills --dry-run
    python -m careercompass.cli.remap_extracted_skills
"""

import argparse
import json
import sys
from pathlib import Path

from careercompass.config import SKILLS_DIR
from careercompass.skills.matcher import (
    ACCEPTED, NEEDS_REVIEW, UNMATCHED, _auto_accept_block, evidence_text,
)
from careercompass.skills.phrases import SYLLABUS_NOISE_TERMS
from careercompass.skills.taxonomy import load_taxonomy, normalize


def _canonical_id(skill: dict):
    canonical = skill.get("canonical") or {}
    match = skill.get("match") or {}
    return canonical.get("id") or match.get("canonical_id")


def plan_repairs(record: dict, taxonomy) -> tuple:
    """
    Work out what one artefact needs, without changing it.

    Returns:
        `(repairs, orphans)` — repairs are
        `(term, old_id, new_id, review_status)`, orphans are
        `(term, old_id, label)` for ids whose label no longer resolves.
    """
    repairs, orphans = [], []
    for skill in record.get("skills") or []:
        skill_id = _canonical_id(skill)
        if not skill_id or taxonomy.index.get(skill_id) is not None:
            continue

        match = skill.get("match") or {}
        label = match.get("canonical_label") or (skill.get("canonical") or {}).get("label")
        details = taxonomy.index.lookup_details(label) if label else None
        successor = details["skill"]["id"] if details else None

        if successor and successor != skill_id:
            repairs.append((skill.get("term"), skill_id, successor,
                            match.get("review_status")))
        else:
            orphans.append((skill.get("term"), skill_id, label))
    return repairs, orphans


def apply_repairs(record: dict, taxonomy) -> int:
    """Repoint every resolvable retired id in one artefact. Returns the count."""
    applied = 0
    for skill in record.get("skills") or []:
        skill_id = _canonical_id(skill)
        if not skill_id or taxonomy.index.get(skill_id) is not None:
            continue

        match = skill.get("match") or {}
        label = match.get("canonical_label") or (skill.get("canonical") or {}).get("label")
        details = taxonomy.index.lookup_details(label) if label else None
        successor = details["skill"]["id"] if details else None
        if not successor or successor == skill_id:
            continue

        # The source name travels with the id: repointing a custom id at an
        # ESCO record and leaving "taxonomy": "custom" behind just moves the
        # inconsistency somewhere quieter.
        taxonomy_source = details["skill"].get("source")
        if skill.get("canonical"):
            skill["canonical"]["id"] = successor
            if taxonomy_source:
                skill["canonical"]["taxonomy"] = taxonomy_source
        if match:
            match["canonical_id"] = successor
            if taxonomy_source:
                match["taxonomy"] = taxonomy_source
        applied += 1
    return applied


def plan_demotions(record: dict, taxonomy) -> list:
    """
    Rows the current auto-accept guards would no longer accept.

    Returns `(term, canonical_label, score, why)` for each.
    """
    demotions = []
    for skill in record.get("skills") or []:
        match = skill.get("match") or {}
        if match.get("review_status") != ACCEPTED:
            continue
        term = (skill.get("term") or "").strip()

        if normalize(term) in SYLLABUS_NOISE_TERMS:
            demotions.append((term, match.get("canonical_label"),
                              match.get("match_score"), "noise term"))
            continue

        # An exact label hit is not a guess and was never the problem.
        if match.get("match_method") == "exact_alias":
            continue

        chosen = taxonomy.index.get(match.get("canonical_id")) or {}
        blocked = _auto_accept_block(term, evidence_text(skill), chosen)
        if blocked:
            demotions.append((term, match.get("canonical_label"),
                              match.get("match_score"), blocked))
    return demotions


def apply_demotions(record: dict, taxonomy) -> int:
    """Demote every row the guards now refuse. Returns the count."""
    applied = 0
    for skill in record.get("skills") or []:
        match = skill.get("match") or {}
        if match.get("review_status") != ACCEPTED:
            continue
        term = (skill.get("term") or "").strip()

        if normalize(term) in SYLLABUS_NOISE_TERMS:
            match.update({
                "review_status": UNMATCHED,
                "canonical_id": None,
                "canonical_label": None,
                "match_method": "noise_filter",
                "match_score": 0.0,
                "reason": "term is on the noise list: too generic to name a skill",
            })
            skill["canonical"] = None
            applied += 1
            continue

        if match.get("match_method") == "exact_alias":
            continue

        chosen = taxonomy.index.get(match.get("canonical_id")) or {}
        blocked = _auto_accept_block(term, evidence_text(skill), chosen)
        if blocked:
            match["review_status"] = NEEDS_REVIEW
            match["reason"] = blocked
            # `canonical` is only ever set for an accepted match; leaving it
            # behind would let a needs_review row join as though it were fact.
            skill["canonical"] = None
            applied += 1
    return applied


def _recount(record: dict) -> None:
    """Rebuild match_summary.by_status after rows have moved."""
    summary = record.get("match_summary")
    if not isinstance(summary, dict) or "by_status" not in summary:
        return
    counts = {}
    for skill in record.get("skills") or []:
        status = (skill.get("match") or {}).get("review_status", UNMATCHED)
        counts[status] = counts.get(status, 0) + 1
    summary["by_status"] = counts


def main():
    parser = argparse.ArgumentParser(
        description="Repoint retired taxonomy ids in data/extracted/skills/*.json"
    )
    parser.add_argument("--skills-dir", default=str(SKILLS_DIR),
                        help="Directory of extracted skill JSON (default: %(default)s)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change and write nothing")
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.exists():
        print(f"❌ Error: skills directory not found: {skills_dir}")
        sys.exit(1)

    taxonomy = load_taxonomy()
    paths = sorted(skills_dir.glob("*.json"))
    print(f"Taxonomy: {len(taxonomy)} skills (version {taxonomy.version})")
    print(f"Scanning: {len(paths)} extracted course files in {skills_dir}")
    print("=" * 72)

    total_repairs = total_orphans = total_demotions = files_changed = 0

    for path in paths:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"  ⚠️  {path.name}: unreadable ({exc})")
            continue

        repairs, orphans = plan_repairs(record, taxonomy)
        demotions = plan_demotions(record, taxonomy)
        if not repairs and not orphans and not demotions:
            continue

        print(f"\n{path.name}  ({record.get('course_code')})")
        for term, old, new, status in repairs:
            print(f"   {term!r} [{status}]")
            print(f"      {old}  ->  {new}")
        for term, old, label in orphans:
            print(f"   ⚠️  {term!r}: {old} is retired and its label {label!r} "
                  f"no longer resolves; left unchanged")

        for term, lab, score, why in demotions:
            print(f"   ↓ {term!r} -> {lab} ({score}) now needs_review: {why}")

        total_repairs += len(repairs)
        total_orphans += len(orphans)
        total_demotions += len(demotions)

        if (repairs or demotions) and not args.dry_run:
            apply_repairs(record, taxonomy)
            if apply_demotions(record, taxonomy):
                _recount(record)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            files_changed += 1

    print("\n" + "=" * 72)
    verb = "would repoint" if args.dry_run else "repointed"
    print(f"{verb} {total_repairs} retired ids across {len(paths)} files")
    verb = "would demote" if args.dry_run else "demoted"
    print(f"{verb} {total_demotions} rows the auto-accept guards now refuse")
    if not args.dry_run:
        print(f"rewrote {files_changed} files")
    if total_orphans:
        print(f"⚠️  {total_orphans} retired ids could not be resolved and were left alone")
    if args.dry_run and (total_repairs or total_demotions):
        print("\nRe-run without --dry-run to apply.")


if __name__ == "__main__":
    main()
