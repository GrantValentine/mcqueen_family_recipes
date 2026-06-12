"""
Build the static recipe website from extracted JSON files.
Reads recipes/ and outputs HTML to site/.
"""

import json
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent.parent
RECIPES_DIR = ROOT / "recipes"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"
SITE_DIR = ROOT / "site"
PHOTOS_DIR = ROOT / "photos"


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

    recipes, by_category = load_recipes()
    intro_paragraphs = load_intro()

    if not recipes:
        print("No recipes found in recipes/ — run extract_recipes.py first.")
        return 1

    # Category display names (slug → original name)
    cat_display: dict[str, str] = {}
    for r in recipes:
        cat_display[r["category_slug"]] = r["category"]

    build_search_index(recipes)

    # Copy static assets
    if STATIC_DIR.exists():
        dest = SITE_DIR / "static"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(STATIC_DIR, dest)

    # Copy photos
    if PHOTOS_DIR.exists():
        dest = SITE_DIR / "photos"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(PHOTOS_DIR, dest)

    # Homepage
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

    # Category pages
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

    # Individual recipe pages
    recipe_tmpl = env.get_template("recipe.html")
    for recipe in recipes:
        page_dir = SITE_DIR / recipe["category_slug"] / recipe["slug"]
        page_dir.mkdir(parents=True, exist_ok=True)

        # Resolve photo path relative to site root
        photo_url = None
        photo_check = PHOTOS_DIR / f"{recipe['slug']}.jpg"
        if photo_check.exists():
            photo_url = f"/photos/{recipe['slug']}.jpg"

        html = recipe_tmpl.render(
            recipe=recipe,
            photo_url=photo_url,
            page_title=f"{recipe['title']} — Julie's Recipes",
            root_path="/",
        )
        (page_dir / "index.html").write_text(html, encoding="utf-8")

    print(f"\nBuilt {len(recipes)} recipe pages -> site/")
    return 0


if __name__ == "__main__":
    sys.exit(build_site())
