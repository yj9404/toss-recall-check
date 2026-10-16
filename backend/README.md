# 리콜체크(RecallCheck) 백엔드

토스 미니앱 "리콜체크"(`recall-check`)용 읽기 전용 API. 여러 공공 API의 리콜·회수 정보를 하나의 스키마로 모아 Postgres(Neon)에 저장하고, 사용자 요청은 메모리 스냅샷에서 처리한다.

## 구조

```
backend/
  schema.sql                  기동 시 CREATE TABLE IF NOT EXISTS로 적용
  app/
    main.py                   FastAPI 앱 팩토리, lifespan(스키마 적용·스냅샷 로드·스케줄러), CORS
    api.py                    /api/v1/*, /healthz, /internal/collect
    snapshot.py               메모리 스냅샷 (검색·카테고리 집계·바코드)
    images.py                 이미지 프록시 (허용목록·5초·3MB·image/*)
    db.py                     연결 풀, upsert, source_state, 스냅샷 로드 쿼리
    collect.py                수집 실행 (advisory lock) + CLI
    config.py, labels.py      환경변수, 카테고리·출처 라벨
    collectors/
      base.py                 Collector, RecallRecord
      foodsafety_i0490.py     식품안전나라 I0490 (구현 완료)
      kats.py, ftc.py, mfds_cosmetic.py   골격만 (명세 대기)
  tests/                      네트워크 없이 httpx MockTransport로 실행
```

### 읽기는 메모리, DB는 저장용

- 기동 시, 그리고 수집이 끝날 때마다 최근 `SNAPSHOT_DAYS`일 안에 등록된 행을 `raw` 없이 읽어 스냅샷을 새로 만들고 통째로 교체한다.
- `/api/v1/*`는 DB에 접근하지 않는다. DB 접근은 수집(upsert), 스냅샷 로드, `/healthz`에서만 일어난다.
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
```

출력은 `source<TAB>status<TAB>row_count`이다. 모두 `ok`면 종료 코드 0, 하나라도 `error`나 `not_implemented`면 1, 다른 곳에서 수집 중이면 2다.
CLI로 수집해도 **실행 중인 서버의 스냅샷은 다음 정기 수집 때까지 그대로다.** 바로 반영하려면 HTTP로 실행한다.

```bash
curl -X POST "https://<host>/internal/collect?source=foodsafety_i0490" -H "X-Admin-Token: $ADMIN_TOKEN"
```

## Neon 연결

1. Neon 콘솔에서 프로젝트를 만들고 Connection string을 복사한다.
2. **Connection pooling을 끈(direct) 연결 문자열을 쓴다.** 호스트 이름에 `-pooler`가 없는 쪽이다. 수집 중복 방지에 쓰는 세션 단위 advisory lock은 PgBouncer transaction 모드(pooler)에서 제대로 동작하지 않는다. 단일 인스턴스에 연결 최대 3개라 direct로 충분하다.
3. `?sslmode=require`를 붙여 `DATABASE_URL`에 넣는다. 테이블은 서버 기동 시(또는 CLI 실행 시) 자동으로 만들어진다.

`prepare_threshold=None`으로 연결하므로 서버 측 prepared statement는 쓰지 않는다.

## Railway 배포

1. GitHub 저장소로 서비스를 만들고 **Root Directory를 `backend`** 로 지정한다. `Dockerfile`이 자동으로 쓰인다.
2. Variables에 아래 환경변수를 넣는다 (`PORT`는 Railway가 주입).
3. Networking에서 도메인을 생성한다. 인스턴스(replica)는 1개로 둔다. 스케줄러가 프로세스 안에서 돈다 (여러 개여도 advisory lock으로 수집이 겹치지는 않는다).
4. Healthcheck Path를 `/healthz`로 둘 수 있다. 단, `/healthz`는 매번 DB를 조회하므로 **외부 업타임 모니터로 자주(예: 1분 간격) 호출하면 Neon이 절전하지 못해 컴퓨트 한도를 넘을 수 있다.**

## 환경변수

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DATABASE_URL` | (필수) | Neon direct 연결 문자열 |
| `FOODSAFETY_API_KEY` | (필수) | 식품안전나라 OpenAPI 인증키 |
| `DATA_GO_KR_API_KEY` | | 공공데이터포털 키 (미구현 수집기용, 쓸지 확인 필요) |
| `ADMIN_TOKEN` | | `POST /internal/collect`의 `X-Admin-Token`. 비우면 이 엔드포인트는 항상 403 |
| `APP_NAME` | `recall-check` | CORS origin `https://{APP_NAME}.web.tossmini.com`, `https://{APP_NAME}.private-web.tossmini.com` |
| `ENV` | `prod` | `dev`면 `http://localhost:5173` CORS 허용, `/docs` 노출 |
| `ENABLED_CATEGORIES` | vehicle을 뺀 전부 | 쉼표 구분. 노출 카테고리이자 기본 수집 대상. 모르는 코드는 기동 시 오류 |
| `COLLECT_INTERVAL_MINUTES` | `60` | 수집 주기 (기동 직후 1회 추가 실행) |
| `SNAPSHOT_DAYS` | `1095` | 스냅샷에 담을 등록일 범위 |
| `HIDE_EMPTY_DAYS` | `180` | 이 기간에 등록 건이 없는 카테고리는 `/categories`에서 숨김 |
| `IMAGE_HOST_ALLOWLIST` | `coop.foodsafetykorea.go.kr` | 이미지 프록시 허용 호스트 (쉼표 구분, 정확히 일치) |
| `KATS_API_URL`, `FTC_API_URL`, `MFDS_COSMETIC_API_URL` | | 미구현 수집기 자리. 명세 확정 후 사용 |

