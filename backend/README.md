# 리콜체크(RecallCheck) 백엔드

토스 미니앱 "리콜체크"(`recall-check`)용 읽기 전용 API. 여러 공공 API의 리콜·회수 정보를 하나의 스키마로 모아 Postgres(Neon)에 저장하고, 사용자 요청은 메모리 스냅샷에서 처리한다.

## 구조

```
backend/
  schema.sql                  기동 시 CREATE TABLE IF NOT EXISTS로 적용
  app/
    main.py                   FastAPI 앱 팩토리, lifespan(스키마 적용·스냅샷 로드·스케줄러), CORS
    api.py                    /api/v1/*, /healthz, /internal/*
    snapshot.py               메모리 스냅샷 (검색·카테고리 집계·바코드)
    images.py                 이미지 프록시 (허용목록·5초·3MB·image/*)
    db.py                     연결 풀, upsert, source_state, 스냅샷 로드 쿼리
    collect.py                수집 실행 (advisory lock) + CLI
    config.py, labels.py      환경변수, 카테고리·출처 라벨
    collectors/
      base.py                 Collector, RecallRecord
      foodsafety_i0490.py     식품안전나라 I0490 (식품·축산물)
      consumer24.py           소비자24 리콜정보 (식품·축산물 외 11개 메뉴)
  tests/                      네트워크 없이 httpx MockTransport로 실행
```

### 읽기는 메모리, DB는 저장용

- 기동 시, 그리고 수집이 끝날 때마다 최근 `SNAPSHOT_DAYS`일 안에 등록된 행을 `raw` 없이 읽어 스냅샷을 새로 만들고 통째로 교체한다.
- `/api/v1/*`는 DB에 접근하지 않는다. DB 접근은 수집(upsert), 스냅샷 로드, `/internal/health/db`에서만 일어난다.
- 연결 풀은 `min_size=0`, `max_idle=60s`로 두어 유휴 연결이 남지 않게 했다. Neon 컴퓨트가 5분 뒤 절전할 수 있다.

## 로컬 실행

```bash
cd backend
uv sync
cp .env.example .env              # 값 채우기 (ENV=dev면 localhost:5173 CORS 허용, /docs 노출)
uv run uvicorn --factory app.main:create_app --reload
```

검사:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

수동 수집:

```bash
uv run python -m app.collect                          # ENABLED_CATEGORIES와 겹치는 수집기 전부
uv run python -m app.collect --source foodsafety_i0490
uv run python -m app.collect --source consumer24      # 키가 있는 소비자24 메뉴 전부
uv run python -m app.collect --source consumer24_0301 # 소비자24 자동차만
```

출력은 `source<TAB>status<TAB>row_count`이다. 모두 `ok`면 종료 코드 0, 하나라도 `error`면 1, 다른 곳에서 수집 중이면 2다.
CLI로 수집해도 **실행 중인 서버의 스냅샷은 다음 정기 수집 때까지 그대로다.** 바로 반영하려면 HTTP로 실행한다.

```bash
curl -X POST "https://<host>/internal/collect?source=foodsafety_i0490" -H "X-Admin-Token: $ADMIN_TOKEN"
```

## Neon 연결

1. Neon 콘솔에서 프로젝트를 만들고 Connection string을 복사한다.
2. **Connection pooling을 끈(direct) 연결 문자열을 쓴다.** 호스트 이름에 `-pooler`가 없는 쪽이다. 수집 중복 방지에 쓰는 세션 단위 advisory lock은 PgBouncer transaction 모드(pooler)에서 제대로 동작하지 않는다. 단일 인스턴스에 연결 최대 3개라 direct로 충분하다.
3. `?sslmode=require`를 붙여 `DATABASE_URL`에 넣는다. 테이블은 서버 기동 시(또는 CLI 실행 시) 자동으로 만들어진다.

`prepare_threshold=None`으로 연결하므로 서버 측 prepared statement는 쓰지 않는다.

로컬에서 연결이 응답 없이 `PoolTimeout`으로 끝나면 네트워크가 Postgres의 SSL 협상(SSLRequest)을 막고 있을 수 있다. `PGSSLNEGOTIATION=direct`(또는 연결 문자열에 `&sslnegotiation=direct`)로 TLS를 바로 시작하면 된다 (libpq 17+).

## Railway 배포

