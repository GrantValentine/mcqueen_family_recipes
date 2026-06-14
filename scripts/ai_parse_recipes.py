"""
Use Claude to re-parse all recipes into clean structured JSON.
Reads raw text from .docx/.pdf source files and asks Claude to identify
ingredients, instructions (as individual steps), and notes.

Usage:
    python scripts/ai_parse_recipes.py           # skip already-parsed recipes
    python scripts/ai_parse_recipes.py --force   # re-parse everything

Requires ANTHROPIC_API_KEY to be set in your environment.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent
SOURCE_DIR = ROOT / "Julie_s Recipes Christmas 2025"
RECIPES_DIR = ROOT / "recipes"
INTRO_FILE = SOURCE_DIR / "Cookbook Introduction.docx"

MODEL = "claude-haiku-4-5-20251001"
CONCURRENCY = 10  # parallel API calls

SYSTEM_PROMPT = """\
You are a recipe parser. Given raw text from a recipe document, return a JSON object with exactly these fields:

{
  "title": "Recipe name (string)",
  "ingredients": ["ingredient 1", "ingredient 2", ...],
  "instructions": ["Step 1 text.", "Step 2 text.", ...],
  "notes": ["note or tip 1", ...]
}

Rules:
- ingredients: each item is one ingredient with its quantity and preparation notes (e.g. "2 cups flour, sifted")
- instructions: break continuous instruction text into individual logical steps. Each step should be one action or closely related group of actions. Never return one giant block of text as a single step.
- notes: tips, variations, serving suggestions, personal anecdotes, make-ahead instructions, storage info
- If a line is ambiguous, use context to decide — a quantity at the start strongly implies an ingredient; an imperative verb strongly implies an instruction
- Return ONLY valid JSON, no markdown fences, no extra text
"""


def extract_raw_text_docx(path: Path) -> str:
    from docx import Document
    doc = Document(path)
    return "\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


def extract_raw_text_pdf(path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    lines = []
    for page in reader.pages:
        lines.extend((page.extract_text() or "").splitlines())
    return "\n".join(l.strip() for l in lines if l.strip())


async def parse_with_claude(
    client: anthropic.AsyncAnthropic,
    sem: asyncio.Semaphore,
    json_path: Path,
    src_path: Path,
    force: bool,
) -> str:
    """Parse one recipe file. Returns a status string for display."""
    existing = json.loads(json_path.read_text(encoding="utf-8"))

    if not force and existing.get("ai_parsed"):
        return f"SKIP  {json_path.stem}"

    try:
        if src_path.suffix.lower() == ".docx":
            raw = extract_raw_text_docx(src_path)
        elif src_path.suffix.lower() == ".pdf":
            raw = extract_raw_text_pdf(src_path)
        else:
            return f"SKIP  {json_path.stem} (unsupported source format)"
    except Exception as exc:
        return f"ERROR {json_path.stem}: could not read source — {exc}"

    async with sem:
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Parse this recipe:\n\n{raw}"}],
            )
        except Exception as exc:
            return f"ERROR {json_path.stem}: API error — {exc}"

    raw_json = response.content[0].text.strip()

    # Strip markdown fences if the model added them despite instructions
    if raw_json.startswith("```"):
        raw_json = "\n".join(raw_json.splitlines()[1:])
    if raw_json.endswith("```"):
        raw_json = "\n".join(raw_json.splitlines()[:-1])

    try:
        parsed = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return f"ERROR {json_path.stem}: bad JSON from model — {exc}"

    # Guard: model occasionally returns a list wrapping the object
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed and isinstance(parsed[0], dict) else {}

    if not isinstance(parsed, dict):
        return f"ERROR {json_path.stem}: unexpected JSON shape from model"

    # Merge Claude's fields back into the existing record (preserve category, slug, etc.)
    existing["title"] = parsed.get("title") or existing["title"]
    existing["ingredients"] = parsed.get("ingredients", [])
    existing["instructions"] = parsed.get("instructions", [])
    existing["notes"] = parsed.get("notes", [])
    existing["ai_parsed"] = True
    # Remove legacy preamble field if present
    existing.pop("preamble", None)

    json_path.write_text(
        json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return f"OK    {existing['category']}/{json_path.stem}"


def find_source_file(json_path: Path) -> Path | None:
    """Locate the original source .docx or .pdf for a recipe JSON."""
    existing = json.loads(json_path.read_text(encoding="utf-8"))
    source_name = existing.get("source_file", "")
    if not source_name:
        return None
    for match in SOURCE_DIR.rglob(source_name):
        if not match.name.startswith("._") and not match.name.startswith("~$"):
            return match
    return None


async def run(force: bool) -> int:
    json_files = [
        p for p in RECIPES_DIR.glob("*/*.json")
    ]

    if not json_files:
        print("No recipe JSON files found — run extract_recipes.py first.")
        return 1

    # Build (json_path, src_path) pairs, skipping those with no source
    pairs: list[tuple[Path, Path]] = []
    missing_src = []
    for jf in sorted(json_files):
        src = find_source_file(jf)
        if src:
            pairs.append((jf, src))
        else:
            missing_src.append(jf.stem)

    if missing_src:
        print(f"Note: {len(missing_src)} recipes have no source file (skipping):")
        for name in missing_src[:5]:
            print(f"  {name}")
        if len(missing_src) > 5:
            print(f"  ... and {len(missing_src) - 5} more")

    total = len(pairs)
    print(f"Parsing {total} recipes with Claude ({MODEL})...")
    if not force:
        print("  (pass --force to re-parse already-processed recipes)")
    print()

    client = anthropic.AsyncAnthropic()
    sem = asyncio.Semaphore(CONCURRENCY)

    tasks = [
        parse_with_claude(client, sem, jf, src, force)
        for jf, src in pairs
    ]

    done = ok = skipped = errors = 0
    for coro in asyncio.as_completed(tasks):
        result = await coro
        done += 1
        if result.startswith("OK"):
            ok += 1
        elif result.startswith("SKIP"):
            skipped += 1
        else:
            errors += 1
        print(f"  [{done}/{total}] {result}")

    print(f"\nParsed {ok}  |  skipped {skipped}  |  errors {errors}")
    return 0 if errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-parse all recipes with Claude")
    parser.add_argument("--force", action="store_true", help="Re-parse already-processed recipes")
    args = parser.parse_args()

    sys.exit(asyncio.run(run(args.force)))


if __name__ == "__main__":
    main()
