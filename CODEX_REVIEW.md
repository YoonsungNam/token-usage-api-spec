# Codex Review: token-usage-api.v2.yaml

대상 파일: [`token-usage-api.v2.yaml`](./token-usage-api.v2.yaml)

## 요약

v2 스펙은 v1의 주요 모호성(캐시 토큰, 미확정 데이터, 집계 키 안정성)을 잘 보완한다.
다만 몇몇 핵심 계약이 설명에는 강하게 적혀 있지만 OpenAPI 스키마에서는 느슨하게 허용되어,
구현체와 수집기 사이에서 해석이 갈릴 수 있다.

## 발견사항

### 1. `status: partial`과 `409 data_not_ready` 규칙이 충돌함

- 위치:
  - `info.description`의 "데이터 확정(finalization) 상태"
  - `components.schemas.DataStatus`
  - `components.responses.DataNotReady`
- 심각도: 높음

문서는 미확정 데이터를 다음처럼 설명한다.

- 진짜 사용량 0: `200` + 빈 `records` + `status: final`
- 아직 집계 전: `409 data_not_ready`

하지만 `UsagePage`의 `status`는 `DataStatus`를 참조하고, `DataStatus`는 `final | partial`을 모두 허용한다.
결과적으로 `200 OK` 응답에서 `status: partial`이 유효한 응답처럼 보인다.

이 경우 수집기는 다음을 명확히 판단하기 어렵다.

- `200 + partial` 페이지를 적재하지 않고 재시도해야 하는지
- `nextCursor`가 있으면 페이지네이션을 계속해야 하는지
- 이미 받은 partial 페이지를 나중에 어떻게 무효화해야 하는지

권장 수정:

- 미확정은 항상 `409 data_not_ready`로만 표현한다면, 200 응답 스키마에서 `status`는 `final`만 허용한다.
- 또는 `200 + partial`을 허용하려면, 수집기의 동작을 명시한다. 예: partial 페이지는 어떤 페이지도 영구 적재하지 않고 전체 date를 나중에 처음부터 재수집한다.

현재 문서의 의도는 "미확정은 409"에 더 가까우므로 `partial`을 200 응답에서 제거하는 편이 안전하다.

### 2. `model` all-or-nothing 규칙이 스키마로 강제되지 않음

- 위치:
  - `info.description`의 "데이터 모델"
  - `components.schemas.UsageRecord`
- 심각도: 높음

문서는 한 서비스의 응답 안에서 `model`이 모든 행에 존재하거나 모든 행에 없어야 한다고 한다.
또 모델을 알 수 없으면 생략하지 말고 `"unknown"`을 쓰라고 한다.

하지만 `UsageRecord.required`에는 `model`이 포함되어 있지 않다.
따라서 같은 응답 안에서 다음과 같은 혼재가 스키마상 유효하다.

```json
[
  { "userType": "identified", "userId": "u1", "model": "claude-opus-4-8", "inputTokens": 10, "outputTokens": 5, "requests": 1 },
  { "userType": "identified", "userId": "u1", "inputTokens": 20, "outputTokens": 8, "requests": 1 }
]
```

이 규칙은 이중 집계 방지에 중요하므로 설명만으로 두기에는 위험하다.

권장 수정:

- v2에서 모델 미상도 `"unknown"`으로 표현하는 방향이면 `model`을 required로 만든다.
- 모델 무관 합산 응답을 계속 허용해야 한다면, 응답 레벨에 `modelGranularity` 같은 명시 필드를 추가해 `by_model` / `all_models`를 구분한다.
- 최소한 예시와 설명에서 "생략 허용"과 `"unknown"` 권장을 동시에 두지 않도록 한쪽으로 정리한다.

### 3. `identified` 사용자와 `userId` 존재 조건이 스키마로 강제되지 않음

- 위치:
  - `components.schemas.UserType`
  - `components.schemas.UsageRecord.properties.userId`
- 심각도: 중간

`UserType` 설명은 `identified`를 "`userId` 존재"로 정의한다.
반대로 `anonymous`와 `unclassified`는 `userId`가 null이라고 설명한다.

하지만 현재 스키마는 다음을 모두 허용한다.

- `userType: identified` + `userId: null`
- `userType: identified` + `userId` 누락
- `userType: anonymous` + `userId: "some-id"`

이 상태에서는 논리 키 `(userId, userType, model)`과 `distinctIdentifiedUsers` 계산이 구현체마다 달라질 수 있다.

권장 수정:

- OpenAPI 3.1 / JSON Schema의 `oneOf` 또는 `if`/`then`을 사용해 조건부 제약을 추가한다.
- 예:
  - `identified`: `userId` required, type string
  - `anonymous`: `userId` required 또는 optional 정책을 정하되 값은 null
  - `unclassified`: `userId` required 또는 optional 정책을 정하되 값은 null

### 4. CHANGELOG에 `401` 응답 추가라고 되어 있지만 실제 응답에는 없음

- 위치:
  - `CHANGELOG (v1 -> v2)`의 `[Nits]`
  - `paths./v1/usage.get.responses`
  - `paths./v1/usage/summary.get.responses`
- 심각도: 낮음

CHANGELOG에는 `401/404/409/429/500/503` 응답 정의를 추가했다고 되어 있다.
그러나 실제 path 응답에는 `401`이 없다.

현재 스펙은 전역 `security: []`로 인증 미요구를 명시하므로, 401이 없는 것이 자연스럽다.

권장 수정:

- 인증 미요구를 유지한다면 CHANGELOG에서 `401`을 제거한다.
- 향후 인증 도입 여지를 문서화하려는 의도라면 401 response component와 path 응답을 실제로 추가한다.

## 추가 권장사항

### 1. `cacheReadTokens` / `cacheCreationTokens`의 optional 정책 정리

`UsageRecord`에서는 캐시 필드가 optional이고 default 0이다.
반면 `UsageSummary`에서는 두 필드가 required다.

이 차이는 의도적일 수 있지만, 수집기 구현 단순성을 생각하면 detail record에서도 두 필드를 required로 두는 편이 더 명확하다.
특히 "summary = detail 합"을 강제하려면 모든 행이 동일한 필드 집합을 갖는 것이 유리하다.

### 2. 날짜 검증 기준을 summary에도 동일하게 명시

`/v1/usage`의 `date` 파라미터 설명은 당일/미래 400, 보존 초과 404를 명시한다.
`/v1/usage/summary`의 `date` 설명은 더 짧다.

두 엔드포인트의 날짜 정책이 같다면 summary에도 같은 문구를 넣는 것이 구현체 해석 차이를 줄인다.

### 3. `generatedAt`의 UTC 강제 방식 보강

`generatedAt` 설명은 UTC, RFC3339라고 되어 있지만 `format: date-time`만으로는 UTC offset이 `Z`인지, 다른 offset도 허용하는지 명확하지 않다.

UTC만 허용하려면 description에 "반드시 `Z` suffix 사용"을 명시하거나 pattern을 추가하는 방법을 고려할 수 있다.

## 검증 메모

로컬에서 `npx --no-install @redocly/cli lint token-usage-api.v2.yaml`를 시도했지만,
프로젝트에 해당 패키지가 고정되어 있지 않아 registry 조회가 발생했고 네트워크 DNS 오류(`EAI_AGAIN`)로 실패했다.

따라서 이 리뷰는 OpenAPI linter 결과가 아니라 파일 내용 기준의 정적 리뷰다.
