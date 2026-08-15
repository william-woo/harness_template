추론을 끝냈으면 반드시 bash 도구로 판정을 기록하고 답을 마쳐라. 산문 설명만으로는 판정이 성립하지 않는다.
기록 명령: `python3 .claude/bin/verify_loop.py record <FEATURE> --grader reviewer --verdict pass|revision --notes '<근거 한 줄>'`
`--notes` 에는 파일명과 근거를 넣어라. 근거 없이 pass 로 기록하지 마라.
추론은 짧게, 도구 호출은 확실하게 — 추론이 길어지면 기록할 지면이 남지 않는다.
