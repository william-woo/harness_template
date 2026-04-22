# Coding Skill

> 코드 구현 시 참조하는 스킬. **Developer 롤**이 기능을 구현할 때 사용한다.
> 패턴: 구현 → 테스트 → 커밋 → 인계

## 구현 패턴

### API 엔드포인트 구현 (Express/FastAPI)

```typescript
// 1. 타입 정의 먼저
interface CreateUserRequest {
  email: string;
  password: string;
  name: string;
}

interface CreateUserResponse {
  id: string;
  email: string;
  name: string;
  createdAt: string;
}

// 2. 서비스 레이어
async function createUser(req: CreateUserRequest): Promise<CreateUserResponse> {
  // 입력 검증
  validateEmail(req.email);
  validatePassword(req.password);
  
  // 비즈니스 로직
  const hashedPassword = await hashPassword(req.password);
  const user = await db.users.create({
    email: req.email,
    passwordHash: hashedPassword,
    name: req.name,
  });
  
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    createdAt: user.createdAt.toISOString(),
  };
}

// 3. 컨트롤러
router.post('/users', async (req, res) => {
  try {
    const result = await createUser(req.body);
    res.status(201).json(result);
  } catch (error) {
    if (error instanceof ValidationError) {
      res.status(400).json({ error: error.message });
    } else {
      logger.error('사용자 생성 실패', error);
      res.status(500).json({ error: '서버 오류가 발생했습니다' });
    }
  }
});
```

### 테스트 패턴 (Jest/Pytest)

```typescript
// 구현과 동시에 작성 — 나중으로 미루지 않는다
describe('createUser', () => {
  beforeEach(async () => {
    await db.users.deleteMany({});  // 격리
  });

  it('유효한 정보로 사용자를 생성한다', async () => {
    const result = await createUser({
      email: 'test@example.com',
      password: 'SecurePass123!',
      name: '홍길동',
    });

    expect(result.id).toBeDefined();
    expect(result.email).toBe('test@example.com');
    expect(result.name).toBe('홍길동');
  });

  it('이미 존재하는 이메일로 생성 시 에러를 반환한다', async () => {
    await createUser({ email: 'test@example.com', ... });
    
    await expect(
      createUser({ email: 'test@example.com', ... })
    ).rejects.toThrow(DuplicateEmailError);
  });
});
```

## 체크리스트

구현 완료 전 확인:
- [ ] 타입/인터페이스 정의됨
- [ ] 에러 케이스 처리됨
- [ ] 단위 테스트 작성 및 통과
- [ ] docstring 작성됨
- [ ] `npm run lint` 통과
- [ ] `npm run typecheck` 통과
