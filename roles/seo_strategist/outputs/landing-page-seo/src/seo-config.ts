/**
 * Synapse Network — Landing Page SEO Configuration
 *
 * Centralised per-page meta tags, Open Graph, Twitter Cards, and canonical URLs.
 * Import into your <head> renderer (Next.js Head / React Helmet / Vite SSR).
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PageSEO {
  /** Unique page key used for lookup */
  slug: string;
  /** <title> tag — 50-60 chars, primary keyword near front */
  title: string;
  /** <meta name="description"> — 150-160 chars */
  description: string;
  /** Canonical path relative to SITE_BASE (no trailing slash) */
  canonical: string;
  /** Open Graph type */
  ogType: 'website' | 'article' | 'product';
  /** Optional OG image override (absolute URL) */
  ogImage?: string;
  /** Primary target keyword for this page */
  primaryKeyword: string;
  /** Secondary keywords (used in content, not stuffed into meta) */
  secondaryKeywords: string[];
  /** Robots directive override — default "index, follow" */
  robots?: string;
  /** hreflang alternates if the page has i18n variants */
  hreflang?: { lang: string; href: string }[];
}

// ---------------------------------------------------------------------------
// Site-wide constants
// ---------------------------------------------------------------------------

export const SITE_BASE = 'https://synapse.network';
export const DEFAULT_OG_IMAGE = `${SITE_BASE}/og/synapse-og-default.png`;
export const TWITTER_HANDLE = '@SynapseNetwork';
export const SITE_NAME = 'Synapse Network';

// ---------------------------------------------------------------------------
// Per-page SEO definitions — Landing Pages
// ---------------------------------------------------------------------------

export const pages: Record<string, PageSEO> = {
  home: {
    slug: 'home',
    title: 'Synapse Network — The Settlement Layer for AI Agents',
    description:
      'Let AI agents discover, invoke, and pay for APIs with zero-gas micropayments. Budget isolation, MCP-native discovery, wallet-first identity. The Stripe for AI Agents.',
    canonical: '',
    ogType: 'website',
    primaryKeyword: 'AI agent payment API',
    secondaryKeywords: [
      'AI agent micropayments',
      'machine-to-machine payments',
      'MCP agent tools',
      'agent budget isolation',
      'Stripe for AI agents',
    ],
  },

  developers: {
    slug: 'developers',
    title: 'Synapse SDK for AI Agent Developers — 3 Lines to Pay-Per-Call',
    description:
      'Integrate Synapse into LangChain, CrewAI, or OpenAI Agents in 3 lines. Give your agent a fixed USDC budget, let it discover APIs via MCP, and pay per call with zero gas.',
    canonical: '/developers',
    ogType: 'website',
    primaryKeyword: 'AI agent SDK',
    secondaryKeywords: [
      'LangChain payment integration',
      'CrewAI tool payments',
      'agent wallet SDK',
      'MCP tool discovery',
      'AI agent API billing',
    ],
  },

  providers: {
    slug: 'providers',
    title: 'Monetize Your API in the Agent Economy — Synapse Provider',
    description:
      'List your API on Synapse Network. Set your price, earn USDC every time an AI agent calls your endpoint. 95% revenue share, zero-gas settlement.',
    canonical: '/providers',
    ogType: 'website',
    primaryKeyword: 'monetize API AI agents',
    secondaryKeywords: [
      'API marketplace AI',
      'sell API to AI agents',
      'API monetization platform',
      'USDC API payments',
      'machine-to-machine API marketplace',
    ],
  },

  pricing: {
    slug: 'pricing',
    title: 'Synapse Network Pricing — Zero-Gas Micropayments from $0.01',
    description:
      'No subscription fees. No minimum transaction. Synapse charges a 5% network fee per API call. Providers set their own price. Agents pay in USDC.',
    canonical: '/pricing',
    ogType: 'website',
    primaryKeyword: 'AI agent API pricing',
    secondaryKeywords: [
      'micropayment API pricing',
      'zero gas fee payments',
      'USDC API settlement cost',
      'M2M transaction pricing',
    ],
  },

  'vs-stripe': {
    slug: 'vs-stripe',
    title: 'Synapse vs Stripe — Why Stripe Fails for AI Agent Payments',
    description:
      'Stripe charges $0.30 minimum per transaction, killing micropayments. Synapse enables $0.01 API calls with zero gas. Built for M2M, not H2M.',
    canonical: '/compare/synapse-vs-stripe',
    ogType: 'article',
    primaryKeyword: 'Synapse vs Stripe',
    secondaryKeywords: [
      'Stripe alternative AI agents',
      'micropayment alternative to Stripe',
      'AI agent payment gateway',
    ],
  },

  'vs-rapidapi': {
    slug: 'vs-rapidapi',
    title: 'Synapse vs RapidAPI — Agent-Native API Marketplace',
    description:
      'RapidAPI is built for humans browsing catalogs. Synapse is built for AI agents that discover and pay for APIs autonomously via MCP.',
    canonical: '/compare/synapse-vs-rapidapi',
    ogType: 'article',
    primaryKeyword: 'Synapse vs RapidAPI',
    secondaryKeywords: [
      'RapidAPI alternative for agents',
      'AI-native API marketplace',
      'MCP API discovery',
    ],
  },
};

// ---------------------------------------------------------------------------
// Helper: generate <head> meta tag attributes for a given page
// ---------------------------------------------------------------------------

export function getHeadMeta(pageKey: string) {
  const page = pages[pageKey];
  if (!page) throw new Error(`Unknown SEO page key: ${pageKey}`);

  const canonicalUrl = `${SITE_BASE}${page.canonical}`;
  const ogImage = page.ogImage ?? DEFAULT_OG_IMAGE;

  return {
    title: page.title,
    meta: [
      { name: 'description', content: page.description },
      { name: 'robots', content: page.robots ?? 'index, follow' },

      // Open Graph
      { property: 'og:title', content: page.title },
      { property: 'og:description', content: page.description },
      { property: 'og:type', content: page.ogType },
      { property: 'og:url', content: canonicalUrl },
      { property: 'og:image', content: ogImage },
      { property: 'og:site_name', content: SITE_NAME },

      // Twitter Card
      { name: 'twitter:card', content: 'summary_large_image' },
      { name: 'twitter:site', content: TWITTER_HANDLE },
      { name: 'twitter:title', content: page.title },
      { name: 'twitter:description', content: page.description },
      { name: 'twitter:image', content: ogImage },
    ],
    link: [
      { rel: 'canonical', href: canonicalUrl },
      ...(page.hreflang ?? []).map((h) => ({
        rel: 'alternate',
        hreflang: h.lang,
        href: h.href,
      })),
    ],
  };
}