1. GitHub 저장소로 서비스를 만들고 **Root Directory를 `backend`** 로 지정한다. `Dockerfile`이 자동으로 쓰인다.
2. Variables에 아래 환경변수를 넣는다 (`PORT`는 Railway가 주입).
3. Networking에서 도메인을 생성한다. 인스턴스(replica)는 1개로 둔다. 스케줄러가 프로세스 안에서 돈다 (여러 개여도 advisory lock으로 수집이 겹치지는 않는다).
4. Healthcheck Path를 `/healthz`로 둘 수 있다. `/healthz`는 메모리만 보므로 업타임 모니터가 자주 호출해도 Neon을 깨우지 않는다. DB 연결 확인용 `/internal/health/db`는 모니터에 걸지 말 것.

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | (필수) | Neon direct 연결 문자열 |
| `FOODSAFETY_API_KEY` | (필수) | 식품안전나라 OpenAPI 인증키 |
| `CONSUMER24_KEY_<메뉴ID>` | | 소비자24 서비스키. 메뉴마다 다르다 (`0101` 공산품, `0405` 생활방사선제품, `0204` 의약품, `0205` 의약외품, `0207` 의료기기, `0206` 화장품, `0401` 생활화학제품, `0301` 자동차, `0403` 먹는물, `0208` 위생용품, `0501` 해외리콜). 비어 있는 메뉴는 수집하지 않고 기동 시 로그에 남긴다. `0201`(식품)·`0203`(축산물)은 키가 있어도 받지 않는다 |
| `CONSUMER24_LOOKBACK_DAYS` | `30` | 소비자24 증분 수집 범위 (아래 데이터 메모) |
| `ADMIN_TOKEN` | | `/internal/*`의 `X-Admin-Token`. 비우면 이 엔드포인트들은 항상 403 |
| `APP_NAME` | `recall` | CORS origin `https://{APP_NAME}.apps.tossmini.com`, `.private-apps.tossmini.com`(SDK 3.1+), `.web.tossmini.com`, `.private-web.tossmini.com`(3.0.x) |
| `ENV` | `prod` | `dev`면 `http://localhost:5173` CORS 허용, `/docs` 노출 |
| `ENABLED_CATEGORIES` | 전부 | 쉼표 구분. 노출 카테고리이자 기본 수집 대상. 모르는 코드는 기동 시 오류 |
| `COLLECT_INTERVAL_MINUTES` | `60` | 수집 주기 (기동 직후 1회 추가 실행) |
| `SNAPSHOT_DAYS` | `1095` | 스냅샷에 담을 등록일 범위 |
| `HIDE_EMPTY_DAYS` | `180` | 이 기간에 등록 건이 없는 카테고리는 `/categories`에서 숨김 |
| `IMAGE_HOST_ALLOWLIST` | `coop.foodsafetykorea.go.kr,www.consumer.go.kr` | 이미지 프록시 허용 호스트 (쉼표 구분, 정확히 일치). 여기서 빼면 그 출처 이미지는 응답에서 빠진다 |

카테고리 코드 (정의 순서가 `/categories` 순서): `food`(식품), `cosmetic`(화장품), `consumer_product`(공산품), `overseas`(해외), `medicine`(의약품), `medical_device`(의료기기), `drinking_water`(먹는물), `vehicle`(자동차), `quasi_drug`(의약외품), `household_chemical`(생활화학제품), `hygiene_product`(위생용품), `radiation_product`(생활방사선제품).

## API

모든 시각은 ISO 8601, `+09:00`. 모든 항목에 출처 기관명(`source_label`)이 들어 있다. 소비자24 항목은 건별 정보 출처 기관(예: 국가기술표준원, 국토교통부)이다.

Detail의 `model_text`(모델명), `consumer_tips`(소비자 행동 요령), `recall_period_text`(리콜 시작~종료일 원문, 예: `20261014~`)는 소비자24 항목에만 값이 있고 나머지는 null이다.

| 경로 | 응답 |
|---|---|
| `GET /api/v1/categories` | `[{code, label, count, latest_registered_at}]` |
| `GET /api/v1/recalls?category=&q=&limit=20&offset=0` | `{items: [Summary], total}`. 등록일 내림차순. `q`는 공백으로 나눈 단어 AND 검색 (제품명·업체명, NFC·대소문자·공백 무시). `limit` 1~100 |
| `GET /api/v1/recalls/{id}` | Detail |
| `GET /api/v1/recalls/barcode/{barcode}` | `{found, items: [Summary]}`. 13자리 숫자가 아니면 400. **`found: false`는 "회수 목록에 없다"는 뜻일 뿐 안전하다는 뜻이 아니다.** |
| `GET /api/v1/image?u=<원본 URL>` | 이미지 프록시. 허용목록 밖이면 400, 원본 실패 502, 시간 초과 504 |
| `GET /healthz` | `{status, snapshot: {count, loaded_at}, sources: [{source, last_success_at, last_error_at, last_row_count}]}`. 메모리 값이며 소스별 값은 이 프로세스가 수집을 한 번 끝낸 뒤부터 채워진다 |
| `GET /internal/health/db` | 헤더 `X-Admin-Token` 필요. `SELECT 1` 성공 시 `{db: "ok"}`, 실패 시 503 |
| `POST /internal/collect?source=` | 헤더 `X-Admin-Token` 필요. 수집 후 스냅샷 교체 |

`thumbnail`과 `images[]`는 **API 기준 상대 경로**(`/api/v1/image?u=...`)다. 프론트엔드가 API 베이스 URL을 앞에 붙여 쓴다. 허용목록 밖 호스트의 이미지는 목록에서 빠진다.

## 데이터 메모

