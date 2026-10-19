import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, fetchBarcode, fetchRecall, fetchRecalls, imageUrl, isNotFound } from './client'

function mockFetch(impl: () => Promise<Response> | Response) {
  const fn = vi.fn(async () => impl())
  vi.stubGlobal('fetch', fn)
  return fn
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

afterEach(() => vi.unstubAllGlobals())

describe('API 클라이언트 에러 처리', () => {
  it('실패 응답은 상태 코드를 담은 ApiError로 던진다', async () => {
    mockFetch(() => json({ detail: 'x' }, 400))
    const err = await fetchBarcode('123').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(400)
  })

  it('404는 isNotFound로 구분된다', async () => {
    mockFetch(() => json({}, 404))
    const err = await fetchRecall('nope').catch((e) => e)
    expect(isNotFound(err)).toBe(true)
    expect(isNotFound(new ApiError(500, 'x'))).toBe(false)
  })

  it('네트워크 오류는 상태 코드 0의 ApiError로 던진다', async () => {
    mockFetch(() => Promise.reject(new TypeError('Failed to fetch')))
    const err = await fetchRecall('1').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
  })

  it('JSON이 아닌 응답도 ApiError로 던진다', async () => {
    mockFetch(() => new Response('<html>', { status: 200 }))
    await expect(fetchRecall('1')).rejects.toBeInstanceOf(ApiError)
  })

  it('취소(AbortError)는 ApiError로 바꾸지 않는다', async () => {
    mockFetch(() => Promise.reject(new DOMException('aborted', 'AbortError')))
    const err = await fetchRecall('1').catch((e) => e)
    expect(err).not.toBeInstanceOf(ApiError)
  })
})

describe('요청 구성', () => {
  it('목록 요청에 빈 값은 싣지 않고 limit/offset은 항상 싣는다', async () => {
    const fn = mockFetch(() => json({ items: [], total: 0 }))
    await fetchRecalls({ category: '', q: '우유', offset: 40 })
    const url = String((fn.mock.calls[0] as unknown[])[0])
    expect(url).toContain('/api/v1/recalls?')
    expect(url).toContain('q=%EC%9A%B0%EC%9C%A0')
    expect(url).toContain('limit=20')
    expect(url).toContain('offset=40')
    expect(url).not.toContain('category=')
  })

  it('이미지 경로는 비면 null, 상대 경로면 API 주소를 붙인다', () => {
    expect(imageUrl(null)).toBeNull()
    expect(imageUrl('')).toBeNull()
    expect(imageUrl('/img/1.jpg')).toMatch(/\/img\/1\.jpg$/)
    expect(imageUrl('https://x.test/a.jpg')).toBe('https://x.test/a.jpg')
  })
})
