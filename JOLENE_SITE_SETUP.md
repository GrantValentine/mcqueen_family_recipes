# Setting up Jolene's Recipe Site from this repo

This repo (Julie's Family Cookbook) is the template. Follow these steps to clone it
into a brand-new, independent site for Jolene — own database, own hosting, own
look and feel. Nothing here touches Julie's live site or Supabase project.

## 1. Clone into a new repo

```
git clone <this-repo-url> jolene-recipes
cd jolene-recipes
rm -rf .git
git init
```

Removing `.git` and reinitializing is important — otherwise pushes could
accidentally go to Julie's GitHub repo.

Delete content that's specific to Julie's cookbook (do this before opening
Claude Code so it doesn't get confused by stale data):

- `Julie_s Recipes Christmas 2025/` (source Word docs — not needed, recipes will live in the new DB)
- `recipes/**/*.json` (local fallback recipe data — Julie's actual recipes)
- `photos/**` (Julie's recipe photos)
- `tag_report_dryrun_*.csv` (old tagging run output)
- `.env` (you'll create a fresh one — never copy Julie's real keys into the new repo)

Keep: `templates/`, `scripts/`, `admin/`, `netlify/functions/`, `supabase/schema.sql`,
`main.py`, `tag_recipes.py`, `netlify.toml`, `package.json`, `pyproject.toml`,
`requirements.txt`, `public/`, `static/`.

## 2. Create a brand-new Supabase project

Go to supabase.com → New project. Name it something like `jolene-recipes`.
This gives Jolene's site its own database, auth users, and storage — completely
separate from Julie's project.

Once created:
1. Project → SQL Editor → run the contents of `supabase/schema.sql` as-is.
   It creates `categories`, `recipes`, `tags`, `recipe_tags`, RLS policies, and
   seeds default categories/tags (Claude can change these later — see step 5).
2. Storage → New bucket → name `recipe-photos`, **Public bucket: YES**.
3. Storage → that bucket → Policies → add a policy allowing
   INSERT/UPDATE/DELETE for `authenticated` role (same pattern as the SQL
   comment at the bottom of `schema.sql`).
4. Authentication → Users → Add user → create Jolene's admin login
   (email + password). This is the only account that can edit recipes.
5. Authentication → Settings → disable "Enable email confirmations" and
   (recommended) disable "Enable Signups".
6. Project Settings → API → copy the **Project URL** and **anon/public key**.
   These are safe to put in client-side code (RLS protects writes) — do not
   confuse the anon key with the **service_role** key, which must never be
   committed or deployed.

## 3. Local environment

```
cp .env.example .env
```

Fill in `.env`:
- `SUPABASE_URL` / `SUPABASE_ANON_KEY` — from step 2.6 above
- `ADMIN_EMAIL` — Jolene's admin email from step 2.4
- `NETLIFY_BUILD_HOOK` — fill in after step 6 below
- `ADMIN_PASSWORD` — only needed if you run a one-time migration script

If you want AI recipe import (`netlify/functions/import-recipe.js`) or the
`tag_recipes.py` auto-tagging script to work, also add:
```
ANTHROPIC_API_KEY=sk-ant-...
SUPABASE_SERVICE_ROLE_KEY=...   # service_role key, LOCAL ONLY — never commit, never deploy
```

## 4. What to tell Claude Code to do in the new repo

Open Claude Code in the cloned repo and give it a prompt along these lines —
adjust names/categories/colors to whatever Jolene actually wants:

> This is a clone of a family recipe site template, being rebranded for my
> mother-in-law Jolene. Her Supabase project is already created and
> `.env` is filled in. Please:
>
> 1. Rebrand all "Julie" / "Julie's" text to "Jolene" / "Jolene's" —
>    check `templates/base.html` (site title, nav, footer), `templates/index.html`
>    (homepage intro/title), `admin/login/index.html` (the "julie" username →
>    email mapping — change it to "jolene"), `admin/index.html`,
>    `admin/import/index.html`, `admin/recipe/index.html`, `netlify.toml`
>    comments, `scripts/build_site.py` page titles, and `supabase/schema.sql`
>    header comment.
> 2. Give the site a new color palette and feel. The current theme uses CSS
>    variables in `templates/base.html` (`--willow-blue`, `--dusty-olive`,
>    `--dusty-rose`, `--willow-light`, `--ink`) — replace these with a new
>    palette themed to [Jolene's style/colors — e.g. "warm autumn, terracotta
>    and sage"]. Also consider whether the fonts (Fraunces + Lora, loaded in
>    `base.html`) should change.
> 3. Update recipe categories to match Jolene's actual cookbook sections —
>    edit the seed data in `supabase/schema.sql` (`categories` insert) before
>    it's run, and `CATEGORY_ORDER` near the top of `scripts/build_site.py`
>    to match.
> 4. Clear out `PHOTO_OVERRIDES` and `TAG_ORDER`/tag seed list in
>    `scripts/build_site.py` and `supabase/schema.sql` — decide with me
>    whether to keep the same tag set (Vegetarian, Gluten-Free, Easy, etc.)
>    or define new ones for Jolene's recipes.
> 5. Update `package.json` / `pyproject.toml` project name fields.
> 6. Leave the Supabase/Netlify/Anthropic env var *names* unchanged (just
>    pointing at Jolene's own project) so the existing scripts keep working.
>
> Do NOT touch anything in the sibling Julie's-cookbook repo — this is a
> fully separate project from here on.

Claude Code can do all of this within the new repo since it's just templates,
CSS, and config — no destructive or cross-repo risk once `.git` has been
reinitialized per step 1.

## 5. Netlify deployment

1. Push the new repo to a new GitHub repo (e.g. `jolene-recipes`).
2. Netlify → Add new site → Import an existing project → pick the new repo.
   `netlify.toml` already defines the build command and publish dir, so
   defaults should work.
3. Site settings → Environment variables, add:
   - `SUPABASE_URL`, `SUPABASE_ANON_KEY` — Jolene's project (step 2.6)
   - `ADMIN_EMAIL` — Jolene's admin login email
   - `ANTHROPIC_API_KEY` — if using AI import/tagging
   - `NETLIFY_BUILD_HOOK` — create this one *after* first deploy:
     Site settings → Build & deploy → Build hooks → Add hook → paste the URL
     back into both Netlify env vars and your local `.env`.
4. Trigger first deploy.

## 6. Keep-alive (optional but recommended)

Supabase free tier projects pause after a period of inactivity.
`.github/workflows/keep-alive.yml` already pings the DB on a schedule —
just make sure the new repo's GitHub Actions secrets include Jolene's
`SUPABASE_URL` / `SUPABASE_ANON_KEY` (same names, new values), and confirm
the workflow runs green after the first scheduled trigger or a manual
`workflow_dispatch`.

## 7. Recipes

Empty database to start. To populate it, use the admin "Import" page
(`/admin/import/`) with the AI extraction function, add recipes manually
through the admin recipe editor, or write a one-off script to bulk-import
if Jolene has digitized recipes already (see `scripts/migrate_to_supabase.py`
for the pattern used to seed Julie's cookbook the first time).

## Summary checklist

- [ ] New git repo, `.git` reinitialized
- [ ] Julie-specific recipe/photo data deleted
- [ ] New Supabase project, schema run, storage bucket + policy, admin user
- [ ] `.env` filled with Jolene's keys
- [ ] Claude Code rebrand pass (copy, colors, categories, tags)
- [ ] New GitHub repo pushed
- [ ] Netlify site connected, env vars set, build hook wired up
- [ ] Keep-alive workflow secrets set for new project
- [ ] First recipes imported
