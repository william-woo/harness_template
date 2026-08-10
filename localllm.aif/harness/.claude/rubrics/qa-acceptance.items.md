# Items — qa-acceptance (AIF 항목형)

<!-- aif-items: v1 -->

> 산문형 [qa-acceptance.md](qa-acceptance.md) 의 항목형 판본. 형식은 [_items-schema.md](_items-schema.md).
> `passes: true` 권한은 QA 단독이며, 항목형에서도 **MUST 전부 met/na** 일 때만 pass 다.

### A1 | MUST | acceptance_criteria 충족
요구: feature_list.json 의 acceptance_criteria 를 **항목 단위로 전부** 충족한다 (부분 동작은 미충족).
증거: 각 기준별로 그것을 충족하는 코드·출력의 `파일:행` 또는 실행 출력 줄
판정: 하나라도 근거를 제시할 수 없으면 unmet

### A2 | MUST | E2E 실행 확인
요구: 실제 실행 경로에서 기대 결과가 관측된다 (코드 읽기만으로 판단하지 않는다).
증거: 실행한 명령과 그 출력의 핵심 줄
판정: 실행 증거가 없으면 unmet

### A3 | MUST | 엣지 케이스
요구: 빈 입력·경계값·오류 경로가 검증된다.
증거: 해당 케이스를 다루는 테스트의 `파일:행` 과 결과
판정: 입력 표면이 없으면 na

### A4 | MUST | 회귀 없음
요구: 기존 기능이 파손되지 않았다.
증거: 기존 테스트 스위트 실행 결과 줄
판정: 실행하지 않았으면 unmet (추정 금지)

### A5 | MUST | 브라우저 검증 해당 여부
요구: acceptance_criteria 에 URL·폼·텍스트 노출·라우팅이 있으면 qa-browser 로 검증한다.
증거: qa-browser 실행 로그 경로 또는 스크린샷 경로
판정: UI 기준이 없으면 na

### A6 | MUST | 결정론 grader 선행
요구: judge 판정 전에 결정론 grader(lint / 테스트 / design-review 해당 시)가 통과했다.
증거: 각 grader 의 실행 결과 요약 줄
판정: 하나라도 미실행이면 unmet
