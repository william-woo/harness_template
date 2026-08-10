# ADR-006: Design-Pick 자동화 + `claude.gstack.auto.design` 변형 신설

> Feature: F011 — Phase 7 Design-Pick + 디자인 변형
> 작성: architect 에이전트 | 날짜: 2026-06-02

## 상태

`Accepted` — 본 ADR 은 사용자가 확정한 옵션 2 (자료 + designer 에이전트 + `/project:design-pick` 커맨드)
위에 8 개 결정을 명시한다. 토큰 자동 추출 (옵션 3) 은 후속 phase 로 분리한다.
F005 brain · F006 host · F007 design-review · F009 lint · F010 backup-sync 의
**외부 의존성 0 + hook-failure-tolerance + 옵셔널 보장 + 단일 파일 헬퍼 + 서브커맨드 +
변형 미러** 패턴을 그대로 일관 유지한다.

---

## 컨텍스트

### F011 의 본질적 질문 — "다운스트림 UI 프로젝트가 디자인을 어떻게 정하느냐"

사용자가 `src/docs/design/ui/` 에 4 개 브랜드 디자인 시스템 명세를 미리 추가해 두었다:

| 파일 | 줄수 | 정체성 | 시그니처 |
|---|---|---|---|
| `apple-design.md` | 287 | 사진 우선 미니멀 | 단일 #0066cc 블루, SF Pro, 그라데이션 0, 풀뷰포트 타일 |
| `claude-design.md` | 289 | 따뜻한 편집물 | 크림 + 코랄, Copernicus 슬랩 세리프, 매거진 레이아웃 |
| `spotify-design.md` | 246 | 다크 콘텐츠 우선 | #121212 채도 0 배경 + 그린 #1ed760, 알약/원형 버튼 |
| `tesla-design.md` | 286 | 급진적 미니멀 | 풀뷰포트 사진, 단일 블루, UI 거의 소거 |

각 파일은 동일 구조 (Overview → Colors → Typography → 컴포넌트). **LLM 컨텍스트로 그대로 활용 가능**.

→ 다운스트림 UI 프로젝트가 새로 시작할 때 "어떤 디자인 정체성을 채택하느냐" 라는 **반복되는 결정**을
designer 에이전트 + tokens.json 산출물 + `/project:design-pick` 커맨드로 자동화한다.

### 사용자 사전 결정 (확정)

- **옵션 2 채택**: 자료 + designer 에이전트 + `/project:design-pick` 커맨드.
- **옵션 3 (토큰 자동 추출 + LINT-DESIGN) 후속 phase 분리**: md 파싱 신뢰성 검증 필요. 본 phase 에서는
  designer 에이전트가 디자인 md 를 **LLM 으로 직접 읽어** 토큰을 정리한다 (코드 파서 X).

### 제약 (F005~F010 일관)

- **외부 의존성 0**: Python stdlib + bash + git CLI 만 (argparse + json + pathlib + datetime)
- **무회귀**: F001~F010 의 동작 무수정 — `.claude/settings.json` / 기존 에이전트 / lint.py /
  backup.py / brain.py / host.py 어떤 비트도 변경 안 함
- **옵셔널 보장**: `/project:design-pick` 호출 안 하면 하네스 동작에 영향 없음 (F005/F009/F010 일관)
- **단일 파일 헬퍼**: 헬퍼가 필요하면 `.claude/bin/design_pick.py` 하나로 (서브커맨드 분리)
- **`feature_list.json` `passes` 절대 미수정**: QA 단독 권한
- **`.claude/settings.json` 무수정**: Claude Code 공식 스키마 격리 (F006 ADR-001 결정 1)

### 자율 모드 분기 — `claude.gstack.auto.design` 가 5번째 변형으로 추가됨

현재 변형 매트릭스:

| 변형 | 정체성 | 자율 오버레이 | 디자인 오버레이 |
|---|---|---|---|
| ⓐ `claude/` (baseline) | Phase 0 동결, Karpathy 4원칙만 | ❌ | ❌ |
| ⓑ `claude.gstack/` (표준) | F001~F010 풀 산출물, 사용자 승인 모드 | ❌ | ❌ |
| ⓑ′ `claude.gstack.auto/` (자율) | ⓑ + 자율 모드 3 규칙 + gatekeeper | ✅ | ❌ |
| ⓒ `openai/.codex/` (codex stub) | F006 stub, Karpathy 만 | ❌ | ❌ |

F011 추가:

| 변형 | 정체성 |
|---|---|
| **ⓑ″ `claude.gstack.auto.design/` (자율 + 디자인)** | ⓑ′ + 디자인 오버레이 (designer.md, design-pick.md, design-references/ 4 파일) |

---

## 결정

### 결정 1 — 디자인 자료의 source-of-truth: **A. 메인 `.claude/` 가 SSoT, 변형 미러는 선별 포함**

**채택**: 메인 `.claude/` 가 모든 산출물 (designer 에이전트 + `/project:design-pick` 커맨드 + 디자인
참조 4 파일) 의 source-of-truth. 변형으로의 미러는 변형 정체성에 맞게 포함/제외.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) 메인 `.claude/` SSoT + 변형 미러는 선별 포함** | F005~F010 패턴 100% 일관 (모든 산출물은 메인에서 변형으로 미러), 메인이 working environment 로서 풀 기능, 디자인 오버레이 정의 자체가 메인에 있어 향후 디자이너가 추가 브랜드를 메인에 추가하면 자동 전파 가능 | 메인 (`harness_update_agent`) 자체가 UI 프로젝트 아닌데 디자인 자료를 보유 — 의미론적 불일치 약간 | **채택** |
| (B) `claude.gstack.auto.design/` 자체가 SSoT | 의미론적 일관 (디자인은 디자인 변형에만), 메인이 깔끔 | F005~F010 의 SSoT 패턴 위배, 향후 메인 외부에서 변형을 직접 편집해야 하는 첫 사례 → 미러링 자동화 불가, design-pick 커맨드도 변형에서만 사용 가능 (메인 dev 환경에서 design-pick 테스트 불가) | 부적합 — 패턴 깨짐 |
| (C) 하이브리드 — 4 ref md 는 변형에만, designer.md + design-pick.md 는 메인 + 변형 양쪽 | 의미론적 균형 (자료는 변형, 도구는 공유) | 두 SSoT 경계 학습 비용, designer 에이전트가 ref md 를 읽으려면 메인 환경에서는 path 가 다름 (변형의 경로) → 컨텍스트 분기 부담 | 부분 매력적이나 단점 우세 |

**근거**:

- **F005 brain.py · F009 lint.py · F010 backup.py** 모두 메인 `.claude/bin/*.py` 가 SSoT, 변형은
  메인의 미러. 디자인도 같은 정신.
- **메인 자체가 working dev environment**: 우리가 designer 에이전트 + tokens.json 시안을 메인에서
  실제로 테스트하지 않으면 발견되는 모든 회귀를 다운스트림 사용자가 짊어진다.
- **사용자 working pattern**: `src/docs/design/ui/*.md` 4 파일이 이미 메인에 있음. 변형은 메인 산출물의
  포장이지 독립 SSoT 가 아니다.

**핵심 분리** — "자료 위치" vs "사용 위치":

| 산출물 | 메인 위치 (SSoT) | 변형 위치 (미러) |
|---|---|---|
| 디자인 명세 4 파일 | `src/docs/design/ui/{apple,claude,spotify,tesla}-design.md` (이미 존재) | `claude.gstack.auto.design/harness/docs/design-references/{apple,claude,spotify,tesla}-design.md` |
| designer 에이전트 정의 | `.claude/agents/designer.md` (신규) | `claude.gstack.auto.design/harness/.claude/agents/designer.md` |
| `/project:design-pick` 커맨드 | `.claude/commands/design-pick.md` (신규) | `claude.gstack.auto.design/harness/.claude/commands/design-pick.md` |
| 토큰 출력 위치 | `.claude/design/tokens.json` (사용 시 생성 — 메인에선 데모용) | 다운스트림에서 `/project:design-pick` 실행 후 자체 `.claude/design/tokens.json` |
| tokens.json 스키마 정의 | `docs/design/F011-tokens-schema.md` (신규, 단일 소스) | `claude.gstack.auto.design/harness/docs/design/F011-tokens-schema.md` |

**경로 보정** — 메인의 디자인 명세는 `src/docs/design/ui/*.md` 이지만, 변형으로 미러될 때는
`docs/design-references/*.md` 로 **이름 변경 + 위치 이동**. 이유:

- 메인의 `src/` 는 "harness_template 의 소스" — `src/docs/` 는 메타 하네스 자기 자신의 디자인 자료 보관소.
- 변형 (`claude.gstack.auto.design/harness/`) 의 입장에선 `src/` 는 **다운스트림 사용자 코드** —
  하네스 산출물은 `docs/`, `.claude/` 에만. 따라서 변형 내부에서는 `docs/design-references/` 위치가 자연.
- designer 에이전트의 path 추출 로직 (결정 2 의 `_find_design_references()`) 이 두 경로를 모두 탐지:
  ```python
  def find_design_references() -> Path:
      candidates = [
          Path.cwd() / "docs" / "design-references",        # 다운스트림 (변형)
          Path.cwd() / "src" / "docs" / "design" / "ui",   # 메타 하네스 (메인)
      ]
      for p in candidates:
          if p.is_dir():
              return p
      return None
  ```

**무회귀**: 기존 `src/docs/design/ui/` 4 파일은 손대지 않는다. 변형으로 복사할 때만 이름 변경.

**영향받는 AC**: AC1 (변형 신설), AC2 (4 파일 포함), AC8 (메인 → 변형 미러)

---

### 결정 2 — `designer` 에이전트 설계: **opus 모델 + Read/Grep/Glob/Bash/Write + LLM-driven 토큰 추출**

**채택**: Architect 와 동일한 opus 모델, 디자인 명세를 LLM 으로 직접 읽어 비교표·추천·tokens.json 시안 생성.

| 항목 | 결정 | 근거 |
|---|---|---|
| **모델** | `claude-opus-4-7` | Gatekeeper (sonnet) 는 단순 PROCEED/ESCALATE 결정. designer 는 287~289 줄 명세 4 개를 동시 비교하고 추천 근거를 산문으로 작성하므로 opus 가 적절. Architect (opus) 와 같은 등급. |
| **도구** | `Read, Glob, Grep, Bash, Write` | Read (4 ref md 읽기), Glob/Grep (다운스트림 컨텍스트 — CLAUDE.md, feature_list.json, README 검색), Bash (tokens.json 생성 시 경로 mkdir, design_pick.py 호출), Write (tokens.json 직접 작성). Edit 는 제외 (tokens.json 은 항상 신규 작성 — `--force` 없이 덮어쓰기 차단은 design_pick.py 가 담당). |
| **입력 형식** | 자유 산문 + 선택적 구조 토큰 | 호출자는 자유롭게 의도 기술 ("HMI 다크 콘텐츠 우선 프로젝트"), 선택적 토큰 (`PROJECT_TYPE`, `TARGET_DEVICES`, `BRAND_DIRECTION`) 도 허용. F011 phase 의 단순성 우선 — 강제 스키마 X |
| **출력 형식** | 4 카테고리 (비교표 / 추천 / tokens.json 시안 / 적용 단계) | 결정 3 의 design-pick 커맨드가 이 4 카테고리를 그대로 표시 |
| **책임 범위** | 스타일 추천 + tokens.json 시안 생성**만** | 컴포넌트 디자인 (예: Button.tsx 작성) 은 Developer 책임. designer 는 토큰 결정까지만. F007 design-review 가 "감사" 인 것과 같이 designer 는 "선택" 까지만. |

