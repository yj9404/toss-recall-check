# 리콜체크 프런트엔드

토스 앱인토스 WebView 미니앱(`appName: recall`). Vite + React + TypeScript, SDK `@apps-in-toss/web-framework` 3.x, TDS `@toss/tds-mobile`.
백엔드(`../backend`)의 읽기 전용 API만 호출해요. 로그인은 없어요.

## 구조

```
src/
  api/        types.ts(응답 타입) · client.ts(fetch 호출은 여기 한 곳, 실패 시 ApiError에 상태 코드)
  lib/        format(등록일·빈 값) · detail(상세 항목 순서) · categories(탭 순서) · homeCache(홈 복원) · barcode · pagination · ads(광고 ID) · analytics · anonymousKey
  hooks/      useAsync · useRecallList(20건씩 이어 붙이기) · useTossBanner(광고 초기화 1회, 화면 이탈 시 destroy)
  components/ RecallCard · DetailImages · BannerAd · ErrorView · ListSkeleton · Disclaimer
  pages/      HomePage(/) · RecallDetailPage(/recall/:id) · BarcodePage(/barcode)
```

경로는 `intoss://recall/...` 딥링크와 그대로 매핑돼요 (`/`, `/recall/:id`, `/barcode`). 상세 공유 링크는 `intoss://recall/recall/{id}`예요.

`appName`(`recall`)은 콘솔에 등록된 값이라 바꿀 수 없어요. `apps-in-toss.config.ts`, 딥링크, 번들 파일명이 모두 이 값을 따라요.

## 앱 아이콘·이름·브랜드 색

**콘솔 앱 로고와 `brand.icon`은 같은 이미지여야 해요.** 원본은 `assets/app-icon.png`(600×600 PNG, 모서리 둥글리기 없음) 하나예요. SDK 3.x의 `apps-in-toss.config.ts`에는 `brand.icon`·`brand.displayName` 항목이 없어서(`primaryColor`만 받음) 내비게이션 바의 아이콘과 이름은 콘솔 **앱 정보**의 앱 로고·국문 앱 이름을 그대로 보여 줘요. 아이콘이나 이름을 바꾸려면 이 파일을 고친 뒤 콘솔에도 같은 이미지·이름을 올려요.

- `index.html`의 favicon도 같은 파일을 써요(로컬 개발용).
- `brand.primaryColor`(`#3182F6`)는 아이콘 배경색이에요. 토스 진입점, 브리지 화면, TDS 버튼 색에 쓰이고, 명도 대비가 부족하면 플랫폼이 자동으로 보정해요.

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
npm run build        # 테스트 광고 ID로 번들 생성 → recall.ait
npm run build:live   # 실제 광고 ID(.env.live)로 번들 생성 (검수 제출용)
```

## 로컬에서 확인하기 (AIT Devtools)

1. 백엔드를 띄워요: `cd ../backend && uv run uvicorn --factory app.main:create_app --reload` (`ENV=dev`면 `localhost:5173` CORS 허용)
2. `npm run dev` 후 브라우저에서 `http://localhost:5173`을 열어요.
3. 화면 오른쪽 아래 **AIT** 버튼으로 Devtools 패널을 열고, Viewport 탭에서 iPhone/Galaxy 폭을 골라요.
4. 브라우저 콘솔의 `SafeAreaInsets를 가져오는 중 에러` 로그는 토스 앱 밖에서 TDS provider가 내는 것이라 무시해도 돼요.

**광고는 샌드박스/Devtools에서 동작하지 않아요.** 배너 확인은 아래 QR 테스트가 필요해요.

## 토스 앱에서 테스트하기 (콘솔 QR)

