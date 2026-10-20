// @vitest-environment jsdom
import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { RecallSummary } from '../api/types'
import { DetailImages } from './DetailImages'
import { RecallCard } from './RecallCard'

// 등급 배지(TDS)는 이 테스트의 관심사가 아니다
vi.mock('./GradeBadge', () => ({ GradeBadge: () => null }))

afterEach(cleanup)

const item = (thumbnail: string | null): RecallSummary => ({
  id: '1',
  category: 'consumer_product',
  category_label: '공산품',
  product_name: '전기히터',
  company_name: '업체',
  reason: '화재 위험',
  grade: null,
  registered_at: '2025-10-20T00:00:00Z',
  source_label: '소비자24',
  thumbnail,
})

describe('목록 카드 썸네일', () => {
  it('thumbnail이 있으면 API 주소를 붙여 제품명을 alt로 그리고, lazy로 불러온다', () => {
    const { container } = render(<RecallCard item={item('/api/v1/image?u=x')} onClick={() => {}} />)
    const img = container.querySelector('img')!
    expect(img.getAttribute('src')).toMatch(/\/api\/v1\/image\?u=x$/)
    expect(img.alt).toBe('전기히터')
    expect(img.getAttribute('loading')).toBe('lazy')
    // 텍스트 뒤(오른쪽)에 둔다
    expect(img.previousElementSibling?.className).toBe('recall-card__body')
  })

  it('thumbnail이 없으면 이미지 없이 텍스트만 그린다', () => {
    const { container, getByText } = render(<RecallCard item={item(null)} onClick={() => {}} />)
    expect(container.querySelector('img')).toBeNull()
    expect(getByText('전기히터')).toBeTruthy()
  })

  it('이미지를 못 불러오면 이미지 요소를 빼고 텍스트만 남긴다', () => {
    const { container, getByText } = render(<RecallCard item={item('/img/1.jpg')} onClick={() => {}} />)
    fireEvent.error(container.querySelector('img')!)
    expect(container.querySelector('img')).toBeNull()
    expect(getByText('전기히터')).toBeTruthy()
  })
})

describe('상세 이미지', () => {
  it('모든 이미지를 제품명 alt, lazy로 그린다', () => {
    const { container } = render(<DetailImages srcs={['a.jpg', 'b.jpg']} alt="전기히터" />)
    const imgs = [...container.querySelectorAll('img')]
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['a.jpg', 'b.jpg'])
    expect(imgs.every((i) => i.alt === '전기히터' && i.getAttribute('loading') === 'lazy')).toBe(true)
  })

  it('못 불러온 이미지만 빼고 나머지는 남긴다', () => {
    const { container } = render(<DetailImages srcs={['a.jpg', 'b.jpg']} alt="전기히터" />)
    fireEvent.error(container.querySelector('img[src="a.jpg"]')!)
    expect([...container.querySelectorAll('img')].map((i) => i.getAttribute('src'))).toEqual(['b.jpg'])
  })

  it('모두 실패하거나 이미지가 없으면 빈 영역을 남기지 않는다', () => {
    const { container } = render(<DetailImages srcs={['a.jpg']} alt="전기히터" />)
    fireEvent.error(container.querySelector('img')!)
    expect(container.innerHTML).toBe('')

    const empty = render(<DetailImages srcs={[]} alt="전기히터" />)
    expect(empty.container.innerHTML).toBe('')
  })
})