#### designer.md 본문 골격

```markdown
---
name: designer
description: |
  디자인 결정 전문 에이전트. 4 브랜드 디자인 시스템 (Apple/Claude/Spotify/Tesla) 을 숙지하고,
  프로젝트 컨텍스트에 맞는 스타일 추천 + tokens.json 시안을 생성한다.
  예: "Use the designer agent to pick a design system for our HMI dashboard"
  주의: claude.gstack.auto.design 변형에서만 사용. 다른 변형엔 없음.
model: claude-opus-4-7
tools: Read, Glob, Grep, Bash, Write
---

# Designer Agent — 디자인 토큰 결정

## 역할
4 개 디자인 명세를 직접 읽어 프로젝트 컨텍스트에 맞는 브랜드를 추천하고,
tokens.json 시안 (색상/타이포/spacing/radius) 을 생성한다.

## 입력
- 프로젝트 컨텍스트 (CLAUDE.md, feature_list.json 자동 읽기)
- 사용자 의도 (자유 산문, `--brand=` 강제 선택, 선택적 PROJECT_TYPE/TARGET_DEVICES/BRAND_DIRECTION 토큰)

## 출력 (4 단계)
1. **비교표** — 4 브랜드를 색상·타이포·radius·접근성·복잡도 5 축으로 비교
2. **추천** — 1~2 후보, 추천 근거 (3~5 문장)
3. **tokens.json 시안** — 결정 4 의 스키마대로 정리. 메인 환경 (dev) 에선 `.claude/design/tokens.preview.json`, 실제 적용은 design_pick.py 가 수행
4. **적용 단계** — 사용자가 추천 수락 시 다음에 할 일 (예: `/project:design-pick --brand=apple --apply`)

## 책임 경계
- ✅ 토큰 결정·추천·시안
- ❌ 컴포넌트 코드 작성 (Developer 책임)
- ❌ 토큰 일관성 점검 (design-review 책임 — 결정 5 참조)
- ❌ tokens.json 자동 적용 (design_pick.py 가 사용자 명시 확인 후 수행)
```

#### 4 브랜드 토큰 카탈로그 (designer.md 본문 내부에 포함)

각 브랜드별 5~7 줄 요약 (LLM 컨텍스트로 사용) + 명세 파일 경로 명시:

```markdown
## 4 브랜드 토큰 카탈로그

### Apple — 사진 우선, 단일 블루
- 정체성: 풀뷰포트 사진 + 미니멀 UI, 단일 #0066cc 블루
- 폰트: SF Pro Display + Text (시스템 폰트 fallback)
- 적합: 제품 카탈로그, 마케팅, 미니멀 SaaS
- 비적합: 콘텐츠 밀도 높은 대시보드, 다크 모드 우선
- 명세: docs/design-references/apple-design.md
- 시그니처 토큰: 단일 brand color, radius pill + sm 2 종, 그라데이션 0

### Claude — 따뜻한 편집물
- 정체성: 크림 + 코랄, Copernicus 슬랩 세리프
- ...

### Spotify — 다크 콘텐츠 우선
- 정체성: #121212 채도 0 + 그린 #1ed760, 알약/원형 버튼
- ...

### Tesla — 급진적 미니멀
- 정체성: 풀뷰포트 사진, UI 거의 소거
- ...
```

**근거**:

- **opus 선택**: gatekeeper 의 sonnet 은 5초 결정용, designer 는 4 개 287~289 줄 명세를 비교하므로
  컨텍스트 윈도우 + 추론 깊이 면에서 opus 가 적절. Architect 와 같은 등급으로 일관.
- **Write 도구 포함**: tokens.preview.json 시안 작성에 필요. 단, **실제 `.claude/design/tokens.json`
  생성은 design_pick.py 가 담당** (결정 3 참조) — designer 는 미리보기까지만.
- **명세 4 카탈로그를 designer.md 본문에 포함**: 매 호출마다 4 ref md 를 풀로 읽지 않아도 카탈로그가
  designer 의 system prompt 역할. 상세 디테일이 필요할 때만 Read 호출.
- **책임 경계 명시**: design-review (감사) ↔ designer (선택) ↔ Developer (구현) 3 단계 분리. F007 의
  Reviewer ↔ design-review 분리와 같은 정신.

**영향받는 AC**: AC3 (designer.md 신규), AC4 (디자이너 호출 + 추천 출력)

---

### 결정 3 — `/project:design-pick` 커맨드 인터페이스: **5 서브커맨드 (비대화형 우선) + design_pick.py 헬퍼**

**채택**: F005 brain · F009 lint · F010 backup 의 verb-based 서브커맨드 패턴 100% 일관. 단,
designer 에이전트 호출은 커맨드 본문에서 위임, 토큰 적용은 design_pick.py 가 담당.

| 서브커맨드 | 동작 | 대화/비대화 |
|---|---|---|
| `compare` (또는 인자 없음) | designer 호출 → 4 브랜드 비교표만 출력 (추천 X) | 비대화 |
| `recommend` | designer 호출 → 비교 + 추천 + tokens.preview.json 시안 | 비대화 |
| `apply --brand=<name>` | tokens.preview.json 또는 명시 brand 를 .claude/design/tokens.json 으로 확정 (idempotent — 기존 tokens.json 백업) | 비대화 |
| `show` | 현재 tokens.json 표시 (없으면 친절 안내) | 비대화 |
| `self` | 셀프 dry-run (4 ref md 존재 확인, designer.md 존재 확인, 변형 미러 정합 — F007/F009/F010 셀프 모드 일관) | 비대화 |

#### 옵션 (전역)

| 옵션 | 의미 | 기본값 |
|---|---|---|
| `--brand=apple\|claude\|spotify\|tesla` | recommend/apply 시 brand 강제 (designer 추천 건너뜀) | (없음 — recommend 가 추천) |
| `--output=<path>` | tokens.json 경로 override | `.claude/design/tokens.json` |
| `--force` | apply 시 기존 tokens.json 백업 없이 덮어쓰기 (위험 — 기본 OFF) | OFF |
| `--strict` | designer 호출 실패 / brand 인식 실패 시 exit 1 (CI gate, F009 일관) | OFF (exit 0) |
| `--format=human\|json` | 출력 형식 (F009 lint 일관) | human |

#### 호출 예시 (CLAUDE.md 에 들어갈 빠른 시작 예시)

```
/project:design-pick                              # = compare (인자 없음 시 4 브랜드 비교표만)
/project:design-pick recommend                    # designer 호출 → 비교 + 추천
/project:design-pick recommend --brand=apple      # apple 강제 (designer 가 apple 만 분석)
/project:design-pick apply --brand=apple          # .claude/design/tokens.json 생성
/project:design-pick show                         # 현재 tokens.json 표시
/project:design-pick self                         # 셀프 dry-run
```

#### 대화형 vs 비대화형

**비대화형 우선** — autonomous 모드 일관성 (F010 backup-sync init 과 동일 정신).

- `recommend` 가 출력한 추천을 사용자가 보고, 다음 호출에서 `apply --brand=<name>` 명시.
- "다음에 무엇을 할지" 는 designer 의 출력 4 단계 (적용 단계) 가 명시 — 사용자가 그대로 복사 실행.
- 대화형 입력 (`input()`) 은 도입하지 않음 — 자율 모드와 호환되지 않음 (Claude Code 환경의 stdin 입력
  제약 + design-pick 자체가 옵셔널이라 인터랙티브 부담 자체가 부적합).

#### design_pick.py 헬퍼 동작

```python
# .claude/bin/design_pick.py — 단일 파일 헬퍼 (F005/F009/F010 패턴)

def cmd_compare(args) -> int:
    """4 브랜드 비교표를 designer 에이전트 위임 없이 정적으로 출력."""
    # 4 ref md 의 Overview 섹션을 읽어 비교표 생성 (LLM 호출 X — 정적 카탈로그)
    # 카탈로그는 design_pick.py 내부 상수 (BRAND_CATALOG dict) — designer.md 와 동일 출처
    ...

def cmd_recommend(args) -> int:
    """designer 에이전트 위임을 안내 — 실제 호출은 슬래시 커맨드 본문에서."""
    # 1. 다운스트림 컨텍스트 (CLAUDE.md, feature_list.json) 사전 읽기
    # 2. designer 에이전트에 위임할 프롬프트를 stdout 출력 (호출자가 복사해 사용)
    # 3. 단, args.brand 가 명시되면 직접 비교 분석 후 시안 생성 (LLM 위임 없이 정적 시안)
    ...

def cmd_apply(args) -> int:
    """brand 명시 → tokens.json 생성. idempotent."""
    # 1. .claude/design/tokens.json 존재 시 → .claude/design/tokens.backup.<ISO>.json 으로 백업
    # 2. brand 의 정적 토큰 카탈로그를 tokens.json 으로 작성 (결정 4 의 스키마)
    # 3. 친절한 출력: "✅ apple 토큰 적용. 다음: /project:design-review 로 일관성 점검"
    ...

def cmd_show(args) -> int:
    """현재 tokens.json 표시."""
    ...

def cmd_self(args) -> int:
    """셀프 dry-run — F007/F009/F010 일관."""
    # - 4 ref md 존재 확인
    # - .claude/agents/designer.md 존재 확인
    # - 변형 미러 정합 (claude.gstack.auto.design/ 에 디자인 오버레이가 누락되지 않았는지)
    ...
```

**왜 design_pick.py 가 필요한가** (header pattern 정당화):

- `apply` 의 tokens.json 자동 생성·백업·idempotent 보장은 결정론적 동작 — designer 에이전트(LLM) 가
  매번 약간 다른 JSON 을 출력하면 신뢰성 ↓. 정적 헬퍼가 4 브랜드 카탈로그를 보유.
- `self` 셀프 dry-run 은 F007/F009/F010 셀프 모드 일관성.
- `compare` 도 LLM 호출 없이 정적 비교표만 보여줄 수 있어 토큰 사용 효율 ↑.

**recommend 가 LLM 호출 필요한 경우**: 사용자가 자유 산문으로 의도 기술 + brand 미명시. 이 때만
designer 에이전트 위임 (디자인 명세 4 개 읽고 추천 산문 작성).

**근거**: F005 brain.py (`init/sync/search/stats/list/prune`) + F009 lint.py
(`check/regenerate-index/report/self`) + F010 backup.py (`init/sync/status/config/self`) 패턴 100% 일관.
호출 진입점이 단일 슬래시 커맨드 + Python 헬퍼라는 패턴 유지.

**영향받는 AC**: AC4 (design-pick 커맨드), AC5 (tokens.json 출력)

