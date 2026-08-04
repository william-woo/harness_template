# 코딩 표준

> 모든 에이전트가 따라야 하는 코딩 규칙. 프로젝트 시작 시 기술 스택에 맞게 수정하세요.

## 외부 의존성 정책 (변형별)

| 변형 | 외부 의존성 | 허용 카탈로그 | 격리 강제 |
|---|---|---|---|
| `claude/` (baseline) | 0 | — | LINT-MR-7 |
| `claude.gstack/` | 0 | — | LINT-MR-7 |
| `claude.gstack.auto/` | 0 | — | LINT-MR-7 |
| `claude.gstack.auto.design/` | 0 | — | LINT-MR-7 |
| **`claude.gstack.auto.design.wiki/`** | **허용** | Obsidian / qmd / Marp | LINT-MR-7 (반대 방향 — 허용 확인) |
| **`claude.gstack.auto.design.wiki.orch/`** | **허용** (wiki 상속) | Obsidian / qmd / Marp (wiki 복사) | LINT-MR-7/MR-8 (orch 자체는 stdlib only) |
| **`localllm/`** (d-2, loope 계보) | **허용** (loope 상속 + OpenCode/Ollama) | Obsidian/qmd/Marp + OpenCode/Ollama | LINT-MR-9 (d-2 격리) + MR-10/11/13 (계보 오버레이) |
| **`claude.hermes/`** | **허용** (wiki 상속) | Obsidian/qmd/Marp (hermes 기능은 stdlib) | LINT-MR-10 (hermes 오버레이 격리) |
| **`claude.productmgr/`** | **허용** (hermes 상속) | Obsidian/qmd/Marp (pm 오버레이는 stdlib/문서) | LINT-MR-11 (pm 오버레이 격리) |
| **`claude.productnw/`** (d-3) | **허용** (productmgr 상속) | Obsidian/qmd/Marp (nw 오버레이는 stdlib/문서) | LINT-MR-12 (nw 오버레이 격리) |
| **`claude.loope/`** | **허용** (productmgr 상속) | Obsidian/qmd/Marp (loop 오버레이는 stdlib/문서) | LINT-MR-13 (loop 오버레이 격리) |
| `openai/.codex/` | 0 | — | LINT-MR-7 |

**wiki 변형 예외 계약**:
- wiki/orch 변형을 가져가는 다운스트림은 외부 도구 설치를 감수한다 (선택적 — graceful degrade)
- 허용 도구: Obsidian (graph view), qmd (BM25/vector 검색), Marp (슬라이드)
- 핵심 wiki 기능 (.md + [[wikilink]] 노드 관리) 은 stdlib only — 외부 도구는 *향상*만
- orch 변형은 wiki 의 외부 의존성 정책 상속 + orch 자체 (researcher/orchestrate) 는 stdlib only
- 다른 4 변형은 이 예외를 절대 상속하지 않음 (LINT-MR-7 이 강제)

**localllm 변형 (d-2) 예외 계약** (ADR-009/017):
- OpenCode + Ollama(로컬 LLM) 구동 — API 비용 0 + 오프라인 추론(보안). 외부 도구는 선택적(graceful degrade)
- **F023 loope 계보 승격**: hermes(session_search/skill_forge)+pm(product-cycle)+loop(verify_loop/hill_climb) 오버레이 보유 — 전부 stdlib. 판정(judge) 역할은 32B+ 로컬 모델 권장
- 핵심 어댑터(opencode.py)·헬퍼는 stdlib only — OpenCode/Ollama 는 *실행 환경*일 뿐
- **검증 범위**: 단일역할(14B) E2E 완료(측정 04) + **loope 도구 조작(32B) E2E 완료(측정 05-5)**. 멀티스텝 값 전달(G4)은 32B Q4 실측 실패(측정 05) — 파일 핸드오프·결정론 도구 우회 + 오케스트레이션은 상위 호스트 하이브리드 권장
- LINT-MR-9 가 d-2 오버레이(.opencode/ 런타임 + docs/poc + opencode-setup.sh) 의 localllm 전용 격리를 강제

**claude.hermes 변형 예외 계약** (ADR-010):
- NousResearch/hermes-agent 패턴 이식 — FTS5 세션검색 + 스킬 자동생성/self-improve + agentskills.io 표준
- 외부 의존성은 wiki 상속분(Obsidian/qmd/Marp)만 허용. **hermes 3종 기능(session_search/skill_forge)은 stdlib only**
- Hermes 본체의 메시징 게이트웨이·유저모델링 등 무거운 부분은 **미이식** (개인비서 영역 — SDLC 하네스 목적과 불일치)
- LINT-MR-10 이 hermes 오버레이(session_search.py + skill_forge.py + 커맨드 2종) 의 claude.hermes 전용 격리를 강제

