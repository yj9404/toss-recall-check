import type { Category, RecallSummary } from '../api/types'

// 상세에서 뒤로 왔을 때 홈을 그대로 복원하기 위한 모듈 단위 캐시.
// 메모리에만 두므로 앱을 새로 시작하면 사라진다.

export interface HomeSnapshot {
  input: string
  query: string
  category: string
  items: RecallSummary[]
  total: number
  scrollY: number
}

let snapshot: HomeSnapshot | null = null
let categories: Category[] | null = null

export const getHomeSnapshot = () => snapshot

/** 불러온 목록이 없으면(로딩 중·실패) 복원할 게 없으므로 저장하지 않고 지운다. */
export function saveHomeSnapshot(next: HomeSnapshot) {
  snapshot = next.items.length > 0 ? next : null
}

export const getCachedCategories = () => categories
export const setCachedCategories = (next: Category[]) => {
  categories = next
}

export function resetHomeCache() {
  snapshot = null
  categories = null
}
