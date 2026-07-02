'use strict';

/**
 * Netlify Function: import-recipe
 *
 * Accepts a POST from the logged-in admin with a Supabase Storage signed URL
 * pointing to an uploaded recipe file (PDF / image / DOCX / text).
 * Verifies the caller's Supabase session JWT, fetches the file, sends it to
 * Claude for extraction, and returns structured JSON.
 *
 * Required environment variables (server-side only — never in client code):
 *   ANTHROPIC_API_KEY
 *   SUPABASE_URL         (same value as the public env var)
 *   SUPABASE_ANON_KEY    (same value as the public env var)
 *
 * Request body (JSON):
 *   { files: [{signedUrl, mimeType}], categories: [{id,slug,name}], tags: [{id,slug,label}] }
 *   (legacy single-file form: { signedUrl, mimeType, ... } is still accepted)
 *
 * Authorization header: Bearer <supabase_access_token>
 */

const Anthropic      = require('@anthropic-ai/sdk');
const { createClient } = require('@supabase/supabase-js');
const mammoth        = require('mammoth');

const { ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY } = process.env;

const MAX_BYTES       = 10 * 1024 * 1024; // 10 MB — documents
const MAX_IMAGE_BYTES =  7 * 1024 * 1024; //  7 MB — images (base64 inflates ~33%, must stay under Claude's 10 MB API limit)

const JSON_HEADERS = { 'Content-Type': 'application/json' };

// ── Entry point ───────────────────────────────────────────────────────────────

