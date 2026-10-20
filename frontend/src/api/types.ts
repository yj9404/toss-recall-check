export interface Category {
  code: string
  label: string
  count: number
  latest_registered_at: string | null
}

export interface RecallSummary {
  id: string
  category: string
  category_label: string
  product_name: string
  company_name: string | null
  reason: string | null
  grade: 1 | 2 | 3 | null
  registered_at: string
  source_label: string
  thumbnail: string | null
}

export interface RecallDetail extends RecallSummary {
  manufactured_text: string | null
  expiry_text: string | null
  package_unit: string | null
  recall_method: string | null
  address: string | null
  barcode: string | null
  images: string[]
  source_url: string | null
  // 소비자24 항목에만 값이 있다
  model_text: string | null
  consumer_tips: string | null
  recall_period_text: string | null
  contact_text: string | null
  last_seen_at: string
}

export interface RecallPage {
  items: RecallSummary[]
  total: number
}

export interface BarcodeResult {
  found: boolean
  items: RecallSummary[]
}
