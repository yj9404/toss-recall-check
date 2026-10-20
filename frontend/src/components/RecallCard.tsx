import { useState } from 'react'
import { imageUrl } from '../api/client'
import type { RecallSummary } from '../api/types'
import { formatRegisteredAt, hasValue } from '../lib/format'
import { GradeBadge } from './GradeBadge'

interface Props {
  item: RecallSummary
  onClick: () => void
}

export function RecallCard({ item, onClick }: Props) {
  const thumb = imageUrl(item.thumbnail)
  // 원본 서버가 이미지를 못 주면 깨진 아이콘 대신 자리째 뺀다(텍스트만 남는다)
  const [thumbFailed, setThumbFailed] = useState(false)

  return (
    <button type="button" className="recall-card" onClick={onClick}>
      <div className="recall-card__body">
        <div className="recall-card__badges">
          {item.grade != null && <GradeBadge grade={item.grade} size="small" />}
          <span className="recall-card__meta">{item.category_label}</span>
        </div>
        <strong className="recall-card__name">{item.product_name}</strong>
        {hasValue(item.company_name) && <span className="recall-card__company">{item.company_name}</span>}
        {hasValue(item.reason) && <p className="recall-card__reason">{item.reason}</p>}
        <span className="recall-card__meta">{formatRegisteredAt(item.registered_at)}</span>
      </div>
      {thumb && !thumbFailed && (
        <img
          className="recall-card__thumb"
          src={thumb}
          alt={item.product_name}
          loading="lazy"
          onError={() => setThumbFailed(true)}
        />
      )}
    </button>
  )
}