- `recalls`는 `(source, source_id)`로 upsert한다. 수집에서 빠진 항목은 지우지 않으며 `last_seen_at`만 갱신되지 않는다.
- 제조일자·소비기한은 원문 텍스트 그대로 저장·표시한다. "데이터없음" 같은 값도 그대로 둔다.
- `registered_at`은 소스 시각을 Asia/Seoul로 해석해 저장한다.
- 수집기 하나가 실패해도 그 수집기의 upsert는 트랜잭션째 롤백되고 다른 수집기는 계속 돈다. 결과는 `source_state`에 남는다. 에러 메시지에서는 API 키를 가린다.
- `source_state.last_row_count`는 마지막 실행에서 upsert한 건수다. 증분 수집하는 출처는 전체 건수가 아니다.

### foodsafety_i0490

- `https://openapi.foodsafetykorea.go.kr/api/{KEY}/I0490/json/{start}/{end}`를 1000건 단위로 전량 수집한다 (ERROR-336: 한 번에 최대 1000건).
- `INFO-000` 정상, `INFO-200`(해당하는 데이터가 없습니다)은 빈 목록, 그 밖의 코드는 실패로 기록한다.
- `BRCDNO`가 13자리 숫자일 때만 `barcode`에 넣는다. 원문은 `raw`에 남는다 (`raw`는 원본 row 전체).
- `PRDLST_TYPE`과 무관하게 category는 `food`다. 건별 상세 링크 필드가 없어 `source_url`은 null이다.

### consumer24 (소비자24 리콜정보)

- `https://www.consumer.go.kr/openapi/recall/contents/index.do`, XML(UTF-8). 메뉴(`cntntsId`)마다 서비스키가 달라 메뉴별로 수집기를 하나씩 만들고 source는 `consumer24_<cntntsId>`다. 실패·성공과 `source_state`도 메뉴별이다.
- 메뉴의 성공 기록이 없으면 `allCnt` 기준으로 100건씩 전량을 받는다. 성공 기록이 있으면 `recallPublictBgnde`(공표 시작일 이후)를 **마지막 성공일**로부터 `CONSUMER24_LOOKBACK_DAYS`일 전으로 걸어 최근분만 받는다. 매시간 수집하면 "오늘 기준"과 같고, 수집이 오래 끊겼다가 다시 돌 때 그 공백까지 받는다.
- 요청 사이 0.3초 간격. 결과코드 `00` 정상, `30` 데이터 없음(빈 목록), 그 밖(`41` 페이지당 건수 초과, `50`·`51` 키 미등록 등)은 실패로 기록한다. 정상 응답은 `channel/return` 아래, 에러 응답은 루트 바로 아래 `return`에 결과가 온다.
- 일부 필드(자동차 결함 내용 등)가 HTML 조각이라 알려진 태그만 지우고 `<br>`·`</p>`는 줄바꿈으로 바꾼다. `<대상차량별 생산일자>`처럼 꺾쇠로 감싼 본문은 남긴다. `raw`에는 원문 그대로 둔다.
- `stdBrcd`에서 처음 나오는 13자리 숫자를 `barcode`로 쓴다 (`a, b`·`a / b`처럼 여러 개면 첫 번째). `recallImgUrls`는 쉼표로 나눈다.
- `registered_at`은 `recallPublictBgnde`(yyyyMMdd)의 Asia/Seoul 자정이다. 공표일이 없는 항목은 건너뛴다.
- `source_url`은 `infoOriginInsttUrl`이다. 문서의 `infoOriginUrl`과 이름이 다르고, 건별 링크가 아니라 기관 홈페이지 주소다.
- `hrmflGrad`(위해성 등급)는 형식이 정해지지 않아 `grade`에 넣지 않는다. 지금까지 받은 데이터에서는 모두 비어 있다.
- 이미지(`recallApiImage.do`)는 로그인 없이 받을 수 있다. 다만 `Content-Type`이 `image//ncis/...`처럼 깨져 오고 실제 형식이 확장자와 다를 때가 있어(PNG 이름의 JPEG), 프록시가 본문 시그니처로 형식을 정한다.

## TODO

- [ ] 키가 없는 소비자24 메뉴(0405, 0204, 0205, 0207, 0401, 0403, 0208, 0501)의 서비스키 발급 후 `.env`·Railway에 등록
- [ ] 프런트엔드 상세 화면에 `model_text`, `consumer_tips`, `recall_period_text` 표시
- [ ] 소비자24 공산품(0101)의 `recallProcssInfo`는 대부분 "인증번호: …"라 `recall_method`(회수 방법)로 보여 주기 부적절. 매핑 또는 표시 라벨 결정
- [ ] 소비자24 `recallEntrpsInfo`는 주소보다 연락처가 많다 (예: "현대자동차 대표번호 080-600-6000"). 상세 화면 라벨("업체 주소") 결정
- [ ] 배포 서버(해외 리전)에서 소비자24 API·이미지와 식품안전나라 이미지(`minfo_image.do`)가 열리는지 확인. 국내 PC에서는 둘 다 로그인 없이 200이었다 (2026-10-19)
