# /role — 롤(페르소나) 전환 (Codex CLI)

Codex CLI는 단일 에이전트이므로 Claude Code의 서브에이전트 대신 **롤(페르소나) 전환** 방식을 사용한다. 이 프롬프트는 현재 세션이 수행할 롤을 명시적으로 선언한다.

> 사용 예시:
> - `/role planner`
> - `/role developer F003`
> - `/role qa F002`

---

사용자가 `/role <이름> [추가인자]` 형식으로 호출했다면 다음을 수행하세요.

## 1. 롤 문서 로드

아래 경로의 문서를 **반드시 읽고**, 해당 롤의 "핵심 원칙"·"프로세스"·"금지 사항"을 이번 세션 동안 준수한다는 점을 명시적으로 확인하세요.

| 인자 | 로드할 문서 |
|---|---|
| `planner` | `.codex/roles/planner.md` |
| `architect` | `.codex/roles/architect.md` |
| `developer` | `.codex/roles/developer.md` |
| `reviewer` | `.codex/roles/reviewer.md` |
| `qa` | `.codex/roles/qa.md` |

## 2. 전환 알림 출력

```
🎭 롤 전환: [이전 롤 | none] → [새 롤]
──────────────────────────────────────
핵심 원칙:
  - [핵심 원칙 1]
  - [핵심 원칙 2]

지금부터 이 롤의 권한과 금지사항을 따릅니다.
──────────────────────────────────────
```

## 3. 추가 인자 처리

Feature ID(`F003`)가 함께 전달되면 즉시 해당 Feature 정보를 `feature_list.json`에서 읽어 출력하고, 해당 롤에 맞는 다음 동작을 제안하세요.

- `developer F003` → F003의 status를 `in-progress`로 변경 (post-write-check 포함), 브랜치 생성 제안
- `qa F002` → F002의 `acceptance_criteria`를 출력하고 검증 계획 제시
- `reviewer F004` → 해당 Feature의 변경 파일을 `git diff`로 확인하고 리뷰 시작

## 4. 권장 실행 모드

롤별 권장 Codex CLI 실행 모드:

| 롤 | 권장 `--profile` | 권장 승인 모드 |
|---|---|---|
| Planner | (기본) | `on-request` |
| Architect | `review` (읽기 전용으로 조사 → 필요 시 전환) | `on-request` |
| Developer | (기본) | `on-request` |
| Reviewer | `review` (read-only) | `on-request` |
| QA | (기본, workspace-write) | `on-request` |

전환 방법: `/approvals on-request`, `/permissions`, 또는 재시작 시 `codex --profile review`

## 금지 사항

- ❌ 롤 전환 후 해당 롤 문서를 읽지 않고 작업 시작
- ❌ QA 롤이 아닌데 `passes: true`로 변경
- ❌ 여러 롤을 동시에 수행 (반드시 한 시점에 하나의 롤)
