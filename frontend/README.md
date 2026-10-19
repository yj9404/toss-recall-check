# 리콜체크 프런트엔드

토스 앱인토스 WebView 미니앱(`appName: recall-check`). Vite + React + TypeScript, SDK `@apps-in-toss/web-framework` 3.x, TDS `@toss/tds-mobile`.
백엔드(`../backend`)의 읽기 전용 API만 호출해요. 로그인은 없어요.

## 구조

```
src/
  api/        types.ts(응답 타입) · client.ts(fetch 호출은 여기 한 곳, 실패 시 ApiError에 상태 코드)
  lib/        format(등록일·빈 값) · barcode · pagination · ads(광고 ID) · analytics · anonymousKey
  hooks/      useAsync · useRecallList(20건씩 이어 붙이기) · useTossBanner(광고 초기화 1회, 화면 이탈 시 destroy)
  components/ RecallCard · BannerAd · ErrorView · ListSkeleton · Disclaimer
  pages/      HomePage(/) · RecallDetailPage(/recall/:id) · BarcodePage(/barcode)
```

경로는 `intoss://recall-check/...` 딥링크와 그대로 매핑돼요 (`/`, `/recall/:id`, `/barcode`).

## 환경변수

`.env.example`을 복사해서 써요. `.env*`는 커밋하지 않아요.

| 이름 | 설명 |
| --- | --- |
| `VITE_API_BASE_URL` | 백엔드 주소. 개발 서버에서 비우면 `http://localhost:8000` |
| `VITE_ADS_MODE` | `test`(기본) 또는 `live`. `build:live`(mode=live)에서는 지정하지 않아도 `live` |
| `VITE_AD_GROUP_HOME` | `live`일 때 쓰는 홈 배너의 실제 광고 그룹 ID. `.env.live`에 넣어요. 비어 있으면 배너를 그리지 않아요 |

운영 빌드의 `VITE_API_BASE_URL`은 `https://` 주소여야 해요(출시 체크리스트: API는 HTTPS만). 백엔드 CORS에도 미니앱 origin이 허용돼 있어야 해요.

## 명령

```bash
npm install
npm run dev          # 개발 서버 (AIT Devtools 패널 포함)
npm run typecheck    # tsc -b
npm run lint
npm test             # vitest
npm run build        # 테스트 광고 ID로 번들 생성 → recall-check.ait
npm run build:live   # 실제 광고 ID(.env.live)로 번들 생성 (검수 제출용)
```

## 로컬에서 확인하기 (AIT Devtools)

1. 백엔드를 띄워요: `cd ../backend && uv run uvicorn --factory app.main:create_app --reload` (`ENV=dev`면 `localhost:5173` CORS 허용)
2. `npm run dev` 후 브라우저에서 `http://localhost:5173`을 열어요.
3. 화면 오른쪽 아래 **AIT** 버튼으로 Devtools 패널을 열고, Viewport 탭에서 iPhone/Galaxy 폭을 골라요.
4. 브라우저 콘솔의 `SafeAreaInsets를 가져오는 중 에러` 로그는 토스 앱 밖에서 TDS provider가 내는 것이라 무시해도 돼요.

**광고는 샌드박스/Devtools에서 동작하지 않아요.** 배너 확인은 아래 QR 테스트가 필요해요.

## 토스 앱에서 테스트하기 (콘솔 QR)

1. `npm run build` → 프로젝트 폴더(`package.json` 옆)에 `recall-check.ait`가 생겨요. (`ait build` 단독 실행은 `dist/`가 없어 실패해요)
2. 앱인토스 콘솔에서 미니앱 `recall-check`를 선택해 **번들 업로드(테스트)** 에 `.ait` 파일을 올려요. 업로드가 끝나면 콘솔에 테스트용 QR이 나와요. (Claude Code에서는 `/ait:test-on-device`가 같은 순서를 진행해요)
3. 토스 앱으로 QR을 스캔해 열어요. 테스트 스킴은 `intoss-private://recall-check?_deploymentId=...`예요. 공유 링크의 `intoss://`는 출시 후에만 열려요.
4. 광고는 `build`(테스트 ID)로 노출 여부를, 검수 제출 전에는 `build:live`로 만든 번들로 실제 광고 그룹 ID가 동작하는지 한 번 더 확인해요. 실제 광고 ID로 개발 중에 테스트하면 정책 위반이 될 수 있어요.

검수 요청과 출시는 콘솔 또는 `/ait:launch`에서 직접 진행해요.

## 동작 규칙 요약

- 라이트 모드 전용, 핀치 줌 비활성화(viewport meta), Safe Area 반영.
- 첫 화면에서 로그인·알림 동의·팝업을 띄우지 않아요. 외부 링크와 iframe은 쓰지 않고 출처는 기관명 텍스트로만 보여줘요.
- 값이 비었거나 `-`, `데이터없음`이면 그 항목을 숨겨요. 이미지는 값이 있을 때만 그려요.
- 배너 광고: 홈 5번째 카드 뒤(5개 미만이면 목록 끝) 1곳만 둬요. 상세·바코드 화면에는 없어요. `TossAds.initialize.isSupported()`가 false이거나 토스 앱 5.241.0 미만이면 영역 자체를 그리지 않아요.
- 로그: 검색어 원문과 바코드 번호는 기록하지 않고 길이·결과 수·발견 여부만 기록해요. 식별키는 서버로 보내지 않아요.
