# ADR-017: localllm 변형 loope 계보 승격 + render-commands + 역할별 로컬 모델 등급 코드화

> Feature: F023 — localllm 하네스를 claude.loope 처럼 동작하도록 승격
> 상태: `Accepted` (구현 — localllm 변형 + 어댑터/lint 는 main·10 변형 미러)
> 관련: ADR-009(opencode 어댑터), ADR-014(loop engineering), ADR-015(main≡loope SSOT), ADR-016(모델 별칭)

## 맥락

localllm(d-2) 변형은 F015 에서 **orch 변형 복사본 + d-2 오버레이**로 만들어졌다. 이후 하네스는
hermes(F016)·pm(F018)·loop(F020)·loope 승격(F021)을 거치며 발전했지만 localllm 은 orch 세대에
머물러 있었다 — 로컬 LLM 사용자는 검증 루프·세션 검색·PM 사이클 없이 구세대 하네스를 쓰는 상태.

사용자 요청 (2026-08-05): "localllm 하네스 템플릿으로 실제 로컬 LLM 하네스를 구성하고,
**claude.loope 를 활용하는 것처럼 동작**하도록 업데이트하라. 에이전트가 작업을 제대로 할 수
있도록 최대한 발전시켜라."

환경 변화: PoC 시점(F015)에 없던 **qwen2.5:32b-instruct-q4_K_M (tools 지원)** 이 Ollama 서버에
확보됨 — F015 가 보류한 "측정 05 (32B 멀티스텝)" 실측이 가능해졌다.

## 결정

### 결정 1 — localllm 계보 전환: orch → loope (hermes+pm+loop 오버레이 이식)
session_search/skill_forge(hermes), product-manager/product-cycle(pm),
verify_loop/hill_climb/rubrics(loop) 를 localllm 에 이식한다. **전부 stdlib** — d-2 의
"핵심은 stdlib only" 계약 유지. LINT-MR-10/11/13 의 보유 변형 목록에 localllm 추가.
qa/reviewer/retro 는 loope 버전(Loop 2 기록 절차 포함) 채택.

### 결정 2 — Loop 2 × 로컬 LLM: "결정론 grader 우선"을 d-2 의 1급 규율로
verify-loop 의 결정론 grader(lint/design-review/qa-browser/test — stdlib 스크립트)는 **모델
크기와 무관하게 100% 신뢰**할 수 있다. 로컬 LLM 의 최대 약점인 검증형 다홉 추론(측정 04:
14B reviewer 판정 실패)을 값싼 결정론 게이트가 선처리하고, judge(reviewer/qa) 판정만
32B 로 올린다. **loope 계보 이식이 로컬 LLM 하네스의 실용성을 구조적으로 끌어올리는 이유.**

### 결정 3 — render-commands 신설 (ADR-009 결정 3 의 보류 항목 구현)
opencode 어댑터에 `render_commands()` 를 추가하고 host.py 에 `render-commands` 서브커맨드를
배선한다. `.claude/commands/*.md` → `.opencode/commands/<name>.md` (OpenCode 커스텀 커맨드
포맷 — opencode.ai/docs/commands): 첫 헤딩에서 description 추출, `/project:foo` → `/foo` 표기
정규화, `$ARGUMENTS` 블록 보장, agent/model frontmatter 는 비지정(호출 시점/opencode.json 결정).
render-agents 와 동일한 멱등 규약(전량 덮어쓰기 + stale 삭제). 30 커맨드 변환 검증 완료.

### 결정 4 — 역할 → 모델 등급을 opencode.json 으로 코드화
프로젝트 루트 `opencode.json` (전역 설정과 deep-merge, baseURL 은 전역에 위임):
- 생성형(developer/architect/designer/planner/researcher/gatekeeper) → `qwen2.5:14b-instruct-q8_0`
- 판정·다홉(reviewer/qa/product-manager) → `qwen2.5:32b-instruct-q4_K_M`
ADR-016 의 "역할별 모델 차등(judge=상위 모델)" 원칙의 로컬 LLM 대응물. MODEL-GRADES 의
산문 권고가 설정 파일로 강제된다.

### 결정 5 — 측정 05: 경로 훼손은 32B 에도 잔존 — 얕은 경로 규율 추가
32B 멀티스텝 실측 중 **서브에이전트가 상대경로에 선행 `/` 를 붙여**
(`/.claude/state/...`) OpenCode external_directory 권한 프롬프트에 걸리고, headless 실행이
응답 불가로 **행**하는 실패 모드를 확인했다. 대응:
- AGENTS.md 에 5번 규칙 "얕은 경로 — 선행 슬래시 금지, 숨김 디렉토리(.claude/...) 대신
  프로젝트 루트 근처 경로 사용" 추가
- 로컬 LLM 용 산출물·핸드오프 파일은 얕은 상대경로 권장 (헬퍼 스크립트 인자로 넘길 땐 무관 —
  bash 도구는 cwd 기준)

### 결정 6 — 적용 범위와 미러
localllm 변형이 1차 대상. 어댑터(opencode.py/claude_code.py/host.py)와 lint.py 는 공용
인프라이므로 main + 10 변형 전체 미러 (ADR-015 SSOT 규약). CLAUDE.md/coding-standards 의
변형 매트릭스·오버레이 목록·커맨드 전용 표기도 전체 갱신. baseline/openai 동결 유지.
MultiEdit 잔재(스킬 도구표·freeze/host 커맨드)도 이번에 일소 (ADR-016 후속 — claude_code
어댑터 multiedit 토큰은 `Edit` 로 렌더).

## 대안 검토

- **localllm 을 loope 1:1 + d-2 로 재생성 (전체 복사)**: settings/호스트 구성·d-2 보강(coding
  스킬 상대경로 등)을 잃는다 — 오버레이 선별 이식이 안전. 기각.
- **판정 역할도 14B 유지 + 사람 검증**: 32B 확보로 불필요한 타협. 기각 (하이브리드는 여전히
  문서에 대안으로 남김).
- **OpenCode plugin 으로 훅 이식**: 외부 의존(플러그인 API) + 유지보수 부담. 커맨드/에이전트
  렌더만으로 하네스 흐름이 성립 — 보류 (후속 검토).

## 결과

- localllm = loope 계보(auto+design+wiki+orch+hermes+pm+loop) + d-2 오버레이. 이식 도구
  전수 실동작 확인 (verify_loop 풀사이클 / hill_climb / session_search / skill_forge).
- render-agents 9 에이전트 + render-commands 30 커맨드 산출 (+ 로컬 LLM 실행 힌트 자동 부착
  — 측정 05-7 행동 교정 실증).
- 측정 05 (05-0 ~ 05-10): G4@32B 실패(정직 기록) / **Loop 2 풀사이클 + 자동 에스컬레이션
  실동작(05-8)** / 스킬 네이티브 발견(05-9) / **세션 회상 d-2 확장(05-10 — OpenCode 세션 DB
  21건 색인·회상)** → docs/poc/measurements/05-32b-multistep.md + MODEL-GRADES 갱신.
- lint LINT-MR 0 BLOCK (MR-10/11/13 보유 목록에 localllm 등재).

## 보류 (후속 phase 후보)

- OpenCode plugin 훅 이식 (settings.json hooks 상당) — plugin API 의존이라 보류
- 측정 06: 신형 로컬 모델(코딩 특화·더 큰 양자화)로 G4 재도전 + judge 품질 벤치
- render-skills 의 .opencode/skills/ 출력 — OpenCode 가 .claude/skills 를 네이티브 발견하므로 현재 불필요
