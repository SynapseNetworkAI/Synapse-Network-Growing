export function openExternalUrlInNewTab(url: string): boolean {
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (opened) return true
  const link = document.createElement('a')
  link.href = url
  link.target = '_blank'
  link.rel = 'noopener noreferrer'
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  return false
}
