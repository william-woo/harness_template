---
name: atlassian
description: >-
  Jira·Confluence 를 하네스 산출물과 연결하는 규약. Atlassian 공식 MCP 커넥터가 있을 때
  이슈를 feature_list 초안으로 가져오고(읽기), ADR·판정을 발행한다(쓰기, 승인 필요).
  매핑·멱등성은 atlassian_map.py 가 담당한다. 커넥터 미연결 시 안내만 하고 차단하지 않는다.
---

# Atlassian 연동 스킬

## 이 스킬이 존재하는 이유

Atlassian **공식 MCP 커넥터**(`mcp.atlassian.com/v1/mcp`)가 Jira·Confluence 도구를 이미
제공합니다. 그래서 이 하네스는 **API 래퍼를 만들지 않습니다** — 에이전트가 MCP 도구를 직접
부릅니다.

빈 곳은 도구가 아니라 **매핑**입니다: 우리 `FNNN` 이 어느 Jira 이슈인지, 이 ADR 을 이미
발행했는지. 이 스킬은 그 규약을, `atlassian_map.py` 는 그 상태를 담당합니다.

## 전제 확인 (항상 먼저)

```bash
claude mcp list | grep -i atlassian     # ✔ Connected 여야 한다
```

미연결이면 **작업을 시작하지 말고** 사용자에게 알립니다 — claude.ai 커넥터 설정에서 승인해야
하고, 비대화형 세션에서는 OAuth 를 진행할 수 없습니다. 커넥터가 없어도 **하네스는 정상
동작합니다**(graceful degrade) — 연동만 불가합니다.

`cloudId` 는 `getAccessibleAtlassianResources` 로 얻습니다. 사이트 호스트명
(`obigoinc.atlassian.net`)을 그대로 `cloudId` 로 넘겨도 대부분 동작합니다.

## 방향 규약 — 우리 리포가 SSOT

| 방향 | 허용 | 이유 |
|---|---|---|
| Atlassian → 하네스 | **읽기만** (초안 생성 입력) | 요구사항의 출발점은 팀 도구에 있다 |
| 하네스 → Atlassian | **발행** (`publish`) | 산출물의 진실은 리포에 있다 |
| Atlassian 편집 → 하네스 역반영 | **금지** | 두 SSOT 는 반드시 어긋난다 |

Confluence 페이지를 사람이 고쳤다면, 그 변경을 리포로 되가져오지 않습니다. 리포를 고치고
다시 발행합니다. 이 방향을 어기면 "어느 쪽이 맞는가"를 매번 판단해야 합니다.

## 읽기 — Jira 이슈 → feature_list 초안

1. `getJiraIssue` 로 이슈를 읽습니다 (`fields`: summary, description, issuetype, priority, status)
2. 다음으로 **번역**합니다 — 그대로 복사하지 않습니다:

| Jira | feature_list.json | 주의 |
|---|---|---|
| `summary` | `title` | 그대로 |
| `description` | `acceptance_criteria` | **검증 가능한 문장으로 분해** — 산문을 그대로 넣지 않는다 |
| `priority` | `priority` | critical/high/medium/low 로 정규화 |
| `key` (PROJ-123) | `external.jira` | 매핑 보존 |
| — | `id` (FNNN) | 우리가 부여. Jira 키를 id 로 쓰지 않는다 |

3. `acceptance_criteria` 는 **planning 스킬의 규칙**을 따릅니다 — "로그인이 잘 되어야 한다"가
   아니라 "이메일/비밀번호로 로그인 시 200 + 토큰 반환, 실패 시 401" 처럼 검증 가능해야 합니다.
   Jira 설명이 모호하면 **모호한 채로 옮기지 말고** 사용자에게 되묻습니다.
4. `passes: false`, `status: "todo"` 로 시작합니다.

## 쓰기 — 발행 (승인 필요)

발행은 **외부 공개**이고 팀에 알림이 갑니다. PR 과 같은 층위로 다룹니다 —
사용자 승인 없이 발행하지 않습니다.

### 순서 (이 순서를 지킵니다)

```bash
# ① digest 계산 — 내용이 바뀌었는지 판정의 근거
D=$(python3 .claude/bin/atlassian_map.py digest docs/adr/ADR-014-*.md)

# ② 발행 필요 여부를 코드에 묻습니다 (모델이 기억으로 판단하지 않습니다)
python3 .claude/bin/atlassian_map.py check adr ADR-014 --digest "$D"
#   exit 0 → 최신, 발행하지 않고 종료
#   exit 2 → 신규: createConfluencePage
#   exit 3 → 변경: updateConfluencePage (기록된 URL 대상)

# ③ MCP 도구로 발행 (신규/갱신 분기)

# ④ 결과를 기록 — 이 단계를 빠뜨리면 다음에 중복 발행됩니다
python3 .claude/bin/atlassian_map.py put adr ADR-014 --url "<발행된 URL>" --id "<pageId>" --digest "$D"
```

②를 건너뛰고 바로 발행하면 **중복 페이지**가 생깁니다. ④를 빠뜨리면 다음 실행이 같은 것을
다시 만듭니다. 두 단계가 이 스킬의 핵심입니다.

### 발행 대상별 매핑

| 하네스 산출물 | Atlassian | kind | 도구 |
|---|---|---|---|
| `docs/adr/ADR-NNN-*.md` | Confluence 페이지 | `adr` | `createConfluencePage` / `updateConfluencePage` |
| 체크포인트 (`.claude/state/checkpoints/*.md`) | Confluence 페이지 | `checkpoint` | 동일 |
| reviewer/qa 판정 | Jira 코멘트 | `judgement` | `addCommentToJiraIssue` |
| feature 상태 전이 | Jira 상태 | `feature` | `transitionJiraIssue` (**단방향만**) |

`getContentFormatGuide` 로 Confluence 본문 포맷을 확인하십시오 — 마크다운이 그대로 통하지
않는 경우가 있습니다.

### 일괄 발행

```bash
python3 .claude/bin/atlassian_map.py pending --kind adr   # 신규·변경분만 나열
```

미발행·변경분만 나옵니다. 목록이 비면 발행할 것이 없습니다.

## 하지 않을 것

- **자동 발행 금지** — 사용자가 요청할 때만 발행합니다. handoff·lint 가 자동으로 부르지 않습니다
- **Jira 상태를 진실로 취급 금지** — `passes` 는 QA 에이전트 단독 권한입니다.
  Jira 에서 Done 으로 바뀌었다고 `passes: true` 로 만들지 않습니다
- **이슈 대량 생성 금지** — feature_list 전체를 Jira 로 밀어넣지 않습니다.
  요청된 건만, 하나씩
- **매핑 파일을 손으로 편집 금지** — `atlassian_map.py put` 으로만 씁니다

## 커넥터가 없을 때

안내만 출력하고 정상 종료합니다. 이 스킬의 모든 기능은 **옵셔널**입니다 —
`atlassian_map.py` 는 MCP 없이도 동작합니다(로컬 매핑 조회·digest 계산).

## 호스트 제약

이 스킬은 **Claude Code 호스트 전용**입니다. `localllm` 계열(OpenCode)에는 이 커넥터가
없습니다. OpenCode 도 MCP 를 지원하지만 별도 설정이며 **미검증**입니다 — 검증 없이
동작한다고 적지 않습니다.
