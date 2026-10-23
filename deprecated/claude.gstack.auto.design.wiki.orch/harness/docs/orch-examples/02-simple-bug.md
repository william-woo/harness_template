# 시나리오 2: 단순 버그 — 로그인 버튼 두 번 제출 방지

> 참조: ADR-008 결정 4 (조건부 라우팅), orchestrate.md 라우팅 매트릭스
> 패턴: 최소 라우팅 (조건부 스킵 시연)

---

## 요청

```
/project:orchestrate "로그인 버튼 클릭 시 두 번 제출되는 버그 수정 — 디바운스 또는 비활성화 처리"
```

---

## 라우팅 판정

supervisor 가 요청을 분석해 각 단계의 필요 여부를 결정한다.

| 단계 | 판정 | 이유 |
|---|:---:|---|
| **researcher** | ❌ 스킵 | 익숙한 영역 — 폼 제출 중복 방지는 표준 패턴 (디바운스/isLoading 상태). 외부 조사 불필요 |
| **architect** | ❌ 스킵 | 구조 변경 없음 — 기존 LoginButton 컴포넌트 내부 로직 수정 (1 파일) |
| **designer** | ❌ 스킵 | UI 변경 없음 — 버튼 외관 그대로, 동작만 수정 |
| **developer** | ✅ 활성 | 코드 변경 발생 |
| **reviewer** | ✅ 활성 | 코드 변경 후 기본 포함 |
| **qa + qa-browser** | ⚠ 조건부 | acceptance_criteria 가 "두 번 클릭해도 1회만 제출" — 단위 테스트로 충분 (이벤트 핸들러 mocking). qa-browser 는 선택적 |
| **design-review** | ❌ 스킵 | UI 변경 없음 |

**라우팅 매트릭스 분류**: "단순 버그 수정" → 최소 라우팅 (developer + reviewer 만).

> **참고**: orchestrate 없이 `Use the developer agent to fix:` 직접 호출도 충분한 경우.
> orchestrate 를 쓰는 이유: 핸드오프 디렉토리에 버그 수정 이력을 남기고 싶을 때.

---

## 핸드오프 디렉토리 상태

```
.claude/state/orch/2026-06-05T09-00-00-fix-login-double-submit/
├── request.md      ← 원본 요청 + 라우팅 판정 (스킵 이유 명시)
├── plan.md         ← 단계 순서: developer → reviewer (researcher/architect/designer 스킵)
├── impl.md         ← 구현 요약 (LoginButton isSubmitting 상태 추가, onClick 가드)
├── review.md       ← APPROVED (1차)
└── final.md        ← 통합 리포트 (단순 — 2개 단계)
```

flow.md, research.md, adr.md, design.md, qa.md 없음 (해당 단계 스킵).

---

## 단계별 실행 흐름

### Step 0: task-id 발급 + 라우팅 판정 기록

request.md:
```markdown
# 원본 요청
로그인 버튼 클릭 시 두 번 제출되는 버그 수정

## 라우팅 판정
- researcher: 스킵 (익숙한 영역 — 중복 제출 방지는 표준 패턴)
- architect: 스킵 (1 파일 수정, 구조 변경 없음)
- designer: 스킵 (UI 외관 변경 없음)
- developer: 필요
- reviewer: 필요
- qa: 선택적 (단위 테스트로 충분)
- design-review: 스킵

## 단계 순서
1. developer
2. reviewer
```

### Step 1: developer 직접 호출

```
Use the developer agent to fix:

ISSUE: 로그인 버튼 클릭 시 두 번 제출되는 버그
FILE: src/components/LoginButton.tsx
APPROACH: onClick 핸들러에 isSubmitting 상태 추가 + 제출 중 버튼 disabled
```

구현:
```typescript
// LoginButton.tsx — isSubmitting 상태 추가
const [isSubmitting, setIsSubmitting] = useState(false);

const handleSubmit = async () => {
  if (isSubmitting) return;  // 중복 제출 방지
  setIsSubmitting(true);
  try {
    await onSubmit();
  } finally {
    setIsSubmitting(false);
  }
};
```

impl.md:
```markdown
## 구현 요약
- LoginButton.tsx: isSubmitting 상태 추가 (useState)
- onClick 가드: isSubmitting 시 early return
- 버튼 disabled 속성: isSubmitting 동안 비활성
- 단위 테스트: LoginButton.test.tsx — 두 번 클릭 시 onSubmit 1회만 호출 확인
```

### Step 2: reviewer 호출

```
Use the reviewer agent to review:

FEATURE: 로그인 버튼 중복 제출 방지 버그 수정
IMPL_SUMMARY: <impl.md 전체>
```

review.md → APPROVED (1차).

리뷰 항목:
- isSubmitting 초기값 false 확인
- finally 블록으로 예외 시에도 상태 복원 확인
- disabled 속성으로 UX 피드백 확인

### Step 3: (선택적) qa 단위 테스트 확인

qa-browser 불필요 — 단위 테스트로 충분:
```typescript
// LoginButton.test.tsx
it('두 번 클릭해도 onSubmit 은 1회만 호출된다', async () => {
  const onSubmit = jest.fn(() => new Promise(r => setTimeout(r, 100)));
  render(<LoginButton onSubmit={onSubmit} />);
  
  fireEvent.click(screen.getByRole('button'));
  fireEvent.click(screen.getByRole('button'));  // 두 번째 클릭
  
  await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
});
```

### Step 4: final.md

```markdown
# 오케스트레이션 완료 — fix-login-double-submit

## 요약
로그인 버튼 중복 제출 버그 수정 완료. 최소 라우팅 (developer + reviewer).

## 스킵 단계
- researcher: 익숙한 영역 (중복 제출 방지 표준 패턴)
- architect: 1 파일 수정, 구조 변경 없음
- designer: UI 외관 무변경
- design-review: UI 변경 없음
- qa-browser: 단위 테스트로 충분

## 결과
- developer: 구현 완료 (isSubmitting 상태 + finally 복원)
- reviewer: APPROVED (1차)
- 단위 테스트: 1회만 호출 확인

## 총 소요 단계
2 / 7 (researcher/architect/designer/design-review/qa 스킵)
```

---

## 학습 포인트

- **orchestrate 가 오버킬인 경우**: 이 요청은 `Use the developer agent to fix:` 직접 호출이 더 효율적. orchestrate 는 핸드오프 이력이 필요할 때 가치를 발휘.
- **스킵 판정 명시**: plan.md 에 스킵 이유를 기록 — QA 가 "왜 researcher 를 안 썼나" 를 이해 가능.
- **단위 테스트 vs qa-browser**: "두 번 클릭 시 1회만 제출" 은 이벤트 mocking 으로 충분 — Playwright 불필요. F008 호출 기준 일관 ("URL 방문·폼 입력·라우팅" 에 해당하지 않음).
- **최소 라우팅 전략**: 불필요한 단계 제거 = 토큰 효율 ↑ + 사용자 신뢰 ↑ (orchestrate 가 항상 풀 파이프라인을 강제하지 않는다는 신뢰).
