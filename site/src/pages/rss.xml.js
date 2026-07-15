import site from '../../../data/derived/site.json';

const esc = (s) =>
  String(s ?? '').replace(/[<>&'"]/g, (c) =>
    ({ '<': '&lt;', '>': '&gt;', '&': '&amp;', "'": '&apos;', '"': '&quot;' })[c]
  );

export async function GET(context) {
  const origin = (context.site?.href || 'http://localhost:4321/').replace(/\/$/, '');
  const base = import.meta.env.BASE_URL.replace(/\/$/, '');
  const items = site.edits
    .filter((e) => e.severity === 'NARRATIVE' || e.severity === 'FACTUAL')
    .slice(0, 50)
    .map((e) => {
      const link = `${origin}${base}/edit/${e.id}/`;
      return `<item>
<title>[${e.severity}] ${esc(e.new_title)}</title>
<link>${link}</link>
<guid isPermaLink="true">${link}</guid>
<pubDate>${new Date(e.detected_at).toUTCString()}</pubDate>
<description>${esc(`${e.source}: ${e.summary || 'silent edit detected'} — original: ${e.url}`)}</description>
</item>`;
    })
    .join('\n');

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
<title>MemoryHole — factual and narrative edits</title>
<link>${origin}${base}/</link>
<description>Silent FACTUAL and NARRATIVE edits detected in published news and official pages</description>
${items}
</channel>
</rss>`;
  return new Response(xml, { headers: { 'Content-Type': 'application/rss+xml' } });
}
