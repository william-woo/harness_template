# .claude/policy/ — 사람이 승인한 역할 지시 오버레이

이 디렉토리의 `<role>.md` 는 `cycle_driver` 가 역할 에이전트를 호출할 때 과제 **앞에 붙이는
지시문**이다. 파일이 없으면 아무것도 붙지 않는다 (기본 동작 = 빈 정책).

```
.claude/policy/developer.md   → developer 호출 시 주입
.claude/policy/reviewer.md    → reviewer 호출 시 주입
```

## 여기 있는 파일은 어디서 오는가

두 경로뿐이다:

1. **사람이 직접 작성** — 평소처럼 편집하면 된다.
2. **autoresearch 승격** — `autoresearch.py promote <exp> --yes` (사람 승인 필수).

autoresearch 는 이 디렉토리를 **자동으로 쓰지 않는다**. 실험이 찾아낸 승자 정책은
`.claude/state/autoresearch/best/` (실험 공간)에 머물고, 여기로 옮기는 것은 사람의 결정이다.
karpathy/autoresearch 의 "결과는 shipped improvement 가 아니라 starting hypothesis" 를
디렉토리 경계로 구현한 것이다 (ADR-019).

## 작성 규칙

- 5줄 이내, 명령형. 긴 지시는 로컬 모델의 도구 호출을 방해한다 (측정 08 라운드 6).
- 과제 내용이 아니라 **작업 방식**을 지시한다.
- 테스트 약화·검증 우회 지시 금지 — 게이트가 잡아내지만 애초에 쓰지 않는다.

## 오버라이드

`HARNESS_POLICY_DIR=<경로>` 로 다른 디렉토리를 주입할 수 있다 (autoresearch 실험이 쓰는 방식).
