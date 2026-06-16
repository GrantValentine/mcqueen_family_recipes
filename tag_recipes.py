#!/usr/bin/env python3
"""
tag_recipes.py — Auto-tag Valentine Family Cookbook recipes via a two-pass Claude pipeline.

Proposer agent suggests tags with confidence + evidence.
Verifier agent independently confirms high-stakes (dietary/allergy) tags only.
High-stakes tags are ONLY applied when the verifier confirms them.

DRY RUN by default — generates a CSV report and console summary, writes nothing to Supabase.
Pass --apply to write confirmed additions.

Usage:
    python tag_recipes.py                        # dry run → report only
    python tag_recipes.py --apply                # apply confirmed tags to DB
    python tag_recipes.py --recipe-id <uuid>     # process one recipe (for testing)
    python tag_recipes.py --apply --recipe-id <uuid>

Prerequisites:
    conda create -n recipetagger python=3.12 -y
    conda activate recipetagger
    pip install anthropic supabase python-dotenv

.env (same directory as this script, never committed):
    SUPABASE_URL=https://<project>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY=<service role key — local admin only, never deployed>
    ANTHROPIC_API_KEY=<your key>
"""

import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Models ─────────────────────────────────────────────────────────────────────
PROPOSER_MODEL = "claude-sonnet-4-6"
VERIFIER_MODEL = "claude-sonnet-4-6"   # swap to "claude-opus-4-8" for extra caution

# ── Retry config ───────────────────────────────────────────────────────────────
MAX_RETRIES      = 4
RETRY_BASE_DELAY = 8   # seconds; doubles each attempt (8 → 16 → 32 → 64)

# ── Tag registry ───────────────────────────────────────────────────────────────
# Every tag the script may apply. Missing tags are created in the DB on --apply.
# slug → display label
TAG_REGISTRY: dict[str, str] = {
    # High-stakes: dietary
    "vegetarian":        "Vegetarian",
    "vegan":             "Vegan",
    "dairy-free":        "Dairy-Free",
    "gluten-free":       "Gluten-Free",
    # High-stakes: allergy
    "nut-free":          "Nut-Free",
    "egg-free":          "Egg-Free",
    # Subjective convenience / occasion
    "easy":              "Easy",
    "quick":             "Quick",
    "make-ahead":        "Make-Ahead",
    "holiday":           "Holiday",
    "kid-friendly":      "Kid-Friendly",
    # Method / occasion
    "one-pot":           "One-Pot / One-Pan",
    "slow-cooker":       "Slow Cooker",
    "no-bake":           "No-Bake",
    "grill-bbq":         "Grill / BBQ",
    "freezer-friendly":  "Freezer-Friendly",
    "5-ingredients":     "5 Ingredients or Fewer",
    "spicy":             "Spicy",
    "comfort-food":      "Comfort Food",
    "potluck":           "Potluck / Crowd-Pleaser",
}

HIGH_STAKES: frozenset[str] = frozenset({
    "vegetarian", "vegan", "dairy-free", "gluten-free", "nut-free", "egg-free",
})

# New tags to create in the DB and make available, in addition to whatever already exists.
# Must be valid slugs from TAG_REGISTRY above.
OPT_IN_NEW_TAGS: dict[str, str] = {
    slug: TAG_REGISTRY[slug] for slug in [
        "nut-free",
        "no-bake",
        "one-pot",
        "grill-bbq",
        "5-ingredients",
        "spicy",
    ]
}

