/**
 * Shared Supabase client and auth utilities for the admin SPA.
 * Loaded by every admin page.  config.js is generated at build time and
 * provides window.ADMIN_EMAIL and window.NETLIFY_BUILD_HOOK.
 *
 * Security model:
 *   - SUPABASE_ANON_KEY is public by design (Supabase documentation).
 *   - Actual write protection is enforced by Row Level Security in Postgres —
 *     the anon role can only SELECT; INSERT/UPDATE/DELETE require an
 *     authenticated session.
 *   - The password is never stored in code or in this repo.
 */

const SUPABASE_URL      = 'https://jiouygrsqxbhtapyffbm.supabase.co';
const SUPABASE_ANON_KEY = 'sb_publishable_REjkQ00uDAp_laGS6rYsmA_KBnDkiv9';

const { createClient } = supabase;
const db = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ── Auth helpers ──────────────────────────────────────────────────────────────

/** Redirect to /admin/login/ if not authenticated; returns session otherwise. */
async function requireAuth() {
  const { data: { session } } = await db.auth.getSession();
  if (!session) {
    window.location.replace('/admin/login/');
    throw new Error('unauthenticated');
  }
  return session;
}

async function logout() {
  await db.auth.signOut();
  window.location.replace('/admin/login/');
}

// Auto-redirect to login on session expiry
db.auth.onAuthStateChange((event) => {
  if (event === 'SIGNED_OUT') window.location.replace('/admin/login/');
});

// ── UI helpers ────────────────────────────────────────────────────────────────

function showBanner(msg, type = 'error') {
  const el = document.getElementById('admin-banner');
  if (!el) return;
  el.textContent = msg;
  el.className = 'admin-banner admin-banner--' + type;
  el.style.display = 'block';
  if (type === 'success') setTimeout(() => { el.style.display = 'none'; }, 3500);
}

function hideBanner() {
  const el = document.getElementById('admin-banner');
  if (el) el.style.display = 'none';
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Netlify rebuild trigger ───────────────────────────────────────────────────

async function triggerRebuild(btn) {
  const hook = window.NETLIFY_BUILD_HOOK;
  if (!hook) {
    showBanner('NETLIFY_BUILD_HOOK is not configured — set it in your .env and rebuild.', 'error');
    return;
  }
  if (btn) { btn.disabled = true; btn.textContent = 'Triggering…'; }
  try {
    await fetch(hook, { method: 'POST' });
    showBanner('Build triggered! Public site updates in ~1 minute.', 'success');
  } catch {
    showBanner('Could not reach Netlify — check your build hook URL.', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Publish Changes'; }
  }
}
