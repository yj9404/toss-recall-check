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
let overseasNoticeSeen = false

export const getHomeSnapshot = () => snapshot

/** 불러온 목록이 없으면(로딩 중·실패) 복원할 게 없으므로 저장하지 않고 지운다. */
export function saveHomeSnapshot(next: HomeSnapshot) {
  snapshot = next.items.length > 0 ? next : null
}

export const getCachedCategories = () => categories
export const setCachedCategories = (next: Category[]) => {
  categories = next
}

// 해외 탭 안내는 처음 연 동안에만 보인다. 다른 탭으로 옮기면 본 것으로 치고, 앱을 새로 시작하면 다시 보인다.
// 상세에서 돌아온 경우는 같은 방문이라 계속 보인다(복원한 스크롤 위치도 밀리지 않는다).
export const isOverseasNoticeSeen = () => overseasNoticeSeen
export const markOverseasNoticeSeen = () => {
  overseasNoticeSeen = true
}

export function resetHomeCache() {
  snapshot = null
  categories = null
  overseasNoticeSeen = false
}
