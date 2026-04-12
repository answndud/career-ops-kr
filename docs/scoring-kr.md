# Scoring KR

한국 개발자 구직용 기본 점수화 항목입니다. 스크립트는 이 기준을 단순화해 사용하고, Codex는 리포트 작성 시 정성 평가를 추가합니다.

현재 이 규칙은 `career-ops-kr score-job`와 `career-ops-kr process-pipeline --score`가 공통으로 사용합니다. 기본 입력은 `config/profile.yml`과 `config/scorecard.kr.yml`이지만, 재현 가능한 실행이나 테스트가 필요하면 CLI에서 `--profile-path`, `--scorecard-path`로 덮어쓸 수 있습니다. 스크립트는 먼저 JD를 `Backend`, `Platform`, `Data` domain 중 하나로 좁힌 뒤, 그 domain 안에서 현재 후보자가 노리는 `target_role`과 가장 가까운 role profile을 선택합니다. 그 다음 해당 role profile의 weights, stack keywords, role-specific company signal keywords를 적용합니다. 기본 제공 role profile은 `Backend`, `Platform`, `Data-Platform`, `Data-AI`이며 보고서에는 `Selected Domain`, `Selected Target Role`, `Selected Role Profile`, `Domain Match Candidates`, `Role Match Candidates`가 표시됩니다.

| Dimension | Weight | Intent |
|-----------|--------|--------|
| Role Alignment | 30 | 타깃 직무와 공고 제목/설명 일치도 |
| Stack Overlap | 20 | 내 기술 스택과 요구 기술의 교집합 |
| Seniority Fit | 15 | 경력 연차와 시니어리티 적합도 |
| Work Mode Fit | 10 | 원격/하이브리드/출근 선호 일치도 |
| Language Fit | 10 | 한국어/영어 협업 요구와 후보자 선호 일치도 |
| Compensation Signal | 10 | 연봉 정보의 존재와 기대 범위 부합 가능성 |
| Company Signal | 5 | 제품, 성장성, 업계 적합성에 대한 정성 신호 |

### Role Profiles

| Profile | Role Alignment | Stack Overlap | Compensation | Notes |
|---------|----------------|---------------|--------------|-------|
| Backend | 34 | 20 | 7 | generic 언어명보다 backend/service 용어를 더 강하게 본다 |
| Platform | 30 | 22 | 8 | infra/SRE 맥락을 더 보고, `aws`/`docker` 같은 범용 키워드 의존은 줄인다 |
| Data-Platform | 31 | 23 | 6 | ETL, Airflow, Spark, warehouse, streaming stack을 더 강하게 본다 |
| Data-AI | 30 | 20 | 8 | AI/ML/LLM, eval, prompt, inference 같은 applied AI 신호를 더 강하게 본다 |

## 운영 원칙