# ── Rules (passed verbatim to agents) ──────────────────────────────────────────
RULES = """\
=== GLOBAL RULE FOR HIGH-STAKES TAGS (DIETARY & ALLERGY) ===

These tags are filters people trust. Each must be true for the recipe as a cook would
actually make it. For an ambiguous or easily-swapped ingredient — an unnamed broth/stock,
"chocolate chips," "soy sauce," an unstated flour — judge it this way:

  • If a common substitution makes the recipe qualify (vegetable broth, dairy-free chips,
    gluten-free tamari, certified-GF flour), APPLY the tag and attach a short
    required_substitution note naming the swap, so the cook knows which type to use.
  • If the ingredient genuinely can't be determined and has no obvious swap (an opaque
    store-bought sauce), add it to flagged_for_review instead of tagging.

This swap logic applies only to incidental or unspecified ingredients. It does NOT rescue
a dish whose defining ingredient is disqualifying — a bacon quiche is not Vegetarian, a
butter pound cake is not Dairy-Free. Those simply do not get the tag.

=== HIGH-STAKES — DIETARY ===

Vegetarian (slug: vegetarian)
No meat, poultry, fish, shellfish, or seafood, and no hidden animal-flesh ingredients.
Eggs and dairy are allowed.
Disqualifiers / watch for: gelatin, lard, suet, tallow, anchovies (check Worcestershire
sauce and Caesar dressing), fish sauce, oyster sauce, shrimp paste, chicken/beef/bone
broth or stock, bacon/pancetta.
If broth/stock type is unspecified → treat as ambiguous → flag, do not tag.

Vegan (slug: vegan)
Must be vegetarian AND contain no dairy (milk, butter, cream, cheese, yogurt, ghee, whey,
casein), no eggs, no honey, no other animal products.
Watch: butter (very common in baking), milk/cream/buttermilk, milk chocolate, whey/casein
in processed items, honey, gelatin, Worcestershire.

Dairy-Free (slug: dairy-free)
No milk, butter, cheese, cream, sour cream, yogurt, ghee, buttermilk, ice cream, custard,
condensed/evaporated milk, whey, casein, or milk chocolate.
IMPORTANT: eggs are NOT dairy — a recipe with eggs but no milk products IS dairy-free.
Watch: butter in baking, cream in sauces, milk in batters, milk-chocolate chips.
Plant milks/butters are fine.

Gluten-Free (slug: gluten-free)
No wheat, barley, rye, spelt, farro, or derivatives.
Watch hidden gluten: all-purpose/bread/cake flour, breadcrumbs/panko, pasta/noodles,
couscous, semolina, bulgur, regular soy sauce (contains wheat; tamari is GF), malt and
malt vinegar, beer, seitan, roux and flour-thickened sauces/gravies, condensed "cream of"
soups, croutons, graham crackers, pretzels.
Oats: treat as GF ONLY if the recipe specifies certified GF oats; otherwise flag.
Be strict — this is celiac safety.

=== HIGH-STAKES — ALLERGY ===

Nut-Free (slug: nut-free)
No tree nuts or peanuts.
Watch: nut flours/meals, nut butters, nut oils, marzipan/almond paste, pesto (pine nuts
or walnuts), praline, Nutella, some granolas.
Almond extract / other nut extracts → flag rather than auto-clear.

Egg-Free (slug: egg-free)
No eggs in any form (whole, yolk, white, powdered, egg wash).
Watch: mayonnaise, aioli, custard, meringue, hollandaise, some fresh pasta, egg-glazed bakes.

=== SUBJECTIVE — CONVENIENCE & OCCASION ===

Easy (slug: easy)
Approachable for a novice: roughly ≤10 ingredients, ≤7 steps, common pantry items, basic
techniques only (mixing, sautéing, baking, boiling), standard equipment.
Disqualifiers: candy/deep-fry thermometer, tempering chocolate, laminated dough, caramel,
easily-curdled custard, complex timing, breaking down whole proteins.
When unsure, do NOT tag.

Quick (slug: quick)
Total time (prep + cook) roughly ≤30 minutes. Use stated times if present; otherwise
estimate conservatively.
Disqualifiers: long bakes, braises, rises, marinades, chilling periods, any "overnight"
step. Quick = TIME; Easy = SKILL — a recipe can be one without the other.

Make-Ahead (slug: make-ahead)
Can be fully or substantially prepared in advance and stored (fridge/freezer) without
meaningful quality loss, OR explicitly includes make-ahead / refrigerate-overnight /
freeze-and-reheat guidance.
Good fits: casseroles, soups, stews, chili, doughs, marinades, dressings, overnight oats,
many braises (often better next day).
Do NOT tag: soufflés, fresh fried foods, crisp salads, anything that wilts/sogs/deflates.

Holiday (slug: holiday)
Explicitly tied to a holiday/celebration in the title or notes, OR a recognized festive
dish: turkey, stuffing/dressing, cranberry sauce, pumpkin/pecan pie, green bean casserole,
glazed ham, latkes, sufganiyot, hot cross buns, gingerbread, fruitcake, eggnog,
cut-out/sugar cookies, panettone.
Everyday dishes that merely could appear at a holiday should NOT be tagged.

Kid-Friendly (slug: kid-friendly)
The finished dish is likely to appeal to young children: mild (not spicy/hot),
familiar/recognizable, not strongly bitter or pungent, no alcohol, not overly sophisticated
(no blue cheese, anchovies, very spicy curries, strong liquor).
Sweet treats, simple pastas, mild baked goods qualify.

=== METHOD / OCCASION — LOW-STAKES, OBJECTIVE ===

One-Pot / One-Pan (slug: one-pot)
Entire dish cooked in a single pot, pan, or sheet pan (including sheet-pan dinners).
Infer from equipment mentioned and steps described.

Slow Cooker (slug: slow-cooker)
Uses a slow cooker / Crock-Pot.

No-Bake (slug: no-bake)
Requires no oven baking — especially desserts set by chilling.

Grill / BBQ (slug: grill-bbq)
Cooked on a grill or barbecue.

Freezer-Friendly (slug: freezer-friendly)
Explicitly freezes well or includes freeze-and-reheat guidance.
Related to but distinct from Make-Ahead.

5 Ingredients or Fewer (slug: 5-ingredients)
Five or fewer ingredients, NOT counting salt, pepper, water, and cooking oil. Objective count.

Spicy (slug: spicy)
Contains notable heat: chili peppers, cayenne, hot sauce, jalapeño/serrano/habanero,
red pepper flakes in meaningful quantity.

Comfort Food (slug: comfort-food)
Hearty, rich, nostalgic, indulgent — subjective; use judgment.

Potluck / Crowd-Pleaser (slug: potluck)
Serves many and/or travels well and holds at room temperature (good for gatherings).
"""