---

### 결정 4 — `tokens.json` 출력 스키마: **A. JSON object SSoT (CSS/Tailwind 변환은 다운스트림)**

**채택**: `.claude/design/tokens.json` 은 정적 JSON object — 다운스트림이 CSS 변수·Tailwind config·SCSS
mixin 등으로 변환은 자체적으로. SSoT 는 JSON 하나만.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) JSON object** | 단순 (1 파일), 모든 빌드 시스템이 JSON 읽기 가능, design-review 가 JSON 으로 파싱 가능 (결정 5), 변환은 다운스트림 자유 | CSS/Tailwind 직접 사용은 불가 — 변환 단계 필요 | **채택** |
| (B) CSS-variables friendly | 즉시 `<style>` 로 inject 가능 | CSS-only — Tailwind/SCSS 와 안 맞음, 키 이름이 CSS 변수 문법 (`--color-primary`) 으로 고정 | 부적합 |
| (C) Tailwind config snippet | Tailwind 사용자에게 즉시 가치 | Tailwind 미사용 프로젝트엔 가치 0, 형식이 Tailwind v3/v4 마다 다름 | 부적합 |
| (D) 다중 출력 (JSON + CSS + Tailwind) | 모든 다운스트림 만족 | 3 SSoT — 동기화 부담, design_pick.py 복잡도 ↑, 첫 phase 에 과도 | 후속 phase 검토 |

**근거**: F009 lint.py 의 BLOCK 정의가 JSON 으로 직렬화되어 `lint-last.json` 에 저장되는 패턴 일관.
JSON 이 가장 범용. CSS/Tailwind 변환은 **후속 phase 의 옵션 3 (자동 추출)** 과 함께 검토 가치 ↑
(자동 추출이 가능해지면 자동 변환도 함께 검토).

#### tokens.json 스키마 (Apple 예시)

```json
{
  "$schema": "docs/design/F011-tokens-schema.md",
  "version": 1,
  "brand": "apple",
  "source_ref": "docs/design-references/apple-design.md",
  "generated_at": "2026-06-02T14:30:00+09:00",
  "generated_by": "design_pick.py apply --brand=apple",
  "colors": {
    "primary": "#0066cc",
    "primary_focus": "#0071e3",
    "primary_on_dark": "#2997ff",
    "canvas": "#ffffff",
    "canvas_parchment": "#f5f5f7",
    "surface_pearl": "#fafafc",
    "surface_tile_1": "#272729",
    "surface_tile_2": "#2a2a2c",
    "surface_tile_3": "#252527",
    "surface_black": "#000000",
    "ink": "#1d1d1f",
    "body": "#1d1d1f",
    "body_on_dark": "#ffffff",
    "body_muted": "#cccccc",
    "ink_muted_80": "#333333",
    "ink_muted_48": "#7a7a7a",
    "divider_soft": "#f0f0f0",
    "hairline": "#e0e0e0"
  },
  "typography": {
    "font_display": "SF Pro Display, system-ui, -apple-system, sans-serif",
    "font_body": "SF Pro Text, system-ui, -apple-system, sans-serif",
    "hero_display": { "size": 56, "weight": 600, "line_height": 1.07, "letter_spacing": -0.28 },
    "display_lg":   { "size": 40, "weight": 600, "line_height": 1.10, "letter_spacing": 0 },
    "display_md":   { "size": 34, "weight": 600, "line_height": 1.47, "letter_spacing": -0.374 },
    "lead":         { "size": 28, "weight": 400, "line_height": 1.14, "letter_spacing": 0.196 },
    "tagline":      { "size": 21, "weight": 600, "line_height": 1.19, "letter_spacing": 0.231 },
    "body":         { "size": 17, "weight": 400, "line_height": 1.47, "letter_spacing": -0.374 },
    "caption":      { "size": 14, "weight": 400, "line_height": 1.43, "letter_spacing": -0.224 },
    "fine_print":   { "size": 12, "weight": 400, "line_height": 1.0,  "letter_spacing": -0.12 }
  },
  "radius": {
    "sm": 4,
    "md": 8,
    "lg": 18,
    "pill": 9999
  },
  "spacing": {
    "section": 96,
    "xl": 32,
    "lg": 24,
    "md": 16,
    "sm": 8,
    "xs": 4
  },
  "shadows": {
    "product_hero": "rgba(0, 0, 0, 0.22) 3px 5px 30px"
  },
  "characteristics": [
    "photography-first",
    "single-blue-accent",
    "no-decorative-gradients",
    "alternating-tile-sections",
    "tight-display-tracking"
  ],
  "anti_patterns": [
    "decorative-gradients",
    "second-brand-color",
    "shadows-on-headlines",
    "border-on-product-photo"
  ]
}
```

#### 스키마 결정 사항 (단일 소스: `docs/design/F011-tokens-schema.md`)

| 필드 | 필수 | 의미 |
|---|---|---|
| `$schema` | 권장 | 스키마 정의 문서 경로 (F009 lint 의 `LINT-DOC-001` 형식 일관) |
| `version` | ✅ | 스키마 버전 — 향후 v2 마이그레이션 경로 (F006 `harness_version` 패턴 일관) |
| `brand` | ✅ | `apple` / `claude` / `spotify` / `tesla` / `custom` 중 하나 |
| `source_ref` | ✅ | 원본 디자인 명세 경로 (변형 내부 기준) |
| `generated_at` | 자동 갱신 | ISO 8601 timestamp |
| `generated_by` | 자동 갱신 | 생성 명령어 (감사 추적용) |
| `colors` | ✅ | 색상 토큰 dict — 키는 의미 기반 (primary/canvas/ink 등) |
| `typography` | ✅ | 폰트 + 스케일 dict — 각 스케일은 size/weight/line_height/letter_spacing 4 필드 |
| `radius` | ✅ | 반경 토큰 dict |
| `spacing` | ✅ | 간격 토큰 dict |
| `shadows` | 선택 | 그림자 토큰 (브랜드별 0~3 개 — Apple 1, Spotify 3, Tesla 0) |
| `characteristics` | 권장 | 시그니처 정체성 태그 (design-review 가 anti-pattern 감지에 사용) |
| `anti_patterns` | 권장 | 피해야 할 패턴 (design-review CONCERN 라벨에 사용 — 결정 5 참조) |

**커스텀 brand 지원**: `brand: "custom"` 일 때 `source_ref` 는 자유 경로 허용. 4 브랜드 외 디자인을
다운스트림이 직접 채우는 진입 — 향후 확장 포인트.

**무결성 보장**: design_pick.py apply 시 결정론적 — 같은 brand 이면 항상 같은 tokens.json
(generated_at 만 차이). 학습 jsonl 의 reproducibility 와 동일 정신.

**영향받는 AC**: AC5 (tokens.json 형식 정의)

---

### 결정 5 — `design-review` 스킬과의 연동: **새 카테고리 D 신설 (TOKEN) — BLOCK X, CONCERN/PASS 만**

**채택**: design-review (F007) 의 IA/A11Y/CON 3 카테고리에 **D. TOKEN 카테고리 추가**. 단, 토큰 위반은
**BLOCK 아닌 CONCERN/PASS 만** 사용 — 거짓 양성 위험 + 점진적 도입.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (i) CON 카테고리에 통합 (CON-N 항목 5~10개 추가) | 카테고리 수 안정 (3 → 3) | CON 카테고리가 비대화 (현재 7~10 항목 → 15+ 항목), 토큰 점검과 일반 일관성 점검의 의미론적 차이 손실 | 부분 매력적이나 단점 우세 |
| **(ii) 새 카테고리 D (TOKEN) 신설** | 의미론적 명확 (토큰 일관성 = 디자인 시스템 충실성), tokens.json 미존재 시 카테고리 D 전체 N/A 자동 처리 → 비-디자인 프로젝트에 부담 0, 향후 옵션 3 (자동 추출 + LINT-DESIGN) 도입 시 카테고리 D 가 그 진입점 | 카테고리 수 증가 (3 → 4), design-review SKILL.md 갱신 범위 ↑ | **채택** |
| (iii) 별도 도구 (`/project:design-token-check`) | 책임 분리 명확 | 신규 커맨드 + 신규 스킬 → 산출물 폭증 (F005~F010 패턴 깨짐), 호출자가 design-review + design-token-check 두 번 실행해야 함 | 과도 |

#### D. TOKEN 카테고리 항목 (다운스트림 모드 한정)

| # | 항목 | 검사 방법 | 라벨 기준 |
|---|---|---|---|
| TOKEN-1 | tokens.json 존재 | `.claude/design/tokens.json` 파일 존재 | 부재 시 카테고리 D 전체 N/A (디자인 결정 안 한 프로젝트) |
| TOKEN-2 | 선택된 brand 외 색상 hex 사용 | 코드/CSS 내 #rrggbb 패턴 grep → tokens.json colors 값과 비교 | 토큰 외 hex 5+ 시 CONCERN |
| TOKEN-3 | 선택된 brand 외 폰트 패밀리 사용 | `font-family:` grep → tokens.json typography 값과 비교 | 토큰 외 폰트 패밀리 시 CONCERN |
| TOKEN-4 | radius 토큰 외 값 | `border-radius:` grep → tokens.json radius 값과 비교 | 토큰 외 값 3+ 시 CONCERN |
| TOKEN-5 | spacing 토큰 외 값 | `margin\|padding\|gap` 의 px 값 grep → tokens.json spacing 값과 비교 | 토큰 외 값 7+ 시 CONCERN (F007 CON-5 와 다름 — TOKEN-5 는 brand 별 spacing 스케일 기준) |
| TOKEN-6 | anti_patterns 위반 | tokens.json 의 anti_patterns 배열 각 항목별 정적 패턴 검사 (예: Apple anti-pattern = `linear-gradient` 사용) | 위반 발견 시 CONCERN |

#### 왜 BLOCK 아닌 CONCERN/PASS 만?

- **거짓 양성 위험**: hex 코드가 토큰 외라도 의도된 일회성 사용 (예: 외부 SDK 색상 강제) 일 수 있음.
  BLOCK 으로 머지 차단 시 점진적 도입 저항 ↑.
- **점진적 도입**: F011 phase 1 은 tokens.json 자동 추출 없이 출발 — 첫 사용자가 수동으로 토큰을
  채택하는 상황에서 너무 엄격하면 도입 자체를 안 하게 됨.
- **향후 BLOCK 승격 경로**: 옵션 3 (LINT-DESIGN) 도입 시 strict 모드에서 일부 항목을 BLOCK 으로
  승격 가능 (예: TOKEN-3 폰트 미일관은 시각 영향 큼).
- **F007 패턴 일관**: design-review 의 PASS/CONCERN/BLOCK 라벨이 점진적이므로 D 카테고리도
  PASS/CONCERN 만 사용 (N/A 포함).

#### design-review SKILL.md 갱신 범위

**가벼운 추가** — 큰 갱신 X:

