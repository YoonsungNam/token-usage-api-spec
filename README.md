# token-usage-api-spec

사내 AI 추론 서비스가 **자신의 LLM 토큰 사용량**을 노출하기 위한 표준 조회 API 계약(OpenAPI 3.1).
중앙 수집기/대시보드가 매일 각 서비스의 `GET` 엔드포인트를 **호출(pull)** 하여 사용자별 사용량을
수합하고, 이를 바탕으로 *서비스별 사용자 / 사용자별 서비스 / 모델별 토큰* 등을 집계한다.

## 파일

- [`token-usage-api.v2.yaml`](./token-usage-api.v2.yaml) — OpenAPI 3.1 스펙 (**현행**, v2.5.0)
- [`token-usage-api.v1.yaml`](./token-usage-api.v1.yaml) — 최초 스펙 원본 (v1.0.0, 보관용 / deprecated)
- [`CHANGELOG.md`](./CHANGELOG.md) — 버전별 변경사항 + 결정 이유
- [`docs/IMPLEMENTATION_NOTES.md`](./docs/IMPLEMENTATION_NOTES.md) — 구현 가이드 (model 필수 이유, provider별 토큰/캐시 매핑, 응답 규칙)

> 스펙 description 은 **v1 원문을 보존하고 그 위에 `[v2 추가]`/`[v2 변경]` 표기로 개정분만
> 덧붙이는** 형식이라, v1 작성자가 변경점을 바로 확인할 수 있다.

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/v1/usage` | 일자별 사용량 (사용자×모델, cursor 페이지네이션) |
| `GET` | `/v1/usage/summary` | 일자별 서비스 합계 (단건) |

## 핵심 설계

- **방향**: pull. 수집기가 다음날 새벽에 직전날(`date`=어제) 데이터를 호출한다. 인증 없음(사내망 전제).
- **집계 단위**: `date`(KST 하루 전체) × `userId` × `userType` × `model` 로 사전 집계해 행으로 제공.
- **식별자**
  - `serviceGroup`(과제명) / `service` = 서비스 그룹 · 서비스 식별 (자유 문자열).
  - `userId` = 사내 id. `identified`(실명)·`anonymous`(비실명 계정)는 **필수(문자열)**,
    `unclassified`(사용자 매핑 없는 사용량)는 **null + 모델 단위 합산**.
  - `model` = **필수**(모르면 `"unknown"`).
- **토큰** (provider 보고 usage 기준)
  - `inputTokens`(cache read 제외) / `cacheReadTokens` / `cacheCreationTokens` /
    `outputTokens`(reasoning 포함) / `requests`.
  - 캐시 미지원 백엔드(vLLM 등)는 cache 필드를 0 또는 생략.
- **확정 / 응답 규칙**
  - 확정된 데이터만 `200`. 아직 집계 전이면 `409`(빈 `200` 금지 — "사용량 0"과 구분).
  - 사용량이 실제 0 이면 `200` + 빈 목록. 당일/미래 `date` 는 `400`, 보존 초과는 `404`.
  - 응답에 집계 산출 시각 `generatedAt`(KST, `+09:00`) 포함.
- **페이지네이션**: 만료되지 않는 keyset 기반 `cursor`. 같은 `date` 데이터셋은 페이지네이션 도중 불변.

## 검증 / CI

PR·push 시 `.github/workflows/openapi-ci.yml` 가 두 단계로 스펙을 검증한다.

1. **Redocly lint** — OpenAPI 3.1 구조 / `$ref` / 정합성 (`redocly.yaml` 룰셋)
   - 참고: Spectral 6 은 `type: 'null'` / if-then 등 3.1 구문에서 크래시하여 Redocly 를 사용한다.
2. **예시 + 제약 회귀 검증** — `scripts/validate_examples.py`
   (모든 `examples` 적합성 + `userType`↔`userId` 조건부 제약 + `generatedAt` KST 강제의 양성/음성 케이스)

로컬 실행:

```bash
# (1) 구조 lint
npx --yes @redocly/cli@latest lint token-usage-api.v2.yaml
# (2) 예시 / 제약 검증
pip install "jsonschema>=4.21" pyyaml && python scripts/validate_examples.py
```

### 프로바이더 셀프 점검

추론 서비스는 구현 중/후에 **자기 서버에** 셀프 점검 스크립트를 돌려 계약 준수를 확인한다.
스키마 적합성 + 불변식(summary=detail 합, model 필수, `userType`↔`userId`, generatedAt KST,
페이지네이션 종료, 미래날짜→400, 잘못된 cursor→400 등)을 검사한다.

```bash
pip install jsonschema pyyaml
python tests/conformance_check.py --base-url https://my-svc.internal --date 2026-06-15
# 서버 없이 스크립트 동작만 확인: python tests/conformance_check.py --demo
```

### if/then 참고

> `if/then` 조건부 제약은 **런타임 JSON Schema 검증기**(ajv/jsonschema 등)에서만 강제된다.
> 다수 OpenAPI **코드 생성기**는 이를 무시하므로, 생성 타입이 아니라 런타임 검증으로 제약을
> 보장해야 한다. 코드 생성 도입 시 해당 도구의 OpenAPI 3.1 지원 여부부터 확인할 것.
