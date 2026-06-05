# 핸드오프 디렉토리 규약 — /project:orchestrate

> ADR-008 결정 3 — 구조화 핸드오프 디렉토리 + 인라인 주입 병행

이 디렉토리는 `/project:orchestrate` 실행마다 생성되는 **task-id 디렉토리**를 담는다.
런타임 산출물이므로 `.gitignore` 로 git 추적 제외. 이 `README.md` 와 `.gitkeep` 만 보존.

---

## 구조

```
.claude/state/orch/
├── .gitkeep                                    # 디렉토리 보존 마커 (커밋 대상)
├── README.md                                   # 이 파일 (커밋 대상)
└── <task-id>/                                  # 런타임 산출물 (gitignore)
    ├── request.md    # 원본 요청 + 라우팅 판정 계획
    ├── plan.md       # 단계별 라우팅 계획 (어떤 에이전트 어떤 순서로)
    ├── research.md   # researcher 에이전트 산출물 (없으면 파일 없음)
    ├── adr.md        # architect 산출물 (없으면 파일 없음)
    ├── design.md     # designer 에이전트 산출물 (없으면 파일 없음)
    ├── impl.md       # developer 산출물 요약 (실제 코드는 git diff)
    ├── review.md     # reviewer 산출물 (APPROVED / NEEDS REVISION)
    ├── qa.md         # qa 산출물 (있으면)
    └── final.md      # supervisor 통합 리포트 (항상 생성)
```

---

## task-id 규칙

형식: `<ISO-8601-no-colon>-<slug>`

예: `2026-06-05T14-30-00-add-oauth-pkce`

- ISO 타임스탬프: 초 단위 고유성 보장
- slug: 요구사항 → kebab-case (40 자 cap)
  - 한글: romanize 또는 `task` fallback
  - 예: "OAuth2 PKCE 추가" → `add-oauth2-pkce`
  - 예: "사용자 인증 개선" → `task` (한글 romanize 불확실 시)
- 충돌 시: `-2`, `-3` suffix

---

## gitignore 정책

```gitignore
# orch 핸드오프 런타임 산출물 (gitignore)
.claude/state/orch/*/
!.claude/state/orch/.gitkeep
!.claude/state/orch/README.md
```

qa-browser 패턴 (`.claude/state/qa-browser/`) 과 100% 일관 (ADR-008 결정 3).

---

## 영구 보관 방법 (선택)

특정 task 를 영구 보관하려면 수동으로 복사:

```bash
cp -r .claude/state/orch/<task-id>/ docs/orch-archive/<task-id>/
git add docs/orch-archive/<task-id>/
git commit -m "docs: orchestrate <task-id> 산출물 영구 보관"
```

본 ADR-008 범위 외 — 팀 정책으로 결정.

---

## 동시 실행 격리

task-id 가 초 단위 timestamp 를 포함해 동시 실행 시에도 디렉토리 충돌 없음.
두 `/project:orchestrate` 가 동시 실행되는 경우 각 task-id 가 독립 디렉토리를 사용.

---

*ADR-008 결정 3 (핸드오프 규약) | F013 세션 1 산출물*