1. SKILL.md 의 "스코프 분기" 섹션에 "D. TOKEN 카테고리 (downstream 모드 + tokens.json 존재 시)" 추가
2. "결과 양식" 섹션에 D 카테고리 표 추가 (위 6 항목)
3. "Reviewer 와의 역할 경계" 표는 무변경 (TOKEN 은 design-review 영역)
4. `docs/design/F007-design-review-checklist.md` (raw 정의) 에 TOKEN 카테고리 표 추가

design-review.md 커맨드 본문은 무변경 — `--scope=downstream` 기본값에서 tokens.json 자동 탐지 후
D 카테고리 자동 활성/비활성.

#### 호출 흐름

```
1. /project:design-pick recommend → designer 추천
2. /project:design-pick apply --brand=apple → .claude/design/tokens.json 생성
3. (개발 진행 — 컴포넌트 작성)
4. /project:design-review → IA/A11Y/CON 3 카테고리 + D. TOKEN 카테고리 자동 활성화
5. CONCERN 발견 시 사용자가 토큰 사용 여부 결정 (BLOCK 아니므로 머지 가능)
```

**근거**: F007 ADR-002 결정 4 의 "체크리스트 구조: 3 카테고리 × PASS/CONCERN/BLOCK 라벨" 정신 일관.
새 카테고리 추가는 design-review 의 확장 포인트 (F007 ADR-002 결정 6 의 "향후 확장 포인트") 와 부합.

**영향받는 AC**: AC6 (design-review 가 tokens.json 기반 일관성 점검)

---

### 결정 6 — `claude.gstack.auto.design` 변형 미러링 정책: **메인 SSoT → 변형 선별 미러 (자율 + 디자인)**

**채택**: 메인 `.claude/` 가 모든 산출물의 SSoT (결정 1). 변형별 미러는 **변형 정체성에 맞게 선별**.

#### 5 변형 미러 매트릭스 (F011 완료 후 최종)

| 변형 | F005~F009 산출물 | F010 backup-sync | 자율 오버레이 (gatekeeper 등) | **디자인 오버레이 (designer/design-pick/refs)** |
|---|---|---|---|---|
| ⓐ `claude/` (baseline) | ❌ (Karpathy 만) | ❌ | ❌ | ❌ |
| ⓑ `claude.gstack/` (표준) | ✅ | ✅ | ❌ | ❌ |
| ⓑ′ `claude.gstack.auto/` (자율) | ✅ | ✅ | ✅ | ❌ |
| **ⓑ″ `claude.gstack.auto.design/` (자율+디자인)** | ✅ | ✅ | ✅ | ✅ |
| ⓒ `openai/.codex/` (codex stub) | ❌ (Karpathy 만) | ❌ | ❌ | ❌ |

#### 디자인 오버레이 정의 (F011 신규)

다음 산출물이 디자인 오버레이:

- `.claude/agents/designer.md` (신규)
- `.claude/commands/design-pick.md` (신규)
- `.claude/bin/design_pick.py` (신규)
- `.claude/skills/design-review/SKILL.md` (수정 — D. TOKEN 카테고리 추가)
- `docs/design-references/{apple,claude,spotify,tesla}-design.md` (변형에서만 — 메인의 `src/docs/design/ui/*.md` 에서 복사)
- `docs/design/F011-tokens-schema.md` (신규)
- (런타임 생성) `.claude/design/tokens.json` (다운스트림이 design-pick apply 시 생성, gitignore 대상)
- (런타임 생성) `.claude/design/tokens.backup.<ISO>.json` (기존 tokens 덮어쓸 때 백업, gitignore 대상)

#### 미러링 흐름 (메인 → 변형)

```bash
# (1) 기본 미러 — ⓑ, ⓑ′, ⓑ″ 모두 메인의 .claude/ 동기
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  --exclude='design/' \   # 런타임 생성물 제외
  .claude/ src/harness_template/claude.gstack/harness/.claude/

rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  --exclude='design/' \
  .claude/ src/harness_template/claude.gstack.auto/harness/.claude/

rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  --exclude='design/' \
  .claude/ src/harness_template/claude.gstack.auto.design/harness/.claude/

# (2) 디자인 오버레이 제거 — ⓑ, ⓑ′ 에서 디자인 산출물 후처리 삭제
# ⓑ (표준) — 자율 + 디자인 오버레이 둘 다 제외
rm -f src/harness_template/claude.gstack/harness/.claude/agents/gatekeeper.md
rm -f src/harness_template/claude.gstack/harness/.claude/agents/designer.md
rm -f src/harness_template/claude.gstack/harness/.claude/commands/design-pick.md
rm -f src/harness_template/claude.gstack/harness/.claude/bin/design_pick.py

# ⓑ′ (자율) — 디자인 오버레이만 제외 (자율 오버레이는 유지)
rm -f src/harness_template/claude.gstack.auto/harness/.claude/agents/designer.md
rm -f src/harness_template/claude.gstack.auto/harness/.claude/commands/design-pick.md
rm -f src/harness_template/claude.gstack.auto/harness/.claude/bin/design_pick.py

# ⓑ″ (자율+디자인) — 디자인 + 자율 오버레이 모두 유지

# (3) 디자인 참조 4 파일 — 메인 src/docs/design/ui/*.md → 변형 docs/design-references/*.md (이름 변경)
mkdir -p src/harness_template/claude.gstack.auto.design/harness/docs/design-references
cp src/docs/design/ui/apple-design.md   src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
cp src/docs/design/ui/claude-design.md  src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
cp src/docs/design/ui/spotify-design.md src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
cp src/docs/design/ui/tesla-design.md   src/harness_template/claude.gstack.auto.design/harness/docs/design-references/

# (4) docs/design/F011-tokens-schema.md, docs/adr/ADR-006-*.md 도 ⓑ, ⓑ′, ⓑ″ 미러
```

#### `claude.gstack.auto.design/` 초기 생성 절차 (세션 1)

```bash
# claude.gstack.auto 를 base 로 cp -r
cp -r src/harness_template/claude.gstack.auto src/harness_template/claude.gstack.auto.design

# state/ 디렉토리 정리 (런타임 — 미러 제외 대상)
rm -rf src/harness_template/claude.gstack.auto.design/harness/.claude/state/checkpoints/*
rm -f src/harness_template/claude.gstack.auto.design/harness/.claude/state/{learnings,analytics,lint-last}.jsonl
# (단, .gitkeep 파일은 유지)

# README.md / CLAUDE.md 의 변형 이름·정체성을 design 으로 갱신 (수동)
# 디자인 오버레이 추가 (위 미러링 흐름)
```

#### 베이스라인 + codex 비미러 일관성

F005~F010 의 baseline + codex 비미러 패턴 100% 일관. F011 도 운영 도구이지 Karpathy 4원칙 같은 보편
사고 원칙 아님 — baseline + codex 에 동기화 안 함.

**근거**:

- **메인 SSoT 정신 (결정 1) 일관**: 메인이 모든 산출물 보유 → 변형은 메인의 선별 포장.
- **변형 정체성 보존**: ⓑ 는 표준 (사용자 승인), ⓑ′ 는 자율 (gatekeeper), ⓑ″ 는 자율+디자인. 각
  변형의 정체성에 맞는 산출물만 포함.
- **F010 미러 회귀 학습**: F010 세션 중 미러 회귀 2회 발생 (auto/settings.json 표준 변형으로 덮어쓰기,
  gstack 에 자율 오버레이 잘못 미러). 디자인 오버레이까지 추가되면 회귀 위험 더 ↑ → 결정 7 의
  자동화 가드 필요.

**영향받는 AC**: AC1 (변형 신설), AC2 (4 파일 포함), AC8 (메인 → 변형 미러 정합)

---

### 결정 7 — 미러 회귀 자동화 가드: **B. `lint.py` 에 LINT-MR 검사기 추가 (F009 확장)**

**채택**: F009 lint.py 에 `LINT-MR` (Mirror) 검사기 추가. F010 의 미러 회귀 2회 사고 재발 방지.
신규 mirror.py 헬퍼는 만들지 않음 — F005~F010 단일 헬퍼 패턴 안에서 확장.

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| (A) 문서 강화만 (CLAUDE.md 매트릭스 표) | 도입 비용 0 | 사람 실수 방지 효과 약함 — F010 에서 매트릭스 표 있어도 회귀 발생 | F010 경험상 부족 |
| **(B) `lint.py` 에 LINT-MR 검사기 추가** | F009 단일 헬퍼 확장 (신규 파일 0), `/project:lint` 호출만으로 모든 변형 정합 검증, design-review 셀프 모드 CON-S3 와 분리 (lint = 거버넌스, design-review = 디자인), 사용자 시간 ≫ 코드 작성 시간 가치 | lint.py 코드 줄수 ↑ (50~80 줄 추가) | **채택** |
| (C) 신규 mirror.py 헬퍼 + 신규 `/project:mirror` 커맨드 | 책임 분리 명확 | 산출물 폭증 (F005~F010 패턴 깨짐), 호출자 부담 ↑ | 과도 |

#### LINT-MR 검사 항목 (5 개) — F011 세션 3 구현 기준

> **노트 (2026-06-02 갱신)**: F011 세션 3 구현 단계에서 ADR 표 정의가 너무 광범위
> (전체 디렉토리 정합 비교 — 변형별 제외 목록 필요) 함을 발견. F010 회귀 2 케이스
> (gatekeeper.md 잘못 미러 / Bash(*) 잘못 적용) 의 **자동 가드** 라는 메타 목적에
> 맞춰 5 항목을 결정론적·실용적 점검으로 재설계. 전체 디렉토리 정합 비교는 후속
> phase 의 `LINT-MR-FULL` 로 분리 예정.

| # | 항목 | 검사 방법 | BLOCK / CONCERN |
|---|---|---|---|
| MR-1 | ⓑ 표준 변형에 자율 오버레이 부재 | `claude.gstack/.claude/agents/gatekeeper.md`, `hooks/pre-bash-auto-boundary-check.sh` 존재 여부 | 존재 시 BLOCK |
| MR-2 | ⓑ 표준 변형의 `settings.json` Bash(*) 미사용 | `Bash(*)` / `Bash("*")` 패턴 (JSON 이스케이프 변종 포함) | 발견 시 BLOCK |
| MR-3 | ⓑ 표준 변형의 `CLAUDE.md` Autonomous Mode 헤딩 부재 | 정규식 `^#{1,6}\s+.*Autonomous Mode` (헤딩만, 본문 인용은 거짓 양성 회피) | 발견 시 BLOCK |
| MR-4 | ⓑ, ⓑ′, ⓐ 3 변형에 디자인 오버레이 부재 | `designer.md` / `design-pick.md` / `design_pick.py` / `docs/design-references/` 존재 여부 | 존재 시 BLOCK |
| MR-5 | ⓑ″ 디자인 변형에 디자인 오버레이 모두 존재 | 위 4 파일 모두 존재 여부 | 누락 시 CONCERN |

F010 미러 회귀 2 케이스는 MR-1 (gatekeeper.md) + MR-2 (Bash(*)) 로 자동 감지된다.
신규 변형 도입 시 MR-1~5 가 핵심 회귀 (오버레이 잘못 미러) 를 잡지만, 변형 내부
파일 추가·삭제 같은 점진적 drift 는 `LINT-MR-FULL` 후속 phase 에서 다룬다.

