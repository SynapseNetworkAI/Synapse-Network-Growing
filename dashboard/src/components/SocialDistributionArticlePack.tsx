import type { SocialDistributionDocument } from '../apiSocialDistribution'
import { StateBadge, copyText } from './SocialDistributionWidgets'
import type { useToast } from './workbench'

interface ArticlePackObject {
  [key: string]: unknown
}

interface MediaManifestItem {
  kind: 'cover' | 'image' | 'gif' | string
  label: string
  placement_after_heading: string
  local_path: string
  target_url: string
  status: string
  dimensions: string
  flow: string
}

interface MarkdownBlock {
  heading: string | null
  lines: string[]
}

export function ArticlePackSection({
  doc,
  toast,
}: {
  doc: SocialDistributionDocument
  toast: ReturnType<typeof useToast>
}) {
  const checklist = stringArray(doc.metadata.manual_publish_checklist)
  const xArticlesUrl = stringValue(doc.metadata.x_articles_url) || 'https://x.com/compose/articles'
  const mediaManifest = mediaManifestItems(doc.metadata)
  const cover = mediaManifest.find((item) => item.kind === 'cover')
  const inlineMedia = mediaManifest.filter((item) => item.kind !== 'cover')
  const blocks = markdownBlocks(doc.body_markdown)
  const fullArticleCopy = articleCopyText(doc.title, doc.body_markdown, mediaManifest)
  const manifestCopy = mediaManifestCopy(mediaManifest)

  return (
    <section className="rounded-3xl border border-emerald-300/25 bg-emerald-300/5 p-4 shadow-[0_18px_80px_rgba(16,185,129,0.08)]">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] uppercase tracking-[0.2em] text-emerald-100/80">Long-form Article Preview</div>
          <h3 className="mt-2 text-xl font-semibold text-[color:var(--ops-text-title)]">{doc.title}</h3>
          <p className="mt-1 text-sm text-[color:var(--ops-text-muted)]">
            X Article 手动发布包：封面、正文和图片/GIF 插入位置都集中在这个内容框里。
          </p>
        </div>
        <StateBadge tone="ready">Manual X Article</StateBadge>
      </div>

      <div className="overflow-hidden rounded-3xl border border-[color:var(--ops-stroke-soft)] bg-[color:var(--ops-panel-strong)]">
        <CoverPreview cover={cover} title={doc.title} />
        <article className="space-y-5 p-5">
          {blocks.map((block, index) => (
            <ArticleBlock
              key={`${block.heading ?? 'intro'}-${index}`}
              block={block}
              media={inlineMedia.filter((item) => normalizeHeading(item.placement_after_heading) === normalizeHeading(block.heading))}
            />
          ))}
          {inlineMedia.filter((item) => !item.placement_after_heading || item.placement_after_heading === 'end').map((item, index) => (
            <MediaSlot key={`${item.kind}-${item.label}-${index}`} item={item} />
          ))}
        </article>
      </div>

      {checklist.length ? (
        <div className="mt-4 rounded-2xl border border-[color:var(--ops-stroke-soft)] bg-black/10 p-4">
          <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-[color:var(--ops-text-caption)]">Manual publish checklist</div>
          <div className="grid gap-2 text-sm text-[color:var(--ops-text-body)]">
            {checklist.map((item, index) => (
              <div key={`${index}-${item}`} className="rounded-xl border border-[color:var(--ops-stroke-soft)] px-3 py-2">
                {index + 1}. {item}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => copyText(fullArticleCopy, toast)}>
          复制完整 Article
        </button>
        <button type="button" className="rounded-xl border border-cyan-300/40 px-3 py-2 text-sm text-cyan-100" onClick={() => copyText(manifestCopy, toast)}>
          复制素材清单
        </button>
        <a className="rounded-xl border border-emerald-300/50 px-3 py-2 text-sm font-semibold text-emerald-100" href={xArticlesUrl} target="_blank" rel="noreferrer">
          打开 X Articles
        </a>
      </div>
    </section>
  )
}

function CoverPreview({ cover, title }: { cover: MediaManifestItem | undefined; title: string }) {
  return (
    <div className="border-b border-[color:var(--ops-stroke-soft)] bg-[radial-gradient(circle_at_15%_20%,rgba(45,212,191,0.18),transparent_32%),linear-gradient(135deg,rgba(2,6,23,0.96),rgba(20,20,20,0.9))] p-5">
      <div className="flex min-h-[220px] flex-col justify-end rounded-2xl border border-emerald-200/20 bg-black/30 p-5">
        <div className="text-[11px] uppercase tracking-[0.2em] text-emerald-100/70">Cover image</div>
        <h4 className="mt-3 max-w-2xl text-3xl font-semibold leading-tight text-white">{title}</h4>
        <MediaEvidence item={cover} compact />
      </div>
    </div>
  )
}

function ArticleBlock({ block, media }: { block: MarkdownBlock; media: MediaManifestItem[] }) {
  return (
    <section className="space-y-3">
      {block.heading ? <h4 className="text-lg font-semibold text-[color:var(--ops-text-title)]">{block.heading}</h4> : null}
      <div className="space-y-3 text-sm leading-7 text-[color:var(--ops-text-body)]">
        {block.lines.length ? block.lines.map((line, index) => <MarkdownLine key={`${index}-${line}`} line={line} />) : null}
      </div>
      {media.map((item, index) => <MediaSlot key={`${item.kind}-${item.label}-${index}`} item={item} />)}
    </section>
  )
}

function MarkdownLine({ line }: { line: string }) {
  const trimmed = line.trim()
  if (!trimmed) return null
  if (/^[-*]\s+/.test(trimmed)) {
    return <p className="pl-4 before:mr-2 before:text-emerald-200 before:content-['•']">{trimmed.replace(/^[-*]\s+/, '')}</p>
  }
  if (/^\d+\.\s+/.test(trimmed)) {
    return <p className="pl-4 font-mono text-xs text-[color:var(--ops-text-muted)]">{trimmed}</p>
  }
  return <p>{trimmed}</p>
}

function MediaSlot({ item }: { item: MediaManifestItem }) {
  const slotLabel = item.kind === 'gif' ? 'GIF slot' : 'Image slot'
  return (
    <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/5 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] uppercase tracking-[0.18em] text-cyan-100/80">{slotLabel}</div>
          <div className="mt-1 font-semibold text-[color:var(--ops-text-title)]">{item.label || item.kind}</div>
        </div>
        <StateBadge tone={item.local_path ? 'ready' : 'validating'}>{item.local_path ? item.status || 'captured' : 'Not captured yet'}</StateBadge>
      </div>
      <MediaEvidence item={item} />
    </div>
  )
}

function MediaEvidence({ item, compact = false }: { item: MediaManifestItem | undefined; compact?: boolean }) {
  if (!item) {
    return <div className="mt-3 text-sm text-[color:var(--ops-text-caption)]">Not captured yet.</div>
  }
  const rows = [
    item.local_path ? ['File', item.local_path] : ['Status', 'Not captured yet'],
    item.dimensions ? ['Dimensions', item.dimensions] : null,
    item.placement_after_heading ? ['Placement', item.placement_after_heading] : null,
    item.target_url ? ['Target', item.target_url] : null,
    item.flow ? ['GIF flow', item.flow] : null,
  ].filter(Boolean) as [string, string][]
  return (
    <div className={`mt-3 grid gap-2 ${compact ? 'text-xs' : 'text-sm'} text-[color:var(--ops-text-caption)]`}>
      {rows.map(([label, value]) => (
        <div key={`${label}-${value}`} className="grid gap-1 rounded-xl border border-white/10 bg-black/20 px-3 py-2 md:grid-cols-[110px_minmax(0,1fr)]">
          <span className="uppercase tracking-[0.14em]">{label}</span>
          {isHttpUrl(value) ? (
            <a className="break-all font-mono text-cyan-100" href={value} target="_blank" rel="noreferrer">{value}</a>
          ) : (
            <span className="break-all font-mono text-cyan-100">{value}</span>
          )}
        </div>
      ))}
    </div>
  )
}

function mediaManifestItems(metadata: Record<string, unknown>): MediaManifestItem[] {
  const manifest = recordArray(metadata.media_manifest)
  if (manifest.length) return manifest.map(mediaItem).filter((item) => item.kind)
  const cover = recordValue(metadata.cover_image)
  const inlineImages = recordArray(metadata.inline_images)
  const inlineGifs = recordArray(metadata.inline_gifs)
  return [
    mediaItem({
      kind: 'cover',
      label: 'Article cover',
      placement_after_heading: 'top',
      local_path: cover.local_path,
      status: cover.local_path ? 'generated' : 'missing',
      dimensions: cover.width && cover.height ? `${cover.width}x${cover.height}` : '',
    }),
    ...inlineImages.map((item) => mediaItem({ kind: 'image', status: 'pending_capture', ...item })),
    ...inlineGifs.map((item) => mediaItem({ kind: 'gif', status: 'pending_capture', ...item })),
  ].filter((item) => item.kind)
}

function mediaItem(value: ArticlePackObject): MediaManifestItem {
  return {
    kind: stringValue(value.kind),
    label: stringValue(value.label),
    placement_after_heading: stringValue(value.placement_after_heading),
    local_path: stringValue(value.local_path),
    target_url: stringValue(value.target_url),
    status: stringValue(value.status),
    dimensions: stringValue(value.dimensions),
    flow: stringValue(value.flow),
  }
}

function markdownBlocks(markdown: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = []
  let current: MarkdownBlock = { heading: null, lines: [] }
  for (const rawLine of markdown.split(/\r?\n/)) {
    const heading = rawLine.match(/^#{1,3}\s+(.+)$/)
    if (heading) {
      if (current.heading || current.lines.some((line) => line.trim())) blocks.push(current)
      current = { heading: heading[1].trim(), lines: [] }
    } else {
      current.lines.push(rawLine)
    }
  }
  if (current.heading || current.lines.some((line) => line.trim())) blocks.push(current)
  return blocks.length ? blocks : [{ heading: null, lines: [markdown] }]
}

function articleCopyText(title: string, body: string, media: MediaManifestItem[]): string {
  const lines = [`# ${title}`, '', body.trim(), '', '## Media placement checklist']
  for (const item of media) {
    const placement = item.kind === 'cover' ? 'top' : `after "${item.placement_after_heading || 'end'}"`
    lines.push(`- ${item.kind.toUpperCase()}: ${item.label || item.kind} · ${placement} · ${item.local_path || item.target_url || 'Not captured yet'}`)
  }
  return lines.join('\n')
}

function mediaManifestCopy(media: MediaManifestItem[]): string {
  return media.map((item) => {
    const placement = item.kind === 'cover' ? 'top' : `after "${item.placement_after_heading || 'end'}"`
    return [
      `${item.kind.toUpperCase()}: ${item.label || item.kind}`,
      `placement: ${placement}`,
      `status: ${item.local_path ? item.status || 'captured' : 'Not captured yet'}`,
      item.local_path ? `file: ${item.local_path}` : '',
      item.target_url ? `target: ${item.target_url}` : '',
      item.dimensions ? `dimensions: ${item.dimensions}` : '',
      item.flow ? `flow: ${item.flow}` : '',
    ].filter(Boolean).join('\n')
  }).join('\n\n')
}

function normalizeHeading(value: string | null): string {
  return String(value ?? '').trim().toLowerCase()
}

function recordValue(value: unknown): ArticlePackObject {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as ArticlePackObject : {}
}

function recordArray(value: unknown): ArticlePackObject[] {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === 'object' && !Array.isArray(item)) as ArticlePackObject[] : []
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item).trim()).filter(Boolean) : []
}

function stringValue(value: unknown): string {
  if (typeof value === 'number') return String(value)
  return typeof value === 'string' ? value : ''
}

function isHttpUrl(value: string): boolean {
  return /^https?:\/\//i.test(value)
}
