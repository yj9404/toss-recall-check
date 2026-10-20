import { describe, expect, it } from 'vitest'
import type { RecallDetail } from '../api/types'
import { detailSections } from './detail'

const base: RecallDetail = {
  id: '1',
  category: 'food',
  category_label: '식품',
  product_name: '우유',
  company_name: '업체',
  reason: '세균 검출',
  grade: 2,
  registered_at: '2025-01-02T09:00:00+09:00',
  source_label: '식품의약품안전처',
  thumbnail: null,
  manufactured_text: '2025-01-01',
  expiry_text: '2025-02-01',
  package_unit: '200ml',
  recall_method: '구입처 반품',
  address: '서울',
  barcode: '8801234567890',
  images: [],
  source_url: null,
  model_text: null,
  consumer_tips: null,
  recall_period_text: null,
  contact_text: null,
  last_seen_at: '2025-01-02T09:00:00+09:00',
}

const labels = (rows: { label: string }[]) => rows.map((r) => r.label)

describe('상세 화면 항목', () => {
  it('소비자24 항목은 새 필드를 정해진 순서로 보여준다', () => {
    const s = detailSections({
      ...base,
      model_text: 'AB-100',
      consumer_tips: '사용을 멈추고\n업체에 연락해 주세요.',
      recall_period_text: '2025.01.01 ~ 2025.12.31',
      contact_text: '고객센터 080-000-0000\nhttps://example.com',
    })
    expect(labels(s.main)).toEqual([
      '회수 사유',
      '모델명',
      '제조일자',
      '소비기한',
      '포장 단위',
      '바코드',
      '회수 방법',
      '리콜 기간',
    ])
    expect(s.tips).toBe('사용을 멈추고\n업체에 연락해 주세요.')
    expect(labels(s.extra)).toEqual(['문의처', '업체 주소', '출처', '등록일'])
    // 줄바꿈은 화면(white-space: pre-line)에서 살리도록 원문 그대로 넘긴다
    expect(s.extra[0].value).toBe('고객센터 080-000-0000\nhttps://example.com')
  })

  it('식품처럼 새 필드가 null이면 해당 항목과 "이렇게 하세요" 박스를 숨긴다', () => {
    const s = detailSections(base)
    expect(labels(s.main)).not.toContain('모델명')
    expect(labels(s.main)).not.toContain('리콜 기간')
    expect(labels(s.extra)).not.toContain('문의처')
    expect(s.tips).toBeNull()
  })

  it('비었거나 "-", "데이터없음"인 값은 숨긴다', () => {
    const s = detailSections({
      ...base,
      model_text: '-',
      consumer_tips: '데이터없음',
      recall_period_text: '  ',
      contact_text: '',
      barcode: '-',
    })
    expect(labels(s.main)).toEqual(['회수 사유', '제조일자', '소비기한', '포장 단위', '회수 방법'])
    expect(s.tips).toBeNull()
    expect(labels(s.extra)).toEqual(['업체 주소', '출처', '등록일'])
  })
})
