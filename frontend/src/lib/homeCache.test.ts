import { beforeEach, describe, expect, it } from 'vitest'
import type { RecallSummary } from '../api/types'
import {
  getCachedCategories,
  getHomeSnapshot,
  resetHomeCache,
  saveHomeSnapshot,
  setCachedCategories,
} from './homeCache'

const item = { id: '1' } as RecallSummary
const snap = { input: '우유', query: '우유', category: 'food', items: [item], total: 30, scrollY: 640 }

beforeEach(resetHomeCache)

describe('홈 복원 캐시', () => {
  it('저장한 검색어·카테고리·목록·스크롤 위치를 그대로 돌려준다', () => {
    saveHomeSnapshot(snap)
    expect(getHomeSnapshot()).toEqual(snap)
  })

  it('불러온 목록이 없으면 저장하지 않고 이전 값도 지운다', () => {
    saveHomeSnapshot(snap)
    saveHomeSnapshot({ ...snap, items: [] })
    expect(getHomeSnapshot()).toBeNull()
  })

  it('카테고리는 한 번 받으면 재사용하고 초기화하면 사라진다', () => {
    expect(getCachedCategories()).toBeNull()
    setCachedCategories([{ code: 'food', label: '식품', count: 1, latest_registered_at: null }])
    expect(getCachedCategories()).toHaveLength(1)
    resetHomeCache()
    expect(getCachedCategories()).toBeNull()
  })
})
