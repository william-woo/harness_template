# 코딩 표준

> 모든 에이전트가 따라야 하는 코딩 규칙. 프로젝트 시작 시 기술 스택에 맞게 수정하세요.

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
