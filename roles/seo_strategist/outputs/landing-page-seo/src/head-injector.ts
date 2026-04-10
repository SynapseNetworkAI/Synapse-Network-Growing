/**
 * Synapse Network — SEO Head HTML Generator
 *
 * Generates all SEO-critical <head> elements as an HTML string.
 * Designed for server-side rendering (SSR) or static site generation (SSG).
 *
 * Integration examples:
 *
 *   // Next.js (app router) — use metadata API or inject in layout.tsx
 *   // Astro — inject directly into <head> in your .astro layout
 *   // Vite SSR — inject into the HTML template string
 *
 *   import { generateHeadHTML } from './head-injector';
 *   const html = generateHeadHTML({ pageKey: 'home', includeFAQ: true, includeHowTo: true });
 *   // Insert `html` into your document's <head> during SSR/SSG build.
 */

import { getHeadMeta } from './seo-config';
import {
  organizationJsonLd,
  websiteJsonLd,
  softwareApplicationJsonLd,
  faqPageJsonLd,
  howToGetStartedJsonLd,
  breadcrumbJsonLd,
  toScriptTag,
} from './structured-data';

export interface HeadOptions {
  pageKey: string;
  /** Include FAQ schema on this page */
  includeFAQ?: boolean;
  /** Include HowTo schema on this page */
  includeHowTo?: boolean;
  /** Breadcrumb items for this page */
  breadcrumbs?: { name: string; url: string }[];
}

/**
 * Generates all SEO-critical <head> elements as an HTML string.
 *
 * IMPORTANT: Inject the returned string into your document's <head> element
 * during SSR or SSG. Do NOT render this in the <body> — search engines
 * expect meta tags, canonical links, and JSON-LD in the <head>.
 */
export function generateHeadHTML(options: HeadOptions): string {
  const { pageKey, includeFAQ = false, includeHowTo = false, breadcrumbs } = options;
  const head = getHeadMeta(pageKey);

  const lines: string[] = [];

  // Title
  lines.push(`<title>${head.title}</title>`);

  // Meta tags
  for (const m of head.meta) {
    if ('property' in m) {
      lines.push(`<meta property="${m.property}" content="${escapeAttr(m.content)}" />`);
    } else {
      lines.push(`<meta name="${m.name}" content="${escapeAttr(m.content)}" />`);
    }
  }

  // Link tags (canonical, hreflang)
  for (const l of head.link) {
    const attrs = Object.entries(l)
      .map(([k, v]: [string, unknown]) => `${k}="${escapeAttr(String(v))}"`)
      .join(' ');
    lines.push(`<link ${attrs} />`);
  }

  // Structured data — always include Organization + WebSite on all pages
  lines.push(toScriptTag(organizationJsonLd()));
  lines.push(toScriptTag(websiteJsonLd()));

  // Page-specific structured data
  if (pageKey === 'home' || pageKey === 'developers') {
    lines.push(toScriptTag(softwareApplicationJsonLd()));
  }

  if (includeFAQ) {
    lines.push(toScriptTag(faqPageJsonLd()));
  }

  if (includeHowTo) {
    lines.push(toScriptTag(howToGetStartedJsonLd()));
  }

  if (breadcrumbs && breadcrumbs.length > 0) {
    lines.push(toScriptTag(breadcrumbJsonLd(breadcrumbs)));
  }

  return lines.join('\n');
}

function escapeAttr(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
