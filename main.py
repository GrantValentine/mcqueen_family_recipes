"""
Build pipeline:
  1. Extract recipes from Word/PDF files → recipes/*.json
  2. AI-parse with Claude to clean up ingredients/instructions  (optional, requires ANTHROPIC_API_KEY)
  3. Generate the static site → site/

Usage:
    python main.py              # full pipeline (skips AI step if no API key)
    python main.py --ai         # force AI parsing step
    python main.py --ai --force # re-parse all recipes even if already processed
    python main.py --no-extract # skip extraction, just build site
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scripts.extract_recipes import extract_all
from scripts.build_site import build_site


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="Run AI parsing step")
    parser.add_argument("--force", action="store_true", help="Re-parse all recipes (with --ai)")
    parser.add_argument("--no-extract", action="store_true", help="Skip extraction step")
    args = parser.parse_args()

    if not args.no_extract:
        print("=== Step 1: Extracting recipes ===")
        rc = extract_all()
        if rc != 0:
            print("Extraction finished with errors — check output above.")

    # AI parsing: run if --ai flag given, or if API key is set and recipes exist
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    run_ai = args.ai or (api_key and not args.no_extract)

    if run_ai:
        if not api_key:
            print("\nSkipping AI parse: ANTHROPIC_API_KEY not set.")
        else:
            print("\n=== Step 2: AI parsing with Claude ===")
            from scripts.ai_parse_recipes import run as ai_run
            rc = asyncio.run(ai_run(force=args.force))
            if rc != 0:
                print("AI parsing finished with errors — check output above.")
    else:
        if not args.no_extract:
            print("\n(Set ANTHROPIC_API_KEY to enable AI-assisted parsing)")

    step = 3 if run_ai and api_key else 2
    print(f"\n=== Step {step}: Building site ===")
    rc = build_site()
    if rc != 0:
        print("Site build failed — check output above.")
        sys.exit(1)

    print("\nDone. Open site/index.html or run: python -m http.server 8000 --directory site")


if __name__ == "__main__":
    main()
