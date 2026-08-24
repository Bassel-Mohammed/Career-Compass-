"""
Pytest wiring for suites that were written as standalone scripts.

Most test modules here predate pytest in this project. They were built to run as
``python -m tests.test_skill_gap``, and they record failures through a module-level
``check()`` helper that appends to ``_failures`` instead of raising — deliberately, so one
run reports every failure rather than stopping at the first.

That design is fine on its own and is kept. It only becomes a problem under pytest, in two
ways, and this file fixes both:

1. ``test_skill_matcher`` builds its matcher inside ``main()`` and passes it to five test
   functions as an argument. pytest reads that argument as a fixture request and errors at
   collection. :func:`matcher` supplies it.

2. Because ``check()`` never raises, pytest saw those modules as passing no matter what the
   checks actually found. Roughly 340 assertions across nine files were being reported green
   without being enforced. :func:`_enforce_recorded_checks` closes that gap.
"""

import os

# Unit tests must never discover a developer's .env and connect to its live
# PostgreSQL while constructing the shared matcher fixture.
os.environ["CC_DB_LOAD_REVIEWS"] = "0"
os.environ["CC_DB_AUTO_MIGRATE"] = "0"

import pytest

from careercompass.skills.embeddings import LexicalEmbedder, VectorIndex
from careercompass.skills.matcher import SkillMatcher
from careercompass.skills.reranker import LexicalReranker
from careercompass.skills.taxonomy import load_taxonomy, skill_text


@pytest.fixture(scope="session")
def matcher():
    """
    The deterministic in-memory matcher ``test_skill_matcher.main()`` builds.

    Constructed exactly as that function does — lexical embedder, lexical reranker, and the
    same accept/review thresholds. Two properties are deliberate and must be preserved:
    it ignores ``.env``, so the suite behaves the same on every machine; and it builds its
    index in memory rather than reading or writing the persisted BGE index, so running the
    tests cannot replace a real index with a lexical one.

    Session-scoped because building it embeds the whole taxonomy, and the five tests that
    use it only read from it.
    """
    taxonomy = load_taxonomy()
    embedder = LexicalEmbedder().fit([skill_text(skill) for skill in taxonomy.skills])
    index = VectorIndex.build(taxonomy, embedder)
    return SkillMatcher(
        taxonomy, index, LexicalReranker(), accept_score=0.62, review_floor=0.40,
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_call(item):
    """
    Fail a test when its ``check()`` calls recorded a failure.

    Without this, a module whose ``check()`` appends to ``_failures`` instead of raising
    reports green under pytest however badly it fails — the failures accumulate in a list
    nobody reads, and CI goes green on a broken build.

    This is a call-phase hook rather than a fixture on purpose. Raising from a fixture's
    teardown gets reported as a teardown *error* while the test itself still prints as
    passed, which is exactly the sort of half-signal that gets skimmed past in CI output.
    Raising here makes it an ordinary test failure.

    Only the failures recorded during *this* test are reported, so one failing test does not
    cascade into every test that follows it in the same module. Modules that use plain
    ``assert`` have no ``_failures`` list and pass straight through. A test that already
    raised keeps its own exception — the recorded checks are the lesser diagnosis.
    """
    failures = getattr(item.module, "_failures", None)
    already_recorded = len(failures) if failures is not None else 0

    result = yield

    if failures is not None:
        new_failures = failures[already_recorded:]
        if new_failures:
            raise AssertionError(
                f"{len(new_failures)} recorded check failure(s):\n\n"
                + "\n\n".join(str(failure) for failure in new_failures)
            )
    return result
