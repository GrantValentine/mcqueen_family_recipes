"""
Build the static recipe website.

Data source (checked in order):
  1. SUPABASE_URL env var set → fetch from Supabase (production mode)
  2. Fallback → read local recipes/**/*.json (development / first-run mode)

Also copies admin/ → site/admin/ and writes site/admin/config.js with
ADMIN_EMAIL and NETLIFY_BUILD_HOOK (both read from env, never hardcoded).
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent.parent
RECIPES_DIR   = ROOT / "recipes"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR    = ROOT / "static"
SITE_DIR      = ROOT / "site"
PHOTOS_DIR    = ROOT / "photos"
PUBLIC_DIR    = ROOT / "public"
ADMIN_DIR     = ROOT / "admin"

# Manually resolved mappings for photos whose filenames don't match the recipe
# slug well enough for automatic matching.
# Key: (category_slug, photo_stem_normalized)  Value: recipe slug
PHOTO_OVERRIDES: dict[tuple[str, str], str] = {
    ("appetizers", "christmas-bruscetta"): "christmas-bruschetta",        # typo in filename
    ("appetizers", "italian-cannelini-dip"): "italian-cannellini-dip",   # typo in filename
    ("appetizers", "parmesan-and-artichoke-wonton-cups"): "warm-artichoke-and-parmesan",
    ("bread", "condensed-sourdough-recipe-for-crusty-artisan-loaf"): "sourdough-for-instructing-groups",
    ("bread", "valentine-waffles"): "fluffy-waffle-recipe",
    ("cookies", "julies-chocolate-chip-cookies"): "moms-chocolate-chip-cookie-recipe",
    ("cookies", "sinckerdoodles"): "snickerdoodles-sandwich-cookies",
}


def _normalize(s: str) -> str:
    """Lowercase, collapse spaces/underscores to hyphens, strip non-alphanum."""
    s = s.lower().strip()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return re.sub(r"-+", "-", s).strip("-")


def _significant_tokens(slug: str) -> list[str]:
    """Words longer than 3 chars — used for fuzzy token matching."""
    return [t for t in slug.split("-") if len(t) > 3]


def _score_match(photo_stem: str, recipe_slug: str) -> int:
    """Return a match score (higher = better). 0 means no useful overlap."""
    if photo_stem == recipe_slug:
        return 100
    if recipe_slug.endswith(photo_stem) or photo_stem.endswith(recipe_slug):
        return 80
    if photo_stem in recipe_slug or recipe_slug in photo_stem:
        return 60
    pt = _significant_tokens(photo_stem)
    rt = _significant_tokens(recipe_slug)
    if not pt:
        return 0
    hits = sum(1 for t in pt if t in recipe_slug)
    if hits >= 2 or (hits == 1 and len(pt) == 1):
        return hits * 10
    return 0


def build_photo_index() -> dict[str, list[tuple[Path, str]]]:
    """Scan photos/ subdirectories and return {category_slug: [(path, norm_stem), ...]}."""
    index: dict[str, list[tuple[Path, str]]] = {}
    if not PHOTOS_DIR.exists():
        return index
    for folder in PHOTOS_DIR.iterdir():
        if not folder.is_dir():
            continue
        cat_slug = _normalize(folder.name)
        entries = []
        for f in folder.iterdir():
            if f.suffix.lower() in (".jpg", ".jpeg", ".png"):
                entries.append((f, _normalize(f.stem)))
        if entries:
            index[cat_slug] = entries
    return index


def find_photo(recipe_slug: str, cat_slug: str,
               photo_index: dict[str, list[tuple[Path, str]]]) -> str | None:
    """Return a site-root-relative URL for the best matching photo, or None."""
    photos = photo_index.get(cat_slug, [])

    # Check manual overrides first
    for path, stem in photos:
        override_key = (cat_slug, stem)
        if override_key in PHOTO_OVERRIDES and PHOTO_OVERRIDES[override_key] == recipe_slug:
            return f"/photos/{path.parent.name}/{path.name}"

    # Automatic scoring
    best_score, best_path = 0, None
    for path, stem in photos:
        # Skip photos claimed by an override for a different recipe
        override_key = (cat_slug, stem)
        if override_key in PHOTO_OVERRIDES and PHOTO_OVERRIDES[override_key] != recipe_slug:
            continue
        score = _score_match(stem, recipe_slug)
        if score > best_score:
            best_score, best_path = score, path

    if best_path is not None:
        return f"/photos/{best_path.parent.name}/{best_path.name}"
    return None


def load_recipes_from_supabase() -> tuple[list[dict], dict]:
    """Fetch recipes from Supabase and return the same shape as load_recipes()."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY must be set.")

    try:
        from supabase import create_client
    except ImportError:
        raise RuntimeError("supabase package not installed — run: pip install supabase")

    client = create_client(url, key)
    result = (
        client.table("recipes")
        .select("*, categories(id, slug, name, sort_order)")
        .execute()
    )

    recipes: list[dict] = []
    by_category: dict[str, list[dict]] = {}

    for row in result.data:
        cat = row.get("categories") or {}
        cat_slug = cat.get("slug") or "uncategorised"
        recipe = {
            "title":           row["title"],
            "slug":            row["slug"],
            "category":        cat.get("name") or cat_slug,
            "category_slug":   cat_slug,
            "ingredients":     row.get("ingredients") or [],
            "instructions":    row.get("instructions") or [],
            "notes":           row.get("notes") or [],
            "source_file":     row.get("source_file"),
            "photo":           None,
            # Supabase Storage photo (takes priority over local fuzzy match)
            "_photo_url_db":   row.get("photo_url"),
        }
        recipes.append(recipe)
        by_category.setdefault(cat_slug, []).append(recipe)

    return recipes, by_category


