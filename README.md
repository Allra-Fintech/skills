# Allra Skills

회사 내 반복 업무를 같은 기준으로 처리하기 위한 공용 AI 스킬 저장소입니다.

## 사용 대상

기획자, 디자이너, 프론트엔드, 백엔드, QA가 공통 산출물 형식과 작업 기준을 맞춰야 할 때 사용합니다.

## 설치 및 업데이트

설치:

```bash
npx skills add Allra-Fintech/skills
```

업데이트:

```bash
npx skills update Allra-Fintech/skills
```

## 설치용 프롬프트

```text
현재 환경에 Allra Fintech 공용 skills 저장소와 skill-creator를 설치해줘.

작업 순서
1. `node -v`, `npm -v`로 실행 가능 여부를 확인한다.
2. 아래 명령으로 설치한다.
   `npx skills add Allra-Fintech/skills`
   `npx skills add anthropics/skills --skill skill-creator`
3. 설치 후 사용 가능한 스킬 목록을 짧게 정리한다.
4. 마지막에 업데이트 명령 `npx skills update`를 안내한다.
```

## 저장소 구조

```text
skills/
├── planning/
├── design/
├── frontend/
└── backend/
```

## 포함된 스킬

| 영역       | 스킬           | 설명                                                                   | 경로                            |
| ---------- | -------------- | ---------------------------------------------------------------------- | ------------------------------- |
| 기획       | `prd-writer`   | 기능 아이디어, 회의 메모, 정책, VOC 등을 근거 기반 PRD로 정리하는 스킬 | `skills/planning/prd-writer/`   |
| 기획       | `issue-writer` | 요구사항, PRD, API 변경사항을 실행 가능한 이슈 초안으로 정리하는 스킬  | `skills/planning/issue-writer/` |
| 디자인     | `design-feedback` | 화면, 플로우, 컴포넌트 등 디자인 산출물에 대한 구조적 피드백 스킬     | `skills/design/design-feedback/` |
| 디자인     | `ux-copy`      | 버튼, 온보딩, 에러 메시지, CTA 등 제품 내 UX 카피 작성 및 검토 스킬   | `skills/design/ux-copy/`        |
| 디자인     | `idea`         | 기능, 플로우, 화면 구성 등 UX 개선 아이디어 제공 스킬                  | `skills/design/idea/`           |
| 디자인     | `hypothesis`   | 데이터 기반 가설 수립 및 검증 방법 설계 스킬                           | `skills/design/hypothesis/`     |
| 프론트엔드 | 없음           | 현재 등록된 전용 스킬 없음                                             | `skills/frontend/`              |
| 백엔드     | 없음           | 현재 등록된 전용 스킬 없음                                             | `skills/backend/`               |

## 새 스킬 만들기

새 스킬이 필요하면 `skill-creator`를 활용해 초안을 만들고, 결과물은 역할별 폴더 아래에 추가합니다.

```bash
npx skills add anthropics/skills --skill skill-creator
```

- `skills/planning/`
- `skills/design/`
- `skills/frontend/`
- `skills/backend/`

## 운영 원칙

- 스킬은 회사 표준과 실제 협업 방식을 반영해야 합니다.
- 추상 설명보다 실행 가능한 규칙, 체크리스트, 템플릿 중심으로 작성합니다.
- 산출물 형식은 일관된 마크다운 구조를 유지합니다.

## 라이선스

이 저장소는 Allra Fintech 내부 사용을 위한 자산입니다. 자세한 내용은 [LICENSE](./LICENSE)를 참고하세요.