**claude.productmgr 변형 예외 계약** (ADR-011):
- hermes 변형 복사 + pm 오버레이 — Product Manager 주도 통합 SDLC(기획→설계→개발→검증→배포)
- 외부 의존성은 hermes 상속분(Obsidian/qmd/Marp)만. **pm 오버레이(product-manager.md/product-cycle.md)는 stdlib/문서뿐 — 신규 의존성 0**
- PM=제품 brief(why·what·성공지표) / planner=feature 분해. PM 은 passes·코드 직접 수정 안 함 (조율자)
- "배포"=하네스 게이트(lint→ship→backup-sync). 실제 prod CI/CD 는 다운스트림 위임
- LINT-MR-11 이 pm 오버레이의 claude.productmgr 전용 격리를 강제

**claude.productnw 변형 예외 계약** (ADR-012, d-3):
- productmgr 변형 복사 + nw 오버레이 — 분산 멀티팀 에이전트 컨소시엄 (팀 간 메시지 계약으로 통합 제품)
- 외부 의존성은 productmgr 상속분(Obsidian/qmd/Marp)만. **nw 오버레이(consortium.py/consortium.md)는 stdlib/문서뿐 — 신규 의존성 0**
- **"프로토콜은 stdlib 로 실재, 네트워크 전송은 stub"**: 메시지 계약+로스터+로컬 큐는 동작, Teams/Slack/Telegram 게이트웨이는 codex/openclaw 처럼 stub (실제 봇 transport·자격증명#3-A 는 다운스트림 책임)
- 팀 내부는 single-host(d-1, 같은 컨텍스트 풀), 팀 **사이**만 계약 연결 — d-3 의 정직한 경계
- **검증 범위**: 로컬 큐(같은 머신) E2E 검증 완료. 실제 원격 봇 연동은 다운스트림이 게이트웨이를 붙여 완성 (localllm 의 32B 위임과 동일 패턴)
- LINT-MR-12 가 nw 오버레이의 claude.productnw 전용 격리를 강제

**claude.loope 변형 예외 계약** (ADR-014):
- productmgr 변형 복사 + loop 오버레이 — LangChain loop engineering 의 Loop 2(검증 루프) 정형화
- 외부 의존성은 productmgr 상속분(Obsidian/qmd/Marp)만. **loop 오버레이(verify_loop.py/rubrics/커맨드)는 stdlib/문서뿐 — 신규 의존성 0**
- **라이브러리 미채택**: LangChain/LangGraph 는 zero-dep·실행모델(host 가 루프 소유)·LangSmith(SaaS) 이유로 부적합 → "루프를 명시·유계로" 규율만 이식
- grader 결정론(lint/design-review/qa-browser) vs judge(reviewer/qa) 구분. revision 3회 자동 에스컬레이션(산문 규칙의 코드화)
- LINT-MR-13 이 loop 오버레이의 claude.loope 전용 격리를 강제

---

## 프롬프트 규율 (Claude 4.6+/5 세대)

신세대 모델은 지시를 **문자 그대로** 따른다. 에이전트·커맨드 프롬프트 작성 시:

1. **강지시어 절제**: "CRITICAL: 반드시 X 도구를 써라" 류는 과잉 트리거를 유발한다.
   "X가 유용한 경우 사용" 처럼 조건을 서술한다. 프로세스 규칙(테스트 동반·커밋 규율)은 예외.
2. **검증 지시 중복 금지**: "다시 확인하라/double-check" 류 self-check 프롬프트를 넣지 않는다
   (신모델은 스스로 검증 — 중복 지시는 과잉검증 유발). **프로세스 게이트(Reviewer→QA, verify-loop)는 유지** — 그것은 프롬프트가 아니라 파이프라인이다.
3. **De-prescribe**: 목표·제약·완료조건 중심으로 서술하고, step-by-step 처방은 순서가 정말 중요한 곳에만 쓴다.

## Simplicity First (Karpathy)

코드는 동작해야 하고, 읽혀야 하고, 유지보수 가능해야 한다. 이 세 목표는 모두 단순함에서 온다.

1. **단순한 답 우선**: 영리한 해법보다 멍청해 보이는 해법이 더 자주 옳다. 비슷한 코드 3줄이 섣부른 헬퍼 함수보다 낫다. 나중에 패턴이 보이면 그때 추상화한다.
2. **추측 추상화 금지**: 두 곳 이상에서 호출되기 전엔 함수로 빼지 않는다. 한 번만 쓰일 인터페이스·제네릭·베이스 클래스 도입을 금지한다. "나중에 필요할 것 같다"는 이유로 추상화하지 않는다.
3. **반쪽 구현 금지**: 동작하지 않는 스텁·TODO 주석·주석 처리된 코드를 커밋에 남기지 않는다. 기능을 시작했으면 그 세션 안에 작동하는 상태로 끝낸다.
4. **에러 처리는 경계에서만**: 내부 함수 간 호출은 신뢰하고 try/except를 남발하지 않는다. 사용자 입력·외부 API·파일 I/O 같은 경계에서만 방어한다. 일어날 수 없는 케이스에 예외 처리를 추가하지 않는다. (단, 훅 스크립트는 예외 — hook-failure-tolerance 정책 유지)

---

## 공통 규칙 (모든 언어)

### 함수/메서드
- 단일 책임 원칙: 함수 하나는 한 가지 일만
- 길이: 40줄 이하 권장 (초과 시 분리 검토)
- 파라미터: 4개 이하 (초과 시 객체/구조체로 묶기)
- 반드시 docstring/JSDoc 작성

### 네이밍
- 변수: 의도를 드러내는 이름 (`userData` ✅, `d` ❌)
- Boolean: `is`, `has`, `can`으로 시작 (`isLoading`, `hasPermission`)
- 함수: 동사로 시작 (`getUserById`, `processPayment`)
- 상수: UPPER_SNAKE_CASE

### 에러 처리
- 모든 외부 API 호출에 에러 핸들링
- 에러 메시지에 컨텍스트 포함 (`"결제 처리 실패: [이유]"`)
- 에러 삼켜버리기 금지 (`catch(e) {}` ❌)

### 주석
- 코드가 무엇을 하는지(what)가 아닌 왜(why)를 주석으로
- TODO는 반드시 이유와 날짜 포함: `// TODO(2026-04-15): 성능 개선 필요 - N+1 쿼리`

---

## TypeScript/JavaScript

```typescript
// ✅ 권장
export async function getUserById(userId: string): Promise<User | null> {
  /**
   * 사용자 ID로 사용자 정보를 조회한다.
   * 존재하지 않는 경우 null 반환 (에러 throw 하지 않음).
   */
  try {
    return await db.users.findById(userId);
  } catch (error) {
    logger.error('사용자 조회 실패', { userId, error });
    throw new DatabaseError(`사용자 조회 실패: ${userId}`);
  }
}

// ❌ 금지
const get = async (id) => {  // 타입 없음, 이름 불명확
  const r = await db.find(id);  // 변수명 불명확
  return r;
}
```

### TypeScript 규칙
- `any` 타입 사용 금지 (→ `unknown` 또는 명확한 타입)
- `interface`로 API 응답 형식 반드시 정의
- `strict: true` 모드 유지

---

## Python

```python
# ✅ 권장
def process_payment(
    user_id: str,
    amount: Decimal,
    currency: str = "KRW"
) -> PaymentResult:
    """
    결제를 처리하고 결과를 반환한다.
    
    Args:
        user_id: 결제를 요청한 사용자 ID
        amount: 결제 금액 (소수점 지원)
        currency: 통화 코드 (기본값: KRW)
        
    Returns:
        PaymentResult: 결제 결과 (성공 여부, 트랜잭션 ID 포함)
        
    Raises:
        PaymentError: 결제 처리 중 오류 발생 시
        ValueError: amount가 0 이하인 경우
    """
    if amount <= 0:
        raise ValueError(f"결제 금액은 0보다 커야 합니다: {amount}")
    ...
```

### Python 규칙
- Type hints 필수
- Pydantic 모델로 API 요청/응답 정의
- f-string 사용 (`format()`, `%` 사용 금지)

---

## 테스트 작성 규칙

```typescript
// 테스트 구조: Given-When-Then
describe('getUserById', () => {
  it('존재하는 사용자 ID로 조회하면 사용자 정보를 반환한다', async () => {
    // Given: 테스트 데이터 준비
    const userId = 'user-123';
    await db.users.create({ id: userId, name: '홍길동' });
    
    // When: 테스트 대상 실행
    const result = await getUserById(userId);
    
    // Then: 결과 검증
    expect(result).not.toBeNull();
    expect(result?.name).toBe('홍길동');
  });

  it('존재하지 않는 사용자 ID로 조회하면 null을 반환한다', async () => {
    const result = await getUserById('non-existent');
    expect(result).toBeNull();
  });
});
```

## 파일 크기 가이드

| 파일 유형 | 권장 크기 | 최대 |
|---|---|---|
| 컴포넌트 | 150줄 | 300줄 |
| 서비스 클래스 | 200줄 | 400줄 |
| 유틸리티 | 100줄 | 200줄 |
| 테스트 파일 | 제한 없음 | - |
