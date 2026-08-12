"""
CareerCompass — Taxonomy Build CLI

Merges the taxonomy sources into one vocabulary and embeds it, so the
matcher has something to retrieve against.

Usage:
    # Custom skills only — enough to run the pipeline end to end
    python -m careercompass.cli.build_taxonomy

    # Add ESCO: crawls the ICT, engineering and science branches (slow,
    # cached, resumable — interrupt and re-run to continue)
    python -m careercompass.cli.build_taxonomy --esco --esco-limit 2000

    # Add ESCO from a bulk CSV export instead, and O*NET from disk
    python -m careercompass.cli.build_taxonomy --esco-csv skills_en.csv --onet ./onet_db

    # Re-embed after changing the embedding backend
    CC_EMBEDDING_BACKEND=bge python -m careercompass.cli.build_taxonomy --rebuild-index
"""

import sys
import logging
import argparse

from careercompass.skills.taxonomy import (
    MERGED_PATH, Taxonomy, load_custom_skills, merge_skills, save_taxonomy,
)
from careercompass.skills.sources import (
    ESCO_ALL_ROOTS, ESCO_DEFAULT_ROOTS, crawl_esco, load_esco_cache,
    load_esco_csv, load_onet,
)
from careercompass.skills.embeddings import INDEX_PATH, load_or_build_index


def main():
    parser = argparse.ArgumentParser(
        description="Build the CareerCompass canonical skill taxonomy and its vector index"
    )
    parser.add_argument("--esco", action="store_true",
                        help="Crawl the ESCO API before merging (cached and resumable)")
    parser.add_argument("--esco-limit", type=int, default=0,
                        help="Stop the crawl after this many new concepts (default: no limit)")
    parser.add_argument("--esco-all", action="store_true",
                        help="Crawl the whole skills pillar instead of the computing branches")
    parser.add_argument("--esco-delay", type=float, default=0.2,
                        help="Seconds between ESCO requests (default: 0.2)")
    parser.add_argument("--esco-csv", default=None,
                        help="Path to an ESCO bulk export (skills_en.csv) to use instead of the API")
    parser.add_argument("--onet", default=None,
                        help="Directory holding the O*NET database text files")
    parser.add_argument("--no-custom", action="store_true",
                        help="Leave out the curated custom technology skills")
    parser.add_argument("--rebuild-index", action="store_true",
                        help="Re-embed even when the stored index is still current")
    parser.add_argument("--backend", default="",
                        help="Embedding backend: lexical, bge, or auto (default: auto)")
    parser.add_argument("--output", default=str(MERGED_PATH),
                        help=f"Where to write the merged taxonomy (default: {MERGED_PATH})")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("Building taxonomy")
    print("=" * 60)

    if args.esco:
        roots = ESCO_ALL_ROOTS if args.esco_all else ESCO_DEFAULT_ROOTS
        print(f"\nCrawling ESCO from {len(roots)} root concepts...")
        try:
            fetched = crawl_esco(roots=roots, limit=args.esco_limit, delay=args.esco_delay)
            print(f"   fetched {fetched} new concepts")
        except (RuntimeError, OSError) as exc:
            print(f"⚠️  ESCO crawl stopped: {exc}")
            print("   Continuing with whatever was cached.")

    groups = []

    if args.esco_csv:
        try:
            esco = load_esco_csv(args.esco_csv)
        except FileNotFoundError as exc:
            print(f"❌ Error: {exc}")
            sys.exit(1)
        print(f"\nESCO (csv)      {len(esco):>6} skills")
        groups.append(esco)
    else:
        esco = load_esco_cache()
        print(f"\nESCO (cache)    {len(esco):>6} skills")
        if esco:
            groups.append(esco)

    if args.onet:
        onet = load_onet(args.onet)
        print(f"O*NET           {len(onet):>6} skills")
        if onet:
            groups.append(onet)

    if not args.no_custom:
        custom = load_custom_skills()
        print(f"Custom          {len(custom):>6} skills")
        groups.append(custom)

    if not groups:
        print("\n❌ No sources produced any skills. Nothing to build.")
        sys.exit(1)

    skills = merge_skills(*groups)
    taxonomy = Taxonomy(skills)

    save_taxonomy(skills, args.output)
    print(f"\nMerged          {len(skills):>6} skills  →  {args.output}")
    for source, count in sorted(taxonomy.counts().items()):
        print(f"   {source:<12} {count:>6}")

    aliases = sum(len(skill["aliases"]) for skill in skills)
    arabic = sum(1 for skill in skills if skill.get("labels", {}).get("ar"))
    print(f"   {'aliases':<12} {aliases:>6}")
    print(f"   {'arabic':<12} {arabic:>6}")
    print(f"   fingerprint  {taxonomy.fingerprint}")

    print("\nEmbedding...")
    index = load_or_build_index(taxonomy, backend=args.backend, rebuild=args.rebuild_index)
    print(f"   {len(index)} vectors via {index.backend}  →  {INDEX_PATH}")

    print("\n✅ Done. Match a course with:")
    print('   python -m careercompass.cli.match_skills "Robotics Syl.pdf"')


if __name__ == "__main__":
    main()
