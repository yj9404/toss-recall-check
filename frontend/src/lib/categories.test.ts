import { describe, expect, it } from 'vitest'
import type { Category } from '../api/types'
import { orderCategories } from './categories'

const cat = (code: string, label = code): Category => ({ code, label, count: 1, latest_registered_at: null })
const codes = (cs: Category[]) => cs.map((c) => c.code)

describe('카테고리 탭 순서', () => {
  it('응답 순서와 관계없이 정해진 순서로 놓고 해외는 맨 끝에 둔다', () => {
    // 백엔드 labels.py 정의 순서
    const res = [
      'food',
      'cosmetic',
      'consumer_product',
      'overseas',
      'medicine',
      'vehicle',
      'quasi_drug',
      'household_chemical',
      'hygiene_product',
    ].map((c) => cat(c))
    expect(codes(orderCategories(res))).toEqual([
      'food',
      'vehicle',
      'consumer_product',
      'household_chemical',
      'medicine',
      'quasi_drug',
      'cosmetic',
      'hygiene_product',
      'overseas',
    ])
  })

  it('응답에 없는 카테고리는 그리지 않는다', () => {
    expect(codes(orderCategories([cat('overseas'), cat('cosmetic'), cat('food')]))).toEqual([
      'food',
      'cosmetic',
      'overseas',
    ])
    expect(orderCategories([])).toEqual([])
  })

  it('순서표에 없는 새 카테고리는 응답 순서대로 해외 앞에 붙인다', () => {
    const res = [cat('overseas'), cat('radiation_product'), cat('food'), cat('medical_device')]
    expect(codes(orderCategories(res))).toEqual(['food', 'radiation_product', 'medical_device', 'overseas'])
  })

  it('라벨은 응답의 label을 그대로 쓴다', () => {
    expect(orderCategories([cat('food', '먹거리')])[0].label).toBe('먹거리')
  })
})
