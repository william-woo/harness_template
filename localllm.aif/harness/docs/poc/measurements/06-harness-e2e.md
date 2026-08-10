# 측정 06 — 하네스 통합 테스트 01: 로컬 LLM SDLC 풀사이클 (F001 fizzbuzz)

- **일시**: 2026-08-05
- **환경**: OpenCode 1.16.2 + Ollama (172.16.10.217, RTX 4500 24GB) — qwen2.5 14B(생성)/32B(판정)
- **구조**: **하이브리드** (측정 05 결론 적용) — 로컬 에이전트가 역할 수행, 상위 호스트
  (Claude Code)가 supervisor 로 핸드오프·grader 실행·북키핑 담당
- **시나리오**: localllm 템플릿을 다운스트림 샌드박스에 배포 → F001(fizzbuzz CLI) 시드 →
  하네스 SDLC 사이클 전체 (구현→검증루프→리뷰→QA→passes)

## 결과: ✅ 풀사이클 완주 — verify-loop 6 기록 / revision 2 / 에스컬레이션 0

| 단계 | 티어 | 결과 |
|---|---|---|
| developer 구현 | 14B (opencode.json 자동) | 파일 2개 생성 — 로직 정확, 단 **테스트 함수 미호출** |
| grader #1 (허술: exit code 만) | 결정론 | ⚠️ **공허 통과(vacuous pass)** — assert 미실행인데 exit 0 |
| grader 엄격화 (exit 0 + `PASS` 출력) | 결정론 | revision 기록 → 재작업 지시 |
| developer 재작업 1 (정밀 편집) | 14B | ❌ edit oldString 불일치 → 질문 이탈 (revision 2/3) |
| developer 재작업 2 (**전체 파일 재작성**) | 14B | ✅ 통과 — 엄격 grader PASS |
| reviewer 판정 1 (read 도구) | 32B | ❌ `/workspace/...` 경로 날조 → 권한 거부 |
| reviewer 판정 2 (**bash-only** 지시) | 32B | ✅ cat 으로 읽고 판정 → `record reviewer pass` |
| qa 인수 검증 (bash-only) | 32B | ✅ 테스트 실행 + 기준 확인 → `record qa pass` |
| supervisor 북키핑 | 상위 호스트 | passes:true / status:done / git 커밋 / 핸드오프 로그 |

## 신규 규율 3건 (AGENTS.md 반영)

1. **공허 통과 주의**: 결정론 grader 는 exit code 만이 아니라 **기대 출력**(`PASS` 등)까지
   확인한다 — 로컬 모델이 테스트를 정의만 하고 호출하지 않는 실패 모드가 실재.
2. **재작업 = 전체 파일 재작성** (AGENTS.md 규칙 6): 정밀 편집(edit oldString)은 불일치로
   실패·이탈. 파일 전체 내용을 제시하고 통째로 재작성시키는 편이 안정적.
3. **판정 역할 파일 접근 = bash `cat`** (AGENTS.md 규칙 7): read 도구는 경로 날조
   (`/workspace/` 등)로 거부됨. reviewer/qa 프롬프트에 "ONLY the bash tool" 명시.

## 운영 참고

- OpenCode 부트스트랩 간헐 행 (vcs init 직후 세션 미생성) 3회째 관찰 — **재시도로 항상 해소**.
  headless 파이프라인에선 timeout + 1회 재시도를 기본 패턴으로.
- 판정 프롬프트의 `--notes '<one short finding>'` 는 32B 가 placeholder 그대로 기록 —
  notes 는 supervisor 가 채우거나 구체 값 예시를 지시문에 넣을 것.

## 종합 판단

localllm 하네스는 **하이브리드 supervisor 패턴으로 실전 SDLC 사이클을 완주할 수 있다**.
로컬 티어의 역할: 생성(14B 초안) + 판정(32B judge, bash-only 규율 하). 결정론 grader 와
verify-loop 상태가 품질을 지탱하고, supervisor 는 핸드오프·북키핑·grader 정의만 담당한다.