# ── Proposer system prompt ──────────────────────────────────────────────────────
PROPOSER_SYSTEM = f"""You are a meticulous recipe tagging assistant for a family cookbook website.
Your job: analyze a recipe and propose tags from a fixed list, following the ruleset below precisely.

You must be CONSERVATIVE on high-stakes tags. An incorrect dietary or allergy tag is far
more harmful than a missed one. Default to NOT tagging when uncertain.

{RULES}

OUTPUT — return ONLY a valid JSON object. No prose, no markdown fences.

{{
  "proposed_tags": [
    {{
      "slug": "<slug from the available list>",
      "confidence": "high|med|low",
      "evidence": "<one-line citation of the specific ingredient(s)/step(s) that triggered this>",
      "required_substitution": "<short note on what to swap — only for high-stakes tags where swap logic applies; omit or null otherwise>"
    }}
  ],
  "conflicts_with_existing": [
    {{
      "slug": "<an existing tag on this recipe that you found a disqualifier for>",
      "disqualifier": "<the specific ingredient or step that disqualifies it>"
    }}
  ],
  "flagged_for_review": [
    {{
      "slug": "<tag you could not determine>",
      "reason": "<why it is ambiguous>"
    }}
  ]
}}

Rules for conflicts_with_existing: check EVERY high-stakes existing tag. If you find a clear
disqualifying ingredient, report it here. You will NOT remove the tag — this is for human review.

Rules for required_substitution: include ONLY when swap logic applies (ambiguous unspecified
ingredient). Do not invent substitutions where the recipe text is unambiguous.

Propose a tag only if you are confident it belongs — not to be thorough, but to be accurate.
"""


def build_proposer_user(recipe: dict, available_slugs: list[str]) -> str:
    existing = ", ".join(sorted(recipe["current_tag_slugs"])) or "(none)"
    ingredients = "\n".join(f"  - {i}" for i in recipe["ingredients"]) or "  (none)"
    instructions = "\n".join(
        f"  {n + 1}. {s}" for n, s in enumerate(recipe["instructions"])
    ) or "  (none)"
    notes = "\n".join(f"  - {n}" for n in recipe["notes"]) or "  (none)"

    return f"""Recipe title: {recipe['title']}
Existing tags on this recipe: {existing}

Ingredients:
{ingredients}

Instructions:
{instructions}

Notes & Tips:
{notes}

Available tag slugs (use ONLY these exact slugs):
{', '.join(sorted(available_slugs))}

Analyze this recipe against the rules and return the JSON object."""