#### 변형별 제외 목록 (lint.py 내부 상수)

```python
# .claude/bin/lint.py — LINT-MR 검사기 내부 상수
VARIANT_OVERLAY_EXCLUDES = {
    "claude.gstack": {
        "agents":   {"gatekeeper.md", "designer.md"},
        "commands": {"design-pick.md"},
        "bin":      {"design_pick.py"},
    },
    "claude.gstack.auto": {
        "agents":   {"designer.md"},
        "commands": {"design-pick.md"},
        "bin":      {"design_pick.py"},
    },
    "claude.gstack.auto.design": {
        # 디자인 변형은 모든 오버레이 포함 — 제외 0
        "agents":   set(),
        "commands": set(),
        "bin":      set(),
    },
}
```

#### 호출 예시 (CLAUDE.md 빠른 시작 갱신)

```
/project:lint                   # MR-1 ~ MR-5 자동 검사 (F009 의 LINT-FL 등과 같이 실행)
/project:lint --only=LINT-MR    # 미러 정합만 검사
/project:lint --strict          # BLOCK 1건이라도 있으면 exit 1
```

#### 호출 시점 권장

- **handoff 직전** (F009 권장 시점 그대로)
- **새 변형 산출물 추가 후** (F011 의 designer.md / design-pick.md / design_pick.py 추가 후 1회 권장)
- **ADR 작성 후** (이 ADR-006 같은 신규 ADR 미러 누락 감지)

**근거**:

- **F010 의 미러 회귀 2회 사고**가 자동화 가드 가치를 증명. 사용자 시간 (디버깅, 미러 회귀 추적) ≫
  lint.py 코드 50~80 줄 추가 비용.
- **F009 단일 헬퍼 확장 패턴 일관**: lint.py 가 이미 거버넌스 검사기 보유. MR 은 자연스러운 확장.
- **design-review 셀프 모드 CON-S3 와 분리**: CON-S3 (gstack 미러 동기화) 는 design-review 영역. MR-1~MR-5 는
  lint.py 영역. design-review 는 IA/A11Y/일관성, lint 는 거버넌스 — F007 ADR-002 결정 2 의 책임 분리 일관.

**영향받는 AC**: AC8 (변형 미러 명시화) + F011 신규 운영 가드

---

### 결정 8 — F011 세션 분할: **3 세션 (A 안 채택, feature_list.estimated_sessions=3 일치)**

**채택**: 사용자 estimated_sessions=3 일치. 세션 1 이 변형 신설 + 디자인 자료 + designer 에이전트 (핵심
기반), 세션 2 가 design-pick 커맨드 + tokens.json 시안 (코어 가치), 세션 3 이 design-review 연동 +
LINT-MR + CLAUDE.md + 미러 정합 (통합).

| 세션 | 범위 | 산출물 | AC 충족 |
|---|---|---|---|
| **세션 1** — 변형 신설 + 디자인 자료 + designer 에이전트 + ADR-006 미러 골격 | `claude.gstack.auto.design/` cp 신설, 4 ref md `docs/design-references/` 로 복사, `.claude/agents/designer.md` 신규, `docs/design/F011-tokens-schema.md` 골격 | claude.gstack.auto.design/ 디렉토리 + 4 ref md 미러 + designer.md + tokens-schema 골격, ADR-006 미러 (ⓑ, ⓑ′, ⓑ″) | AC1 (변형 신설), AC2 (4 파일 포함), AC3 (designer.md) |
| **세션 2** — design_pick.py + /project:design-pick 커맨드 + tokens.json 시안 | `.claude/bin/design_pick.py` (compare/recommend/apply/show/self), `.claude/commands/design-pick.md`, 4 브랜드 정적 토큰 카탈로그 (design_pick.py 내부 상수), tokens.preview.json 생성 시연 | design_pick.py 5 서브커맨드, design-pick.md 커맨드, 4 브랜드 토큰 시안 작동 확인 | AC4 (design-pick 커맨드), AC5 (tokens.json 형식), AC9 (옵션 3 분리) |
| **세션 3** — design-review 연동 + LINT-MR + CLAUDE.md 통합 + 최종 미러 정합 | design-review SKILL.md 에 D. TOKEN 카테고리 추가, `docs/design/F007-design-review-checklist.md` 갱신, `lint.py` 에 LINT-MR 검사기 추가, CLAUDE.md 빠른 시작 + 호출 기준 + 디렉토리 트리 + 5 변형 미러 매트릭스 표 갱신, learnings 3개 append, 최종 미러 동기화 (ⓑ + ⓑ′ + ⓑ″) | design-review SKILL.md 갱신, lint.py LINT-MR, CLAUDE.md 통합, learnings, 최종 미러 | AC6 (design-review 연동), AC7 (CLAUDE.md), AC8 (메인 → 변형 미러 명시화) |

#### 세션 분할 근거

- **세션 1 의 응집도**: 변형 신설 + 4 ref md 복사 + designer.md + tokens-schema 골격은 모두 "디자인
  자료 인프라" 카테고리. 한 세션에 몰아 응집도 ↑. design_pick.py 가 없어도 designer 에이전트를
  사용자가 직접 호출해 시안 받을 수 있음 (degraded mode 작동).
- **세션 2 의 응집도**: design_pick.py 5 서브커맨드 + 슬래시 커맨드 + tokens.json 시안. F005/F009/F010
  의 "헬퍼 + 커맨드 세션" 패턴 일관.
- **세션 3 의 응집도**: design-review 연동 (SKILL.md + 체크리스트) + LINT-MR + CLAUDE.md 통합 + 최종
  미러는 모두 "통합 + 가드 + 문서화" 카테고리. F009/F010 의 마지막 세션 정신 일관.

#### 대안 비교

| 옵션 | 장점 | 단점 | 결정 |
|---|---|---|---|
| **(A) 3 세션 (사용자 estimated 일치)** | feature_list 일관, 세션별 응집도 ↑, F010 와 같은 호흡 | 세션 1 의 변형 신설이 큰 작업 — 디스크 사용량 ↑ 미러링 시간 ↑ | **채택** |
| (B) 2 세션 (압축) | 세션 수 ↓ | 세션 1 부하 ↑ (변형 + designer + design_pick.py + 커맨드 모두), 회귀 위험 ↑ | 부담 ↑ |
| (C) 4 세션 (LINT-MR 별도) | 부하 최소 | feature_list 와 불일치, 과도 분할 | 과함 |

**근거**: F010 의 3 세션 분할 성공 패턴 일관. 세션 3 의 LINT-MR + CLAUDE.md + 미러 정합이 한 세션에
적정 — 별 세션으로 분리하면 세션 4 가 너무 작아짐.

**영향받는 AC**: 전체 진행 계획 (feature_list.estimated_sessions=3 유지)

---

## 대안 검토 (요약)

| 대안 | 장점 | 단점 | 제외 이유 |
|---|---|---|---|
| 디자인 자료를 변형에만 두기 (결정 1 B) | 의미론적 일관 (디자인은 디자인 변형만) | F005~F010 SSoT 패턴 깨짐, 메인에서 design-pick 테스트 불가 | 결정 1 |
| designer 에이전트 sonnet 모델 | 토큰 사용 ↓ | 4 개 287~289 줄 명세 비교에 추론 깊이 부족 | 결정 2 |
| `/project:design-pick` 대화형 입력 | 발견성 ↑ | autonomous 모드 호환성 X, Claude Code stdin 제약 | 결정 3 |
| tokens.json 다중 출력 (JSON + CSS + Tailwind) | 모든 다운스트림 만족 | 3 SSoT 동기화 부담 | 결정 4 |
| tokens.json BLOCK 라벨 사용 | 토큰 미사용 강제 | 거짓 양성 위험 + 점진적 도입 저항 | 결정 5 |
| design-review CON 카테고리에 통합 (결정 5 i) | 카테고리 수 안정 | CON 비대화 + 의미론 손실 | 결정 5 |
| 별도 `/project:design-token-check` 도구 (결정 5 iii) | 책임 분리 | 산출물 폭증 + 호출 부담 ↑ | 결정 5 |
| 미러 회귀 가드 문서만 (결정 7 A) | 도입 비용 0 | F010 경험상 부족 | 결정 7 |
| 신규 mirror.py 헬퍼 (결정 7 C) | 책임 분리 | 산출물 폭증 + F005~F010 패턴 깨짐 | 결정 7 |
| 2 세션 분할 (결정 8 B) | 세션 수 ↓ | 세션 1 부하 ↑ + 회귀 위험 ↑ | 결정 8 |
| 4 세션 분할 (결정 8 C) | 부하 최소 | feature_list 불일치 + 과도 분할 | 결정 8 |
| 토큰 자동 추출 (옵션 3) 본 phase 포함 | 토큰 정의 자동화 | md 파싱 신뢰성 검증 필요 — F011 phase 부담 ↑ | 사용자 사전 결정 |

---

## 결과

### 긍정적 영향

- **F011 모든 AC 충족 예정** (AC1~AC9, 세션별 매핑은 결정 8 표 참조)
- **외부 의존성 0 정책 100% 일관** — Python stdlib + bash + git CLI 만
- **무회귀**: F001~F010 의 동작 무수정. `.claude/settings.json` / 기존 에이전트 6 개 (planner/architect/
  developer/reviewer/qa/gatekeeper) / brain.py / host.py / lint.py / backup.py / qa_browser.py 모두 그대로
- **F005/F006/F007/F009/F010 패턴 100% 일관**: 단일 파일 헬퍼 + 서브커맨드 + 옵셔널 + exit 0 +
  hook-failure-tolerance + 변형 미러 + 셀프 모드
- **5 변형 매트릭스 명시화**: F010 미러 회귀 사고 학습 반영 — LINT-MR 가드로 재발 방지
- **다운스트림 UI 프로젝트 가치 ↑**: 디자인 결정의 반복성 자동화 — 4 브랜드 카탈로그 + 추천 + 토큰 +
  일관성 점검 풀 파이프라인
- **확장 경로 명시**: 옵션 3 (자동 추출 + LINT-DESIGN) 의 진입점이 결정 4 (`$schema` + `version`) +
  결정 5 (TOKEN 카테고리) 에 미리 마련됨

### 부정적 영향 / 트레이드오프

- **신규 변형 1개** (`claude.gstack.auto.design/`) — 디스크 사용량 ↑ (claude.gstack.auto 와 거의 같은 크기
  + 디자인 자료 4 ref md ≈ 1.1MB 합) + 미러링 시간 ↑
- **신규 파일 5~6 개** (`.claude/agents/designer.md`, `.claude/commands/design-pick.md`,
  `.claude/bin/design_pick.py`, `docs/design/F011-tokens-schema.md`, `docs/adr/ADR-006-*.md`, 선택 1)
- **`.claude/skills/design-review/SKILL.md` 수정** (D. TOKEN 카테고리 추가) — F007 산출물 변경.
  단, 추가만 — 기존 IA/A11Y/CON 항목은 무수정 (무회귀 유지)
