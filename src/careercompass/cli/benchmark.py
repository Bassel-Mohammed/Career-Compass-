"""
CareerCompass — Hot-path benchmark

ENGINEERING_NOTES.md §6 is a list of five optimisations that were obvious and
wrong: dedup was going to collapse the job corpus 10x and managed 2.0x, the GPU
embedder was going to be faster and was slower. The lesson recorded there is
"measure before building". This is the cheapest way to keep doing that.

It measures the paths that actually cost something, so a change can be compared
against a number rather than an intuition:

  * the artefact loaders every API request depends on
  * the taxonomy and vector index built once per process
  * one LLM decision, serial and concurrent

Nothing here writes anything. The LLM section is skipped unless the provider is
reachable, and `--no-llm` skips it regardless.

Usage:
    python -m careercompass.cli.benchmark
    CUDA_VISIBLE_DEVICES="" python -m careercompass.cli.benchmark --llm-concurrency 4
"""

import argparse
import time
from pathlib import Path


def _time(fn, n: int):
    """Median of n runs, in milliseconds, after one warm-up call."""
    fn()
    samples = []
    for _ in range(n):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    return samples[len(samples) // 2]


def _row(label: str, ms: float, note: str = "") -> None:
    print(f"  {label:44} {ms:9.3f} ms  {note}")


def bench_loaders() -> None:
    from careercompass.config import SKILLS_DIR, TAXONOMY_PATH
    from careercompass.skills.course_index import INDEX_PATH, load_index
    from careercompass.skills.gap import attach_skill_types, load_requirements
    from careercompass.skills.ontology import ONTOLOGY_PATH
    from careercompass.skills.vector import load_course_skills

    print("\nARTEFACT LOADERS  (every API request depended on these uncached)")
    size = Path(INDEX_PATH).stat().st_size / 1e6 if Path(INDEX_PATH).exists() else 0
    _row("load_index()  [/recommendations]", _time(load_index, 20), f"{size:.1f} MB file")
    # Deliberately the uncached function: the API wraps it in
    # `app._load_course_skills`, so this row is the parse cost the cache avoids,
    # not what a request pays.
    _row("load_course_skills()  [uncached parse]",
         _time(lambda: load_course_skills(SKILLS_DIR.glob("*.json")), 10))
    _row("load_requirements()  [gap/rec]",
         _time(lambda: load_requirements(ONTOLOGY_PATH, "AI & Machine Learning"), 20))
    _row("attach_skill_types()  [gap/rec]",
         _time(lambda: attach_skill_types(
             load_requirements(ONTOLOGY_PATH, "AI & Machine Learning"), TAXONOMY_PATH), 20))


def bench_startup() -> None:
    from careercompass.skills.embeddings import load_or_build_index
    from careercompass.skills.taxonomy import load_taxonomy

    print("\nSTARTUP  (once per process)")
    started = time.perf_counter()
    taxonomy = load_taxonomy()
    _row("load_taxonomy()", (time.perf_counter() - started) * 1000,
         f"{len(taxonomy)} skills")
    started = time.perf_counter()
    index = load_or_build_index(taxonomy)
    _row("load_or_build_index()", (time.perf_counter() - started) * 1000,
         f"{index.backend}, {len(index)} entries")


def bench_llm(concurrency: int) -> None:
    import concurrent.futures as cf

    from careercompass.skills.llm import LLMDecider
    from careercompass.skills.taxonomy import load_taxonomy

    decider = LLMDecider(enabled=True)
    print(f"\nLLM  ({decider.display_name})")
    if not decider.available:
        print(f"  unavailable: {decider.reason_unavailable}")
        return

    candidates = [(skill, 0.5) for skill in load_taxonomy().skills[:10]]
    terms = [("containerisation", "packaging applications into containers"),
             ("version control", "branching and merging"),
             ("query language", "relational queries and joins"),
             ("unit testing", "writing test cases for classes")]

    decider.decide("warmup", "warm the model", candidates)  # pay any reload once

    started = time.perf_counter()
    for term, evidence in terms:
        decider.decide(term, evidence, candidates)
    serial = time.perf_counter() - started
    _row(f"decide() x{len(terms)} serial", serial * 1000, f"{serial / len(terms):.2f} s/term")

    if concurrency > 1:
        # Kept as a probe, not as a setting the pipeline uses. Concurrency was
        # measured end to end and gained nothing (201 s against 199 s over 132
        # terms); this row exists so that a future Ollama or hardware change is
        # noticed rather than assumed. Treat a single run as noise — the serial
        # baseline alone varies 6.7-9.4 s.
        started = time.perf_counter()
        with cf.ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(lambda te: decider.decide(te[0], te[1], candidates), terms))
        parallel = time.perf_counter() - started
        _row(f"decide() x{len(terms)} at concurrency {concurrency}", parallel * 1000,
             f"{serial / parallel:.2f}x vs serial (probe only; pipeline is serial)")


def main():
    parser = argparse.ArgumentParser(description="Measure the CareerCompass hot paths")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM section")
    parser.add_argument("--llm-concurrency", type=int, default=4,
                        help="parallel LLM requests to compare against serial")
    parser.add_argument("--skip-startup", action="store_true",
                        help="skip the taxonomy and index build")
    args = parser.parse_args()

    print("CareerCompass hot-path benchmark")
    print("=" * 72)
    bench_loaders()
    if not args.skip_startup:
        bench_startup()
    if not args.no_llm:
        bench_llm(args.llm_concurrency)
    print("\nLoaders are cached on file fingerprints, so a second call is a dict lookup.")
    print("A number that regresses here is a cache that stopped invalidating, or one")
    print("that stopped hitting. Both are worth knowing about.")


if __name__ == "__main__":
    main()
