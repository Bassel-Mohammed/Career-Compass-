"""
CareerCompass — Job Corpus and Ontology Tests

Covers the two stages between extraction and the knowledge base: pooling
terms across the corpus with a document-frequency cutoff, and aggregating
the matched result into per-path requirements.

The arithmetic here is load-bearing and easy to get quietly wrong. A
requirement is a fraction of a path's postings, not a count, because the
paths are different sizes; a term's level is the mode, not the maximum,
because a maximum over 2,238 postings saturates to "advanced" and stops
meaning anything.

Usage:
    python -m tests.test_job_corpus
"""

import sys

from careercompass.skills.job_corpus import (
    _modal_level, _pick_surface, _pool_evidence, build_term_pool, to_skills,
)
from careercompass.skills.ontology import _required_level, build_ontology, path_totals
from collections import Counter

_failures = []
_checks = 0


def check(label: str, actual, expected):
    global _checks
    _checks += 1
    if actual != expected:
        _failures.append(f"{label}\n      expected: {expected!r}\n      actual:   {actual!r}")


def posting(path, title, body, seniority=None):
    return {"career_path": path, "title": title, "description": body,
            "seniority_level": seniority}


JOBS = [
    posting("Backend", "Backend Developer",
            "Requirements\nKubernetes\nPostgreSQL\n", "Entry level"),
    posting("Backend", "Backend Developer",
            "Requirements\nKubernetes\nRedis\n", "Entry level"),
    posting("Backend", "Senior Backend Developer",
            "Requirements\nKubernetes\n", "Mid-Senior level"),
    posting("DevOps", "DevOps Engineer",
            "Requirements\nKubernetes\nTerraform\n", "Mid-Senior level"),
]


# ── Pooling ────────────────────────────────────────────────────
def test_document_frequency_counts_postings():
    pool = build_term_pool(JOBS)
    check("df.kubernetes", pool["kubernetes"]["document_frequency"], 4)
    check("df.postgresql", pool["postgresql"]["document_frequency"], 1)
    check("df.by_path", pool["kubernetes"]["by_career_path"],
          {"Backend": [0, 1, 2], "DevOps": [3]})


def test_repeated_mentions_do_not_inflate_frequency():
    """One verbose posting must not outvote several concise ones."""
    verbose = [posting("Backend", "Dev",
                       "Requirements\nKubernetes\nKubernetes\nKubernetes\n")]
    pool = build_term_pool(verbose)
    check("df.repeats", pool["kubernetes"]["document_frequency"], 1)


def test_cutoff_filters_by_frequency():
    pool = build_term_pool(JOBS)
    check("cutoff.df1", len(to_skills(pool, min_df=1)) > 4, True)
    kept = {s["term"].lower() for s in to_skills(pool, min_df=2)}
    check("cutoff.df2.keeps_common", "kubernetes" in kept, True)
    check("cutoff.df2.drops_rare", "redis" in kept, False)
    check("cutoff.df5.empty", to_skills(pool, min_df=5), [])


def test_pool_key_folds_spelling_variants():
    """The pool keys on the normalised form, so casing does not split a term."""
    jobs = [posting("Backend", "Dev", "Requirements\nPostgreSQL\n"),
            posting("Backend", "Dev", "Requirements\npostgresql\n")]
    pool = build_term_pool(jobs)
    check("fold.one_entry", pool["postgresql"]["document_frequency"], 2)


def test_surface_prefers_the_common_spelling():
    check("surface.majority",
          _pick_surface(Counter({"PostgreSQL": 9, "postgresql": 2})), "PostgreSQL")
    # A tie breaks toward the longer form, which keeps the cased spelling.
    check("surface.tie",
          _pick_surface(Counter({"CI/CD": 3, "ci/cd": 3})), "CI/CD")


def test_modal_level_does_not_saturate():
    """
    The reason this is the mode and not the maximum.

    Over a large corpus almost every term appears in at least one senior
    posting, so a maximum would report "advanced" for everything.
    """
    check("level.mode", _modal_level(Counter(
        {"beginner": 40, "intermediate": 5, "advanced": 1})), "beginner")
    # Ties break deeper: asking too much of a student is the safer error.
    check("level.tie", _modal_level(Counter(
        {"beginner": 5, "advanced": 5})), "advanced")
    check("level.empty", _modal_level(Counter()), "intermediate")


def test_evidence_prefers_the_strongest_zone():
    pooled = _pool_evidence([
        (0.5, "loose prose about the company"),
        (1.0, "Requirements: Kubernetes in production"),
        (0.7, "Responsible for cluster upkeep"),
    ])
    check("evidence.order", pooled[0], "Requirements: Kubernetes in production")
    check("evidence.capped", len(_pool_evidence(
        [(1.0, f"line {i}") for i in range(20)])), 3)
    check("evidence.deduped", _pool_evidence(
        [(1.0, "same"), (1.0, "same"), (0.5, "other")]), ["same", "other"])