# ── Verifier system prompt ──────────────────────────────────────────────────────
VERIFIER_SYSTEM = f"""You are a skeptical dietary and allergy safety reviewer.

A "proposer" AI has analyzed a recipe and suggested high-stakes dietary/allergy tags.
Your job: INDEPENDENTLY verify each suggestion by looking for hidden disqualifiers the
proposer may have missed. You are the last line of defense.

You review ONLY high-stakes tags: vegetarian, vegan, dairy-free, gluten-free, nut-free, egg-free.

For each proposed tag, you must:
1. Re-read every ingredient carefully for disqualifying items (including hidden sources).
2. Check for hidden disqualifiers: Worcestershire sauce contains anchovies; regular soy
   sauce contains wheat; miso may contain barley; some baking powders contain gluten;
   some chocolates contain milk; "natural flavors" may contain allergens.
3. If a required_substitution was proposed, verify it is the correct swap AND that making
   that swap would genuinely cause the recipe to qualify for the tag.
4. Confirm OR reject with clear, specific reasoning.

{RULES}

OUTPUT — return ONLY a valid JSON object. No prose, no markdown fences.

{{
  "verifications": [
    {{
      "slug": "<tag slug>",
      "confirmed": true,
      "reasoning": "<brief explanation of what you checked and found>"
    }},
    {{
      "slug": "<tag slug>",
      "confirmed": false,
      "reasoning": "<the specific disqualifier you found>"
    }}
  ]
}}

A required_substitution makes confirmed=true ONLY if the swap is correct and complete
and genuinely makes the tag hold. If unsure, set confirmed=false."""


def build_verifier_user(recipe: dict, proposed_high_stakes: list[dict]) -> str:
    ingredients = "\n".join(f"  - {i}" for i in recipe["ingredients"]) or "  (none)"
    instructions = "\n".join(
        f"  {n + 1}. {s}" for n, s in enumerate(recipe["instructions"])
    ) or "  (none)"
    notes = "\n".join(f"  - {n}" for n in recipe["notes"]) or "  (none)"

    return f"""Recipe title: {recipe['title']}

Ingredients (examine every line):
{ingredients}

Instructions (for context):
{instructions}

Notes & Tips:
{notes}

High-stakes tags to verify:
{json.dumps(proposed_high_stakes, indent=2)}

Verify each one. Return the JSON object."""


# ── Claude call helpers ─────────────────────────────────────────────────────────

