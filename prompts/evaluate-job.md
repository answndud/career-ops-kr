# Evaluate Job Prompt

다음 파일을 기준으로 공고를 평가한다.

- `config/profile.yml`
- `config/scorecard.kr.yml`
- 대상 공고 markdown 파일

출력 규칙:

1. 선택된 `Selected Target Role`과 `Selected Role Profile`을 먼저 명시한다.
2. 7개 차원 점수와 총점을 표로 작성한다.
3. 주요 후보 match는 `Role Match Candidates`로 요약에 명시한다.
4. "왜 맞는지", "무엇이 부족한지", "지원할지 말지"를 분리한다.
5. 근거가 약한 항목은 추정이라고 명시한다.
6. 3.0 미만이면 기본 권고는 스킵이다.
7. 한국 개발자 관점에서 출근 방식, 조직 특성, 영어 요구, 보상 신호를 꼭 언급한다.
8. `company_signal`은 후보자 공통 도메인 선호뿐 아니라 선택된 role profile의 positive/negative company signal도 함께 해석한다.
