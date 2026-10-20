import type { Category } from '../api/types'

export const OVERSEAS = 'overseas'

// "전체" 다음에 오는 탭 순서. 해외는 항상 맨 끝이다.
const TAB_ORDER = [
  'food',
  'vehicle',
  'consumer_product',
  'household_chemical',
  'medicine',
  'quasi_drug',
  'cosmetic',
  'hygiene_product',
]

/**
 * /categories 응답을 탭 순서로 정렬한다. 응답에 없는 카테고리는 그리지 않고,
 * 순서표에 없는 새 카테고리는 응답 순서대로 해외 앞에 붙인다.
 */
export function orderCategories(categories: Category[]): Category[] {
  const byCode = new Map(categories.map((c) => [c.code, c]))
  const known = TAB_ORDER.flatMap((code) => byCode.get(code) ?? [])
  const unknown = categories.filter((c) => !TAB_ORDER.includes(c.code) && c.code !== OVERSEAS)
  const overseas = byCode.get(OVERSEAS)
  return [...known, ...unknown, ...(overseas ? [overseas] : [])]
}
