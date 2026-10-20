// @vitest-environment jsdom
import { ThemeProvider } from '@toss/tds-mobile'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RecallSummary } from '../api/types'
import { resetHomeCache } from '../lib/homeCache'
import { HomePage } from './HomePage'

const fetchRecalls = vi.fn()
vi.mock('../api/client', () => ({
  fetchRecalls: (...args: unknown[]) => fetchRecalls(...args),
  fetchCategories: () => Promise.resolve([]),
  imageUrl: () => null,
}))
// 토스 앱 밖이라 분석·광고 SDK는 아무것도 하지 않게 둔다
vi.mock('@apps-in-toss/web-framework', () => ({
  Analytics: { screen: () => {}, click: () => {} },
  isMinVersionSupported: () => false,
  TossAds: { initialize: { isSupported: () => false }, attachBanner: { isSupported: () => false } },
}))

const item = (id: string, name: string): RecallSummary => ({
  id,
  category: 'food',
  category_label: '식품',
  product_name: name,
  company_name: null,
  reason: null,
  grade: null,
  registered_at: '2026-10-20T00:00:00+09:00',
  source_label: '식품의약품안전처',
  thumbnail: null,
})

beforeEach(() => {
  resetHomeCache()
  fetchRecalls.mockReset()
  fetchRecalls.mockImplementation(async ({ q }: { q?: string }) =>
    q ? { items: [item('9', `${q} 소스`)], total: 1 } : { items: [item('1', '우유'), item('2', '두부')], total: 2 },
  )
})
afterEach(cleanup)

const lastQuery = () => (fetchRecalls.mock.lastCall?.[0] as { q?: string }).q

function renderHome() {
  const view = render(
    <ThemeProvider>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </ThemeProvider>,
  )
  const input = screen.getByPlaceholderText('제품명이나 업체명을 입력해요') as HTMLInputElement
  return { ...view, input, form: input.closest('form')! }
}

describe('홈 검색', () => {
  it('검색어 삭제(X)를 누르면 입력과 검색을 함께 풀어 전체 목록으로 돌아간다', async () => {
    const { input, form } = renderHome()
    await screen.findByText('우유')

    fireEvent.change(input, { target: { value: '성게' } })
    fireEvent.submit(form)
    await screen.findByText('성게 소스')
    expect(lastQuery()).toBe('성게')

    fireEvent.click(screen.getByRole('button', { name: '검색어 삭제' }))
    await screen.findByText('우유')
    expect(input.value).toBe('')
    expect(lastQuery()).toBe('')
    expect(screen.queryByText('성게 소스')).toBeNull()
  })

  it('검색어 삭제(X)는 폼을 제출하지 않는다', async () => {
    const { input, form } = renderHome()
    await screen.findByText('우유')
    const onSubmit = vi.fn((e: Event) => e.preventDefault())
    form.addEventListener('submit', onSubmit)

    fireEvent.change(input, { target: { value: '성게' } })
    fireEvent.click(screen.getByRole('button', { name: '검색어 삭제' }))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('검색 중이 아니면 X를 눌러도 다시 불러오지 않는다', async () => {
    const { input } = renderHome()
    await screen.findByText('우유')
    const calls = fetchRecalls.mock.calls.length

    fireEvent.change(input, { target: { value: '성' } })
    fireEvent.click(screen.getByRole('button', { name: '검색어 삭제' }))
    await waitFor(() => expect(input.value).toBe(''))
    expect(fetchRecalls.mock.calls.length).toBe(calls)
  })
})
