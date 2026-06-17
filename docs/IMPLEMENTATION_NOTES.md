# 구현 가이드 (추론 서비스 팀용)

`token-usage-api.yaml` 를 구현할 때 자주 헷갈리는 부분을 정리한 문서다.
계약 본문은 스펙 파일이 우선이며, 이 문서는 그 의도와 provider 별 매핑을 설명한다.

---

## 1. `model` 은 왜 필수인가 (이중 집계 방지)

`model` 을 필수로 둔 이유는 **이중 집계(double counting) 방지**다.

모델별 행과 "모델 무관 합산" 행이 한 응답에 섞이면 수집기가 토큰을 두 번 더하게 된다.
예) 사용자 `u1` 이 하루에 opus·haiku 를 썼을 때:

```yaml
# ❌ 이렇게 섞이면 위험 (model 생략 = 모델 무관 합산)
- userId: u1, model: claude-opus-4-8, inputTokens: 100
- userId: u1, model: claude-haiku-4-5, inputTokens: 50
- userId: u1,  # model 생략 = 합산
  inputTokens: 150
# 수집기 단순 합산 → 100+50+150 = 300  (실제 150 의 2배)
```

`model` 을 필수로 하면 모든 행이 `(userId, model)` 격자의 **겹치지 않는 한 칸**이 되어
단순 합산이 항상 정확하다.

```yaml
# ✅ model 필수 — 겹침 없음
- userId: u1, model: claude-opus-4-8, inputTokens: 100
- userId: u1, model: claude-haiku-4-5, inputTokens: 50
# 합 = 150 ✔
```

**모델을 구분할 수 없는 서비스**는 전부 `model: "unknown"` 한 칸에 담는다. 이렇게 하면 모델
무관 총합을 표현하면서도 겹침이 없다.

```yaml
- userId: u1, model: unknown, inputTokens: 150
```

규칙: **한 응답 안에서 model 은 모든 행에 존재**해야 하며(혼재 금지), 모르면 `"unknown"`.

---

## 2. 토큰 필드 — provider 별 매핑

캐시 토큰은 **input 에 합산**해서 단일 `inputTokens` 로 보고한다(별도 cache 필드 없음).

### 정의 (스펙 기준)
- `inputTokens`: input(prompt) 토큰 **전체 — 캐시 토큰 포함**
- `outputTokens`: output 토큰 — **reasoning/thinking 포함**
- `requests`: provider 로의 API 호출 수
- 값은 모두 **provider 가 응답으로 보고한 usage** 기준 (자체 tokenizer 추정 금지)

### provider 별 변환표

| | `inputTokens` | `outputTokens` |
|---|---|---|
| **Claude (Anthropic)** | `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` | `output_tokens` |
| **Codex (OpenAI)** | `prompt_tokens` (cached 이미 포함) | `completion_tokens` |
| **vLLM (self-hosted)** | `prompt_tokens` (cached 이미 포함) | `completion_tokens` |

### ⚠️ provider별 합산 주의

- **Claude**: `input_tokens` 는 캐시를 **제외한** 값이다. 캐시 토큰
  (`cache_read_input_tokens` + `cache_creation_input_tokens`)을 **더해서** 전체 input 으로 만든다.
- **OpenAI / vLLM**: `prompt_tokens` 가 캐시를 **이미 포함**한다. 그대로 `inputTokens` 로 쓴다
  (다시 더하면 이중 집계).

### output 의 reasoning 포함 여부
대부분 provider 의 output/completion 토큰 수는 **이미 reasoning 을 포함**한다
(Claude `output_tokens`, OpenAI `completion_tokens`, vLLM `completion_tokens` 모두 포함).
"reasoning 포함" 문구는 빠질까봐 넣은 게 아니라, **서비스가 임의로 reasoning 을 빼고 보고하지
않도록** 통일하기 위한 것이다. 즉 provider 가 준 수치를 그대로 쓰면 된다.

> 참고: vLLM 은 자체 호스팅이라 토큰에 가격이 없다(자기 GPU). vLLM 의 cache/토큰 수치는
> "비용"이 아니라 "사용량·캐시 효율" 지표다.

---

## 3. 응답 규칙 빠른 참고 (확정/미확정/0/보존초과)

| 상황 | 응답 |
|---|---|
| 확정된 사용량 있음 | `200` + `records` |
| 유효한 일자, 실제 사용량 0 | `200` + 빈 `records` |
| 아직 집계 전(미확정) | `409 data_not_ready` (+`Retry-After`) — 빈 `200` 금지 |
| 당일/미래 일자 | `400` |
| 보존 기간 초과(데이터 삭제됨) | `404 data_not_retained` — 데이터를 무기한 보관하면 발생 안 함 |

`generatedAt` 은 KST(`+09:00`)로 집계 산출 시각을 함께 반환한다(`date` 와 같은 KST 기준).
