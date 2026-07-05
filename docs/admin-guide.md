# Admin Guide — JoLene's Family Recipes

This guide covers everything you need to manage recipes on the site.

---

## Table of contents

1. [Signing in](#signing-in)
2. [The admin dashboard](#the-admin-dashboard)
3. [Adding a recipe manually](#adding-a-recipe-manually)
4. [Importing a recipe from a photo or document](#importing-a-recipe-from-a-photo-or-document)
5. [Editing a recipe](#editing-a-recipe)
6. [Managing tags](#managing-tags)
7. [Moving a recipe to a different category](#moving-a-recipe-to-a-different-category)
8. [Deleting a recipe](#deleting-a-recipe)
9. [Publishing changes](#publishing-changes)

---

## Signing in

1. Go to `/admin/login/` or click **Sign in** in the top navigation bar.
2. Enter the admin email and password. (These are set in the `.env` file / Netlify environment variables and are never stored in the code.)
3. You are redirected to the admin dashboard on success.

Your session stays active until you log out or it expires. If you are logged in, the navigation bar shows **Admin** instead of Sign in.

---

## The admin dashboard

The dashboard (`/admin/`) lists all recipes grouped by category.

**Toolbar features:**

| Control | What it does |
|---|---|
| Search box | Filters recipes by title as you type — no need to press Enter |
| Category dropdown | Narrows the list to one category |
| **+ Add Recipe** button | Opens a modal to create a new recipe |
| **↑ Import** link | Goes to the import page to extract a recipe from a photo or document |

**Counts:** Each category heading shows how many recipes are visible given your current search/filter.

**Empty states:**
- "No recipes match your search." — clear your search/filter to see all recipes.
- "No recipes yet — add one to get started." — no recipes exist in the database yet.

---

## Adding a recipe manually

1. Click **+ Add Recipe** in the toolbar.
2. Enter a title and choose a category. Click **Create**.
3. You land on the recipe editor. Fill in ingredients, instructions, notes, and optionally upload a photo.
4. Click **Save** when done.
5. Click **Publish Changes** in the top bar to rebuild the public site.

---

## Importing a recipe from a photo or document

The import tool uses Claude AI to extract recipe text automatically.

**Supported file types:** JPEG, PNG, WebP, PDF, Word document (.docx), plain text

**Multi-photo support:** If a recipe spans multiple pages, you can select several photos at once. The tool combines them into one import.

**Large photos:** iPhone photos and other large images are automatically compressed before sending. You do not need to resize them manually.

### Steps

1. Click **↑ Import** from the dashboard toolbar.
2. Click **Choose files** and select one or more files (photos, PDFs, or documents).
3. Click **Import Recipe**. Large photos are compressed automatically and the button shows "Compressing…" while this happens.
4. Review the extracted recipe. Fields are pre-filled — correct anything that looks wrong.
5. Choose the right category and adjust the title if needed.
6. Click **Save**.
7. Click **Publish Changes** to push the recipe to the public site.

**Tips:**
- Clear, well-lit photos work best. Avoid heavy shadows across the text.
- If a recipe is on two pages, select both photos in one import rather than importing them separately.
- Handwritten recipes can work but may need more manual correction.

---

## Editing a recipe

Click a recipe title in the dashboard to open the recipe editor (`/admin/recipe/?id=…`).

**Fields you can edit:**

| Field | Notes |
|---|---|
| Title | The name shown on the site |
| Category | Also changeable from the dashboard dropdown |
| Ingredients | One item per line. Use `## Section Name` on its own line to create a labeled section (e.g., `## Frosting`) |
| Instructions | One step per line. Use `## Section Name` to match a section in the ingredients |
| Notes | Tips, substitutions, storage instructions, make-ahead guidance — one note per line |
| Photo | Upload a new photo (JPEG or PNG). Large photos are compressed automatically |
| Photo is stock | Check this if the photo is a generic/stock image rather than a photo of the actual dish |

Click **Save** to write changes to the database. Changes do not appear on the public site until you click **Publish Changes**.

---

## Managing tags

Tags appear as filter chips on category pages and on individual recipe pages (e.g., *Easy*, *Make-ahead*, *Vegetarian*).

**From the dashboard:**
- Each recipe row shows its current tags as chips.
- Click **+ tag** on any recipe row to add a tag from the available list.
- Click **×** on a tag chip to remove it.

**Available tags** (defined in the database):
`vegetarian` · `vegan` · `dairy-free` · `gluten-free` · `nut-free` · `egg-free` · `easy` · `quick` · `make-ahead` · `kid-friendly` · `holiday` · `no-bake` · `one-pot` · `slow-cooker` · `grill-bbq` · `freezer-friendly` · `5-ingredients` · `spicy` · `comfort-food` · `potluck`

To add new tags to the available list, insert a row into the `tags` table in Supabase with a `slug` and `label`.

---

## Moving a recipe to a different category

From the dashboard, find the recipe row and change its category using the dropdown on that row. The change saves immediately.

You can also change the category inside the recipe editor.

---

## Deleting a recipe

1. Open the recipe editor by clicking its title from the dashboard.
2. Scroll to the bottom and click **Delete Recipe**.
3. Confirm the deletion in the prompt.

If you opened a new recipe that has never been saved, clicking Delete will take you back to the dashboard without deleting anything.

> **Note:** Deletion is permanent. The recipe is removed from the database. Its photo URL is removed but the photo file in Supabase Storage is not automatically deleted.

---

## Publishing changes

Any change — adding, editing, or deleting a recipe — only affects the database. The public site is static HTML rebuilt from the database. To push changes live:

1. Click **Publish Changes** in the top bar of the admin dashboard or recipe editor.
2. Netlify triggers a new build. The public site updates within about 60–90 seconds.

If the button shows an error about `NETLIFY_BUILD_HOOK`, the build hook URL needs to be added to the Netlify environment variables. See the [project README](README.md) for setup instructions.
