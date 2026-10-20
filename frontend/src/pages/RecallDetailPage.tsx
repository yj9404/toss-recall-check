import { Badge, Button, Top } from '@toss/tds-mobile'
import { Share } from '@apps-in-toss/web-framework'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchRecall, imageUrl, isNotFound } from '../api/client'
import type { RecallDetail } from '../api/types'
import { ErrorView, LoadFailedView } from '../components/ErrorView'
import { GradeBadge } from '../components/GradeBadge'
import { ListSkeleton } from '../components/ListSkeleton'
import { useAsync } from '../hooks/useAsync'
import { logClick, logScreen } from '../lib/analytics'
import { detailSections, type DetailRow } from '../lib/detail'
import { hasValue } from '../lib/format'

function DetailRows({ rows }: { rows: DetailRow[] }) {
  if (rows.length === 0) return null
  return (
    <dl className="detail-rows">
      {rows.map(({ label, value }) => (
        <div key={label} className="detail-row">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function RecallDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { state, reload } = useAsync((signal) => fetchRecall(id, signal), id)
  const [sharing, setSharing] = useState(false)

  const loaded = state.status === 'ok' ? state.data : null
  useEffect(() => {
    if (loaded) logScreen('recall_detail_screen', { id: loaded.id, category: loaded.category })
  }, [loaded])

  async function share(d: RecallDetail) {
    if (sharing) return
    setSharing(true)
    logClick('share_click', { id: d.id })
    try {
      const link = await Share.createLink({ path: `intoss://recall/recall/${d.id}` })
      await Share.sendMessage({ message: `[리콜체크] ${d.product_name} 회수 정보\n${link}` })
    } catch (e) {
      console.warn('공유하지 못했어요', e)
    } finally {
      setSharing(false)
    }
  }

  if (state.status === 'loading') return <ListSkeleton />
  if (state.status === 'error') {
    return isNotFound(state.error) ? (
      <ErrorView
        title="찾을 수 없는 정보예요"
        description="삭제됐거나 잘못된 주소일 수 있어요."
        actionLabel="목록으로 가기"
        onAction={() => navigate('/', { replace: true })}
      />
    ) : (
      <LoadFailedView onRetry={reload} />
    )
  }

  const d = state.data
  const images = d.images.map(imageUrl).filter((u): u is string => u !== null)
  const { main, tips, extra } = detailSections(d)

  return (
    <main className="page">
      <Top
        title={<Top.TitleParagraph size={22}>{d.product_name}</Top.TitleParagraph>}
        subtitleBottom={
          hasValue(d.company_name) ? (
            <Top.SubtitleParagraph size={15}>{d.company_name}</Top.SubtitleParagraph>
          ) : undefined
        }
      />

      <div className="detail-badges">
        {d.grade != null && <GradeBadge grade={d.grade} size="medium" />}
        <Badge size="medium" variant="weak" color="elephant">
          {d.category_label}
        </Badge>
      </div>

      {images.length > 0 && (
        <div className="detail-images">
          {images.map((src) => (
            <img key={src} src={src} alt="" loading="lazy" onError={(e) => (e.currentTarget.hidden = true)} />
          ))}
        </div>
      )}

      <DetailRows rows={main} />

      {tips && (
        // 행동 안내라 경고처럼 보이지 않게 배경색만 다른 중립 카드로 둔다
        <section className="detail-tips" aria-labelledby="detail-tips-title">
          <h2 id="detail-tips-title">이렇게 하세요</h2>
          <p>{tips}</p>
        </section>
      )}

      <DetailRows rows={extra} />

      <div className="section">
        <Button display="full" variant="weak" size="large" loading={sharing} onClick={() => share(d)}>
          공유하기
        </Button>
      </div>
    </main>
  )
}
