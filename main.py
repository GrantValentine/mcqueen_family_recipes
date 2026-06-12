"""
Build pipeline: extract recipes from Word/PDF files, then generate the static site.
Usage: python main.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scripts.extract_recipes import extract_all
from scripts.build_site import build_site


def main() -> None:
    print("=== Step 1: Extracting recipes ===")
    rc = extract_all()
    if rc != 0:
        print("Extraction finished with errors — check output above.")

    print("\n=== Step 2: Building site ===")
    rc2 = build_site()
    if rc2 != 0:
        print("Site build failed — check output above.")
        sys.exit(1)

    print("\nDone. Open site/index.html in a browser to preview.")


if __name__ == "__main__":
    main()