def call_claude(client: anthropic.Anthropic, **kwargs: Any) -> anthropic.types.Message:
    """Call Claude with exponential-backoff retry on rate-limit / 5xx errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt == MAX_RETRIES - 1:
                raise
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f"      Rate limit — waiting {delay}s (retry {attempt + 1}/{MAX_RETRIES - 1})…")
            time.sleep(delay)
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500 and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"      API {exc.status_code} — retrying in {delay}s…")
                time.sleep(delay)
            else:
                raise
    raise RuntimeError("Max retries exceeded")


def parse_json_response(response: anthropic.types.Message) -> dict:
    """
    Extract and parse JSON from a Claude response.
    - Finds text block by type (never assumes content[0]).
    - Strips code fences.
    - Falls back to regex extraction if there's surrounding prose.
    """
    text: str | None = None
    for block in response.content:
        if block.type == "text":
            text = block.text
            break
    if text is None:
        raise ValueError("No text block found in Claude response")

    cleaned = text.strip()
    # Strip code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    # If there's surrounding prose, extract the JSON object
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

    return json.loads(cleaned)


# ── Tag management ──────────────────────────────────────────────────────────────

def load_tags(supabase: Client) -> dict[str, str]:
    """Return {slug: id} for all tags currently in the DB."""
    result = supabase.table("tags").select("id,slug").execute()
    return {row["slug"]: row["id"] for row in (result.data or [])}


def ensure_tags_exist(supabase: Client, slug_to_id: dict[str, str]) -> list[str]:
    """
    Create any TAG_REGISTRY tags missing from the DB.
    Mutates slug_to_id in-place with new IDs.
    Returns list of newly created slugs.
    """
    created: list[str] = []
    for slug, label in TAG_REGISTRY.items():
        if slug not in slug_to_id:
            result = supabase.table("tags").insert({"slug": slug, "label": label}).execute()
            if result.data:
                slug_to_id[slug] = result.data[0]["id"]
                created.append(slug)
                print(f"  Created tag: {slug!r}  →  {label!r}")
    return created


# ── Recipe loading ──────────────────────────────────────────────────────────────

def load_recipes(supabase: Client) -> list[dict]:
    """
    Load all recipes with their current tag slugs.
    Uses a fresh tag query internally so it doesn't depend on slug_to_id state.
    """
    # Fresh tag map for decoding existing recipe_tags join rows
    tags_result = supabase.table("tags").select("id,slug").execute()
    id_to_slug  = {row["id"]: row["slug"] for row in (tags_result.data or [])}

    recipes_result = supabase.table("recipes").select(
        "id,title,ingredients,instructions,notes,recipe_tags(tag_id)"
    ).execute()

    recipes: list[dict] = []
    for row in (recipes_result.data or []):
        tag_ids       = [rt["tag_id"] for rt in (row.get("recipe_tags") or [])]
        current_slugs = {id_to_slug[tid] for tid in tag_ids if tid in id_to_slug}
        recipes.append({
            "id":               row["id"],
            "title":            row["title"] or "(untitled)",
            "ingredients":      row.get("ingredients") or [],
            "instructions":     row.get("instructions") or [],
            "notes":            row.get("notes") or [],
            "current_tag_slugs": current_slugs,
        })
    return recipes


# ── Core: per-recipe processing ─────────────────────────────────────────────────

def process_recipe(recipe: dict, ai: anthropic.Anthropic, available_slugs: list[str]) -> dict:
    """
    Run proposer + verifier on a single recipe.
    available_slugs controls which tags the AI may propose — pass existing DB slugs
    to restrict to tags already on the site, or TAG_REGISTRY keys to allow new ones.
    Returns a result dict used for both the report and the apply step.
    """
    result: dict[str, Any] = {
        "recipe_id":             recipe["id"],
        "title":                 recipe["title"],
        "current_tags":          sorted(recipe["current_tag_slugs"]),
        "proposed_additions":    [],   # slugs that passed all gates
        "high_stakes_confirmed": [],   # subset of proposed_additions that are high-stakes
        "required_swaps":        {},   # slug → substitution note
        "conflicts":             [],   # existing tags with found disqualifiers
        "flagged_for_review":    [],   # ambiguous cases
        "low_confidence":        [],   # proposer proposed but confidence=low (not applied)
        "rationale":             {},   # slug → evidence string
        "error":                 None,
    }

    allowed: set[str] = set(available_slugs)

    # ── Pass 1: Proposer ────────────────────────────────────────────────────
    try:
        p_resp = call_claude(
            ai,
            model=PROPOSER_MODEL,
            max_tokens=2500,
            system=PROPOSER_SYSTEM,
            messages=[{"role": "user", "content": build_proposer_user(recipe, available_slugs)}],
        )
        p_data = parse_json_response(p_resp)
    except Exception as exc:
        result["error"] = f"Proposer failed: {exc}"
        return result

    proposed_tags: list[dict] = p_data.get("proposed_tags") or []
    conflicts_raw: list[dict] = p_data.get("conflicts_with_existing") or []
    flagged_raw:   list[dict] = p_data.get("flagged_for_review") or []

    # Conflicts with already-applied tags
    for c in conflicts_raw:
        slug = c.get("slug", "")
        if slug in recipe["current_tag_slugs"]:
            result["conflicts"].append(f"{slug}: {c.get('disqualifier', '?')}")

    # Flagged for human review
    for f in flagged_raw:
        result["flagged_for_review"].append(f"{f.get('slug', '?')}: {f.get('reason', '?')}")

    # Split proposals into high-stakes and low-stakes buckets
    # Skip anything already tagged or not in our registry
    proposed_high: list[dict] = []
    proposed_low:  list[dict] = []

    for tag in proposed_tags:
        slug = tag.get("slug", "")
        if slug not in allowed:
            continue
        if slug in recipe["current_tag_slugs"]:
            continue
        if slug in HIGH_STAKES:
            proposed_high.append(tag)
        else:
            proposed_low.append(tag)

    # ── Pass 2: Verifier (high-stakes only) ────────────────────────────────
    confirmed_high: set[str] = set()

    if proposed_high:
        try:
            v_resp = call_claude(
                ai,
                model=VERIFIER_MODEL,
                max_tokens=1500,
                system=VERIFIER_SYSTEM,
                messages=[{"role": "user", "content": build_verifier_user(recipe, proposed_high)}],
            )
            v_data = parse_json_response(v_resp)
        except Exception as exc:
            # Verifier failure → conservatively skip all high-stakes additions
            result["error"] = f"Verifier failed (high-stakes skipped): {exc}"
            v_data = {"verifications": []}

        for v in (v_data.get("verifications") or []):
            slug = v.get("slug", "")
            if v.get("confirmed") and slug in TAG_REGISTRY:
                confirmed_high.add(slug)

    # ── Collect confirmed additions ─────────────────────────────────────────

    # High-stakes: verifier-confirmed only
    for tag in proposed_high:
        slug = tag.get("slug", "")
        if slug in confirmed_high:
            result["proposed_additions"].append(slug)
            result["high_stakes_confirmed"].append(slug)
            result["rationale"][slug] = tag.get("evidence", "")
            sub = tag.get("required_substitution")
            if sub:
                result["required_swaps"][slug] = sub

    # Low-stakes: high + med confidence applied; low confidence reported only
    for tag in proposed_low:
        slug = tag.get("slug", "")
        conf = tag.get("confidence", "low")
        if conf in ("high", "med"):
            result["proposed_additions"].append(slug)
            result["rationale"][slug] = tag.get("evidence", "")
        else:
            result["low_confidence"].append(
                f"{slug} ({tag.get('evidence', 'no evidence given')})"
            )

    return result


# ── Report ──────────────────────────────────────────────────────────────────────

CSV_FIELDS = [
    "recipe_id", "title",
    "current_tags", "proposed_additions", "high_stakes_confirmed",
    "required_swaps", "conflicts", "flagged_for_review",
    "low_confidence", "rationale", "error",
]


def write_csv(results: list[dict], created_tags: list[str], dry_run: bool) -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "dryrun" if dry_run else "applied"
    path = Path(f"tag_report_{mode}_{ts}.csv")

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()

        # Metadata row for created tags
        if created_tags:
            writer.writerow({
                "recipe_id": "__meta__",
                "title": f"Tags {'would be' if dry_run else ''} created in DB",
                "proposed_additions": "; ".join(created_tags),
            })

        for r in results:
            writer.writerow({
                "recipe_id":             r["recipe_id"],
                "title":                 r["title"],
                "current_tags":          "; ".join(r["current_tags"]),
                "proposed_additions":    "; ".join(r["proposed_additions"]),
                "high_stakes_confirmed": "; ".join(r["high_stakes_confirmed"]),
                "required_swaps":        "; ".join(
                    f"{k}: {v}" for k, v in r["required_swaps"].items()
                ),
                "conflicts":             "; ".join(r["conflicts"]),
                "flagged_for_review":    "; ".join(r["flagged_for_review"]),
                "low_confidence":        "; ".join(r.get("low_confidence", [])),
                "rationale":             "; ".join(
                    f"{k}: {v}" for k, v in r["rationale"].items()
                ),
                "error":                 r.get("error") or "",
            })

    return path


def print_console_summary(
    results: list[dict], created_tags: list[str], dry_run: bool
) -> None:
    mode_label = "DRY RUN — nothing written to DB" if dry_run else "APPLIED"
    print("\n" + "═" * 72)
    print(f"  TAG RECIPE REPORT  [{mode_label}]")
    print("═" * 72)

    if created_tags:
        prefix = "[DRY RUN] Would create" if dry_run else "Created"
        print(f"\n  {prefix} tags: {', '.join(created_tags)}")

    total_adds      = 0
    total_conflicts = 0
    total_flagged   = 0
    total_errors    = 0

    for r in results:
        has_anything = (
            r["proposed_additions"] or r["conflicts"] or
            r["flagged_for_review"] or r["error"] or r.get("low_confidence")
        )
        if not has_anything:
            continue

        print(f"\n  ┌─ {r['title']}")

        if r["error"]:
            print(f"  │  ⚠  ERROR: {r['error']}")
            total_errors += 1

        for slug in r["proposed_additions"]:
            swap = r["required_swaps"].get(slug)
            hs   = slug in r["high_stakes_confirmed"]
            ev   = r["rationale"].get(slug, "")
            tag_label  = f"+  {slug}"
            swap_note  = f"  [swap: {swap}]" if swap else ""
            hs_note    = "  ✓ verifier confirmed" if hs else ""
            print(f"  │  {tag_label}{swap_note}{hs_note}")
            if ev:
                print(f"  │     ↳ {ev}")
        total_adds += len(r["proposed_additions"])

        for lc in r.get("low_confidence", []):
            print(f"  │  ~  low confidence (not applied): {lc}")

        for c in r["conflicts"]:
            print(f"  │  ⚡ CONFLICT (existing tag, not changed): {c}")
        total_conflicts += len(r["conflicts"])

        for fl in r["flagged_for_review"]:
            print(f"  │  ⚑  FLAG FOR REVIEW: {fl}")
        total_flagged += len(r["flagged_for_review"])

    print("\n" + "─" * 72)
    print(f"  Recipes processed  : {len(results)}")
    print(f"  Tag additions      : {total_adds}"
          + (" (pending --apply)" if dry_run else ""))
    print(f"  Conflicts flagged  : {total_conflicts}")
    print(f"  Flagged for review : {total_flagged}")
    print(f"  Errors             : {total_errors}")
    print("─" * 72)


# ── Apply ───────────────────────────────────────────────────────────────────────

def apply_tags(
    supabase: Client,
    results: list[dict],
    slug_to_id: dict[str, str],
) -> None:
    """
    Write confirmed tag additions to recipe_tags.
    Idempotent: re-fetches each recipe's current tags and skips any already present.
    """
    total_applied  = 0
    total_skipped  = 0

    for r in results:
        if not r["proposed_additions"] or r["error"]:
            continue

        recipe_id = r["recipe_id"]

        # Re-fetch current tags to guarantee idempotency
        existing_rows = (
            supabase.table("recipe_tags")
            .select("tag_id")
            .eq("recipe_id", recipe_id)
            .execute()
        )
        existing_ids: set[str] = {row["tag_id"] for row in (existing_rows.data or [])}

        to_insert: list[dict] = []
        for slug in r["proposed_additions"]:
            tag_id = slug_to_id.get(slug)
            if not tag_id or str(tag_id).startswith("__pending__"):
                print(f"  ⚠  No DB id for slug {slug!r} — skipping")
                continue
            if tag_id in existing_ids:
                total_skipped += 1
            else:
                to_insert.append({"recipe_id": recipe_id, "tag_id": tag_id})

        if to_insert:
            supabase.table("recipe_tags").insert(to_insert).execute()
            total_applied += len(to_insert)
            labels = [row["tag_id"] and next(
                (s for s, i in slug_to_id.items() if i == row["tag_id"]), row["tag_id"]
            ) for row in to_insert]
            print(f"  ✓  {r['title']}: +{len(to_insert)} ({', '.join(labels)})")

    print(f"\n  Applied: {total_applied}   Already present (skipped): {total_skipped}")


# ── CSV report loader ───────────────────────────────────────────────────────────

def load_results_from_csv(path: Path) -> list[dict]:
    """
    Reconstruct a results list from a previously saved dry-run CSV.
    Only the fields needed by apply_tags are populated.
    Rows with no proposed_additions or with __meta__ recipe_id are skipped.
    """
    results: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("recipe_id", "").startswith("__"):
                continue
            proposed = [
                s.strip()
                for s in row.get("proposed_additions", "").split(";")
                if s.strip()
            ]
            if not proposed:
                continue
            results.append({
                "recipe_id":          row["recipe_id"],
                "title":              row.get("title", row["recipe_id"]),
                "proposed_additions": proposed,
                "error":              row.get("error") or None,
            })
    return results


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Auto-tag recipes using a two-pass Claude pipeline.\n"
            "Dry run by default — pass --apply to write to Supabase."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write confirmed tag additions to Supabase (default: dry run, report only)",
    )
    parser.add_argument(
        "--recipe-id",
        metavar="UUID",
        help="Process only this one recipe ID (useful for spot-checking)",
    )
    parser.add_argument(
        "--apply-from-report",
        metavar="CSV",
        help="Apply tags from a previous dry-run CSV without re-calling Claude",
    )
    args = parser.parse_args()
    dry_run = not args.apply and not args.apply_from_report

    # ── Environment ──────────────────────────────────────────────────────────
    load_dotenv()
    missing_vars = [
        v for v in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ANTHROPIC_API_KEY")
        if not os.environ.get(v)
    ]
    if missing_vars:
        print(f"ERROR: Missing env vars: {', '.join(missing_vars)}")
        print("Create a .env file with those keys (see script header for details).")
        sys.exit(1)

    supabase_url     = os.environ["SUPABASE_URL"]
    service_role_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    anthropic_key    = os.environ["ANTHROPIC_API_KEY"]

    # ── Connections ───────────────────────────────────────────────────────────
    supabase = create_client(supabase_url, service_role_key)
    ai       = anthropic.Anthropic(api_key=anthropic_key)

    # ── Fast path: apply from a previous dry-run CSV ──────────────────────────
    if args.apply_from_report:
        csv_path = Path(args.apply_from_report)
        if not csv_path.exists():
            print(f"ERROR: File not found: {csv_path}")
            sys.exit(1)

        print(f"\nApplying from report: {csv_path}")

        # Ensure opt-in new tags exist in DB before writing joins
        slug_to_id = load_tags(supabase)
        missing_opt_in = {s: l for s, l in OPT_IN_NEW_TAGS.items() if s not in slug_to_id}
        for slug, label in missing_opt_in.items():
            result = supabase.table("tags").insert({"slug": slug, "label": label}).execute()
            if result.data:
                slug_to_id[slug] = result.data[0]["id"]
                print(f"  Created tag: {slug!r}  →  {label!r}")
        slug_to_id = load_tags(supabase)  # refresh after any inserts

        results = load_results_from_csv(csv_path)
        print(f"  {len(results)} recipe(s) with proposed additions\n")
        apply_tags(supabase, results, slug_to_id)
        print("\nDone. Run `python tag_recipes.py` (dry run) to verify.")
        return

    print(f"\nProposer : {PROPOSER_MODEL}")
    print(f"Verifier : {VERIFIER_MODEL}")
    print(f"Mode     : {'DRY RUN (--apply to write)' if dry_run else 'APPLY'}\n")

    # ── Tags ─────────────────────────────────────────────────────────────────
    print("Loading tags from DB…")
    slug_to_id = load_tags(supabase)

    # Create any OPT_IN_NEW_TAGS that don't yet exist in the DB.
    missing_opt_in = {s: l for s, l in OPT_IN_NEW_TAGS.items() if s not in slug_to_id}
    if missing_opt_in:
        if dry_run:
            print(f"  [DRY RUN] Would create {len(missing_opt_in)} new tag(s): "
                  f"{', '.join(missing_opt_in)}")
            created_tags = list(missing_opt_in.keys())
            # Add placeholder IDs so available_slugs includes them in the report
            for slug in missing_opt_in:
                slug_to_id[slug] = f"__pending__{slug}"
        else:
            created_tags = []
            for slug, label in missing_opt_in.items():
                result = supabase.table("tags").insert({"slug": slug, "label": label}).execute()
                if result.data:
                    slug_to_id[slug] = result.data[0]["id"]
                    created_tags.append(slug)
                    print(f"  Created tag: {slug!r}  →  {label!r}")
    else:
        created_tags = []

    # Available slugs = existing DB tags + opted-in new tags.
    # The AI may only propose from this list — no other tags will be created.
    available_slugs = list(slug_to_id.keys())
    print(f"  Using {len(available_slugs)} tag(s): {', '.join(sorted(available_slugs))}")

    # ── Recipes ───────────────────────────────────────────────────────────────
    print("Loading recipes…")
    recipes = load_recipes(supabase)

    if args.recipe_id:
        recipes = [r for r in recipes if r["id"] == args.recipe_id]
        if not recipes:
            print(f"ERROR: Recipe ID {args.recipe_id!r} not found.")
            sys.exit(1)

    n = len(recipes)
    est_calls = n * 2
    print(f"Found {n} recipe(s) → ~{est_calls} Claude API calls\n")

    # ── Process ───────────────────────────────────────────────────────────────
    results: list[dict] = []
    for i, recipe in enumerate(recipes, 1):
        prefix = f"[{i:>{len(str(n))}}/{n}]"
        print(f"{prefix} {recipe['title']}")
        result = process_recipe(recipe, ai, available_slugs)
        results.append(result)

        if result["error"]:
            print(f"        ✗ {result['error']}")
        elif result["proposed_additions"]:
            print(f"        → {', '.join(result['proposed_additions'])}")
        else:
            print(f"        (no new tags)")

    # ── Report ────────────────────────────────────────────────────────────────
    print_console_summary(results, created_tags, dry_run)
    csv_path = write_csv(results, created_tags, dry_run)
    print(f"\n  CSV saved: {csv_path}")

    # ── Apply ─────────────────────────────────────────────────────────────────
    if not dry_run:
        print("\nApplying tags to Supabase…")
        apply_tags(supabase, results, slug_to_id)
        print("\nDone. Run `python tag_recipes.py` (dry run) to verify the final state.")
    else:
        print(
            f"\n  Nothing written. Review the CSV, then apply it with:\n"
            f"    python tag_recipes.py --apply-from-report {csv_path}\n"
            f"\n  Or to re-run Claude and apply in one shot:\n"
            f"    python tag_recipes.py --apply\n"
        )


if __name__ == "__main__":
    main()
