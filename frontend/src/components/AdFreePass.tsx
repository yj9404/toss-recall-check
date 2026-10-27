import { Button } from '@toss/tds-mobile'
import { useEffect, useState, useSyncExternalStore } from 'react'
import { getAdsSnapshot, preloadAds, showAdFreeReward, subscribeAds } from '../lib/ads'
import { formatRemaining } from '../lib/format'

const TICK_MS = 30_000

/**
 * 리워드 광고를 보면 24시간 동안 전면광고를 건너뛰는 이용권. 이용권이 있는 동안은 남은 시간을 보여주고 버튼을 막는다.
 * 리워드 광고를 쓸 수 없는 환경이면 아무것도 그리지 않는다.
 */
export function AdFreePass() {
  const ads = useSyncExternalStore(subscribeAds, getAdsSnapshot)
  const [now, setNow] = useState(Date.now)
  const [showFailed, setShowFailed] = useState(false)
  const active = ads.adFreeUntil > now

  useEffect(() => {
    if (!active) return
    const id = setInterval(() => {
      const t = Date.now()
      setNow(t)
      // 화면을 보는 중에 이용권이 끝나면 다음 광고를 다시 받아 둔다
      if (t >= ads.adFreeUntil) preloadAds()
    }, TICK_MS)
    return () => clearInterval(id)
  }, [active, ads.adFreeUntil])

  async function watch() {
    setShowFailed(false)
    const result = await showAdFreeReward()
    setNow(Date.now())
    setShowFailed(result === 'failed')
  }

  if (active) {
    return (
      <div className="adfree">
        <Button display="full" variant="weak" size="large" disabled>
          광고 없이 쓰는 중 · {formatRemaining(ads.adFreeUntil - now)} 남음
        </Button>
        <p className="adfree__note">사진으로 확인할 때 나오는 광고가 나오지 않아요. 목록 속 광고는 그대로 보여요.</p>
      </div>
    )
  }

  if (ads.reward === 'unsupported' || ads.reward === 'failed') return null

  const ready = ads.reward === 'loaded'
  return (
    <div className="adfree">
      <Button
        display="full"
        variant="weak"
        size="large"
        disabled={!ready}
        loading={ads.rewardShowing}
        onClick={watch}
      >
        광고 보고 24시간 광고 없이 쓰기
      </Button>
      <p className="adfree__note" role={showFailed ? 'alert' : undefined}>
        {showFailed
          ? '광고를 보여주지 못했어요. 잠시 후 다시 시도해 주세요.'
          : ready
            ? '광고를 끝까지 보면 사진으로 확인할 때 나오는 광고가 24시간 동안 나오지 않아요.'
            : '광고를 준비하고 있어요.'}
      </p>
    </div>
  )
}