def test_skills_carry_the_matcher_contract():
    skills = to_skills(build_term_pool(JOBS), min_df=1)
    keys = set(skills[0])
    for required in ("term", "canonical", "level", "weight", "evidence_count",
                     "sources", "evidence", "normalized", "by_career_path",
                     "postings_by_path"):
        check(f"shape.{required}", required in keys, True)
    check("shape.evidence_dicts", "text" in skills[0]["evidence"][0], True)


# ── Ontology ───────────────────────────────────────────────────
def accepted(skill_id, label="X"):
    return {"review_status": "accepted", "canonical_id": skill_id,
            "canonical_label": label}


def test_requirement_is_a_fraction_not_a_count():
    """
    The paths are different sizes, so counts are not comparable.

    Kubernetes is in 3 of 3 Backend postings and 30 of 300 DevOps ones.
    By count DevOps looks like the bigger requirement; by coverage
    Backend plainly is.
    """
    skills = [{
        "normalized": "kubernetes", "term": "Kubernetes", "level": "advanced",
        "postings_by_path": {"Backend": [0, 1, 2],
                             "DevOps": list(range(100, 130))},
    }]
    matches = {"kubernetes": accepted("custom:k8s", "Kubernetes")}
    rows = build_ontology(skills, matches, {"Backend": 3, "DevOps": 300})
    by_path = {r["career_path"]: r for r in rows}
    check("ontology.backend_score", by_path["Backend"]["required_score"], 100.0)
    check("ontology.devops_score", by_path["DevOps"]["required_score"], 10.0)


def test_unaccepted_matches_never_become_requirements():
    skills = [
        {"normalized": "a", "term": "A", "level": "advanced",
         "postings_by_path": {"Backend": [0, 1, 2]}},
        {"normalized": "b", "term": "B", "level": "advanced",
         "postings_by_path": {"Backend": [0, 1, 2]}},
        {"normalized": "c", "term": "C", "level": "advanced",
         "postings_by_path": {"Backend": [0, 1, 2]}},
    ]
    matches = {
        "a": accepted("custom:a"),
        "b": {"review_status": "needs_review", "canonical_id": "custom:b",
              "canonical_label": "B"},
        "c": {"review_status": "no_match", "canonical_id": None,
              "canonical_label": None},
    }
    rows = build_ontology(skills, matches, {"Backend": 3})
    check("ontology.only_accepted", [r["skill_id"] for r in rows], ["custom:a"])


def test_several_terms_for_one_skill_union_their_postings():
    """
    The double-counting regression.

    "Grafana", "Prometheus", "logging", "monitoring" and "observability"
    all resolve to one skill. A posting naming three of them is one
    posting; summing the term counts scored it three times and put the
    skill at 100% of the DevOps path, which is the number the gap
    analysis subtracts against.
    """
    skills = [
        {"normalized": "grafana", "term": "Grafana", "level": "advanced",
         "postings_by_path": {"DevOps": [1, 2, 3]}},
        {"normalized": "prometheus", "term": "Prometheus", "level": "advanced",
         "postings_by_path": {"DevOps": [1, 2, 3]}},
        {"normalized": "monitoring", "term": "monitoring", "level": "advanced",
         "postings_by_path": {"DevOps": [1, 2, 4]}},
    ]
    matches = {name: accepted("custom:obs", "monitoring and observability")
               for name in ("grafana", "prometheus", "monitoring")}
    rows = build_ontology(skills, matches, {"DevOps": 10})
    check("union.one_row", len(rows), 1)
    # Four distinct postings out of ten, not the nine a sum would report.
    check("union.posting_count", rows[0]["posting_count"], 4)
    check("union.coverage", rows[0]["coverage"], 0.4)
    check("union.score", rows[0]["required_score"], 40.0)
    check("union.terms", rows[0]["terms"], ["Grafana", "Prometheus", "monitoring"])


def test_coverage_never_exceeds_one():
    """Even a term list covering every posting caps at a true fraction."""
    skills = [
        {"normalized": "k8s", "term": "k8s", "level": "advanced",
         "postings_by_path": {"Backend": list(range(10))}},
        {"normalized": "kubernetes", "term": "Kubernetes", "level": "advanced",
         "postings_by_path": {"Backend": list(range(10))}},
    ]
    matches = {"k8s": accepted("custom:k8s", "Kubernetes"),
               "kubernetes": accepted("custom:k8s", "Kubernetes")}
    rows = build_ontology(skills, matches, {"Backend": 10})
    check("cap.one_row", len(rows), 1)
    check("cap.coverage", rows[0]["coverage"], 1.0)
    check("cap.count", rows[0]["posting_count"], 10)


