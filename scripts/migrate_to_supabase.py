"""
One-time migration: reads existing recipes/*/  JSON files and upserts them
into the Supabase database.  Safe to re-run (uses upsert on slug).

Required env vars (set in .env or shell):
  SUPABASE_URL       — project URL
  SUPABASE_ANON_KEY  — public anon key
  ADMIN_EMAIL        — email of the Supabase Auth admin user
  ADMIN_PASSWORD     — admin password (local only; never commit)

Usage:
  python scripts/migrate_to_supabase.py            # live run
  python scripts/migrate_to_supabase.py --dry-run  # parse only, no writes
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# Load .env before importing supabase so env vars are available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import os
from supabase import create_client, Client

ROOT = Path(__file__).parent.parent
RECIPES_DIR = ROOT / "recipes"


# ── Supabase client ───────────────────────────────────────────────────────────

def get_client() -> Client:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        sys.exit("Error: SUPABASE_URL and SUPABASE_ANON_KEY must be set.")
    return create_client(url, key)


def authenticate(db: Client) -> None:
    email = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        sys.exit(
            "Error: ADMIN_EMAIL and ADMIN_PASSWORD must be set.\n"
            "The migration authenticates as the admin so Supabase RLS allows writes."
        )
    result = db.auth.sign_in_with_password({"email": email, "password": password})
    if not result.user:
        sys.exit("Error: authentication failed — check ADMIN_EMAIL / ADMIN_PASSWORD.")
    print(f"  Authenticated as {result.user.email}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_category_map(db: Client) -> dict[str, str]:
    """Return {category_slug: uuid} for all seeded categories."""
    rows = db.table("categories").select("id, slug").execute().data
    return {r["slug"]: r["id"] for r in rows}


def iter_recipe_files():
    for path in sorted(RECIPES_DIR.glob("*/*.json")):
        yield path


# ── Main migration ────────────────────────────────────────────────────────────

def migrate(dry_run: bool = False) -> None:
    db = get_client()
    print("Authenticating with Supabase…")
    authenticate(db)

    cat_map = load_category_map(db)
    print(f"  Categories found: {', '.join(sorted(cat_map))}\n")

    recipe_files = list(iter_recipe_files())
    print(f"Recipe JSON files found: {len(recipe_files)}")
    if dry_run:
        print("  (dry-run: no writes will be made)\n")

    inserted = skipped = 0
    errors: list[str] = []

    for path in recipe_files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.name}: JSON error — {exc}")
            continue

        slug = data.get("slug", "").strip()
        title = data.get("title", "").strip()
        if not slug or not title:
            errors.append(f"{path.name}: missing slug or title, skipping")
            skipped += 1
            continue

        cat_slug = data.get("category_slug") or path.parent.name
        cat_id = cat_map.get(cat_slug)
        if not cat_id:
            errors.append(f"{path.name}: unknown category '{cat_slug}', skipping")
            skipped += 1
            continue

        row = {
            "title":        title,
            "category_id":  cat_id,
            "ingredients":  data.get("ingredients") or [],
            "instructions": data.get("instructions") or [],
            "notes":        data.get("notes") or [],
            "photo_url":    None,   # uploaded via admin UI; local photos stay in photos/
            "slug":         slug,
            "source_file":  data.get("source_file"),
        }

        if dry_run:
            print(f"  would upsert: {title[:55]}")
            inserted += 1
            continue

        try:
            db.table("recipes").upsert(row, on_conflict="slug").execute()
            inserted += 1
            if inserted % 25 == 0:
                print(f"  … {inserted}/{len(recipe_files)}")
        except Exception as exc:
            errors.append(f"{path.name}: insert error — {exc}")

    # ── Report ────────────────────────────────────────────────────────────────
    label = "Dry-run" if dry_run else "Inserted/updated"
    print(f"\n{label}: {inserted}   Skipped: {skipped}   Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  {e}")

    if dry_run or errors:
        return

    # ── Verify counts ─────────────────────────────────────────────────────────
    print("\nVerifying counts in Supabase:")
    cats = db.table("categories").select("id, slug, name").order("sort_order").execute().data
    total = 0
    for cat in cats:
        r = (
            db.table("recipes")
            .select("id", count="exact")
            .eq("category_id", cat["id"])
            .execute()
        )
        n = r.count or 0
        total += n
        print(f"  {cat['name']:<35} {n}")
    print(f"  {'TOTAL':<35} {total}")
    print("\nExpected totals from JSON files:")
    print("  Appetizers 16, Bread 14, Cookies 25, Desserts 44,")
    print("  Main Dishes 62, Salads 13, Vegetables 14  →  188")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate JSON recipes to Supabase.")
    parser.add_argument("--dry-run", action="store_true", help="Parse without writing")
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
