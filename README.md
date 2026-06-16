# token-usage-api-spec

사내 AI 추론 서비스들의 **사용자별 토큰 사용량**을 수합하기 위한 표준 조회 API 계약(OpenAPI).

각 서비스가 이 스펙대로 `GET` 엔드포인트를 노출하면, 중앙 수집기/대시보드가 일 단위로
각 서비스를 **호출(pull)** 하여 사용량을 수합한다.

## 파일

- [`token-usage-api.v2.yaml`](./token-usage-api.v2.yaml) — OpenAPI 3.1 스펙 (**현행**, v2.2.0)
- [`token-usage-api.v1.yaml`](./token-usage-api.v1.yaml) — 최초 스펙 원본 (v1.0.0, 보관용 / deprecated)
- [`CHANGELOG.md`](./CHANGELOG.md) — v1 → v2 변경사항 + 결정 이유 (쉬운 설명)

## 핵심 설계

- **방향**: pull (수집기가 각 서비스의 `GET /v1/usage` 를 호출). push 도구(OTel 등)는
  어댑터 서비스로 이 계약을 충족시킨다.
- **집계 단위**: 일자(KST) × 사용자 × 모델, 사전 집계.
- **토큰**: `inputTokens`(cache read 제외) / `cacheReadTokens` / `cacheCreationTokens` /
  `outputTokens`(reasoning 포함). 캐시 미지원 백엔드(vLLM 등)는 cache 필드 0.
- **확정 상태**: `status`(final|partial) + `generatedAt` 으로 "미확정"과 "사용량 0" 을 구분
  (미확정은 `409 data_not_ready`).
- **집계 키**: `serviceGroupId`/`serviceId`(불변·정규화) + 표시명 분리.
- **페이지네이션**: stateless keyset 기반 cursor.

자세한 변경 이력은 스펙 파일 끝의 `CHANGELOG (v1 → v2)` 참고.

## 검증 / CI

PR·push 시 `.github/workflows/openapi-ci.yml` 가 두 단계로 스펙을 검증한다.

1. **Redocly lint** — OpenAPI 3.1 구조/`$ref`/정합성 (`redocly.yaml` 룰셋)
   - 참고: Spectral 6 은 `type: 'null'` / if-then 등 3.1 구문에서 크래시하여 Redocly 를 사용한다.
2. **예시 + if/then 회귀 검증** — `scripts/validate_examples.py`
   (모든 `examples` 적합성 + `userType`↔`userId` 조건부 제약의 양성/음성 케이스)

로컬 실행:

```bash
# (1) 구조 lint
npx --yes @redocly/cli@latest lint token-usage-api.v2.yaml
# (2) 예시 / if-then 검증
pip install "jsonschema>=4.21" pyyaml && python scripts/validate_examples.py
```

> 참고: `if/then` 조건부 제약은 **런타임 JSON Schema 검증기**(ajv/jsonschema 등)에서만
> 강제된다. 다수 OpenAPI **코드 생성기**는 이를 무시하므로, 생성 타입이 아니라
> 런타임 검증으로 제약을 보장해야 한다. 코드 생성 도입 시 해당 도구의 OpenAPI 3.1 지원
> 여부부터 확인할 것.

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/v1/usage` | 일자별 사용량 (사용자×모델, 페이지네이션) |
| `GET` | `/v1/usage/summary` | 일자별 서비스 합계 (단건) |
