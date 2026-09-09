# /project:atlassian — Jira·Confluence 연동

Atlassian 공식 MCP 커넥터를 하네스 산출물과 연결한다. **API 래퍼는 없다** — 에이전트가
MCP 도구를 직접 부르고, 매핑·멱등성만 `atlassian_map.py` 가 담당한다.

규약 전문은 [atlassian 스킬](../skills/atlassian/SKILL.md) 을 따른다.

## 사용

```
/project:atlassian check                        # 커넥터 연결·권한·사이트 확인
/project:atlassian import <ISSUE-KEY>           # Jira 이슈 → feature_list 초안 (읽기)
/project:atlassian pending                      # 발행 대상 나열 (신규·변경분)
/project:atlassian publish adr ADR-014 --space SD   # ADR → Confluence (승인 필요)
/project:atlassian publish checkpoint <파일명> --space SD
/project:atlassian comment <ISSUE-KEY> --feature F001   # 판정 결과 → Jira 코멘트
/project:atlassian map                          # 현재 매핑 표 출력
```

## 실행 순서

### `check` — 항상 먼저

```bash
claude mcp list | grep -i atlassian
```

`✔ Connected` 가 아니면 **여기서 멈추고** 사용자에게 알린다. claude.ai 커넥터 설정에서
승인해야 하며, 비대화형 세션에서는 OAuth 를 진행할 수 없다. 커넥터가 없어도 하네스는
정상 동작한다 — 연동만 불가하다.

연결됐으면 `getAccessibleAtlassianResources` 로 사이트·`cloudId`·스코프를 출력한다.

### `import <ISSUE-KEY>` — 읽기 전용

1. `getJiraIssue` 로 이슈를 읽는다
2. 스킬의 번역 표대로 `feature_list.json` 초안을 만든다 —
   **`description` 을 그대로 복사하지 않고 검증 가능한 `acceptance_criteria` 로 분해**한다
3. `id` 는 우리가 부여한다 (`FNNN`). Jira 키는 `external.jira` 에 보존한다
4. 모호한 설명은 모호한 채로 옮기지 않는다 — 사용자에게 되묻는다
5. `passes: false`, `status: "todo"` 로 시작한다

### `pending` — 발행 대상 확인

```bash
python3 .claude/bin/atlassian_map.py pending --kind adr
```

### `publish <kind> <local-id> --space <KEY>` — 승인 필요

발행은 외부 공개이고 팀에 알림이 간다. **사용자 승인 없이 발행하지 않는다.**

```bash
D=$(python3 .claude/bin/atlassian_map.py digest <파일경로>)
python3 .claude/bin/atlassian_map.py check <kind> <local-id> --digest "$D"
```

종료 코드로 분기한다 — 모델의 기억으로 판단하지 않는다:

| exit | 의미 | 행동 |
|---|---|---|
| 0 | 최신 | **발행하지 않고 종료** |
| 2 | 신규 | `createConfluencePage` |
| 3 | 변경 | `updateConfluencePage` (기록된 URL 대상) |

발행 후 **반드시** 기록한다 — 빠뜨리면 다음 실행이 중복 생성한다:

```bash
python3 .claude/bin/atlassian_map.py put <kind> <local-id> --url "<URL>" --id "<pageId>" --digest "$D"
```

Confluence 본문 포맷은 `getContentFormatGuide` 로 확인한다 (마크다운이 그대로 통하지 않을 수 있다).

### `comment <ISSUE-KEY> --feature <FNNN>`

`verify_loop.py status <FNNN>` 의 판정 기록을 요약해 `addCommentToJiraIssue` 로 남긴다.
판정을 **만들지 않는다** — 이미 기록된 것만 옮긴다.

## 호출 기준

다음에 해당하면 이 커맨드가 유용하다:

- 팀이 Jira 로 요구사항을 관리하고, 그것을 하네스 사이클에 넣고 싶을 때 (`import`)
- 설계 근거(ADR)를 리포 밖 팀 구성원에게 보여야 할 때 (`publish adr`)
- 판정 결과를 이슈 히스토리에 남겨야 할 때 (`comment`)

해당 없으면 호출하지 않는다. **옵셔널** — 호출하지 않아도 하네스 동작에 영향 없다.

## 하지 않는 것

- 자동 발행 (handoff·lint 가 부르지 않는다)
- Jira 상태로 `passes` 변경 (`passes` 는 QA 단독 권한)
- feature_list 전체 일괄 이슈 생성
- Atlassian 편집 내용의 리포 역반영 (**우리 리포가 SSOT**)

## 변형 제약

**`claude.vela.*` 계열 전용**. 다른 변형엔 `atlassian_map.py` / 이 커맨드 / atlassian 스킬이
없어 명령 미인식이다. `localllm` 계열(OpenCode 호스트)에는 이 커넥터 자체가 없다.