exports.handler = async (event) => {
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 204, headers: JSON_HEADERS, body: '' };
  }
  if (event.httpMethod !== 'POST') {
    return respond(405, { error: 'Method not allowed' });
  }

  // ── 1. Verify session JWT ──────────────────────────────────────────────────
  const rawAuth = event.headers.authorization || event.headers.Authorization || '';
  const token   = rawAuth.replace(/^Bearer\s+/i, '').trim();
  if (!token) return respond(401, { error: 'Missing auth token' });

  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  const { data: { user }, error: authErr } = await supabase.auth.getUser(token);
  if (authErr || !user) {
    return respond(401, { error: 'Invalid or expired session — please log in again.' });
  }

  // ── 2. Parse body ──────────────────────────────────────────────────────────
  let body;
  try { body = JSON.parse(event.body || '{}'); }
  catch { return respond(400, { error: 'Invalid JSON body' }); }

  const { files, signedUrl, mimeType, categories = [], tags = [] } = body;

  // Accept both new multi-file form and legacy single-file form
  const fileList = files && files.length
    ? files
    : (signedUrl && mimeType ? [{ signedUrl, mimeType }] : null);

  if (!fileList) {
    return respond(400, { error: 'files array (or signedUrl + mimeType) is required' });
  }

  // ── 3. Fetch all files and build Claude content blocks ────────────────────
  let contentBlocks = [];
  for (const { signedUrl: url, mimeType: mime } of fileList) {
    let buffer;
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Storage responded ${res.status}`);
      const ab = await res.arrayBuffer();
      const isImg = mime.startsWith('image/');
      const limit = isImg ? MAX_IMAGE_BYTES : MAX_BYTES;
      if (ab.byteLength > limit) {
        const mb = (ab.byteLength / 1024 / 1024).toFixed(1);
        return respond(400, {
          error: isImg
            ? `Photo is ${mb} MB — please use one under 7 MB. On iPhone, share the photo and choose a smaller size before uploading.`
            : `File is ${mb} MB — please use a version under 10 MB.`,
        });
      }
      buffer = Buffer.from(ab);
    } catch (err) {
      return respond(400, { error: `Could not fetch file: ${err.message}` });
    }

    try {
      const blocks = await buildContentBlocks(buffer, mime);
      contentBlocks = contentBlocks.concat(blocks);
    } catch (err) {
      return respond(400, { error: err.message });
    }
  }

  if (!contentBlocks.length) {
    return respond(400, { error: 'No content could be extracted from the uploaded files.' });
  }

  // ── 5. Call Claude ─────────────────────────────────────────────────────────
  if (!ANTHROPIC_API_KEY) {
    return respond(500, { error: 'ANTHROPIC_API_KEY is not configured on the server.' });
  }

  const anthropic = new Anthropic({ apiKey: ANTHROPIC_API_KEY });

  const catList = categories.map(c => c.slug).join(', ') || '(none)';
  const tagList = tags.map(t => t.slug).join(', ')      || '(none)';

  const systemPrompt =
`You are a recipe extraction assistant. Extract the recipe from the provided content and \
return ONLY a valid JSON object — no prose, no markdown fences, no commentary before or after.

Return exactly this shape:
{
  "title": "string",
  "ingredients": ["string", ...],
  "instructions": ["string", ...],
  "notes": ["string", ...],
  "suggested_category": "one slug from the list below, or null",
  "suggested_tags": ["slugs from the list below only"],
  "confidence_flags": ["field names you were uncertain about"]
}

Available category slugs: ${catList}
Available tag slugs: ${tagList}

Rules — ingredients & instructions:
- ingredients, instructions, notes are arrays of plain strings — one item per entry.
- Preserve quantities and units exactly as written; do not convert or round.
- Keep instructions in original order; split into one action per entry where possible.
- Sections: whenever the recipe has a named component (Frosting, Icing, Glaze, Filling, Sauce, Dough, Crust, Topping, Syrup, Ganache, or any other named part), insert a heading entry "## Section Name" at the start of that section in BOTH ingredients and instructions. Use the exact name from the document. Apply this even if the document just uses a bold label or a line like "For the frosting:" — strip the "For the" and use the noun as the heading.

Rules — notes:
- notes captures everything that is NOT a core ingredient or instruction step. Cast a wide net:
  - Explicit tip/note/hint blocks (labelled "Note:", "Tip:", "Cook's note:", etc.)
  - Make-ahead, storage, and freezing guidance
  - Serving suggestions and plating ideas
  - Substitution options ("you can use X instead of Y")
  - Yield, pan size, or altitude adjustments
  - Explanatory asides the author included (e.g. "This is our family's favourite…")
- Each note is one self-contained sentence or short phrase — split compound notes into separate entries.
- Do NOT put cooking steps or timing instructions in notes.

Rules — other:
- Do NOT invent, improve, or add anything absent from the source document.
- Return [] or null for any field that is absent; never guess.
- suggested_category: choose the single best slug from the available list, or null if unsure.
- suggested_tags: only slugs from the available list; empty array if none clearly apply.
- confidence_flags: list field names (e.g. "ingredients", "title") where you were uncertain.`;

  let claudeResp;
  try {
    claudeResp = await anthropic.messages.create({
      model: 'claude-sonnet-4-6',
      max_tokens: 2000,
      system: systemPrompt,
      messages: [{
        role: 'user',
        content: [
          ...contentBlocks,
          { type: 'text', text: 'Extract the recipe and return the JSON object.' },
        ],
      }],
    });
  } catch (err) {
    return respond(502, { error: `Claude API error: ${err.message}` });
  }

  // ── 6. Parse response ──────────────────────────────────────────────────────
  const textBlock = claudeResp.content.find(b => b.type === 'text');
  if (!textBlock) return respond(502, { error: 'Claude returned no text in its response.' });

  let extracted;
  try {
    // Strip any accidental code fences Claude might add despite instructions
    const raw = textBlock.text
      .replace(/^```(?:json)?\s*/i, '')
      .replace(/\s*```\s*$/, '')
      .trim();
    extracted = JSON.parse(raw);
  } catch {
    return respond(502, {
      error: 'Could not parse the extraction result. Try a clearer or higher-quality file.',
    });
  }

  // Normalise arrays so the editor never receives null where it expects []
  extracted.ingredients   = extracted.ingredients   || [];
  extracted.instructions  = extracted.instructions  || [];
  extracted.notes         = extracted.notes         || [];
  extracted.suggested_tags     = extracted.suggested_tags     || [];
  extracted.confidence_flags   = extracted.confidence_flags   || [];

  return respond(200, { recipe: extracted });
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function respond(status, body) {
  return { statusCode: status, headers: JSON_HEADERS, body: JSON.stringify(body) };
}

async function buildContentBlocks(buffer, rawMime) {
  const mime = rawMime.toLowerCase().split(';')[0].trim();

  // PDF — send natively; Claude handles scanned/photographed pages via vision
  if (mime === 'application/pdf') {
    return [{
      type: 'document',
      source: { type: 'base64', media_type: 'application/pdf', data: buffer.toString('base64') },
    }];
  }

  // Images — send natively
  if (['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'].includes(mime)) {
    const mediaType = mime === 'image/jpg' ? 'image/jpeg' : mime;
    return [{
      type: 'image',
      source: { type: 'base64', media_type: mediaType, data: buffer.toString('base64') },
    }];
  }

  // DOCX — extract text with mammoth, send as text block
  if (
    mime === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    mime === 'application/msword'
  ) {
    const { value: text } = await mammoth.extractRawText({ buffer });
    if (!text.trim()) {
      throw new Error('The Word document appears to be empty or image-only. Try exporting it as a PDF.');
    }
    return [{ type: 'text', text }];
  }

  // Plain text / markdown
  if (mime === 'text/plain' || mime === 'text/markdown') {
    return [{ type: 'text', text: buffer.toString('utf-8') }];
  }

  throw new Error(
    `"${rawMime}" is not supported. Please upload a PDF, Word document (.docx), ` +
    `image (JPEG / PNG / WebP), or plain text file.`
  );
}
