'use strict';

/**
 * Scheduled function — runs daily to prevent Supabase free-tier pausing.
 * Schedule is declared in netlify.toml.
 */

exports.handler = async () => {
  const url = (process.env.SUPABASE_URL || '').replace(/\/$/, '');
  const key  = process.env.SUPABASE_ANON_KEY || '';

  if (!url || !key) {
    console.error('supabase-ping: SUPABASE_URL or SUPABASE_ANON_KEY not set');
    return { statusCode: 500, body: 'Missing env vars' };
  }

  try {
    const res = await fetch(`${url}/rest/v1/categories?limit=1`, {
      headers: {
        'apikey':        key,
        'Authorization': `Bearer ${key}`,
      },
    });
    console.log(`supabase-ping: ${res.status}`);
    return { statusCode: 200, body: 'ok' };
  } catch (err) {
    console.error('supabase-ping failed:', err.message);
    return { statusCode: 500, body: err.message };
  }
};