- 점수는 의사결정 보조 도구이지 자동 지원 트리거가 아닙니다.
- 4.0 이상: 적극 검토
- 3.0 이상 4.0 미만: 선택적 검토
- 3.0 미만: 원칙적으로 스킵 권장
- role profile이 달라도 점수 차원 자체는 유지하고, weight만 바꿉니다.
- `score-job`와 `process-pipeline --score`는 같은 role selection / weight resolution 로직을 공유합니다.
- 어떤 role profile과도 의미 있는 overlap이 없으면 `General` fallback으로 내려가고 기본 weight를 사용합니다.
- `General` fallback일 때 `role_alignment`는 중립값이 아니라 최저점으로 처리해 무관한 JD가 3점대 초반으로 부풀지 않게 합니다.
- `target_roles[].scorecard_profile`가 있으면 keyword 추론보다 그 값을 우선 사용합니다.
- `company_signal`은 후보자 공통 선호/회피 도메인과 role profile별 positive/negative company keyword를 함께 반영합니다.
- role selection은 `domain -> role profile` 2단계입니다. 현재 domain은 `Backend`, `Platform`, `Data`입니다.
- domain selection은 anchor count만 보지 않고 domain-level total signal을 더 우선합니다. 그래서 `Airflow / warehouse / Spark`가 충분히 많은 JD는 `Kubernetes`가 일부 섞여 있어도 `Data`로 내려갈 수 있습니다.
- report의 `Domain Match Candidates`는 각 domain의 `total / anchor / signal / tie` count를 같이 보여줘서, mixed JD가 왜 `Platform` 또는 `Data`로 선택됐는지 바로 다시 볼 수 있게 합니다.
- report의 `Role Match Candidates`는 각 role 후보의 `total / anchor / signal / ratio / preferred`를 같이 보여줘서, 최종 role profile 선택이 domain specialization 때문인지 실제 JD signal 때문인지 다시 확인할 수 있게 합니다.
- report의 `Domain Selection Note`, `Role Selection Note`는 near-tie tie-break, preferred specialization, General fallback 같은 최종 결정 이유를 한 줄로 바로 설명합니다.
- role profile 선택에서는 generic runtime 키워드보다 역할명과 도메인 맥락을 더 우선합니다.
- role profile 선택에서는 각 profile의 `selection_anchor_keywords`를 먼저 보고, 일반 `match_keywords` count와 ratio로 tie-break 합니다.
- anchor가 비슷하게 붙는 경우에는 `selection_signal_keywords`로 domain signal을 한 번 더 비교해 `data infra for ML teams`와 `analytics infrastructure platform` 같은 혼합 JD의 흔들림을 줄입니다.
- `Data` domain 안에서는 `specialization_keywords`를 한 번 더 보고 `Data-Platform`과 `Data-AI`를 가릅니다. 차이가 작으면 기존 profile selector로 되돌아가 과한 강제 분류를 피합니다.
- specialization 점수 차가 `1` 수준의 near-tie면 `specialization_anchor_keywords`를 한 번 더 보고 우선순위를 정합니다. anchor도 애매하면 기존 selector로 되돌아갑니다.
- `Platform`과 `Data` domain이 붙는 near-tie에서는 domain-level total signal을 먼저 보고, 정말 비슷할 때만 domain tie-break anchor를 참고합니다. 이때 tie-break는 한두 개의 keyword 차이로 total-signal winner를 뒤집지 않도록 margin을 두고 적용합니다. `Data` tie-break anchor는 `feature store / Airflow / warehouse` 같은 Data-Platform 신호뿐 아니라 `model serving / inference / llmops` 같은 Data-AI 신호도 포함해 `AI infrastructure` 류 JD가 infra 단어만 보고 `Platform`으로 굳지 않게 합니다.
- role profile 선택은 raw match count만 보지 않고, selection keyword 대비 최소 match ratio가 낮으면 `General` fallback으로 내립니다.
- title이 `Product Designer`, `QA Automation Engineer`, `Embedded Software Engineer`, `Game Client Engineer`처럼 현재 target role 바깥의 역할군으로 명확하면 unsupported family guard를 먼저 적용해 억지 분류를 막고 `General` fallback으로 내립니다.
- role/stack keyword ratio 점수는 `0.7 / 0.4 / 0.2 / 0.08` 구간으로 나눠서 강한 적합 공고가 4점대에 더 잘 올라오도록 조정했습니다.
- seniority 판정은 first-match가 아니라 keyword count와 seniority priority를 함께 봅니다. `senior`와 `engineer`가 같이 있는 JD는 `mid`로 잘못 내려가지 않습니다.
- `mid ↔ senior`는 인접 mismatch로 보고 `seniority_fit 4.0`을 주고, 더 큰 차이는 `3.0`으로 둡니다.
- compensation signal은 단어 존재만 보지 않습니다. `no compensation details`, `salary not disclosed`, `연봉 비공개` 같은 부정 문구는 disclosure 가산점을 주지 않습니다.
- `ML Platform`처럼 혼합 표현이 많은 JD는 anchor phrase로 먼저 AI-heavy / platform-heavy 방향을 가른 뒤 일반 keyword overlap으로 보정합니다.