카테고리 코드: `food`(식품), `cosmetic`(화장품), `consumer_product`(공산품), `overseas`(해외), `medicine`(의약품), `medical_device`(의료기기), `drinking_water`(먹는물), `vehicle`(자동차).

## API

모든 시각은 ISO 8601, `+09:00`. 모든 항목에 출처 기관명(`source_label`)이 들어 있다.

| 경로 | 응답 |
|---|---|
| `GET /api/v1/categories` | `[{code, label, count, latest_registered_at}]` |
| `GET /api/v1/recalls?category=&q=&limit=20&offset=0` | `{items: [Summary], total}`. 등록일 내림차순. `q`는 공백으로 나눈 단어 AND 검색 (제품명·업체명, NFC·대소문자·공백 무시). `limit` 1~100 |
| `GET /api/v1/recalls/{id}` | Detail |
| `GET /api/v1/recalls/barcode/{barcode}` | `{found, items: [Summary]}`. 13자리 숫자가 아니면 400. **`found: false`는 "회수 목록에 없다"는 뜻일 뿐 안전하다는 뜻이 아니다.** |
| `GET /api/v1/image?u=<원본 URL>` | 이미지 프록시. 허용목록 밖이면 400, 원본 실패 502, 시간 초과 504 |
| `GET /healthz` | `{status, db, snapshot: {count, loaded_at}, sources: [{source, last_success_at, last_error_at, last_row_count}]}` |
| `POST /internal/collect?source=` | 헤더 `X-Admin-Token` 필요. 수집 후 스냅샷 교체 |

`thumbnail`과 `images[]`는 **API 기준 상대 경로**(`/api/v1/image?u=...`)다. 프론트엔드가 API 베이스 URL을 앞에 붙여 쓴다. 허용목록 밖 호스트의 이미지는 목록에서 빠진다.

## 데이터 메모

- `recalls`는 `(source, source_id)`로 upsert한다. 수집에서 빠진 항목은 지우지 않으며 `last_seen_at`만 갱신되지 않는다.
- 제조일자·소비기한은 원문 텍스트 그대로 저장·표시한다. "데이터없음" 같은 값도 그대로 둔다.
- `registered_at`은 소스 시각을 Asia/Seoul로 해석해 저장한다.
- 수집기 하나가 실패해도 그 수집기의 upsert는 트랜잭션째 롤백되고 다른 수집기는 계속 돈다. 결과는 `source_state`에 남는다. 에러 메시지에서는 API 키를 가린다.

### foodsafety_i0490

- `https://openapi.foodsafetykorea.go.kr/api/{KEY}/I0490/json/{start}/{end}`를 1000건 단위로 전량 수집한다 (ERROR-336: 한 번에 최대 1000건).
- `INFO-000` 정상, `INFO-200`(해당하는 데이터가 없습니다)은 빈 목록, 그 밖의 코드는 실패로 기록한다.
- `BRCDNO`가 13자리 숫자일 때만 `barcode`에 넣는다. 원문은 `raw`에 남는다 (`raw`는 원본 row 전체).
- `PRDLST_TYPE`과 무관하게 category는 `food`다. 건별 상세 링크 필드가 없어 `source_url`은 null이다.

## TODO

- [ ] **kats** (국가기술표준원 제품 안전인증·리콜, 공산품·해외): 엔드포인트, 인증키 종류, 페이지네이션, 응답 필드 명세와 샘플 → `app/collectors/kats.py`, `tests/fixtures/kats_sample.*`
- [ ] **ftc_\<category\>** (공정위 리콜정보, XML 공통 스키마): 엔드포인트, 카테고리 파라미터 값, XML 요소명, 페이지네이션 → `app/collectors/ftc.py`, `tests/fixtures/ftc_<category>_sample.xml`
- [ ] **mfds_cosmetic** (식약처 화장품 회수·판매중지): 엔드포인트, 응답 형식, 필드 → `app/collectors/mfds_cosmetic.py`, `tests/fixtures/mfds_cosmetic_sample.*`
- [ ] 위 세 출처의 `source_label` 표기 확인 (`app/labels.py`)
- [ ] 각 출처 이미지 호스트를 `IMAGE_HOST_ALLOWLIST`에 추가
- [ ] vehicle 노출 정책 확인 후 `ENABLED_CATEGORIES`에 추가 여부 결정
- [ ] 실제 키로 `python -m app.collect --source foodsafety_i0490` 확인
- [ ] 실제 이미지 URL(`minfo_image.do`)이 `image/*` content-type으로 오는지 확인 (아니면 프록시가 502를 준다)