def test_rare_skills_are_dropped():
    skills = [{"normalized": "x", "term": "X", "level": "advanced",
               "postings_by_path": {"Backend": [0]}}]
    matches = {"x": accepted("custom:x")}
    check("ontology.below_min_coverage",
          build_ontology(skills, matches, {"Backend": 300}), [])


def test_path_totals():
    check("totals", dict(path_totals(JOBS)), {"Backend": 3, "DevOps": 1})


def test_required_level_is_the_median_not_the_mode():
    """Where the requirement level comes from, and why the mode was wrong.

    "Advanced" is the largest single bucket corpus-wide, so a mode hands it the plurality for
    nearly every skill even when most postings asked for less. Measured on the real corpus, a
    mode produced "advanced" for 83% of requirements against a corpus where 51% of mentions
    were advanced — a level that no longer distinguished anything.
    """
    # A plurality is not a majority: 40 of 100 postings want advanced, 60 want less.
    check("median.plurality_loses", _required_level(Counter(
        {"beginner": 25, "intermediate": 35, "advanced": 40})), "intermediate")
    # A real majority still carries.
    check("median.majority_wins", _required_level(Counter(
        {"intermediate": 10, "advanced": 90})), "advanced")
    # Exactly half satisfied at intermediate is satisfied — the median is inclusive.
    check("median.exact_half", _required_level(Counter(
        {"intermediate": 50, "advanced": 50})), "intermediate")
    check("median.single", _required_level(Counter({"beginner": 7})), "beginner")
    check("median.empty", _required_level(Counter()), "intermediate")


def test_required_level_uses_the_distribution_not_the_collapsed_mode():
    """The ontology aggregates the level mix, not one level per term.

    Each term arrives already collapsed to a modal `level` for the job_skills row it becomes.
    Aggregating those modes takes a mode of modes, and the two collapses compound. `levels`
    carries the real distribution so the second pass sees what the postings actually asked for.
    """
    # Ten postings, and the term is mostly asked for at intermediate depth.
    skills = [{
        "normalized": "k8s", "term": "Kubernetes",
        "level": "advanced",  # the collapsed value the DB row keeps
        "levels": {"intermediate": 7, "advanced": 3},
        "postings_by_path": {"DevOps": list(range(10))},
    }]
    matches = {"k8s": accepted("custom:k8s", "Kubernetes")}
    rows = build_ontology(skills, matches, {"DevOps": 10})
    check("distribution.used", rows[0]["required_level"], "intermediate")

    # Without `levels` the old behaviour stands, so an ontology built before the field
    # existed still produces a level rather than failing.
    legacy = [{"normalized": "k8s", "term": "Kubernetes", "level": "advanced",
               "postings_by_path": {"DevOps": list(range(10))}}]
    rows = build_ontology(legacy, matches, {"DevOps": 10})
    check("distribution.legacy_fallback", rows[0]["required_level"], "advanced")


def test_level_aggregation_weights_by_postings_not_terms():
    """A skill named by a term in 9 postings outweighs one named in a single posting.

    Several terms resolve to one skill, and they are not equally common. Counting each term's
    mix once would let a rare synonym in one posting outvote the phrase fifty employers used.
    """
    skills = [
        {"normalized": "common", "term": "Kubernetes", "level": "intermediate",
         "levels": {"intermediate": 1}, "postings_by_path": {"DevOps": list(range(9))}},
        {"normalized": "rare", "term": "K8s cluster ops", "level": "advanced",
         "levels": {"advanced": 1}, "postings_by_path": {"DevOps": [9]}},
    ]
    matches = {name: accepted("custom:k8s", "Kubernetes") for name in ("common", "rare")}
    rows = build_ontology(skills, matches, {"DevOps": 10})
    check("weighting.posting_count", rows[0]["posting_count"], 10)
    check("weighting.level", rows[0]["required_level"], "intermediate")


def main():
    test_document_frequency_counts_postings()
    test_repeated_mentions_do_not_inflate_frequency()
    test_cutoff_filters_by_frequency()
    test_pool_key_folds_spelling_variants()
    test_surface_prefers_the_common_spelling()
    test_modal_level_does_not_saturate()
    test_evidence_prefers_the_strongest_zone()
    test_skills_carry_the_matcher_contract()
    test_requirement_is_a_fraction_not_a_count()
    test_unaccepted_matches_never_become_requirements()
    test_several_terms_for_one_skill_union_their_postings()
    test_coverage_never_exceeds_one()
    test_rare_skills_are_dropped()
    test_path_totals()
    test_required_level_is_the_median_not_the_mode()
    test_required_level_uses_the_distribution_not_the_collapsed_mode()
    test_level_aggregation_weights_by_postings_not_terms()

    print(f"Ran {_checks} checks")
    if _failures:
        print(f"\n❌ {len(_failures)} failed\n")
        for failure in _failures:
            print(f"   - {failure}")
        sys.exit(1)
    print("✅ All checks passed")


if __name__ == "__main__":
    main()
