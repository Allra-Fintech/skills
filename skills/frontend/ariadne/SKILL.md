---
name: ariadne
description: 백엔드 서버 코드를 기준으로 프론트의 API 구현 상태를 로컬 상태 파일에 저장하고, 이후에는 GitHub merge PR 기준 변경 범위만 다시 점검하는 API parity 스킬이다.
---

# ariadne

한 줄 설명: 백엔드 API 목록을 기준으로 프론트의 호출 흔적을 점검하고, 불확실하면 review로 남기는 증분 검증 스킬이다.

## 언제 사용해야 하는지

- 프론트 API 계층이 백엔드 서버 코드와 대체로 맞는지 빠르게 확인하고 싶을 때
- 백엔드 API 목록을 로컬 기준 catalog로 고정하고, 이후 변경분만 다시 보고 싶을 때
- "자동으로 확신하지 말고, 애매하면 review로 남겨달라"는 기준이 중요할 때
- wrapper나 템플릿 문자열 때문에 완전 자동 판정이 어려운 프로젝트에서 보수적으로 점검하고 싶을 때

## 먼저 읽어야 할 파일

- 설정 예시는 [references/config-template.md](./references/config-template.md)
- 실제 CLI는 [scripts/api_parity_state.py](./scripts/api_parity_state.py)

## 기본 전제

- 현재 작업 디렉터리는 프론트엔드 레포라고 가정한다.
- 백엔드 truth source는 서버 코드다.
- 프론트 evidence도 현재 로컬 워크스페이스의 파일 내용을 기준으로만 모은다.
- 증분 범위는 GitHub merge PR cursor를 기준으로 계산한다.
- `.ariadne/`는 로컬 상태 저장소이며 Git tracked artifact로 올리지 않는다.
- API 식별자는 항상 `HTTP method + normalized path` 조합이다.
- 자동 판정은 보수적으로 한다. 조금이라도 애매하면 `needs-review`로 둔다.

## 입력으로 기대하는 정보

### `init`

- 백엔드 코드가 있는 루트 경로
- 프론트 호출 코드를 읽을 루트 경로
- 필요하면 GitHub repo slug와 base branch
- 필요하면 route glob, frontend glob, ignore glob
- 필요하면 path normalization rule

### `check`

- 기본값은 저장된 마지막 처리 PR 이후 merge된 PR
- 필요하면 `--repo`, `--base-branch`, `--since-pr`, `--until-pr`
- 공통 HTTP 레이어 변경처럼 전체 재점검이 필요하면 `--full-rescan`

## 로컬 파일 계약

- `.ariadne/config.yaml`
  - 백엔드/프론트 루트, glob, ignore, full rescan 규칙, path normalization, wrapper 힌트를 저장한다.
- `.ariadne/catalog.json`
  - 백엔드 기준 API 목록과 route evidence를 저장한다.
- `.ariadne/state.json`
  - API별 현재 상태, reason code, frontend/backend evidence, 원격 PR cursor, 수동 판정과 마지막 실행 결과를 저장한다.
- `.ariadne/waivers.yaml`
  - 합의된 예외만 저장한다.

## 4단계 워크플로

1. `init`
   - 백엔드 route를 스캔해 `catalog.json`을 만든다.
   - 프론트 호출 흔적을 모아 첫 상태를 기록한다.
   - 기존 복잡한 v1 상태 파일은 버리고 v2 계약으로 다시 시작한다.
2. `check`
   - 기본적으로 마지막 처리 PR 이후 merge된 PR만 읽는다.
   - 변경 파일이 `full_rescan_globs`에 걸리면 전체 재점검으로 폴백한다.
   - exact match만 자동 `matched`로 올리고, frontend-only나 method drift도 기본적으로 `needs-review`로 남긴다.
3. `report`
   - 짧은 마크다운 리포트만 출력한다.
   - 검증 컨텍스트에는 repo, base branch, 처리 PR 범위, 처리 PR 수를 보여준다.
4. `resolve`
   - 수동 검토 결과를 `matched`, `mismatch`, `waived`로 반영한다.
   - 수동 판정은 다음 `check`에서도 기본 유지되고, 강한 반증이 나오면 `manual-resolution-conflict`로 review에 올린다.
   - waiver는 `waivers.yaml`에도 함께 기록한다.

## 상태 정의

- `matched`
  - 메서드와 경로가 명확하게 맞는 프론트 evidence가 있다.
- `missing`
  - 백엔드 API는 있지만 프론트 evidence가 없다.
- `mismatch`
  - 수동 검토로 불일치가 확정된 상태다.
- `needs-review`
  - 템플릿 문자열, wrapper 힌트, 불완전한 path shape처럼 확신하기 어려운 경우다.
- `waived`
  - 의도된 차이로 합의되어 다음 실행부터 예외 처리한다.

### reason code 예시

- `no-frontend-evidence`
- `method-path-drift`
- `frontend-only`
- `uncertain-binding`
- `manual-resolution-conflict`
- `manual-waiver`
- `manual-match`
- `manual-mismatch`

## Python CLI 표면

- `python3 skills/frontend/ariadne/scripts/api_parity_state.py init ...`
- `python3 skills/frontend/ariadne/scripts/api_parity_state.py check ...`
- `python3 skills/frontend/ariadne/scripts/api_parity_state.py report`
- `python3 skills/frontend/ariadne/scripts/api_parity_state.py resolve --api-key ... --status matched|mismatch|waived --note ...`

## 품질 체크리스트

- `catalog.json`, `state.json`, `waivers.yaml`, `config.yaml`만 남겼는가
- `check`가 merge된 GitHub PR changed files를 기준으로 후보 API를 좁혔는가
- 명확한 근거가 없는데 `matched`로 확정하지 않았는가
- `needs-review` 항목이 report의 `조치 필요 항목`에 드러나는가
- 수동 `matched`/`mismatch`가 다음 `check`에서도 그대로 유지되는가
- waiver는 실제 합의된 항목만 저장했는가
- v1 명령어를 더 이상 정상 워크플로처럼 안내하지 않는가

## 예시 요청

- `ariadne init으로 지금 레포 기준 catalog부터 다시 잡아줘.`
- `main 브랜치에 merge된 PR 기준으로 마지막 체크 이후 바뀐 API만 ariadne check로 다시 봐줘.`
- `report만 출력해서 지금 조치가 필요한 API가 뭔지 보여줘.`
- `GET /users/{id}는 의도된 차이니까 ariadne resolve로 waived 처리해줘.`
- `GET /ghosts는 실제 불일치가 맞으니 ariadne resolve로 mismatch 처리해줘.`
