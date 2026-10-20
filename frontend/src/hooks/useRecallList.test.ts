// @vitest-environment jsdom
import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { RecallSummary } from '../api/types'
import { useRecallList } from './useRecallList'

const fetchRecalls = vi.fn()
vi.mock('../api/client', () => ({ fetchRecalls: (...args: unknown[]) => fetchRecalls(...args) }))

const item = (id: string): RecallSummary => ({
  id,
  category: 'food',
  category_label: '식품',
  product_name: `제품 ${id}`,
  company_name: null,
  reason: null,
  grade: null,
  registered_at: '2025-10-20T00:00:00Z',
  source_label: '식품의약품안전처',
  thumbnail: null,
})

// 블록으로 감싼다: beforeEach가 함수를 돌려주면 vitest가 테스트 뒤 정리 함수로 호출한다
beforeEach(() => {
  fetchRecalls.mockReset()
})

describe('useRecallList 복원', () => {
  it('복원된 목록으로 시작하고 다시 불러오지 않는다', async () => {
    const restored = { items: [item('1'), item('2')], total: 5 }
    const { result } = renderHook(() => useRecallList('food', '우유', undefined, restored))

    expect(result.current.items.map((i) => i.id)).toEqual(['1', '2'])
    expect(result.current.status).toBe('idle')
    expect(result.current.hasMore).toBe(true)
    await Promise.resolve()
    expect(fetchRecalls).not.toHaveBeenCalled()
  })

  it('복원 뒤 더 보기는 복원된 개수 다음부터 이어 붙인다', async () => {
    fetchRecalls.mockResolvedValue({ items: [item('2'), item('3')], total: 3 })
    const restored = { items: [item('1'), item('2')], total: 3 }
    const { result } = renderHook(() => useRecallList('', '', undefined, restored))

    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.status).toBe('idle'))

    expect(fetchRecalls).toHaveBeenCalledWith({ category: '', q: '', offset: 2 }, expect.any(AbortSignal))
    expect(result.current.items.map((i) => i.id)).toEqual(['1', '2', '3'])
    expect(result.current.hasMore).toBe(false)
  })

  it('복원 뒤 카테고리가 바뀌면 처음부터 다시 불러온다', async () => {
    fetchRecalls.mockResolvedValue({ items: [item('9')], total: 1 })
    const restored = { items: [item('1')], total: 1 }
    const { result, rerender } = renderHook(({ c }) => useRecallList(c, '', undefined, restored), {
      initialProps: { c: 'food' },
    })
    expect(fetchRecalls).not.toHaveBeenCalled()

    rerender({ c: 'cosmetic' })
    await waitFor(() => expect(result.current.items.map((i) => i.id)).toEqual(['9']))
    expect(fetchRecalls).toHaveBeenCalledWith({ category: 'cosmetic', q: '', offset: 0 }, expect.any(AbortSignal))
  })

  it('첫 요청이 실패(타임아웃 포함)하면 전체 오류 화면 상태가 된다', async () => {
    fetchRecalls.mockRejectedValue(new Error('응답 시간 초과'))
    const { result } = renderHook(() => useRecallList('', ''))
    await waitFor(() => expect(result.current.status).toBe('error'))
    expect(result.current.failedFirst).toBe(true)
  })

  it('복원이 없으면 첫 페이지를 불러온다', async () => {
    fetchRecalls.mockResolvedValue({ items: [item('1')], total: 1 })
    const { result } = renderHook(() => useRecallList('', ''))
    expect(result.current.status).toBe('loading')
    await waitFor(() => expect(result.current.items).toHaveLength(1))
    expect(fetchRecalls).toHaveBeenCalledTimes(1)
  })
})
