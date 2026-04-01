# Ariadne v2 Config Template

`ariadne`는 기본적으로 자동 탐색을 시도하고, 반복적으로 같은 파일을 잘못 읽을 때만 `config.yaml`을 보정한다.
PR cursor는 `config.yaml`이 아니라 `state.json`에 저장된다.
v2는 설정 범위를 최소화한다. 복잡한 profile, rubric, 별도 PR ledger, topology 설정은 없다.

## `config.yaml` 기본 예시

```yaml
schema_version: 2

backend_roots:
  - "backend"

frontend_roots:
  - "src"

backend_route_globs:
  - "**/*controller.ts"
  - "**/*route.ts"
  - "**/*.py"
  - "**/*Controller.java"

frontend_globs:
  - "src/**/*.ts"
  - "src/**/*.tsx"
  - "src/**/*.js"
  - "src/**/*.jsx"

ignore_globs:
  - "**/*.test.ts"
  - "**/*.spec.ts"
  - "**/__tests__/**"

full_rescan_globs:
  - "src/lib/http/**/*.ts"
  - "src/shared/http/**/*.ts"

path_normalization_rules:
  - match: "^/api/v[0-9]+"
    replace: ""

frontend_wrapper_callees:
  - "handleProcedure"
```

## 각 항목이 하는 일

- `backend_roots`
  - 백엔드 route 파일을 찾을 루트다.
- `frontend_roots`
  - 프론트 호출 흔적을 읽을 루트다.
- `backend_route_globs`
  - 백엔드 API inventory 대상 파일 패턴이다.
- `frontend_globs`
  - 프론트 evidence 대상 파일 패턴이다.
- `ignore_globs`
  - 점검에서 제외할 파일 패턴이다.
- `full_rescan_globs`
  - merge된 PR changed files 안에 이 파일이 있으면 `check`가 부분 점검 대신 전체 재점검으로 폴백한다.
- `path_normalization_rules`
  - `/api/v1` 제거 같은 공통 path 정규화 규칙이다.
- `frontend_wrapper_callees`
  - literal `method`/`path`를 같이 받는 wrapper가 있으면 여기에 callee 이름만 넣는다.

## 원격 PR 기준 메모

- `init`와 `check`는 `gh` 인증이 되어 있어야 한다.
- repo slug와 base branch는 CLI 인자로 줄 수 있고, 비워 두면 현재 git remote와 GitHub repo 정보에서 자동 감지한다.
- 마지막 처리한 PR 번호와 시각은 `.ariadne/state.json` 안의 cursor에 저장된다.

## 편집 규칙

- 자동으로 잘 읽히는 값은 굳이 적지 않는다.
- `full_rescan_globs`는 정말 전체 재점검이 필요한 파일만 넣는다.
- `frontend_wrapper_callees`는 명확한 literal method/path를 함께 전달하는 경우에만 사용한다.
- wrapper 안에서 signature를 따라가거나 schema를 깊게 추론하는 용도로 설정을 늘리지 않는다.
- path normalization은 최소 규칙만 유지한다.

## `waivers.yaml` 예시

```yaml
schema_version: 2

waivers:
  - api_key: "GET /users/{id}"
    reason_code: "manual-waiver"
    note: "Template literal path는 현재 수동 검토로 허용"
    updated_at: "2026-04-02T09:00:00Z"
```

## `waivers.yaml` 편집 규칙

- 실제로 합의된 예외만 저장한다.
- `api_key` 기준으로 중복 없이 유지한다.
- 임시 디버깅이나 단순 실험은 waiver로 남기지 않는다.