def load_recipes() -> tuple[list[dict], dict]:
    recipes = []
    by_category: dict[str, list[dict]] = {}

    for json_file in sorted(RECIPES_DIR.glob("*/*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))
        recipes.append(data)
        cat = data["category_slug"]
        by_category.setdefault(cat, [])
        by_category[cat].append(data)

    return recipes, by_category


def load_intro() -> list[str]:
    intro_file = RECIPES_DIR / "intro.json"
    if intro_file.exists():
        return json.loads(intro_file.read_text(encoding="utf-8")).get("paragraphs", [])
    return []


def build_search_index(recipes: list[dict]) -> None:
    index = []
    for r in recipes:
        snippet = " ".join(r.get("ingredients", [])[:3])
        index.append(
            {
                "title": r["title"],
                "category": r["category"],
                "category_slug": r["category_slug"],
                "slug": r["slug"],
                "snippet": snippet,
            }
        )
    out = SITE_DIR / "search-index.json"
    out.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")


def recipe_url(recipe: dict, from_root: bool = True) -> str:
    return f"/{recipe['category_slug']}/{recipe['slug']}/"


def category_url(cat_slug: str) -> str:
    return f"/{cat_slug}/"


def build_site() -> int:
    SITE_DIR.mkdir(exist_ok=True)

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
    env.globals["recipe_url"] = recipe_url
    env.globals["category_url"] = category_url

    # Choose data source
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    if supabase_url:
        print("  Data source: Supabase")
        try:
            recipes, by_category = load_recipes_from_supabase()
        except Exception as exc:
            print(f"  WARNING: Supabase load failed ({exc}); falling back to JSON files.")
            recipes, by_category = load_recipes()
    else:
        recipes, by_category = load_recipes()

    intro_paragraphs = load_intro()

    if not recipes:
        print("No recipes found — run extract_recipes.py first or configure Supabase.")
        return 1

    # Category display names (slug → original name)
    cat_display: dict[str, str] = {}
    for r in recipes:
        cat_display[r["category_slug"]] = r["category"]

    build_search_index(recipes)

    # Resolve photos for every recipe upfront so category pages can use them.
    photo_index = build_photo_index()
    matched = 0
    for recipe in recipes:
        db_photo = recipe.pop("_photo_url_db", None)
        photo_url = db_photo or find_photo(recipe["slug"], recipe["category_slug"], photo_index)
        recipe["photo"] = photo_url  # category template reads recipe.photo
        if photo_url:
            matched += 1

    # ── Copy assets ──────────────────────────────────────────────────────────
    for src, label in [
        (STATIC_DIR, "static"),
        (PUBLIC_DIR, "public"),
        (PHOTOS_DIR, "photos"),
    ]:
        if src.exists():
            dest = SITE_DIR / label
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)

    # ── Copy admin SPA and generate config.js ────────────────────────────────
    if ADMIN_DIR.exists():
        dest = SITE_DIR / "admin"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ADMIN_DIR, dest)
        # config.js injects env-var values into the client-side SPA.
        # ADMIN_EMAIL and NETLIFY_BUILD_HOOK are injected here so they never
        # appear in source control.  config.js itself is git-ignored.
        admin_email   = os.environ.get("ADMIN_EMAIL", "")
        netlify_hook  = os.environ.get("NETLIFY_BUILD_HOOK", "")
        config_js = (
            "// Generated at build time — do not commit.\n"
            f"window.ADMIN_EMAIL = {json.dumps(admin_email)};\n"
            f"window.NETLIFY_BUILD_HOOK = {json.dumps(netlify_hook)};\n"
        )
        (dest / "config.js").write_text(config_js, encoding="utf-8")
        print("  site/admin/")

    # ── Homepage ─────────────────────────────────────────────────────────────
    tmpl = env.get_template("index.html")
    categories_summary = [
        {
            "name": cat_display[slug],
            "slug": slug,
            "count": len(recs),
            "sample": recs[:3],
        }
        for slug, recs in sorted(by_category.items())
    ]
    html = tmpl.render(
        intro_paragraphs=intro_paragraphs,
        categories=categories_summary,
        total=len(recipes),
        page_title="Julie's Christmas 2025 Recipes",
        root_path="/",
    )
    (SITE_DIR / "index.html").write_text(html, encoding="utf-8")
    print("  site/index.html")

    # ── Category pages ────────────────────────────────────────────────────────
    cat_tmpl = env.get_template("category.html")
    for slug, recs in sorted(by_category.items()):
        cat_dir = SITE_DIR / slug
        cat_dir.mkdir(exist_ok=True)
        html = cat_tmpl.render(
            category_name=cat_display[slug],
            category_slug=slug,
            recipes=sorted(recs, key=lambda r: r["title"]),
            page_title=f"{cat_display[slug]} — Julie's Recipes",
            root_path="/",
        )
        (cat_dir / "index.html").write_text(html, encoding="utf-8")
        print(f"  site/{slug}/index.html  ({len(recs)} recipes)")

    # ── Individual recipe pages ───────────────────────────────────────────────
    recipe_tmpl = env.get_template("recipe.html")
    for recipe in recipes:
        page_dir = SITE_DIR / recipe["category_slug"] / recipe["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)
        html = recipe_tmpl.render(
            recipe=recipe,
            photo_url=recipe.get("photo"),
            page_title=f"{recipe['title']} — Julie's Recipes",
            root_path="/",
        )
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    print(f"\nBuilt {len(recipes)} recipe pages -> site/  ({matched} with photos)")
    return 0


if __name__ == "__main__":
    sys.exit(build_site())
