import { Badge } from '@toss/tds-mobile'
import { imageUrl } from '../api/client'
import type { RecallSummary } from '../api/types'
import { formatRegisteredAt, hasValue } from '../lib/format'

interface Props {
  item: RecallSummary
  onClick: () => void
}

export function RecallCard({ item, onClick }: Props) {
  const thumb = imageUrl(item.thumbnail)
  return (
    <button type="button" className="recall-card" onClick={onClick}>
      {thumb && <img className="recall-card__thumb" src={thumb} alt="" loading="lazy" />}
      <div className="recall-card__body">
        <div className="recall-card__badges">
          {item.grade != null && (
            <Badge size="small" variant="weak" color="elephant">
              회수 {item.grade}등급
            </Badge>
          )}
          <span className="recall-card__meta">{item.category_label}</span>
        </div>
        <strong className="recall-card__name">{item.product_name}</strong>
        {hasValue(item.company_name) && <span className="recall-card__company">{item.company_name}</span>}
        {hasValue(item.reason) && <p className="recall-card__reason">{item.reason}</p>}
        <span className="recall-card__meta">{formatRegisteredAt(item.registered_at)}</span>
      </div>
    </button>
  )
}
