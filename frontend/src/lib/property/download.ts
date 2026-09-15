import { apiClient } from '../api-client'

/**
 * Download an authenticated file (a bill or receipt PDF). The request goes
 * through apiClient so it carries the bearer token and X-Tenant-ID — a plain
 * <a href> could send neither — and the backend decides visibility. The blob
 * URL is revoked once the browser has taken the file.
 */
export async function downloadFile(path: string, filename: string): Promise<void> {
  const blob = await apiClient.getBlob(path)
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}