- **`.claude/bin/lint.py` 수정** (LINT-MR 검사기 추가) — F009 산출물 변경. 단, 추가만 — 기존
  LINT-FL/LINT-ADR/LINT-LEARN/LINT-LRN 항목은 무수정
- **CLAUDE.md 디렉토리 트리 + 5 변형 매트릭스 표 갱신** — 분량 ↑ 약 30~50 줄
- **디자인 명세 경로 분기**: 메인 (`src/docs/design/ui/`) vs 변형 (`docs/design-references/`) — designer
  에이전트의 `find_design_references()` 분기 학습 비용 1
- **designer 에이전트 호출은 opus 모델 — 토큰 비용 ↑** (mitigation: 결정 3 의 design_pick.py 가 정적
  카탈로그를 보유해 LLM 호출은 사용자가 자유 산문 의도 기술 시에만)

### 후속 조치

- [ ] (F011 세션 1) 변형 신설 + 4 ref md 복사 + designer.md + tokens-schema 골격 + ADR-006 미러
- [ ] (F011 세션 2) design_pick.py 5 서브커맨드 + design-pick.md + tokens.json 4 브랜드 카탈로그
- [ ] (F011 세션 3) design-review D. TOKEN 카테고리 + lint.py LINT-MR + CLAUDE.md 통합 + 미러 정합
- [ ] (F011 QA) `/project:design-pick self` + `/project:lint --only=LINT-MR` + `/project:design-review --scope=self` 3 검증
- [ ] (F012 가칭 — 후속) 토큰 자동 추출 (옵션 3) — designer 가 md 파싱 → tokens.json 직접 생성 (현 phase 는 정적 카탈로그)
- [ ] (F013 가칭 — 후속) `tokens.json` → CSS variables / Tailwind config 자동 변환 (결정 4 D 안 후속)
- [ ] (F014 가칭 — 후속) `--brand=custom` 시 designer 가 신규 브랜드 추가 워크플로우 (4 브랜드 외 확장)
- [ ] (F015 가칭 — 후속) D. TOKEN 카테고리 일부 항목 BLOCK 승격 (옵션 3 자동 추출 신뢰도 확보 후)

---

## 구현 가이드 (Developer 인계용)

### 변경/신규 파일 목록

**신규 생성 (세션 1)**:

```
src/harness_template/claude.gstack.auto.design/                          # 변형 디렉토리 자체 (cp -r 신설)
src/harness_template/claude.gstack.auto.design/harness/docs/design-references/apple-design.md
src/harness_template/claude.gstack.auto.design/harness/docs/design-references/claude-design.md
src/harness_template/claude.gstack.auto.design/harness/docs/design-references/spotify-design.md
src/harness_template/claude.gstack.auto.design/harness/docs/design-references/tesla-design.md
.claude/agents/designer.md                                                # 신규 에이전트 (메인 SSoT)
docs/design/F011-tokens-schema.md                                         # tokens.json 스키마 단일 소스
docs/adr/ADR-006-design-pick-and-design-variant.md                        # 본 ADR
```

**신규 생성 (세션 2)**:

```
.claude/bin/design_pick.py                                                # 단일 파일 헬퍼 (5 서브커맨드)
.claude/commands/design-pick.md                                           # /project:design-pick 슬래시 커맨드
```

**신규 생성 (세션 3, 선택)**:

```
docs/design/F011-design-pick.md                                           # (선택) design-pick 사용 가이드 — F010 의 docs/design/ 패턴 일관
```

**수정 (세션 3)**:

```
.claude/skills/design-review/SKILL.md                                     # D. TOKEN 카테고리 추가 (추가만, 기존 무수정)
docs/design/F007-design-review-checklist.md                               # D. TOKEN 카테고리 raw 정의 추가
.claude/bin/lint.py                                                       # LINT-MR 검사기 추가 (추가만)
CLAUDE.md                                                                 # 빠른 시작 + 호출 기준 + 5 변형 매트릭스 + 디렉토리 트리
feature_list.json                                                         # F011 status: in-progress → review
.claude/state/learnings.jsonl                                             # 새 학습 3개 (architecture/pattern/pitfall)
```

**미러링 (ⓑ + ⓑ′ + ⓑ″ — 결정 6 의 선별 미러)**:

```
# ⓑ (claude.gstack) — 디자인 오버레이 제외 + 자율 오버레이 제외 (gatekeeper, designer, design-pick.md, design_pick.py 모두 없음)
src/harness_template/claude.gstack/harness/.claude/skills/design-review/SKILL.md      # D. TOKEN 카테고리 추가됨
src/harness_template/claude.gstack/harness/.claude/bin/lint.py                        # LINT-MR 추가됨
src/harness_template/claude.gstack/harness/CLAUDE.md                                  # 빠른 시작 + 매트릭스
src/harness_template/claude.gstack/harness/docs/adr/ADR-006-*.md
src/harness_template/claude.gstack/harness/docs/design/F007-design-review-checklist.md # D. TOKEN raw 정의
src/harness_template/claude.gstack/harness/docs/design/F011-tokens-schema.md
src/harness_template/claude.gstack/harness/feature_list.json (있다면, 데모 샘플 갱신)

# ⓑ′ (claude.gstack.auto) — 디자인 오버레이만 제외 (gatekeeper 는 유지, designer/design-pick.md/design_pick.py 없음)
src/harness_template/claude.gstack.auto/harness/.claude/skills/design-review/SKILL.md
src/harness_template/claude.gstack.auto/harness/.claude/bin/lint.py
src/harness_template/claude.gstack.auto/harness/CLAUDE.md
src/harness_template/claude.gstack.auto/harness/docs/adr/ADR-006-*.md
src/harness_template/claude.gstack.auto/harness/docs/design/F007-design-review-checklist.md
src/harness_template/claude.gstack.auto/harness/docs/design/F011-tokens-schema.md

# ⓑ″ (claude.gstack.auto.design) — 모든 오버레이 포함 (자율 + 디자인)
src/harness_template/claude.gstack.auto.design/harness/.claude/agents/designer.md
src/harness_template/claude.gstack.auto.design/harness/.claude/commands/design-pick.md
src/harness_template/claude.gstack.auto.design/harness/.claude/bin/design_pick.py
src/harness_template/claude.gstack.auto.design/harness/.claude/skills/design-review/SKILL.md
src/harness_template/claude.gstack.auto.design/harness/.claude/bin/lint.py
src/harness_template/claude.gstack.auto.design/harness/CLAUDE.md
src/harness_template/claude.gstack.auto.design/harness/docs/adr/ADR-006-*.md
src/harness_template/claude.gstack.auto.design/harness/docs/design/F007-design-review-checklist.md
src/harness_template/claude.gstack.auto.design/harness/docs/design/F011-tokens-schema.md
src/harness_template/claude.gstack.auto.design/harness/docs/design-references/*.md (4 파일)
```

**의도적 미수정 (제약 준수)**:

```
.claude/settings.json                                                     # Claude Code 스키마 격리 (F006)
.claude/agents/{planner,architect,developer,reviewer,qa,gatekeeper}.md   # 기존 6 에이전트 무수정
.claude/bin/brain.py                                                      # F005 격리
.claude/bin/host.py, host_adapters/*.py                                   # F006 격리
.claude/bin/qa_browser.py                                                 # F008 격리
.claude/bin/backup.py                                                     # F010 격리
.claude/commands/{init-project,handoff,...}.md (F011 무관 커맨드)         # 무수정
.claude/skills/{coding,planning,testing,qa-browser}/SKILL.md              # design-review/SKILL.md 만 수정 (D 카테고리)
docs/adr/ADR-001*.md ~ ADR-005*.md                                        # 기존 ADR 무수정
src/docs/design/ui/{apple,claude,spotify,tesla}-design.md                 # 메인 원본 무수정 (변형으로 복사만)
src/harness_template/claude/                                              # baseline 동결 (결정 6)
src/harness_template/openai/                                              # codex stub (결정 6)
```

### 단계별 작업 순서

#### 세션 1 — 변형 신설 + 디자인 자료 + designer 에이전트

**Step 1.1 — `claude.gstack.auto.design/` 변형 디렉토리 신설**

```bash
cp -r src/harness_template/claude.gstack.auto src/harness_template/claude.gstack.auto.design

# 런타임 state 정리 (미러 제외 대상)
find src/harness_template/claude.gstack.auto.design/harness/.claude/state -type f \
  ! -name '.gitkeep' -delete 2>/dev/null || true
find src/harness_template/claude.gstack.auto.design/harness/.claude/state -type d -empty \
  ! -path '*qa-browser*' -delete 2>/dev/null || true

# README.md / CLAUDE.md 의 변형 이름·정체성 갱신 (Step 1.6 에서 일괄)
```

**Step 1.2 — 디자인 참조 4 파일 복사 (메인 → 변형, 경로 변경)**

```bash
mkdir -p src/harness_template/claude.gstack.auto.design/harness/docs/design-references
cp src/docs/design/ui/apple-design.md   src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
cp src/docs/design/ui/claude-design.md  src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
cp src/docs/design/ui/spotify-design.md src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
cp src/docs/design/ui/tesla-design.md   src/harness_template/claude.gstack.auto.design/harness/docs/design-references/
```

**Step 1.3 — `.claude/agents/designer.md` 신규 작성** (메인 SSoT)

- frontmatter: `model: claude-opus-4-7`, `tools: Read, Glob, Grep, Bash, Write`
- 본문: 결정 2 의 designer.md 본문 골격 + 4 브랜드 토큰 카탈로그
- 책임 경계 명시 (디자인 추천만, 코드 작성 X, 자동 적용 X)

**Step 1.4 — `docs/design/F011-tokens-schema.md` 골격 작성** (메인 SSoT)

- 결정 4 의 tokens.json 스키마 표 + Apple 예시 JSON 그대로
- 필드 의미 표
- 4 브랜드별 핵심 토큰 차이 요약 (designer 가 카탈로그로 사용 가능한 형식)

**Step 1.5 — `docs/adr/ADR-006-*.md` 미러링 (ⓑ + ⓑ′ + ⓑ″)**

```bash
cp docs/adr/ADR-006-design-pick-and-design-variant.md \
   src/harness_template/claude.gstack/harness/docs/adr/
cp docs/adr/ADR-006-design-pick-and-design-variant.md \
   src/harness_template/claude.gstack.auto/harness/docs/adr/
cp docs/adr/ADR-006-design-pick-and-design-variant.md \
   src/harness_template/claude.gstack.auto.design/harness/docs/adr/
```

**Step 1.6 — `claude.gstack.auto.design/` 의 README.md / CLAUDE.md 정체성 갱신**

- README.md 헤더에 "자율 + 디자인" 정체성 명시
- CLAUDE.md 빠른 시작에 design-pick 안내 (세션 3 에서 본격 갱신 — 골격만)

**Step 1.7 — 디자인 자료 SSoT 미러링 (메인 .claude/agents/designer.md → ⓑ″)**

```bash
mkdir -p src/harness_template/claude.gstack.auto.design/harness/.claude/agents
cp .claude/agents/designer.md \
   src/harness_template/claude.gstack.auto.design/harness/.claude/agents/

mkdir -p src/harness_template/claude.gstack.auto.design/harness/docs/design
cp docs/design/F011-tokens-schema.md \
   src/harness_template/claude.gstack.auto.design/harness/docs/design/
```

