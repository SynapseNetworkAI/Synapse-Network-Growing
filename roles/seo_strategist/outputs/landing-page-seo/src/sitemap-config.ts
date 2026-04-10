/**
 * Synapse Network — XML Sitemap Configuration
 *
 * Use with next-sitemap, vite-plugin-sitemap, or any static-site sitemap generator.
 * Each entry defines a URL, its priority, and change frequency.
 */

import { SITE_BASE } from './seo-config';

export interface SitemapEntry {
  loc: string;
  changefreq: 'daily' | 'weekly' | 'monthly' | 'yearly';
  priority: number;
  lastmod?: string;
}

export const sitemapEntries: SitemapEntry[] = [
  // Core landing pages — highest priority
  { loc: `${SITE_BASE}/`, changefreq: 'weekly', priority: 1.0 },
  { loc: `${SITE_BASE}/developers`, changefreq: 'weekly', priority: 0.9 },
  { loc: `${SITE_BASE}/providers`, changefreq: 'weekly', priority: 0.9 },
  { loc: `${SITE_BASE}/pricing`, changefreq: 'monthly', priority: 0.8 },

  // Comparison pages — high SEO value
  { loc: `${SITE_BASE}/compare/synapse-vs-stripe`, changefreq: 'monthly', priority: 0.8 },
  { loc: `${SITE_BASE}/compare/synapse-vs-rapidapi`, changefreq: 'monthly', priority: 0.8 },

  // Documentation & resources
  { loc: `${SITE_BASE}/docs`, changefreq: 'weekly', priority: 0.7 },
  { loc: `${SITE_BASE}/docs/quickstart`, changefreq: 'weekly', priority: 0.7 },
  { loc: `${SITE_BASE}/docs/sdk/python`, changefreq: 'weekly', priority: 0.6 },
  { loc: `${SITE_BASE}/docs/sdk/typescript`, changefreq: 'weekly', priority: 0.6 },
  { loc: `${SITE_BASE}/docs/mcp-integration`, changefreq: 'monthly', priority: 0.6 },

  // Blog content
  { loc: `${SITE_BASE}/blog`, changefreq: 'weekly', priority: 0.6 },
  { loc: `${SITE_BASE}/blog/mcp-budgeted-tool-use`, changefreq: 'monthly', priority: 0.5 },

  // Legal & trust
  { loc: `${SITE_BASE}/privacy`, changefreq: 'yearly', priority: 0.2 },
  { loc: `${SITE_BASE}/terms`, changefreq: 'yearly', priority: 0.2 },
];

/**
 * Generate raw XML sitemap string.
 * For static builds, write this to `public/sitemap.xml`.
 */
export function generateSitemapXml(
  entries: SitemapEntry[] = sitemapEntries,
): string {
  const urlEntries = entries
    .map(
      (e) => `  <url>
    <loc>${e.loc}</loc>
    <changefreq>${e.changefreq}</changefreq>
    <priority>${e.priority.toFixed(1)}</priority>${
        e.lastmod ? `\n    <lastmod>${e.lastmod}</lastmod>` : ''
      }
  </url>`,
    )
    .join('\n');

  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlEntries}
</urlset>`;
}
