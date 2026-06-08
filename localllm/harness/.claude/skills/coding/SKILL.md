---
name: coding
description: |
  코드 구현 시 참조하는 스킬. Developer 에이전트가 기능을 구현할 때 사용한다.
  패턴: 구현 → 테스트 → 커밋 → 인계
  호스트: opencode
---

# Coding Skill

> 이 파일은 `opencode` 호스트 기준으로 렌더된 SKILL.md입니다.
> 원본 템플릿: `coding/SKILL.md.template`

## 도구 사용 안내 (opencode)

이 하네스에서 코드를 구현할 때 다음 도구를 사용하세요:

| 용도 | 도구명 |
|---|---|
| 셸 명령 실행 | `bash` |
| 파일 읽기 | `read` |
| 파일 쓰기 | `edit` |
| 파일 수정 | `edit` |
| 다중 파일 수정 | `edit` |
| 파일 검색 | `glob` |
| 텍스트 검색 | `grep` |

## 커맨드 호출 안내 (opencode)

구현 완료 후 다음 커맨드로 인계하세요:

```
opencode run --command handoff
```

세션 시작 시:

```
opencode run --command start-session
```

프로젝트 루트는 `$PWD` 환경변수에서 읽을 수 있습니다.

## 경로 사용 안내 — 상대경로 우선 (로컬 LLM 보강)

> 로컬 LLM(OpenCode + Ollama) 측정에서 발견된 보강 사항입니다 (PoC 측정 02).
> 로컬 모델은 `/home/user/...` 같은 **절대경로를 임의 생성하는 습관**이 있어,
> 실제 프로젝트 밖 경로를 만들거나 권한 경계를 벗어날 수 있습니다.

파일을 읽고 쓸 때는 **프로젝트 루트 기준 상대경로**를 우선 사용하세요:

- ✅ `.claude/agents/developer.md`, `src/foo.ts`, `docs/adr/ADR-001.md`
- ❌ `/home/obigo/project/.../developer.md` (절대경로 임의 생성 금지)
- 절대경로가 꼭 필요하면 `$PWD` 를 기준으로 조합하세요.
- 호스트가 cwd 기반(OpenCode 등)이면 현재 작업 디렉토리가 곧 프로젝트 루트입니다.

이는 비용·보안 목적(d-2)과도 직결됩니다 — 작업 디렉토리 경계를 벗어나지 않아야
권한 경계(autonomous 규칙 #3-B 외부 디렉토리)를 안전하게 유지합니다.

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