1. `npm run build` → 프로젝트 폴더(`package.json` 옆)에 `recall.ait`가 생겨요. (`ait build` 단독 실행은 `dist/`가 없어 실패해요)
2. 앱인토스 콘솔에서 미니앱 `recall`을 선택해 **번들 업로드(테스트)** 에 `.ait` 파일을 올려요. 업로드가 끝나면 콘솔에 테스트용 QR이 나와요. (Claude Code에서는 `/ait:test-on-device`가 같은 순서를 진행해요)
3. 토스 앱으로 QR을 스캔해 열어요. 테스트 스킴은 `intoss-private://recall?_deploymentId=...`예요. 공유 링크의 `intoss://`는 출시 후에만 열려요.
4. 광고는 `build`(테스트 ID)로 노출 여부를, 검수 제출 전에는 `build:live`로 만든 번들로 실제 광고 그룹 ID가 동작하는지 한 번 더 확인해요. 실제 광고 ID로 개발 중에 테스트하면 정책 위반이 될 수 있어요.

검수 요청과 출시는 콘솔 또는 `/ait:launch`에서 직접 진행해요.

## 분석 이벤트

`lib/analytics.ts`의 `logScreen`/`logClick`이 SDK `Analytics.screen`/`Analytics.click`으로 보내요. `log_name`이 콘솔 **분석 > 이벤트**에 보이는 이름이에요. 토스 앱 밖에서는 보내지 않고, 실패해도 화면 동작에 영향을 주지 않아요.

| 종류 | `log_name` | 보내는 때 | 파라미터 |
| --- | --- | --- | --- |
| screen | `home_screen` | 홈에 들어올 때(상세·바코드에서 돌아올 때 포함) | 없음 |
| screen | `recall_detail_screen` | 상세 정보를 불러왔을 때 | `id`, `category` |
| screen | `barcode_screen` | 바코드 화면에 들어올 때 | 없음 |
| click | `search_submit_click` | 검색 버튼으로 시작한 조회의 첫 결과를 받았을 때 | `category`(전체는 `all`), `query_length`, `result_count` |
| click | `category_tab_click` | 카테고리 탭을 바꿀 때 | `category`(전체는 `all`) |
| click | `recall_item_click` | 목록 카드를 누를 때 | `id`, `category`, `position`(1부터) |
| click | `share_click` | 상세에서 공유하기를 누를 때 | `id` |
| click | `barcode_check_click` | 바코드 조회 결과를 받았을 때 | `found` |

검색어 원문과 바코드 번호는 보내지 않아요(길이·결과 수·발견 여부만).

**콘솔 전환 지표는 `recall_detail_screen`으로 등록해요.** 콘솔 **핵심 지표 > 전환 지표 > 직접 조합하기**에서 이 이벤트를 고르면 돼요. 회수 정보를 실제로 열어 본 순간이 이 미니앱의 핵심 목표 행동이라서예요. 지표를 바꾸면 다음 날부터 적용돼요.

## 동작 규칙 요약

- 라이트 모드 전용, 핀치 줌 비활성화(viewport meta), Safe Area 반영.
- 첫 화면에서 로그인·알림 동의·팝업을 띄우지 않아요. 외부 링크와 iframe은 쓰지 않고 출처는 기관명 텍스트로만 보여줘요.
- 값이 비었거나 `-`, `데이터없음`이면 그 항목을 숨겨요. 이미지는 값이 있을 때만 그리고, 못 불러오면 그 이미지를 빼요(빈 영역·깨진 아이콘을 남기지 않아요).
- 배너 광고: 홈 5번째 카드 뒤(5개 미만이면 목록 끝) 1곳만 둬요. 상세·바코드 화면에는 두지 않아요(비게임 출시 체크리스트: 배너는 스크롤 가능한 화면에만). `TossAds.initialize.isSupported()`가 false이거나 토스 앱 5.241.0 미만이면 영역 자체를 그리지 않아요.
- 로그: 검색어 원문과 바코드 번호는 기록하지 않고 길이·결과 수·발견 여부만 기록해요. 식별키는 서버로 보내지 않아요.
