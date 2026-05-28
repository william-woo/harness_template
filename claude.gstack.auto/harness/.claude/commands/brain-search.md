# /project:brain-search — Cross-project 지식 검색

`~/.harness/brain.db` 에서 learnings · ADRs · features 를 LIKE 기반으로 검색.
`/project:learn search` (현재 프로젝트만) 보다 범위가 넓다.

**HARD GATE: 읽기 전용 검색.**

## 사용

```
/project:brain-search <검색어>                              # 모든 프로젝트
/project:brain-search <검색어> --project <slug>             # 특정 프로젝트만
/project:brain-search <검색어> --type pitfall               # learning type 필터
/project:brain-search <검색어> --limit 50                   # 결과 개수
```

## 실행

```bash
python3 .claude/bin/brain.py search "$QUERY"
# 옵션 추가:
python3 .claude/bin/brain.py search "$QUERY" --project harness_template --type pitfall
```

## 검색 범위

| 테이블 | 검색 대상 컬럼 | type 필터 적용 시 |
|---|---|---|
| learnings | key, insight | ✅ |
| adrs | title, decision | ❌ (ADR 검색 생략) |
| features | title | ❌ (Feature 검색 생략) |

## 출력 예시

```
🧠 BRAIN SEARCH 'jsonl'
═══════════════════════════════════════

[LEARNINGS] 3 matches
  • harness_update_agent::analytics-jsonl-event-stream [F004]  (architecture, conf 9/10)
    └─ 분석 이벤트는 단순 JSONL 스트림으로 append-only 저장하고...
  • harness_update_agent::append-only-tombstone [F001]  (pattern, conf 8/10)
    └─ JSONL 학습·체크포인트는 append-only로 유지하고, 삭제는 tombstone 엔트리...

[ADRs] 1 matches
  • foo_project::ADR-002 Event Stream Format  (accepted)
    └─ JSONL 채택. 이유: git diff 가시성, grep 가능, 외부 의존성 없음.
```

## 사용 시나리오

1. **새 프로젝트 시작 시**: 비슷한 문제를 다른 프로젝트에서 해결한 적 있는지 확인
   ```
   /project:brain-search "rate limit"
   ```
2. **함정 회피**: pitfall 만 골라서 검토
   ```
   /project:brain-search auth --type pitfall
   ```
3. **결정 참고**: 다른 프로젝트의 architecture 결정 확인
   ```
   /project:brain-search caching --type architecture
   ```

## brain.db 가 비어있다면

검색 전 한 번 이상 `/project:brain-sync` 를 실행한 프로젝트만 검색 가능.
완전히 비어있으면:
```
ℹ️  brain.db 없음. 먼저 sync 하세요: /home/<user>/.harness/brain.db
```

## 체크리스트

- [ ] 검색어 1글자 이상
- [ ] (선택) `--project` 슬러그 정확
- [ ] (선택) `--type` 은 pattern/pitfall/preference/architecture/tool 중 하나
