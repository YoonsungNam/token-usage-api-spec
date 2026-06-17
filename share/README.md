# Service Usage Provider API

사내 AI 추론 서비스가 **자신의 LLM 사용량**(input/output/cache token, request 수)을
**사용자별·모델별**로 노출하기 위한 표준 조회 API 계약입니다.

- 각 서비스가 이 스펙대로 `GET` 엔드포인트를 **구현(노출)** 합니다.
- 중앙 **수집기/대시보드**가 매일 각 서비스의 API 를 **호출(pull)** 하여 사용량을 수합합니다.
  (서비스가 밀어넣는 push 가 아니라, 수집기가 끌어가는 pull 방식)

## 파일

| 파일 | 설명 |
|---|---|
| [`token-usage-api.yaml`](./token-usage-api.yaml) | **API 계약 (OpenAPI 3.1)** — 이 파일이 기준입니다 |
| [`docs/IMPLEMENTATION_NOTES.md`](./docs/IMPLEMENTATION_NOTES.md) | 구현 가이드 (model 필수 이유, provider별 토큰/캐시 매핑, 응답 규칙) |
| [`tests/conformance_check.py`](./tests/conformance_check.py) | 셀프 점검 스크립트 (자기 서버에 돌려 계약 준수 확인) |

스펙을 보기 좋게 렌더링하려면:

```bash
npx --yes @redocly/cli@latest preview-docs token-usage-api.yaml
```

## 엔드포인트

| Method | Path | 설명 |
|---|---|---|
| `GET` | `/v1/usage` | 일자별 사용량 (사용자×모델, cursor 페이지네이션) |
| `GET` | `/v1/usage/summary` | 일자별 서비스 합계 (단건) |

- 인증 없음 (사내 신뢰망 전제). 수집기 IP 만 허용하는 네트워크 ACL 등은 운영 측에서 통제합니다.

## 구현 체크리스트

- **집계 단위**: `date`(KST 하루 전체) × `userId` × `userType` × `model` 로 **사전 집계**해
  행으로 제공. 한 응답 내 같은 키 조합은 중복 금지.
- **시간대**: 모든 일자는 **KST**. `date` 는 보통 어제. 수집기는 다음날 새벽에 직전날을 호출하므로,
  **KST 자정 이후 직전날 데이터가 확정**되어 있어야 함.
- **사용자 분류 / `userId`**
  - `identified`(실명), `anonymous`(비실명 계정) → `userId` **필수**(문자열, 사내 id)
  - `unclassified`(사용자 매핑 없는 사용량) → `userId` **null** + 모델 단위 합산
- **`model` 필수**: 모르거나 모델 무관 총합이면 `"unknown"`. (일부 행만 model 을 갖는 혼재 금지 —
  이중 집계 방지)
- **토큰** (provider 가 보고한 usage 기준; 자체 추정 금지)
  - `inputTokens`(input/prompt 토큰 전체, **캐시 포함**) / `outputTokens`(reasoning 포함) /
    `requests`(provider API 호출 수)
  - provider(Claude/OpenAI/vLLM)별 합산 방법은 `docs/IMPLEMENTATION_NOTES.md` 참고.
- **확정 / 응답 규칙**
  - 확정된 데이터만 `200`. 사용량이 실제 0 이면 `200` + 빈 목록.
  - 아직 집계 전이면 `409`(빈 `200` 으로 응답 금지 — "사용량 0" 과 구분).
  - 당일/미래 `date` 는 `400`, 보존 기간 초과는 `404`.
  - 응답에 집계 산출 시각 `generatedAt`(**KST, `+09:00`**) 포함.
- **페이지네이션**: 만료되지 않는 keyset 기반 `cursor` 권장. 같은 `date` 의 데이터셋은
  페이지네이션 도중 불변.

자세한 의도·예시는 `docs/IMPLEMENTATION_NOTES.md` 를 참고하세요.

## 셀프 점검

구현 중/후에 **자기 서버에** 점검 스크립트를 돌려 계약 준수를 확인합니다. 스키마 적합성과
불변식(요약=상세 합, model 필수, `userType`↔`userId`, generatedAt KST, 페이지네이션 종료,
미래날짜→400, 잘못된 cursor→400 등)을 검사합니다.

```bash
pip install jsonschema pyyaml
python tests/conformance_check.py --base-url https://my-svc.internal --date 2026-06-15
# 서버 없이 스크립트 동작만 확인:
python tests/conformance_check.py --demo
```

실패 시 어떤 케이스가 왜 틀렸는지(스키마 경로 / 위반 행 / 기대값 vs 실제값)를 출력하고,
하나라도 실패하면 종료 코드 1 로 끝납니다.

## 폴더 구조 (권장)

```
token-usage-api.yaml          # API 계약
docs/IMPLEMENTATION_NOTES.md  # 구현 가이드
tests/conformance_check.py    # 셀프 점검 (token-usage-api.yaml 을 상위 경로에서 참조)
```

## 문의

- 계약/수집 관련 문의: <담당자/채널 기입>