→ ⓑ / ⓑ′ 에는 designer.md 가 들어가지 않아야 함 (결정 6 변형별 제외).

**Step 1.8 — 세션 1 자체 검증**

- `ls src/harness_template/claude.gstack.auto.design/harness/docs/design-references/` → 4 파일 확인
- `ls src/harness_template/claude.gstack.auto.design/harness/.claude/agents/designer.md` → 존재 확인
- `ls src/harness_template/claude.gstack.auto/harness/.claude/agents/designer.md` → **부재** 확인
- `diff src/docs/design/ui/apple-design.md src/harness_template/claude.gstack.auto.design/harness/docs/design-references/apple-design.md` → 무차이 확인

**Step 1.9 — 세션 1 핸드오프**

- `feature_list.json` F011: `status: in-progress` (그대로)
- `/project:context-save "F011 세션 1 — claude.gstack.auto.design 변형 + 4 ref md + designer.md + tokens-schema 골격 완료"`
- claude-progress.txt 갱신 (F009 prefix 컨벤션 사용)

#### 세션 2 — design_pick.py + /project:design-pick 커맨드 + 4 브랜드 정적 토큰 카탈로그

**Step 2.1 — `.claude/bin/design_pick.py` 코어 골격**

- F005 brain.py / F009 lint.py / F010 backup.py 헤더 docstring 형식 모방
- argparse 서브커맨드 등록: `compare`, `recommend`, `apply`, `show`, `self`
- 옵션: `--brand`, `--output`, `--force`, `--strict`, `--format`
- 경로 상수: `_PROJECT_ROOT`, `_TOKENS_JSON_DEFAULT`, `_DESIGN_REFS_CANDIDATES`

**Step 2.2 — 4 브랜드 정적 토큰 카탈로그 (design_pick.py 내부 상수)**

`BRAND_CATALOG` dict — 각 brand 별 결정 4 의 Apple 예시 형식. 4 디자인 명세를 읽어 정적 추출:

```python
BRAND_CATALOG = {
    "apple": {
        "source_ref": "docs/design-references/apple-design.md",
        "colors": { ... },          # 결정 4 의 Apple 예시 그대로
        "typography": { ... },
        "radius": { "sm": 4, "md": 8, "lg": 18, "pill": 9999 },
        "spacing": { "section": 96, "xl": 32, "lg": 24, "md": 16, "sm": 8, "xs": 4 },
        "shadows": { "product_hero": "rgba(0, 0, 0, 0.22) 3px 5px 30px" },
        "characteristics": ["photography-first", "single-blue-accent", ...],
        "anti_patterns": ["decorative-gradients", "second-brand-color", ...],
    },
    "claude":  { ... },
    "spotify": { ... },
    "tesla":   { ... },
}
```

각 brand 의 카탈로그는 4 ref md 를 읽어 채움 — Developer 가 명세를 참고해 손으로 채택 (LLM
호출 없이 결정론적).

**Step 2.3 — `cmd_compare()` 구현**

- `BRAND_CATALOG` 의 4 brand 를 비교표로 출력 (색상 primary, 폰트, radius pill 여부, 타이포 스타일, 적합성)
- 형식: 마크다운 표 (human) 또는 JSON (--format=json)
- LLM 호출 0 — 정적 카탈로그만

**Step 2.4 — `cmd_recommend()` 구현**

- 옵션 A: `--brand=<name>` 명시 → 해당 brand 시안 출력 (LLM 호출 0)
- 옵션 B: brand 미명시 → designer 에이전트 호출 안내 출력 (호출자 = Claude Code 가 Task 도구로 designer 위임)
- 출력: 비교 + 추천 (산문 1~2 문단) + tokens.preview.json 시안 + 적용 단계

**Step 2.5 — `cmd_apply()` 구현 (핵심)**

```python
def cmd_apply(args) -> int:
    brand = args.brand
    if brand not in BRAND_CATALOG and brand != "custom":
        print(f"❌ 알 수 없는 brand: {brand}. 가능: apple, claude, spotify, tesla, custom")
        return 1 if args.strict else 0

    target = Path(args.output or ".claude/design/tokens.json")
    target.parent.mkdir(parents=True, exist_ok=True)

    # idempotent — 기존 tokens.json 백업
    if target.exists() and not args.force:
        backup = target.parent / f"tokens.backup.{now_iso_safe()}.json"
        shutil.copy2(target, backup)
        print(f"📦 기존 tokens.json → {backup.name} 백업")

    # 카탈로그 → tokens.json
    tokens = build_tokens_json(brand)  # version=1, $schema, generated_at 자동 채움
    target.write_text(json.dumps(tokens, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {brand} 토큰 적용 → {target}")
    print("   다음: /project:design-review 로 일관성 점검")
    return 0
```

**Step 2.6 — `cmd_show()` 구현**

- `.claude/design/tokens.json` 읽기 → human / json 출력
- 부재 시 친절 안내 (`먼저 /project:design-pick apply --brand=<name> 실행`)

**Step 2.7 — `cmd_self()` 구현 (셀프 dry-run — F007/F009/F010 일관)**

- 4 ref md 존재 확인 (메인 `src/docs/design/ui/` 또는 변형 `docs/design-references/`)
- `.claude/agents/designer.md` 존재 확인
- `BRAND_CATALOG` 의 4 brand 가 모두 채워졌는지 확인 (colors / typography / radius / spacing 필수 필드)
- 출력: 양식대로 + exit 0

**Step 2.8 — `.claude/commands/design-pick.md` 작성**

