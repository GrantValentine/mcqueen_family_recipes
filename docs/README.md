# JoLene's Family Recipes — Project Overview

A static recipe website for the McQueen family. Recipes live in Supabase (PostgreSQL), the site is built with Python + Jinja2, and deployed on Netlify.

---

## How it works

1. **`python main.py --no-extract`** runs the build (Netlify uses this command)
2. `scripts/build_site.py` connects to Supabase, fetches all recipes, renders Jinja2 templates, and writes static HTML to `site/`
3. Netlify serves the `site/` directory as a static site
4. Admin features (adding/editing recipes) are a client-side SPA under `admin/`, which talks directly to Supabase

## Folder structure

```
mcqueen_family_recipes/
├── admin/              Client-side admin SPA (copied to site/admin/ at build time)
│   ├── index.html      Dashboard — list, search, filter recipes
│   ├── recipe/         Edit a single recipe
│   ├── import/         Import a recipe from a photo or PDF
│   ├── login/          Sign-in page
│   ├── admin.js        Shared auth/helpers (Supabase client, showBanner, etc.)
│   └── config.js       Generated at build time — injects env vars (git-ignored)
├── docs/               Documentation (this folder)
├── netlify/
│   └── functions/      Netlify serverless functions
│       ├── import-recipe.js    Calls Claude API to extract a recipe from a file
│       └── supabase-ping.js    Daily keep-alive ping so Supabase doesn't pause
├── public/             Static assets (images, cursors, icons) → served at /public/
├── recipes/
│   └── intro.json      Homepage letter paragraphs (always read locally, never from DB)
├── scripts/
│   └── build_site.py   Main build script
├── static/             JS/CSS copied to site/static/ at build time
│   └── search.js       Client-side fuzzy search (Fuse.js)
├── templates/          Jinja2 HTML templates
│   ├── base.html       Nav, footer, global CSS
│   ├── index.html      Homepage (seed-packet category cards + letter)
│   ├── category.html   Category listing page
│   ├── recipe.html     Individual recipe page
│   └── help.html       Public help page (/help/)
├── netlify.toml        Build config + scheduled function schedule
├── requirements.txt    Python dependencies
└── .env                Local secrets (git-ignored — never commit this)
```

## Environment variables

| Variable | Where used | Notes |
|---|---|---|
| `SUPABASE_URL` | Build script + admin SPA + Netlify functions | Public — safe in client code |
| `SUPABASE_ANON_KEY` | Build script + admin SPA + Netlify functions | Public — safe in client code |
| `ANTHROPIC_API_KEY` | `import-recipe` Netlify function only | **Secret — server-side only** |
| `ADMIN_EMAIL` | Injected into `admin/config.js` at build time | Used for Supabase auth |
| `NETLIFY_BUILD_HOOK` | Injected into `admin/config.js` at build time | Lets the admin trigger a rebuild |

**Never commit `.env`.** Set all variables in the Netlify dashboard under Site → Environment Variables for production.

## Local development

```bash
# Install Python deps
pip install -r requirements.txt

# Copy .env.example → .env and fill in your values
cp .env.example .env

# Build the site locally
python main.py --no-extract

# Open site/index.html in a browser (or serve with any static file server)
python -m http.server 8000 --directory site
```

## Deployment

Push to `main` → Netlify auto-deploys. The build command is:

```
pip install -r requirements.txt && python main.py --no-extract
```

To manually trigger a rebuild from the admin dashboard, click **Publish Changes**.

## Supabase schema (key tables)

- **`recipes`** — title, slug, category_id, ingredients (jsonb), instructions (jsonb), notes (jsonb), photo_url, photo_is_stock
- **`categories`** — id, slug, name, sort_order
- **`tags`** — id, slug, label
- **`recipe_tags`** — recipe_id, tag_id (join table)

See the [admin guide](admin-guide.md) for day-to-day content management.
