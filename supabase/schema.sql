-- ============================================================
-- Julie's Family Recipes — Supabase schema
-- Run this in the Supabase SQL editor (Project → SQL editor → New query)
-- ============================================================

-- ── Tables ───────────────────────────────────────────────────

create table if not exists categories (
  id          uuid primary key default gen_random_uuid(),
  slug        text unique not null,
  name        text not null,
  sort_order  integer not null default 0,
  created_at  timestamptz default now()
);

create table if not exists recipes (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  category_id uuid references categories(id) on delete set null,
  ingredients jsonb not null default '[]'::jsonb,
  instructions jsonb not null default '[]'::jsonb,
  notes       jsonb not null default '[]'::jsonb,
  photo_url   text,
  slug        text unique not null,
  source_file text,
  created_at  timestamptz default now(),
  updated_at  timestamptz default now()
);

create table if not exists tags (
  id    uuid primary key default gen_random_uuid(),
  slug  text unique not null,
  label text not null
);

create table if not exists recipe_tags (
  recipe_id uuid not null references recipes(id) on delete cascade,
  tag_id    uuid not null references tags(id)    on delete cascade,
  primary key (recipe_id, tag_id)
);

-- ── updated_at trigger ───────────────────────────────────────

create or replace function _update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists recipes_updated_at on recipes;
create trigger recipes_updated_at
  before update on recipes
  for each row execute function _update_updated_at();

-- ── Row Level Security ───────────────────────────────────────
--
-- Real security gate: anon users can only read.
-- Authenticated users (the admin) can read + write.
-- Nav-hiding in the UI is cosmetic; RLS is the actual enforcement.

alter table categories  enable row level security;
alter table recipes     enable row level security;
alter table tags        enable row level security;
alter table recipe_tags enable row level security;

-- SELECT open to all (public site needs to read)
create policy "read categories"  on categories  for select using (true);
create policy "read recipes"     on recipes     for select using (true);
create policy "read tags"        on tags        for select using (true);
create policy "read recipe_tags" on recipe_tags for select using (true);

-- Writes only for authenticated admin session
create policy "admin write categories"  on categories  for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "admin write recipes"     on recipes     for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "admin write tags"        on tags        for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

create policy "admin write recipe_tags" on recipe_tags for all
  using (auth.role() = 'authenticated')
  with check (auth.role() = 'authenticated');

-- ── Seed data ────────────────────────────────────────────────

insert into categories (slug, name, sort_order) values
  ('appetizers',                  'Appetizers',                  1),
  ('bread',                       'Bread',                       2),
  ('cookies',                     'Cookies',                     3),
  ('desserts',                    'Desserts',                    4),
  ('main-dishes',                 'Main Dishes',                 5),
  ('salads',                      'Salads',                      6),
  ('vegetables-and-side-dishes',  'Vegetables and Side Dishes',  7)
on conflict (slug) do nothing;

insert into tags (slug, label) values
  ('easy',         'Easy'),
  ('vegetarian',   'Vegetarian'),
  ('gluten-free',  'Gluten-Free'),
  ('dairy-free',   'Dairy-Free'),
  ('vegan',        'Vegan'),
  ('quick',        'Quick'),
  ('make-ahead',   'Make-Ahead'),
  ('kid-friendly', 'Kid-Friendly'),
  ('holiday',      'Holiday')
on conflict (slug) do nothing;

-- ── Storage ──────────────────────────────────────────────────
--
-- After running this SQL, create the storage bucket manually:
--   Supabase dashboard → Storage → New bucket
--   Name: recipe-photos
--   Public bucket: YES (photos are publicly readable)
--
-- Then add a storage policy:
--   Allowed operation: INSERT, UPDATE, DELETE
--   Target roles: authenticated
--   Policy name: "admin upload photos"
--
-- ── Auth setup ───────────────────────────────────────────────
--
-- 1. In Supabase dashboard → Authentication → Users → Add user
--    Email: your-admin-email@example.com  (set ADMIN_EMAIL env var to match)
--    Password: theridge  ← CHANGE THIS in the dashboard after first login
-- 2. In Authentication → Settings → disable "Enable email confirmations"
--    so you can log in immediately without verifying the email.
-- 3. Optionally disable "Enable Signups" to prevent others from registering.
