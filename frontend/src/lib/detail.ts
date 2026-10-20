import type { RecallDetail } from '../api/types'
import { formatRegisteredAt, hasValue } from './format'

export interface DetailRow {
  label: string
  value: string
}

export interface DetailSections {
  /** 회수 사유 ~ 리콜 기간. "이렇게 하세요" 박스 위에 둔다 */
  main: DetailRow[]
  /** "이렇게 하세요" 박스 본문. 없으면 박스를 그리지 않는다 */
  tips: string | null
  /** 문의처 ~ 등록일. 박스 아래에 둔다 */
  extra: DetailRow[]
}

// 값이 비었거나 "-", "데이터없음"이면 항목째 숨긴다
const rows = (pairs: [string, string | null][]): DetailRow[] =>
  pairs.flatMap(([label, value]) => (hasValue(value) ? [{ label, value }] : []))

/** 상세 화면 항목을 화면 순서대로 정리한다. 제품명·업체명·배지는 화면 상단에서 따로 그린다. */
export function detailSections(d: RecallDetail): DetailSections {
  return {
    main: rows([
      ['회수 사유', d.reason],
      ['모델명', d.model_text],
      ['제조일자', d.manufactured_text],
      ['소비기한', d.expiry_text],
      ['포장 단위', d.package_unit],
      ['바코드', d.barcode],
      ['회수 방법', d.recall_method],
      ['리콜 기간', d.recall_period_text],
    ]),
    tips: hasValue(d.consumer_tips) ? d.consumer_tips : null,
    extra: rows([
      ['문의처', d.contact_text],
      ['업체 주소', d.address],
      ['출처', d.source_label],
      ['등록일', formatRegisteredAt(d.registered_at)],
    ]),
  }
}
