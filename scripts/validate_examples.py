#!/usr/bin/env python3
"""
예시(examples) 및 userType↔userId if/then 제약 회귀 검증.

Spectral 은 구조/스타일/$ref 를 보지만, 스키마 레벨 `examples` 배열과 조건부
(if/then) 의미까지는 보장하지 않는다. 이 스크립트가 그 부분을 강제한다.

- 모든 component 스키마가 유효한 JSON Schema 인지(check_schema)
- 선언된 모든 examples 가 자기 스키마에 대해 valid 인지
- UsageRecord 의 userType↔userId 조건부 제약이 의도대로 양성/음성 케이스를 가르는지

실패가 하나라도 있으면 종료 코드 1.
"""
import json
import sys

import yaml

try:  # 최신 jsonschema (OpenAPI 3.1 = JSON Schema 2020-12)
    from jsonschema import Draft202012Validator as Validator
    DIALECT = "2020-12"
except Exception:  # 구버전 폴백 (if/then/const 는 Draft7 부터 지원)
    from jsonschema import Draft7Validator as Validator
    DIALECT = "draft7"

SPEC = "token-usage-api.v2.yaml"

failures = []


def build(schemas, name):
    """component 스키마 하나를 $defs 로 자립시켜 $ref 를 해소한다."""
    s = dict(schemas[name])
    s["$defs"] = schemas
    return json.loads(json.dumps(s).replace("#/components/schemas/", "#/$defs/"))


def expect(label, validator, inst, want_valid):
    errs = list(validator.iter_errors(inst))
    ok = not errs
    good = ok == want_valid
    print(f"[{'ok' if good else 'FAIL'}] {label}: valid={ok} expected={want_valid}")
    if not good:
        failures.append((label, [e.message for e in errs[:3]]))


def main():
    print(f"jsonschema dialect: {DIALECT}")
    doc = yaml.safe_load(open(SPEC, encoding="utf-8"))
    schemas = doc["components"]["schemas"]

    print("\n== schema sanity (check_schema) ==")
    for name in schemas:
        try:
            Validator.check_schema(build(schemas, name))
            print(f"[ok] {name}")
        except Exception as e:  # noqa: BLE001
            print(f"[FAIL] {name}: {e}")
            failures.append((f"check_schema {name}", [str(e)]))

    print("\n== declared examples must be VALID ==")
    for name, sch in schemas.items():
        exs = sch.get("examples")
        if not exs:
            continue
        v = Validator(build(schemas, name))
        for i, ex in enumerate(exs):
            expect(f"{name} example #{i}", v, ex, True)

    print("\n== UsageRecord userType<->userId if/then regression ==")
    rec = Validator(build(schemas, "UsageRecord"))
    base = {"model": "m", "inputTokens": 1, "outputTokens": 1, "requests": 1}

    negatives = [
        ("identified + userId null", {**base, "userType": "identified", "userId": None}),
        ("identified + userId missing", {**base, "userType": "identified"}),
        ("anonymous + userId null", {**base, "userType": "anonymous", "userId": None}),
        ("anonymous + userId missing", {**base, "userType": "anonymous"}),
        ("unclassified + userId string", {**base, "userType": "unclassified", "userId": "u"}),
        ("missing model", {"userType": "unclassified", "userId": None,
                           "inputTokens": 1, "outputTokens": 1, "requests": 1}),
        ("empty model", {**base, "model": "", "userType": "unclassified", "userId": None}),
    ]
    for label, inst in negatives:
        expect(f"neg: {label}", rec, inst, False)

    positives = [
        ("identified + userId string", {**base, "userType": "identified", "userId": "u"}),
        ("anonymous + userId string", {**base, "userType": "anonymous", "userId": "anon-1"}),
        ("unclassified + userId null", {**base, "userType": "unclassified", "userId": None}),
    ]
    for label, inst in positives:
        expect(f"pos: {label}", rec, inst, True)

    print("\n== generatedAt KST(+09:00) regression ==")
    page = Validator(build(schemas, "UsagePage"))
    base_page = {
        "serviceGroup": "G", "service": "S",
        "date": "2026-06-15", "records": [],
    }
    expect("gen KST +09:00", page, {**base_page, "generatedAt": "2026-06-16T02:05:00+09:00"}, True)
    expect("gen UTC Z (reject)", page, {**base_page, "generatedAt": "2026-06-16T17:05:00Z"}, False)
    expect("gen +00:00 (reject)", page, {**base_page, "generatedAt": "2026-06-16T17:05:00+00:00"}, False)

    if failures:
        print(f"\n{len(failures)} FAILURE(S):")
        for label, msgs in failures:
            print(f"  - {label}")
            for m in msgs:
                print(f"      {m}")
        sys.exit(1)
    print("\nAll example / if-then checks passed.")


if __name__ == "__main__":
    main()
