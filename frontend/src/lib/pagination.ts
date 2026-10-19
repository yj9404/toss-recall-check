/** 다음 페이지를 이어 붙인다. 등록 중 데이터가 밀려 겹친 항목은 id로 걸러낸다. */
export function appendPage<T extends { id: string }>(prev: T[], next: T[]): T[] {
  const seen = new Set(prev.map((item) => item.id))
  return [...prev, ...next.filter((item) => !seen.has(item.id))]
}
