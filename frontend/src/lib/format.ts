const DAY_MS = 24 * 60 * 60 * 1000

const pad = (n: number) => String(n).padStart(2, '0')

/** 7일 이내는 "오늘/어제/N일 전", 이후는 "YYYY.MM.DD" (기기 시간대 기준 날짜 차이) */
export function formatRegisteredAt(iso: string, now: Date = new Date()): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const days = Math.round(
    (Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) -
      Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())) /
      DAY_MS,
  )
  if (days <= 0) return '오늘'
  if (days === 1) return '어제'
  if (days <= 7) return `${days}일 전`
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`
}

/** 남은 시간을 "N시간 M분"으로. 1분 미만이 남아도 "1분"으로 올려 보여준다. */
export function formatRemaining(ms: number): string {
  const minutes = Math.max(1, Math.ceil(ms / 60_000))
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h === 0) return `${m}분`
  return m === 0 ? `${h}시간` : `${h}시간 ${m}분`
}

const EMPTY_VALUES = new Set(['', '-', '데이터없음'])

/** 값이 없거나 "-", "데이터없음"이면 화면에서 숨긴다 */
export function hasValue(value: string | null | undefined): value is string {
  return value != null && !EMPTY_VALUES.has(value.trim())
}
