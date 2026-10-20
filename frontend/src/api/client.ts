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

/** 응답이 이보다 늦으면 요청을 끊고 오류 화면("다시 시도")으로 보낸다. 재시도는 사용자가 한다. */
export const REQUEST_TIMEOUT_MS = 8000

const isAbortError = (e: unknown) => e instanceof DOMException && e.name === 'AbortError'

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  // 호출한 쪽의 취소(signal)와 타임아웃을 한 컨트롤러로 묶는다. 본문을 다 읽을 때까지 타임아웃을 건다.
  const ctrl = new AbortController()
  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    ctrl.abort()
  }, REQUEST_TIMEOUT_MS)
  const forwardAbort = () => ctrl.abort()
  if (signal?.aborted) ctrl.abort()
  else signal?.addEventListener('abort', forwardAbort)

  // 호출한 쪽이 취소한 것이면 AbortError 그대로, 타임아웃이면 ApiError로 바꿔 오류 화면으로 보낸다
  const toError = (e: unknown, fallback: ApiError) => {
    if (timedOut) return new ApiError(0, '응답 시간 초과')
    if (isAbortError(e)) return e
    return fallback
  }

  try {
    let res: Response
    try {
      res = await fetch(`${BASE_URL}${path}`, { signal: ctrl.signal })
    } catch (e) {
      throw toError(e, new ApiError(0, '네트워크 오류'))
    }
    if (!res.ok) throw new ApiError(res.status, `요청 실패 (${res.status})`)
    try {
      return (await res.json()) as T
    } catch (e) {
      throw toError(e, new ApiError(res.status, '응답 형식 오류'))
    }
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', forwardAbort)
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
