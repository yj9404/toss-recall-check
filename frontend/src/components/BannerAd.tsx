import { useTossBanner } from '../hooks/useTossBanner'

/** 광고가 지원되지 않거나 광고 ID가 없으면 아무것도 그리지 않는다. 컨테이너 안은 SDK가 채우므로 비워 둔다. */
export function BannerAd({ adGroupId }: { adGroupId: string | null }) {
  const { ref, available } = useTossBanner(adGroupId)
  if (!available) return null
  return (
    <div className="banner-slot">
      <div ref={ref} style={{ width: '100%', height: 96 }} />
    </div>
  )
}
