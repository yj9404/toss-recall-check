import { describe, expect, it } from 'vitest'
import { resolveHomeAdGroupId, TEST_BANNER_ID } from './ads'
import { isValidBarcode, sanitizeBarcode } from './barcode'
import { formatRegisteredAt, hasValue } from './format'
import { appendPage } from './pagination'

describe('바코드 입력 검증', () => {
  it('13자리 숫자만 유효하다', () => {
    expect(isValidBarcode('8801234567890')).toBe(true)
    expect(isValidBarcode('880123456789')).toBe(false)
    expect(isValidBarcode('88012345678901')).toBe(false)
    expect(isValidBarcode('880123456789a')).toBe(false)
  })

  it('숫자 외 문자는 지우고 13자리까지만 받는다', () => {
    expect(sanitizeBarcode('880-1234 5678 90123456')).toBe('8801234567890')
  })
})

describe('등록일 표시', () => {
  const now = new Date(2025, 9, 20, 15, 0) // 2025-10-20 15:00 (로컬)

  it('7일 이내는 오늘/어제/N일 전', () => {
    expect(formatRegisteredAt(new Date(2025, 9, 20, 1).toISOString(), now)).toBe('오늘')
    expect(formatRegisteredAt(new Date(2025, 9, 19, 23).toISOString(), now)).toBe('어제')
    expect(formatRegisteredAt(new Date(2025, 9, 17, 9).toISOString(), now)).toBe('3일 전')
    expect(formatRegisteredAt(new Date(2025, 9, 13, 9).toISOString(), now)).toBe('7일 전')
  })

  it('7일을 넘으면 날짜로 표시한다', () => {
    expect(formatRegisteredAt(new Date(2025, 9, 12, 9).toISOString(), now)).toBe('2025.10.12')
  })

  it('미래·잘못된 값도 깨지지 않는다', () => {
    expect(formatRegisteredAt(new Date(2025, 9, 21).toISOString(), now)).toBe('오늘')
    expect(formatRegisteredAt('not-a-date', now)).toBe('')
  })

  it('비었거나 "-", "데이터없음"이면 값이 없는 것으로 본다', () => {
    for (const v of [null, undefined, '', '  ', '-', '데이터없음']) expect(hasValue(v)).toBe(false)
    expect(hasValue('2026-01-01까지')).toBe(true)
  })
})

describe('목록 이어 붙이기', () => {
  it('다음 페이지를 뒤에 붙이고 겹친 id는 한 번만 둔다', () => {
    const a = [{ id: '1' }, { id: '2' }]
    const b = [{ id: '2' }, { id: '3' }]
    expect(appendPage(a, b).map((x) => x.id)).toEqual(['1', '2', '3'])
    expect(appendPage([], b)).toEqual(b)
  })
})

describe('홈 배너 광고 그룹 ID', () => {
  it('기본은 테스트 ID', () => {
    expect(resolveHomeAdGroupId({}, 'production')).toBe(TEST_BANNER_ID)
    expect(resolveHomeAdGroupId({ VITE_ADS_MODE: 'test', VITE_AD_GROUP_HOME: 'home-id' }, 'production')).toBe(
      TEST_BANNER_ID,
    )
  })

  it('live는 홈 광고 그룹 ID, 비어 있으면 null', () => {
    expect(resolveHomeAdGroupId({ VITE_ADS_MODE: 'live', VITE_AD_GROUP_HOME: 'home-id' }, 'production')).toBe(
      'home-id',
    )
    expect(resolveHomeAdGroupId({ VITE_AD_GROUP_HOME: 'home-id' }, 'live')).toBe('home-id')
    expect(resolveHomeAdGroupId({ VITE_ADS_MODE: 'live', VITE_AD_GROUP_HOME: ' ' }, 'live')).toBeNull()
    expect(resolveHomeAdGroupId({}, 'live')).toBeNull()
  })
})
