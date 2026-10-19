# 테스트 fixture

| 파일 | 내용 |
|---|---|
| `i0490_sample.json` | 식품안전나라 I0490 샘플 (정상 바코드 / 빈 바코드 / 비표준 `R...` 코드 각 1행) |
| `consumer24_0101.xml` | 소비자24 공산품 실제 응답 원문 (`pageNo=1&cntPerPage=3`, 2026-10-19). 이미지 2장씩, `stdBrcd`는 `-`/빈 값 |
| `consumer24_0301.xml` | 소비자24 자동차 실제 응답 원문 (같은 조건). `shrtcomCn`·`etcInfo`가 HTML |
| `consumer24_code30.xml` | 결과코드 30(데이터없음) 실제 응답. 에러 응답은 `channel` 없이 루트 아래 `return`에 온다 |
| `consumer24_code50.xml` | 결과코드 50(등록되지 않은 서비스키) 실제 응답 |

API 키가 들어간 URL이나 응답 헤더는 fixture에 넣지 않는다.
