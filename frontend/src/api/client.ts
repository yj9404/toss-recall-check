import type { BarcodeResult, Category, RecallDetail, RecallPage } from './types'

const BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')

export const PAGE_SIZE = 20

export class ApiError extends Error {
  /** HTTP 상태 코드. 네트워크 오류처럼 응답이 없으면 0 */
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE_URL}${path}`, { signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, '네트워크 오류')
  }
  if (!res.ok) throw new ApiError(res.status, `요청 실패 (${res.status})`)
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiError(res.status, '응답 형식 오류')
  }
}

export const isNotFound = (e: unknown): boolean => e instanceof ApiError && e.status === 404

export function fetchCategories(signal?: AbortSignal) {
  return getJson<Category[]>('/api/v1/categories', signal)
}

export function fetchRecalls(
  params: { category?: string; q?: string; offset?: number },
  signal?: AbortSignal,
) {
  const qs = new URLSearchParams()
  if (params.category) qs.set('category', params.category)
  if (params.q) qs.set('q', params.q)
  qs.set('limit', String(PAGE_SIZE))
  qs.set('offset', String(params.offset ?? 0))
  return getJson<RecallPage>(`/api/v1/recalls?${qs}`, signal)
}

export function fetchRecall(id: string, signal?: AbortSignal) {
  return getJson<RecallDetail>(`/api/v1/recalls/${encodeURIComponent(id)}`, signal)
}

export function fetchBarcode(barcode: string, signal?: AbortSignal) {
  return getJson<BarcodeResult>(`/api/v1/recalls/barcode/${encodeURIComponent(barcode)}`, signal)
}

/** 상대 경로면 API 주소를 붙이고, 비어 있으면 null (이미지 영역을 그리지 않는다) */
export function imageUrl(path: string | null | undefined): string | null {
  if (!path) return null
  return /^https?:\/\//.test(path) ? path : `${BASE_URL}${path}`
}