## Role Profiles

### Backend

- `role_alignment`, `stack_overlap` 비중을 가장 높게 둡니다.
- API, server, distributed systems, JVM 계열 요구가 강한 JD에 맞춥니다.
- developer tools, B2B SaaS, fintech 같은 제품 조직 신호를 조금 더 긍정적으로 봅니다.
- `python`, `go` 같은 범용 언어명만으로는 backend를 강하게 선택하지 않도록 generic keyword를 줄였습니다.

### Platform

- `stack_overlap`, `work_mode_fit`, `company_signal` 비중을 조금 더 높게 둡니다.
- Kubernetes, Terraform, observability, SRE, infrastructure 계열 JD에 맞춥니다.
- cloud, infra, reliability, platform 조직 문맥을 company signal에서 추가로 반영합니다.
- `aws`, `docker`처럼 여러 역할에 공통으로 나오는 키워드는 match보다 stack 쪽에 더 가깝게 봅니다.

### Data-AI

- `role_alignment`, `compensation_signal`, `company_signal` 비중을 높게 둡니다.
- LLM, ML, RAG, eval, agent, prompt, applied AI 계열 JD에 맞춥니다.
- AI tooling, inference, research 성격이 강한 팀 신호를 company signal에서 추가로 반영합니다.
- generic `data` 키워드는 Data-Platform과 충돌이 커서 직접 match keyword에서 제외했습니다.
- `model serving`, `inference`, `llmops`, `embeddings`, `eval` 같은 specialization keyword가 강하면 같은 Data domain 안에서도 Data-AI를 우선합니다.
- `Platform`과 `Data` domain이 near-tie인 경우에도 위 anchor가 충분히 강하면 `AI Infrastructure`처럼 infra 단어가 섞인 JD를 Data-AI 쪽으로 유지합니다.
- `Data Platform SRE`, `Analytics Infrastructure`처럼 infra 운영 단어가 섞여도 data pipeline/warehouse/streaming 문맥이 총합에서 더 강하면 `Data-Platform`으로 유지합니다.
- 반대로 `DevOps Engineer`처럼 ops title이 전면에 있고 Kubernetes/Terraform/observability/runtime 운영이 더 강한 JD는 data 문맥이 일부 섞여 있어도 `Platform`으로 남길 수 있습니다.
- 하지만 `DevOps Engineer` 제목이어도 Kafka/Spark/warehouse/Airflow/dbt/data quality 같은 pipeline orchestration 문맥이 더 강하면 `Data-Platform`으로 내려갈 수 있습니다.
- `MLOps Engineer`처럼 title이 애매해도 model serving / inference / eval / llmops 신호가 강하면 `Data-AI`로 유지합니다.

### Data-Platform

- `role_alignment`, `stack_overlap`, `company_signal` 비중을 함께 둡니다.
- Airflow, Spark, warehouse, streaming, ETL, analytics platform 계열 JD에 맞춥니다.
- analytics, experimentation, warehouse, data product 문맥을 company signal에서 추가로 반영합니다.
- Data-AI보다 compensation 비중을 낮추고 stack 비중을 높여서 infra/data pipeline 성격을 더 강하게 반영합니다.
- `feature pipeline`, `training dataset`, `experimentation platform`, `warehouse`, `Airflow`, `Spark` 같은 specialization keyword가 강하면 같은 Data domain 안에서도 Data-Platform을 우선합니다.

## 한국 시장에서 추가로 볼 것

- 실제 출근지와 출근 빈도
- 병역/비자/국적 요구
- 영어 회의 빈도
- 조직 규모 대비 역할 폭
- SI/외주형 포지션인지 제품 조직인지