- 다른 commands/*.md 와 동일 구조
- 본문: `python3 .claude/bin/design_pick.py <subcmd>` 호출
- 옵셔널 보장 명시
- `recommend` 가 brand 미명시 시 designer 에이전트 위임 흐름 설명

**Step 2.9 — 미러링 (ⓑ″ 만 — design_pick.py / design-pick.md 는 디자인 오버레이)**

```bash
cp .claude/bin/design_pick.py \
   src/harness_template/claude.gstack.auto.design/harness/.claude/bin/
cp .claude/commands/design-pick.md \
   src/harness_template/claude.gstack.auto.design/harness/.claude/commands/
```

→ ⓑ / ⓑ′ 에는 두 파일 모두 들어가지 않아야 함 (결정 6).

**Step 2.10 — 세션 2 자체 검증**

```bash
python3 .claude/bin/design_pick.py compare                           # 비교표 출력
python3 .claude/bin/design_pick.py recommend --brand=apple           # apple 시안
python3 .claude/bin/design_pick.py apply --brand=apple --output=/tmp/test-tokens.json
cat /tmp/test-tokens.json | python3 -m json.tool                     # JSON 유효성
python3 .claude/bin/design_pick.py self                              # 셀프 dry-run
```

**Step 2.11 — 세션 2 핸드오프**

- `feature_list.json` F011: `status: in-progress` (그대로)
- `/project:context-save "F011 세션 2 — design_pick.py 5 서브커맨드 + 4 브랜드 카탈로그 + design-pick.md 완료"`

#### 세션 3 — design-review 연동 + LINT-MR + CLAUDE.md 통합 + 미러 정합

**Step 3.1 — `docs/design/F007-design-review-checklist.md` 갱신 (D. TOKEN raw 정의)**

- 결정 5 의 TOKEN 카테고리 6 항목 표 그대로 추가
- 기존 IA/A11Y/CON 항목은 무수정

**Step 3.2 — `.claude/skills/design-review/SKILL.md` 갱신 (D. TOKEN 카테고리 추가)**

- "스코프 분기" 섹션에 "D. TOKEN 카테고리 (downstream + tokens.json 존재 시)" 단락 추가
- "결과 양식" 섹션에 D 표 추가
- "Reviewer 와의 역할 경계" 표는 무변경
- 기존 IA/A11Y/CON 항목 무수정 (추가만)

**Step 3.3 — `.claude/bin/lint.py` 에 LINT-MR 검사기 추가**

- `LINT_MR_VARIANT_OVERLAY_EXCLUDES` 상수 추가 (결정 7)
- `check_mirror()` 함수 추가 (MR-1 ~ MR-5)
- `cmd_check()` 의 검사기 목록에 `LINT_MR` 등록
- `--only=LINT-MR` 옵션 분기 추가

**Step 3.4 — `CLAUDE.md` 통합** (가장 큰 변경)

다음 4 블록 갱신:

1. **빠른 시작 신규 블록**:
   ```markdown
   ### 디자인 결정 자동화 (Phase 7 업그레이드 — F011)

   /project:design-pick                              # 4 브랜드 비교표
   /project:design-pick recommend                    # designer 호출 → 비교 + 추천 + 시안
   /project:design-pick recommend --brand=apple      # apple 강제 (designer 추천 생략)
   /project:design-pick apply --brand=apple          # .claude/design/tokens.json 생성
   /project:design-pick show                         # 현재 tokens.json 표시
   /project:design-pick self                         # 셀프 dry-run

   > 사용 가능 변형: claude.gstack.auto.design/ 만.
   > 다운스트림이 design-pick apply 실행 시 .claude/design/tokens.json 생성.
   > design-review 가 tokens.json 존재 시 D. TOKEN 카테고리 자동 활성화.
   ```

2. **호출 기준 박스**:
   ```markdown
   ### design-pick 호출 기준

   - 새 UI 프로젝트 시작 시 디자인 토큰 결정 단계 — 1회
   - 4 브랜드 외 (`--brand=custom`) 신규 토큰 시스템 도입 시
   - 디자인 시스템 마이그레이션 (예: apple → spotify) 시 — 기존 tokens.json 자동 백업
   - 옵셔널 — 호출 안 해도 하네스 동작에 영향 없음
   ```

3. **5 변형 미러 매트릭스 표** (CLAUDE.md "harness_template 동기화 정책" 섹션):
   ```markdown
   ## 5 변형 미러 매트릭스 (F011 완료 후)

   | 변형 | F005~F010 | 자율 오버레이 | 디자인 오버레이 | 미러 정책 |
   |---|---|---|---|---|
   | ⓐ `claude/` | ❌ | ❌ | ❌ | Karpathy 만 |
   | ⓑ `claude.gstack/` | ✅ | ❌ | ❌ | 표준 SSoT 미러 |
   | ⓑ′ `claude.gstack.auto/` | ✅ | ✅ | ❌ | 자율 오버레이 포함 |
   | ⓑ″ `claude.gstack.auto.design/` | ✅ | ✅ | ✅ | 자율 + 디자인 오버레이 |
   | ⓒ `openai/.codex/` | ❌ | ❌ | ❌ | Karpathy 만 (stub) |

   > 미러 회귀 자동 감지: `/project:lint --only=LINT-MR` (F011)
   ```

4. **디렉토리 트리** 갱신:
   - `src/harness_template/claude.gstack.auto.design/` 신규 항목 추가
   - `.claude/agents/designer.md`, `.claude/commands/design-pick.md`, `.claude/bin/design_pick.py` 추가
   - `.claude/design/tokens.json` (런타임) 추가 + gitignore 주석

**Step 3.5 — 학습 jsonl append (3 개)**

- `architecture`: "디자인 자료 SSoT 는 메인 .claude/ — F005~F010 패턴 일관. 변형은 메인의 선별 포장
  (자율 / 디자인 오버레이별 변형 매트릭스)"
- `pattern`: "designer 에이전트는 추천까지만, design_pick.py 가 적용 결정론 — LLM 비결정 행동을
  헬퍼가 결정론으로 마무리하는 패턴 (F005~F010 일관)"
- `pitfall`: "F010 미러 회귀 2회 사고 학습 — 변형 증가 시 LINT-MR 같은 자동 가드 없이는 사람 실수
  방지 어려움. 디자인 오버레이 추가 시 ⓑ/ⓑ′ 에 잘못 들어가지 않게 결정 6 제외 목록 명시"

**Step 3.6 — 최종 미러 정합 동기화**

```bash
# ⓑ (자율 + 디자인 오버레이 제외)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  --exclude='design/' .claude/ src/harness_template/claude.gstack/harness/.claude/
rm -f src/harness_template/claude.gstack/harness/.claude/agents/{gatekeeper,designer}.md
rm -f src/harness_template/claude.gstack/harness/.claude/commands/design-pick.md
rm -f src/harness_template/claude.gstack/harness/.claude/bin/design_pick.py

# ⓑ′ (디자인 오버레이 제외 — gatekeeper 유지)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  --exclude='design/' .claude/ src/harness_template/claude.gstack.auto/harness/.claude/
rm -f src/harness_template/claude.gstack.auto/harness/.claude/agents/designer.md
rm -f src/harness_template/claude.gstack.auto/harness/.claude/commands/design-pick.md
rm -f src/harness_template/claude.gstack.auto/harness/.claude/bin/design_pick.py

# ⓑ″ (모든 오버레이 포함)
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='state/' \
  --exclude='design/' .claude/ src/harness_template/claude.gstack.auto.design/harness/.claude/

# CLAUDE.md / docs/adr/ADR-006 / docs/design/F007 / F011 도 3 변형 cp
for v in claude.gstack claude.gstack.auto claude.gstack.auto.design; do
  cp CLAUDE.md                                                     src/harness_template/$v/harness/
  cp docs/adr/ADR-006-design-pick-and-design-variant.md            src/harness_template/$v/harness/docs/adr/
  cp docs/design/F007-design-review-checklist.md                   src/harness_template/$v/harness/docs/design/
  cp docs/design/F011-tokens-schema.md                             src/harness_template/$v/harness/docs/design/
done
```

**Step 3.7 — LINT-MR 자체 검증**

```bash
python3 .claude/bin/lint.py --only=LINT-MR             # MR-1 ~ MR-5 모두 PASS 확인
python3 .claude/bin/lint.py                            # 전체 검사 — 모두 PASS 또는 명시적 CONCERN
```

**Step 3.8 — 세션 3 핸드오프**

- `feature_list.json` F011: `status: "in-progress" → "review"`
- `/project:context-save "F011 완료 — design-pick + claude.gstack.auto.design + LINT-MR + CLAUDE.md 통합"`
- claude-progress.txt 최종 항목

### 인수 기준 매핑

| AC | 충족 단계 | 비고 |
|---|---|---|
| AC1 — `claude.gstack.auto.design` 변형 신설 (claude.gstack.auto 1:1 + 디자인 오버레이) | 세션 1 Step 1.1 + 세션 3 Step 3.6 | 결정 6 |
| AC2 — 4 디자인 명세 → `docs/design-references/` | 세션 1 Step 1.2 | 결정 1 (경로 분기) |
| AC3 — `.claude/agents/designer.md` 신규 | 세션 1 Step 1.3 + 1.7 | 결정 2 |
| AC4 — `/project:design-pick` 커맨드 (designer → 비교 + 추천 + tokens.json) | 세션 2 Step 2.3~2.8 | 결정 3 |
| AC5 — `.claude/design/tokens.json` 출력 형식 정의 | 세션 1 Step 1.4 (스키마 문서) + 세션 2 Step 2.2 (카탈로그) + 2.5 (apply) | 결정 4 |
| AC6 — design-review 가 tokens.json 기반 일관성 점검 | 세션 3 Step 3.1 + 3.2 | 결정 5 (D. TOKEN 카테고리) |
| AC7 — CLAUDE.md 빠른 시작 + 호출 기준 | 세션 3 Step 3.4 | 일관성 |
| AC8 — 메인 → `claude.gstack.auto.design` 1:1 미러 + 디자인 오버레이 명시화 | 세션 1 Step 1.5 + 1.7 + 세션 3 Step 3.6 + LINT-MR | 결정 6 + 결정 7 |
| AC9 — 토큰 자동 추출은 후속 phase 분리 | ADR 결과 섹션 + 후속 조치 F012 | 사용자 사전 결정 |

### 피해야 할 패턴

- ❌ `.claude/settings.json` 수정 (F006 격리 — designer 에이전트 정의는 `.claude/agents/designer.md` 만)
- ❌ `claude/` (baseline) 또는 `openai/.codex/` 에 디자인 오버레이 미러 (결정 6 위배 — Karpathy 만)
- ❌ `claude.gstack/` 에 designer.md / design-pick.md / design_pick.py 미러 (결정 6 위배 — 표준 변형은 디자인 오버레이 제외)
- ❌ `claude.gstack.auto/` 에 designer.md / design-pick.md / design_pick.py 미러 (결정 6 위배 — 자율 변형은 디자인 오버레이 제외)
- ❌ `.claude/agents/` 의 기존 6 에이전트 (planner/architect/developer/reviewer/qa/gatekeeper) 정의 수정 (무회귀)
- ❌ 디자인 명세 4 파일을 `claude.gstack/` 또는 `claude.gstack.auto/` 에 복사 (결정 6 위배)
- ❌ `src/docs/design/ui/*.md` 4 원본을 변형으로 옮기거나 변경 (메인 SSoT — 무수정)
- ❌ tokens.json 에 BLOCK 라벨 (결정 5 — CONCERN/PASS 만, 점진적 도입)
- ❌ design-review CON 카테고리에 TOKEN 항목 통합 (결정 5 — 별 카테고리 D)
- ❌ tokens.json 다중 출력 (CSS + Tailwind + SCSS) — 본 phase JSON 만 (결정 4)
- ❌ `/project:design-pick` 대화형 입력 (`input()`) — 자율 모드 호환성 위배 (결정 3)
- ❌ designer 에이전트가 컴포넌트 코드 작성 (책임 경계 위배 — Developer 영역)
- ❌ designer 에이전트가 tokens.json 자동 적용 (결정 2 — design_pick.py 가 결정론적 적용 담당)
- ❌ tokens.json 자동 추출 (md 파싱) 구현 (옵션 3 — 후속 phase F012)
- ❌ LINT-MR 검사기를 별도 `mirror.py` 헬퍼로 분리 (결정 7 — lint.py 단일 확장)
- ❌ 신규 mirror.py / `/project:mirror` 커맨드 신설 (결정 7 위배)
- ❌ 변형 미러 자동화 가드 누락 (결정 7 — LINT-MR 필수)
- ❌ designer 에이전트 sonnet 모델로 다운그레이드 (결정 2 — opus 필수, 4 명세 비교 추론 깊이)
- ❌ `/project:design-pick` 의 서브커맨드를 단일 동작으로 압축 (결정 3 — F005/F009/F010 패턴 위배)
- ❌ `.claude/design/tokens.json` 을 git 커밋 (런타임 생성 — gitignore 필수)
- ❌ 기존 ADR (ADR-001 ~ ADR-005) 수정 (무회귀)
- ❌ F011 세션 1 ~ 3 동안 `feature_list.json` 의 `passes` 필드 수정 (QA 단독 권한)

---

## 부록 A — designer 에이전트 vs design-review 스킬 책임 경계 (재명시)

F007 의 Reviewer ↔ design-review 분리 + F011 의 designer / design_pick.py / design-review 분리.
3 도구 + 1 에이전트가 디자인 라이프사이클을 분담:

| 단계 | 도구/에이전트 | 책임 | 라벨 사용 |
|---|---|---|---|
| **선택** (브랜드·토큰 결정) | designer 에이전트 + `/project:design-pick recommend` | 4 브랜드 비교 + 추천 산문 + tokens.preview.json 시안 | (LLM 산문) |
| **적용** (tokens.json 생성) | `design_pick.py apply` (결정론적 헬퍼) | 정적 카탈로그 → tokens.json 백업·생성 | (결정론) |
| **구현** (컴포넌트 작성) | Developer 에이전트 | tokens.json 참조해 UI 코드 작성 | (코드) |
| **감사** (정합성 점검) | design-review 스킬 + `/project:design-review` | IA / A11Y / CON / **D. TOKEN** 카테고리 검사 | PASS / CONCERN / BLOCK |
| **거버넌스** (미러 정합) | lint.py LINT-MR + `/project:lint --only=LINT-MR` | 5 변형 매트릭스 정합 검증 | PASS / BLOCK |

이 5 단계가 디자인 라이프사이클의 좌측 끝부터 우측 끝까지 단일 SSoT 흐름을 보장.

---

## 부록 B — 5 변형 매트릭스 산출물 분포표 (Developer / QA 참고)

| 산출물 | ⓐ `claude/` | ⓑ `claude.gstack/` | ⓑ′ `claude.gstack.auto/` | **ⓑ″ `claude.gstack.auto.design/`** | ⓒ `openai/.codex/` |
|---|:---:|:---:|:---:|:---:|:---:|
| `.claude/agents/{planner,architect,developer,reviewer,qa}.md` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/agents/gatekeeper.md` | ❌ | ❌ | ✅ | ✅ | ❌ |
| `.claude/agents/designer.md` (F011) | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/commands/{handoff,start-session,...}.md` (공통) | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/commands/design-pick.md` (F011) | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/commands/design-review.md` (F007) | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/{brain,host,lint,backup}.py` | ❌ | ✅ | ✅ | ✅ | ❌ |
| `.claude/bin/design_pick.py` (F011) | ❌ | ❌ | ❌ | ✅ | ❌ |
| `.claude/skills/design-review/SKILL.md` (F007 + F011 D. TOKEN 추가) | ❌ | ✅ | ✅ | ✅ | (Karpathy 만) |
| `docs/design-references/{apple,claude,spotify,tesla}-design.md` (F011) | ❌ | ❌ | ❌ | ✅ | ❌ |
| `docs/design/F011-tokens-schema.md` (F011) | ❌ | ✅ | ✅ | ✅ | ❌ |
| `docs/adr/ADR-006-*.md` (F011) | ❌ | ✅ | ✅ | ✅ | ❌ |
| Karpathy 4원칙 (think/simplicity/surgical/goal) | ✅ | ✅ | ✅ | ✅ | ✅ |

→ 디자인 오버레이는 **ⓑ″ 에만 존재**. ⓑ + ⓑ′ 는 자율 + 표준 정체성 보존.

---

*작성: architect 에이전트 | 날짜: 2026-06-02 | 상태: Accepted*
