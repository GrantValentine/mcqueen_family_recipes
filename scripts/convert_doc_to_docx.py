"""
Bulk-convert all .doc files in the recipe folder to .docx using Word.
Requires Microsoft Word to be installed. Run once, then re-run main.py.

Usage: python scripts/convert_doc_to_docx.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
SOURCE_DIR = ROOT / "Julie_s Recipes Christmas 2025"

# Word's wdFormatXMLDocument constant
WD_FORMAT_DOCX = 16


def convert_all() -> None:
    doc_files = [
        p for p in SOURCE_DIR.rglob("*.doc")
        if not p.name.startswith("._") and not p.name.startswith("~$")
    ]

    if not doc_files:
        print("No .doc files found.")
        return

    print(f"Found {len(doc_files)} .doc files. Opening Word...")

    try:
        import win32com.client
    except ImportError:
        print("ERROR: pywin32 not installed. Run: python -m pip install pywin32")
        sys.exit(1)

    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False

    converted = errors = 0
    try:
        for src in doc_files:
            dest = src.with_suffix(".docx")
            if dest.exists():
                print(f"  SKIP (already exists) {src.name}")
                continue
            try:
                doc = word.Documents.Open(str(src.resolve()))
                doc.SaveAs2(str(dest.resolve()), FileFormat=WD_FORMAT_DOCX)
                doc.Close()
                print(f"  OK  {src.name} -> {dest.name}")
                converted += 1
            except Exception as exc:
                print(f"  ERROR {src.name}: {exc}", file=sys.stderr)
                errors += 1
    finally:
        word.Quit()

    print(f"\nConverted {converted}  |  errors {errors}")
    if converted:
        print("Now run:  python main.py  to include the new recipes in the site.")


if __name__ == "__main__":
    convert_all()
