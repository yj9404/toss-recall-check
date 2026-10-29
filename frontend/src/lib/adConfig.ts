// 광고 그룹 ID와 노출 정책 상수. 광고 운영 값은 이 파일에서만 바꾼다.

/**
 * 개발·테스트용 공식 테스트 광고 그룹 ID. 실제 ID로 테스트하면 정책 위반이다.
 * 출시 번들에 테스트 ID가 있으면 검수가 자동 반려되므로, live 빌드에서는 문자열이 번들에서 빠지게 상수 조건으로 가른다.
 */
export const TEST_AD_GROUP_ID: Record<'banner' | 'interstitial' | 'reward', string> =
  import.meta.env.VITE_ADS_MODE === 'live'
    ? { banner: '', interstitial: '', reward: '' }
    : {
        banner: 'ait-ad-test-banner-id',
        interstitial: 'ait-ad-test-interstitial-id',
        reward: 'ait-ad-test-rewarded-id',
      }

/**
 * live 빌드에서 쓰는 실제 광고 그룹 ID. 비워 두면 해당 광고는 노출하지 않는다(기능은 그대로 동작).
 * 홈 배너 ID는 기존처럼 .env.live의 VITE_AD_GROUP_HOME에서 읽는다.
 */
export const LIVE_AD_GROUP_ID = {
  interstitial: 'ait.v2.live.5c1f5b561d8f4ed2',
  reward: 'ait.v2.live.84e064fe31184e54',
}

/** 앱 전체에서 전면광고 사이 최소 간격 */
export const INTERSTITIAL_COOLDOWN_MS = 90_000

/** 앱 설치 후 처음 N번의 바코드 사진 스캔은 전면광고 없이 통과시킨다. 0이면 이 혜택을 끈다. */
export const FREE_FIRST_N = 2

/** 리워드 광고를 끝까지 보면 이 시간 동안 전면광고를 건너뛴다(배너는 그대로) */
export const AD_FREE_PASS_MS = 24 * 60 * 60 * 1000
