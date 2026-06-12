# /project:skill-forge — 스킬 자동 생성 + self-improve + agentskills.io 검증 (claude.hermes 전용)

Hermes Agent 의 "복잡 작업 후 재사용 스킬 자동 생성 + 사용 중 self-improve" 패턴을
하네스에 이식한다. 스킬은 **agentskills.io 개방 표준**(Anthropic 원작)에 맞춰 생성·검증한다 (ADR-010).

## 사용법

```bash
# 새 스킬 scaffold (표준 구조 + frontmatter)
python3 .claude/bin/skill_forge.py new <name> --description "<무엇 + 언제 사용>"

# 누적 학습으로부터 스킬 초안 생성
python3 .claude/bin/skill_forge.py from-learning <learning-key>

# agentskills.io 표준 검증 (미지정 시 전체 스킬)
python3 .claude/bin/skill_forge.py validate [<skill-dir>]

# self-improve 추적
python3 .claude/bin/skill_forge.py record-use <name>      # 사용 1회 기록
python3 .claude/bin/skill_forge.py nudge --threshold 5    # 자주 쓰인 스킬 = 개선 후보
python3 .claude/bin/skill_forge.py list                   # 목록 + uses/version
```

## 워크플로 (자동 생성 + self-improve 루프)

1. **생성**: 복잡한 작업을 반복하게 되면 `new` 또는 `from-learning` 으로 스킬을 scaffold.
   헬퍼는 **구조·메타데이터·표준 적합성**만 만든다 — **본문(단계/예시/엣지케이스)은 에이전트가 작성**.
   (Karpathy: 추측 자동화 금지 — 결정론적 부분만 자동화)
2. **사용 추적**: 그 스킬을 쓸 때마다 `record-use` 로 카운트 (metadata.uses 증가).
3. **self-improve nudge**: `nudge` 가 `uses>=임계치` 인데 오래 개선 안 된 스킬을 짚는다.
   → 에이전트가 본문을 다듬고 `metadata.version` 증가 + `last_improved` 갱신.
4. **검증**: handoff 전 `validate` 로 모든 스킬의 agentskills.io 적합성 확인.

## agentskills.io 표준 (요약)

- 스킬 = `SKILL.md` 를 가진 폴더 (+ 선택 `scripts/`, `references/`, `assets/`)
- 필수 frontmatter: `name`(1-64, 소문자·숫자·하이픈, 디렉토리명과 일치) + `description`(1-1024)
- 선택: `license`, `compatibility`(≤500), `metadata`(맵), `allowed-tools`
- progressive disclosure: 평소 name+description 만 로드 → 활성화 시 본문 → 필요 시 references

## 호출 기준

- 같은 절차를 2회 이상 반복하게 됐을 때 (재사용 스킬로 승격)
- `/project:learn` 으로 쌓인 학습이 절차적 지식일 때 (`from-learning`)
- 새 스킬 추가/수정 후 handoff 전 (`validate`)

> **claude.hermes 변형 전용** — 다른 변형엔 skill_forge.py 가 없다 (LINT-MR-10 격리).
> 기존 하네스 스킬(coding/testing/planning/...)은 이미 agentskills.io 호환 (validate PASS 확인됨).
