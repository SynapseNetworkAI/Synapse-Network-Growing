/**
 * Synapse Network — JSON-LD Structured Data Templates
 *
 * Generates Schema.org JSON-LD for rich results in Google / Bing / AI search.
 * Inject the output of each function as a <script type="application/ld+json"> block.
 */

import { SITE_BASE, SITE_NAME } from './seo-config';

// ---------------------------------------------------------------------------
// Organization
// ---------------------------------------------------------------------------

export function organizationJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: SITE_NAME,
    url: SITE_BASE,
    logo: `${SITE_BASE}/logo.png`,
    sameAs: [
      'https://twitter.com/SynapseNetwork',
      'https://github.com/Synapse-Network',
    ],
    description:
      'The decentralized settlement layer for AI agent micropayments. Stripe for AI Agents.',
    foundingDate: '2025',
    contactPoint: {
      '@type': 'ContactPoint',
      contactType: 'technical support',
      email: 'support@synapse.network',
      availableLanguage: ['English', 'Chinese'],
    },
  };
}

// ---------------------------------------------------------------------------
// WebSite (enables Google Sitelinks Search Box)
// ---------------------------------------------------------------------------

export function websiteJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: SITE_NAME,
    url: SITE_BASE,
    potentialAction: {
      '@type': 'SearchAction',
      target: {
        '@type': 'EntryPoint',
        urlTemplate: `${SITE_BASE}/docs?q={search_term_string}`,
      },
      'query-input': 'required name=search_term_string',
    },
  };
}

// ---------------------------------------------------------------------------
// SoftwareApplication (the SDK / Platform product)
// ---------------------------------------------------------------------------

export function softwareApplicationJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'SoftwareApplication',
    name: 'Synapse Network SDK',
    applicationCategory: 'DeveloperApplication',
    operatingSystem: 'Cross-platform',
    offers: {
      '@type': 'Offer',
      price: '0',
      priceCurrency: 'USD',
      description: 'Free SDK. 5% network fee per API transaction.',
    },
    description:
      'Python & TypeScript SDK for AI agents to discover, invoke, and pay for APIs via MCP with USDC micropayments.',
    url: `${SITE_BASE}/developers`,
    downloadUrl: 'https://pypi.org/project/synapse-sdk/',
    softwareVersion: '0.1.0',
    author: {
      '@type': 'Organization',
      name: SITE_NAME,
    },
    featureList: [
      'Budget isolation per agent task',
      'Zero-gas USDC micropayments',
      'MCP-native service discovery',
      'Wallet-first identity',
      'LangChain / CrewAI / OpenAI Agents SDK support',
    ],
  };
}

// ---------------------------------------------------------------------------
// FAQPage — high-value for rich snippets
// ---------------------------------------------------------------------------

export interface FAQItem {
  question: string;
  answer: string;
}

export const landingPageFAQs: FAQItem[] = [
  {
    question: 'What is Synapse Network?',
    answer:
      'Synapse Network is a decentralized settlement layer that lets AI agents autonomously discover, invoke, and pay for API services with USDC micropayments as low as $0.01 — without gas fees or human intervention.',
  },
  {
    question: 'How does budget isolation work?',
    answer:
      'You allocate a fixed USDC budget (e.g., $5.00) per agent task via the SDK. The budget is cryptographically locked so the agent cannot overspend. When the budget is exhausted, the agent stops. Unspent funds are retained.',
  },
  {
    question: 'What frameworks does Synapse support?',
    answer:
      'Synapse provides Python and TypeScript SDKs with native MCP (Model Context Protocol) support. It integrates with LangChain, CrewAI, AutoGen, and OpenAI Agents SDK out of the box.',
  },
  {
    question: 'How much does Synapse cost?',
    answer:
      'The SDK is free. Synapse charges a 5% network fee on each API transaction. There are no subscriptions, no minimum fees, and no gas costs. Providers set their own per-call prices.',
  },
  {
    question: 'How is Synapse different from Stripe?',
    answer:
      "Stripe's $0.30 minimum per-transaction fee makes micropayments economically impossible. Synapse uses off-chain state channels to enable $0.01 API calls with zero gas, purpose-built for machine-to-machine commerce.",
  },
  {
    question: 'How do API providers earn money on Synapse?',
    answer:
      'Providers list their API, set a per-call price, and earn USDC every time an AI agent invokes their endpoint. Revenue share is 95% to the provider. Settlement is instant via state channels.',
  },
];

export function faqPageJsonLd(faqs: FAQItem[] = landingPageFAQs) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: faqs.map((faq) => ({
      '@type': 'Question',
      name: faq.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: faq.answer,
      },
    })),
  };
}

// ---------------------------------------------------------------------------
// BreadcrumbList — pass an array of {name, url} pairs
// ---------------------------------------------------------------------------

export function breadcrumbJsonLd(
  items: { name: string; url: string }[],
) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };
}

// ---------------------------------------------------------------------------
// HowTo — "Get Started in 3 Steps" (rich snippet potential)
// ---------------------------------------------------------------------------

export function howToGetStartedJsonLd() {
  return {
    '@context': 'https://schema.org',
    '@type': 'HowTo',
    name: 'Get Started with Synapse Network in 3 Steps',
    description:
      'Connect your AI agent to the Synapse payment network and make your first paid API call.',
    step: [
      {
        '@type': 'HowToStep',
        position: 1,
        name: 'Install the SDK',
        text: 'pip install synapse-sdk',
        url: `${SITE_BASE}/developers#install`,
      },
      {
        '@type': 'HowToStep',
        position: 2,
        name: 'Create an Agent Wallet',
        text: 'wallet = AgentWallet.connect(budget=5.0)  # lock $5 USDC',
        url: `${SITE_BASE}/developers#wallet`,
      },
      {
        '@type': 'HowToStep',
        position: 3,
        name: 'Run Your Agent',
        text: 'agent.run(tools=[wallet.mcp_tool(...)])  # agent discovers & pays',
        url: `${SITE_BASE}/developers#run`,
      },
    ],
    totalTime: 'PT3M',
  };
}

// ---------------------------------------------------------------------------
// Helper: serialize any schema to a <script> tag string
// ---------------------------------------------------------------------------

export function toScriptTag(schema: Record<string, unknown>): string {
  return `<script type="application/ld+json">${JSON.stringify(schema, null, 2)}</script>`;
}
