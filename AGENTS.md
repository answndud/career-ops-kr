# AGENTS.md

## 프로젝트 목적

- 이 저장소는 한국 개발자용 구직 운영 도구를 Python CLI로 제공한다.
- 핵심 흐름은 `공고 저장 -> 공고 평가 -> tracker 반영 -> 이력서 HTML/PDF 생성`이다.
- 파일 기반 워크플로우를 유지한다. DB, 웹서버, 프론트엔드 앱을 기본 전제로 두지 않는다.
- 다만 초보자용 product surface로 `serve-web` 기반 로컬 FastAPI 앱은 허용한다. 이 web layer는 선택 기능이며 core CLI/file 흐름을 대체하지 않는다.

## 실행 명령

초기 설정:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m playwright install chromium
```

주요 실행:

```bash
source .venv/bin/activate
career-ops-kr --help
career-ops-kr serve-web
career-ops-kr discover-jobs wanted --limit 10
SARAMIN_ACCESS_KEY=... career-ops-kr discover-jobs saramin --limit 10
career-ops-kr discover-jobs remember --limit 10
career-ops-kr process-pipeline --limit 3 --score --profile-path config/profile.example.yml
career-ops-kr fetch-job "https://example.com/jobs/backend"
career-ops-kr score-job jds/<job-file>.md --profile-path config/profile.example.yml
career-ops-kr score-job jds/<job-file>.md --tracker-out data/tracker-additions/<file>.tsv --profile-path config/profile.example.yml
career-ops-kr prepare-company-research Toss --homepage https://toss.im --careers-url https://toss.im/career/jobs
career-ops-kr prepare-company-followup research/<brief>.md --mode summary
career-ops-kr prepare-resume-tailoring jds/<job-file>.md reports/<report-file>.md --base-context examples/resume-context.example.json
career-ops-kr apply-resume-tailoring output/resume-tailoring/<packet>.json examples/resume-context.example.json --out output/<company>-resume-context.json
career-ops-kr build-tailored-resume jds/<job-file>.md reports/<report-file>.md examples/resume-context.platform.ko.example.json templates/resume-ko.html --html-out output/<company>-resume.html
career-ops-kr build-tailored-resume-from-url "https://career.rememberapp.co.kr/job/posting/293599" examples/resume-context.platform.ko.example.json templates/resume-ko.html --job-out jds/remember-platform.md --report-out reports/remember-platform.md --html-out output/remember-platform.html --profile-path config/profile.example.yml
career-ops-kr backfill-artifact-manifests
career-ops-kr backfill-artifact-manifests --dry-run
career-ops-kr validate-live-smoke-targets
career-ops-kr validate-live-smoke-targets --max-candidates 2
career-ops-kr validate-live-smoke-reports output --max-age-hours 24
career-ops-kr list-live-smoke-targets
career-ops-kr smoke-live-resume --target remember_platform_ko --keep-artifacts
career-ops-kr smoke-live-resume --target remember_platform_ko --report-out output/single-live-smoke-report.json
career-ops-kr list-live-smoke-reports output
career-ops-kr list-live-smoke-reports output --type batch --failed-only --latest 3
career-ops-kr list-live-smoke-reports output --latest-per-target
career-ops-kr show-live-smoke-report output/single-live-smoke-report.json
career-ops-kr show-live-smoke-report --latest-from output --type batch --target remember_platform_ko
career-ops-kr smoke-live-resume-batch --target remember_platform_ko --target remember_backend_ko
career-ops-kr smoke-live-resume-batch --target remember_platform_ko --report-out output/live-smoke-report.json
career-ops-kr show-live-smoke-report output/live-smoke-report.json
career-ops-kr compare-live-smoke-reports output/previous-live-smoke-report.json output/live-smoke-report.json
career-ops-kr compare-live-smoke-reports --latest-from output --type batch --target remember_platform_ko
career-ops-kr finalize-tracker
career-ops-kr merge-tracker
career-ops-kr normalize-statuses
career-ops-kr verify
career-ops-kr render-resume templates/resume-en.html examples/resume-context.example.json output/sample.html
career-ops-kr render-resume templates/career-description-ko.html examples/career-description-context.platform.ko.example.json output/sample-career-description.html
career-ops-kr generate-pdf output/sample.html output/sample.pdf
```

역할별 기본 resume context:

- `examples/resume-context.backend.example.json`
- `examples/resume-context.backend.ko.example.json`
- `examples/resume-context.platform.example.json`
- `examples/resume-context.platform.ko.example.json`
- `examples/resume-context.data-platform.example.json`
- `examples/resume-context.data-platform.ko.example.json`
- `examples/resume-context.data-ai.example.json`
- `examples/resume-context.data-ai.ko.example.json`
- `examples/career-description-context.platform.ko.example.json`
- `examples/career-description-context.backend.ko.example.json`
- `examples/career-description-context.data-platform.ko.example.json`
- `examples/career-description-context.data-ai.ko.example.json`
- `templates/career-description-ko.html`

네트워크 fetch에서 로컬 인증서 문제로 TLS 검증이 실패하면:

```bash
career-ops-kr fetch-job "<url>" --insecure
career-ops-kr discover-jobs wanted --insecure
```

## 테스트 명령

대규모 정식 테스트 스위트는 아직 없지만, 리팩터 회귀를 막는 `unittest` 기반 기본 검증은 있다. 변경 후 아래를 기본 검증으로 실행한다.

전체 공통:

```bash
source .venv/bin/activate
career-ops-kr verify
python -m compileall src
python -m unittest discover -s tests
```

CLI 변경 시:

```bash
source .venv/bin/activate
career-ops-kr --help
career-ops-kr serve-web --help
```

web 변경 시:

```bash
source .venv/bin/activate
python -m unittest tests.test_web
python -m unittest discover -s tests
career-ops-kr serve-web --help
```

브라우저 E2E는 선택 검증:

```bash
source .venv/bin/activate
CAREER_OPS_RUN_BROWSER_E2E=1 python -m unittest tests.test_web_e2e
```

resume 렌더링 변경 시:

```bash
source .venv/bin/activate
career-ops-kr prepare-resume-tailoring jds/test-example.md reports/test-example.md --base-context examples/resume-context.example.json --out output/test-tailoring.json
career-ops-kr apply-resume-tailoring output/test-tailoring.json examples/resume-context.example.json --out output/test-resume-context.json
career-ops-kr build-tailored-resume jds/test-example.md reports/test-example.md examples/resume-context.platform.ko.example.json templates/resume-ko.html --html-out output/test-wrapper-resume.html --tailoring-out output/test-wrapper-tailoring.json --context-out output/test-wrapper-context.json
career-ops-kr build-tailored-resume-from-url "https://career.rememberapp.co.kr/job/posting/293599" examples/resume-context.platform.ko.example.json templates/resume-ko.html --job-out jds/test-wrapper-job.md --report-out reports/test-wrapper-report.md --html-out output/test-wrapper-url-resume.html --tailoring-out output/test-wrapper-url-tailoring.json --context-out output/test-wrapper-url-context.json --profile-path config/profile.example.yml
career-ops-kr smoke-live-resume --target remember_platform_ko --out-dir output/test-live-smoke --keep-artifacts
career-ops-kr render-resume templates/resume-en.html output/test-resume-context.json output/test-resume.html
career-ops-kr render-resume templates/career-description-ko.html examples/career-description-context.platform.ko.example.json output/test-career-description.html
career-ops-kr generate-pdf output/test-resume.html output/test-resume.pdf
rm -f output/test-tailoring.json output/test-resume-context.json output/test-resume.html output/test-resume.pdf output/test-career-description.html output/test-wrapper-resume.html output/test-wrapper-tailoring.json output/test-wrapper-context.json output/test-wrapper-url-resume.html output/test-wrapper-url-tailoring.json output/test-wrapper-url-context.json jds/test-wrapper-job.md reports/test-wrapper-report.md
rm -rf output/test-live-smoke
```

fetch 또는 score 변경 시:

```bash
source .venv/bin/activate
career-ops-kr fetch-job https://example.com --out jds/test-example.md --source smoke-test --insecure
career-ops-kr score-job jds/test-example.md --out reports/test-example.md --tracker-out data/tracker-additions/test-example.tsv --profile-path config/profile.example.yml
rm -f jds/test-example.md reports/test-example.md data/tracker-additions/test-example.tsv
```

discovery 변경 시:

```bash
source .venv/bin/activate
career-ops-kr discover-jobs wanted --limit 5 --out data/pipeline-smoke.md
career-ops-kr discover-jobs jumpit --limit 5 --out data/pipeline-smoke.md
career-ops-kr discover-jobs remember --limit 5 --out data/pipeline-smoke.md
rm -f data/pipeline-smoke.md
```

Saramin API discovery 변경 시:

```bash
source .venv/bin/activate
SARAMIN_ACCESS_KEY=... career-ops-kr discover-jobs saramin --limit 5 --out data/pipeline-smoke.md
python -m unittest tests.test_portals
rm -f data/pipeline-smoke.md
```

pipeline 처리 변경 시:

```bash
source .venv/bin/activate
career-ops-kr process-pipeline --pipeline data/pipeline-smoke.md --limit 1 --out-dir jds/pipeline-smoke --score --report-dir reports/pipeline-smoke --tracker-dir data/tracker-additions/pipeline-smoke --profile-path config/profile.example.yml
python -m unittest discover -s tests
rm -f data/pipeline-smoke.md
rm -f data/pipeline-smoke.md.lock
rm -rf jds/pipeline-smoke
rm -rf reports/pipeline-smoke data/tracker-additions/pipeline-smoke
```

company research 변경 시:

```bash
source .venv/bin/activate
career-ops-kr prepare-company-research Toss --out research/test-toss.md --homepage https://toss.im --careers-url https://toss.im/career/jobs --extra-source news=https://example.com/news
career-ops-kr prepare-company-followup research/test-toss.md --mode summary --out research/test-toss-summary.md
python -m unittest discover -s tests
rm -f research/test-toss.md research/test-toss-summary.md
```

## 아키텍처 규칙

- CLI 엔트리포인트는 [src/career_ops_kr/cli.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/cli.py)다. 실제 command group 등록은 [src/career_ops_kr/commands](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands) 아래로 분리한다.
- 공통 헬퍼는 [src/career_ops_kr/utils.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/utils.py)에 둔다.
- 공고 fetch 본문 추출과 markdown 저장 로직은 [src/career_ops_kr/jobs.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/jobs.py)에 둔다.
- pipeline inbox 처리 로직은 [src/career_ops_kr/pipeline.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/pipeline.py)에 둔다.
- 공고 점수화와 리포트 생성 로직은 [src/career_ops_kr/scoring.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/scoring.py)에 둔다.
- 포털 discovery 로직은 [src/career_ops_kr/portals.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/portals.py)에 둔다.
- 회사 조사 brief와 follow-up scaffold 생성 로직은 [src/career_ops_kr/research.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/research.py)에 둔다.
- 새 CLI 기능은 가능하면 [src/career_ops_kr/commands](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands) 아래 해당 command group 모듈에 둔다. `cli.py`는 얇은 엔트리포인트로 유지한다.
- optional web product surface는 [src/career_ops_kr/web](/Users/alex/project/career-ops-kr/src/career_ops_kr/web) 아래에 둔다. 엔트리포인트는 [src/career_ops_kr/commands/web.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands/web.py)와 `career-ops-kr serve-web`만 사용한다.
- web layer는 local-only SQLite sidecar를 써도 되지만, deterministic JD/report/resume 산출은 기존 core helper를 재사용해야 한다.
- web 검색/설정/이력서/트래커 표면은 [src/career_ops_kr/web/app.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/app.py)와 [src/career_ops_kr/web/templates](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/templates)에서 관리한다. AI 표면은 기본 비활성화이고 필요할 때만 `serve-web --enable-ai`로 노출한다.
- 모든 채용 플랫폼을 crawler 대상으로 취급하지 않는다. source role이 `company_research`인 항목은 리서치 입력원으로만 다룬다.
- `Indeed`는 현재 manual detail-only source다. `viewjob?jk=<job_key>`만 canonical detail로 보고, search/listing URL은 intake로 취급하지 않는다.
- `RocketPunch`는 현재 manual detail-only reference source다. `jobs/<job_id>`를 canonical detail URL로 보고, localized/slug 변형은 여기에 맞춰 canonicalize한다. listing/company recruit URL은 intake로 취급하지 않는다.
- pipeline URL dedup은 raw string 비교가 아니라 canonical detail URL 기준이다. 새 포털을 추가할 때는 [src/career_ops_kr/portals.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/portals.py)에 canonicalization 규칙부터 넣는다.
- Codex 로컬 설정은 `.codex/`와 `.agents/skills/`만 사용한다.
- `.codex/config.toml`은 런타임 기본값과 custom agent registry만 둔다.
- `.codex/agents/*.toml`은 역할이 좁은 custom agent 정의만 둔다.
- agent 역할은 아래처럼 분리한다.
  - `planner`: 계획과 단계화
  - `builder`: 구현, 작은 리팩터, 필요한 최소 테스트 추가
  - `reviewer`: 변경 검토, 규칙 위반, 보안, 회귀 위험 점검
  - `tester`: 실행, 실패 재현, 로그 확인, 원인 추적
  - `docs_researcher`: 외부 문서, 의존성, 포털 조사
- `.agents/skills/*/SKILL.md`는 반복 작업 절차를 둔다. 이 저장소에서 command surface는 skills가 기본이다.
- 같은 책임을 config, agent, skill에 중복 정의하지 않는다.
- `reviewer`와 `tester`는 기본적으로 소스 파일을 수정하지 않는다. 수정은 `builder`가 맡는다.
- tracker의 source of truth는 [data/applications.md](/Users/alex/project/career-ops-kr/data/applications.md)다.
- tracker에 새 항목을 직접 추가하지 말고 `data/tracker-additions/*.tsv`를 만든다. 기본 반영 경로는 `career-ops-kr finalize-tracker`이고, 세밀한 제어가 필요할 때만 `career-ops-kr merge-tracker`를 직접 사용한다.
- web tracker bulk update는 `status`, `source`, `follow_up`만 다룬다. `status/source`는 markdown tracker와 같이 맞추고, `follow_up`는 web sidecar 전용으로 유지한다. 선택 row에 메모/위치 미저장 draft가 있으면 bulk 적용 전에 먼저 저장을 요구한다.
- `prepare-resume-tailoring`는 `jds/*.md`와 `reports/*.md`에서 deterministic resume-tailoring packet만 생성한다. 템플릿 HTML이나 canonical resume context를 직접 수정하지 않는다.
- `apply-resume-tailoring`는 resume-tailoring packet을 base context에 반영해 render-ready JSON을 만든다. 없는 기술을 자동 추가하지 않고, visible patch는 `headline`, `summary`, `skills` 순서, `experience/projects` 정렬까지만 허용한다.
- `build-tailored-resume`는 `prepare-resume-tailoring -> apply-resume-tailoring -> render-resume` wrapper다. score report parsing과 render wiring만 묶고, fetch/score 단계까지 확장하지 않는다.
- `build-tailored-resume-from-url`는 `fetch-job -> score-job -> build-tailored-resume` wrapper다. 출력 경로를 먼저 preflight하고, tracker addition은 `--tracker-out`을 준 경우에만 생성한다.
- `backfill-artifact-manifests`는 기존 HTML 산출물 옆에 sibling `.manifest.json`을 생성해 web inventory provenance를 최신 규칙으로 맞춘다. 기본은 manifest가 없는 HTML만 채우고, `--overwrite`로 기존 manifest를 다시 쓸 수 있다. 같은 실행에서 output root의 `artifact-index.json` derived cache도 같이 맞춘다.
- `build-tailored-resume`, `build-tailored-resume-from-url`, `backfill-artifact-manifests`가 쓰는 manifest에는 `build_run_id`와 `inventory_key`를 같이 기록한다.
- `smoke-live-resume`는 registry 기반 target을 읽어 `build-tailored-resume-from-url` 경로를 검증하는 수동 smoke helper다. 기본은 성공 후 artifact를 정리하고, 확인이 필요할 때만 `--keep-artifacts`를 사용한다.
- `validate-live-smoke-targets`는 registry를 네트워크 없이 검증하는 저비용 helper다. live smoke를 돌리기 전에 먼저 실행한다.
- `validate-live-smoke-targets --strict`는 모든 target에 fallback candidate가 있을 때만 통과한다. coverage gate가 필요할 때 사용한다.
- `validate-live-smoke-targets`는 candidate가 3개 이상인 crowded target도 경고한다. fallback를 더 붙이기 전에 pruning이나 target 분리를 먼저 검토한다.
- 기본 live smoke registry는 target당 최대 2개 candidate를 유지한다. `validate-live-smoke-targets --max-candidates 2`를 기준 gate로 사용한다.
- `validate-live-smoke-reports`는 saved report 기준으로 registry target들의 최신 상태를 검증한다. 운영상 “최근 성공 상태가 모든 target에 대해 fresh한가”를 볼 때 사용하고, stale/failed/missing이면 nonzero로 끝난다.
- `smoke-live-resume --report-out`은 단일 smoke 실행의 성공 manifest JSON을 남긴다. target key, selected URL, fallback 여부, artifact 경로를 나중에 다시 볼 때 사용한다.
- `smoke-live-resume-batch`는 여러 target을 순차 실행하는 수동 smoke helper다. 기본은 끝까지 돌고 마지막에 요약을 출력한다. stdout에는 primary/fallback 여부와 winning candidate label을 같이 보여주고, `--report-out`을 주면 운영 기록용 JSON report를 남긴다.
- `list-live-smoke-reports`는 디렉터리 아래 저장된 live smoke JSON report inventory를 출력한다. report가 쌓였을 때 파일 이름과 생성 시각, single/batch 유형을 먼저 확인할 때 사용하고, `--type`, `--target`, `--failed-only`, `--used-fallback-only`, `--latest`로 바로 좁힌다. target별 최신 상태만 보고 싶으면 `--latest-per-target`을 쓴다.
- `show-live-smoke-report`는 single 또는 batch JSON report를 다시 읽어 사람이 확인하기 쉬운 요약으로 출력한다. raw JSON을 직접 열지 않고 최근 smoke 결과를 확인할 때 사용하고, `--latest-from`에 inventory filter를 붙여 가장 최근 matching report를 바로 열 수 있다. filter 결과가 비면 현재 filter와 ignored invalid/unrecognized JSON 개수를 같이 확인한다.
- `compare-live-smoke-reports`는 이전/현재 live smoke report 두 개를 비교해 added/removed/changed target을 출력한다. smoke 결과 변화 확인은 raw JSON diff보다 이 명령을 우선 사용하고, `--latest-from`에 inventory filter를 붙여 가장 최근 matching report 두 개를 바로 비교할 수 있다.
- live smoke registry는 `url` 단일 필드 또는 ordered `candidates` fallback URL 목록을 가질 수 있다. fallback 성공 시 실제 사용된 URL을 보고한다.
- 공고 원문은 `jds/*.md`, 평가 리포트는 `reports/*.md`, 회사 조사 brief는 `research/*.md`, 생성물은 `output/`에 둔다.
- 상태값의 기준은 [config/states.yml](/Users/alex/project/career-ops-kr/config/states.yml)이다.
- 점수화 기준의 기준은 [config/scorecard.kr.yml](/Users/alex/project/career-ops-kr/config/scorecard.kr.yml)이다.
- 이력서 템플릿은 Jinja HTML로 유지하고 [templates/resume-ko.html](/Users/alex/project/career-ops-kr/templates/resume-ko.html), [templates/resume-en.html](/Users/alex/project/career-ops-kr/templates/resume-en.html)에서 렌더링한다.
- 동작 변경이 있으면 문서도 같이 고친다. 최소 [README.md](/Users/alex/project/career-ops-kr/README.md)와 관련 `docs/*.md`를 맞춘다.

## 코드 스타일

- Python 3.11+ 기준으로 작성한다.
- 경로 처리는 문자열 연결 대신 `pathlib.Path`를 사용한다.
- 파일 입출력은 UTF-8을 명시한다.
- 설정 파일은 YAML, tracker additions는 TSV, 리포트와 원문은 Markdown 형식을 유지한다.
- `config/portals.kr.example.yml`의 `source_role` 의미를 유지한다. intake source와 company research source를 혼합해 구현하지 않는다.
- 사용자에게 보여주는 canonical status는 한국어로 유지한다. 영어 alias는 [config/states.yml](/Users/alex/project/career-ops-kr/config/states.yml)에만 추가한다.
- HTML 템플릿 렌더링은 Jinja로 처리한다. 템플릿을 Python 문자열 조합으로 대체하지 않는다.
- 네트워크 접근은 `fetch-job`, `discover-jobs`, `process-pipeline`, `build-tailored-resume-from-url`처럼 명시된 명령에서만 수행한다. 파일 정합성 명령은 외부 네트워크에 의존하지 않게 유지한다.
- `prepare-company-research`와 `prepare-company-followup`는 네트워크 fetch를 하지 않는다. tracker, pipeline, report 디렉터리를 직접 수정하지 않고 `research/*.md`만 생성한다.
- `prepare-resume-tailoring`는 기존 scoring 결과를 재사용하는 bridge다. 새 scoring heuristic이나 tracker mutation을 이 경로에 넣지 않는다.
- `apply-resume-tailoring`는 deterministic merge helper다. JD나 score report를 다시 파싱해서 새 score를 만들지 않고, packet에 없는 기술을 resume에 직접 주입하지 않는다.
- `process-pipeline --score`가 실패하더라도 fetch가 성공한 URL은 이미 `jds/`에 저장된 것으로 간주한다. pipeline은 URL intake queue로 유지하고, 점수화 재실행은 `score-job`로 처리한다.
- `process-pipeline`는 같은 pipeline 파일에 대해 sidecar `.lock`를 잡고 실행한다. live lock이 있으면 즉시 실패시키고, stale lock은 자동 정리한다. lock metadata가 손상된 경우에는 file age fallback으로만 회수한다.
- `score-job`는 필요할 때만 `--tracker-out`를 써서 tracker addition 경로를 덮어쓴다. profile과 scorecard override가 필요하면 `--profile-path`, `--scorecard-path`를 사용한다. 기본 tracker 출력 경로는 `data/tracker-additions/`다.

## 변경 금지 구역

- [config/profile.yml](/Users/alex/project/career-ops-kr/config/profile.yml)은 로컬 개인 정보 파일이다. 사용자가 명시적으로 요청하지 않으면 수정하지 않는다.
- `jds/`, `reports/`, `research/`, `output/`, `data/tracker-additions/` 아래 생성물은 검증용 임시 산출물까지 포함해 작업 후 정리한다. 의미 없는 샘플 파일을 남기지 않는다.
- canonical status를 추가하거나 이름을 바꿀 때 [config/states.yml](/Users/alex/project/career-ops-kr/config/states.yml)만 고치지 말고 `finalize-tracker`, `normalize-statuses`, `merge-tracker`, 문서까지 함께 수정한다.
- 핵심 런타임은 Python이다. 명시적 요청 없이 Node/Go 기반 새 실행 경로를 추가하지 않는다.
- 명시적 요청 없이 `.claude/` 설정을 이 저장소에 추가하지 않는다.
- tracker 병합 규칙을 바꾸면서 [data/applications.md](/Users/alex/project/career-ops-kr/data/applications.md) 포맷을 임의 변경하지 않는다.
- web layer를 수정하면서 core CLI/file workflow가 web DB에 종속되도록 바꾸지 않는다.

## 작업 순서

1. 작업을 시작하기 전에 [PLAN.md](/Users/alex/project/career-ops-kr/PLAN.md)와 [PROGRESS.md](/Users/alex/project/career-ops-kr/PROGRESS.md)를 읽는다.
2. 아래 "반드시 읽어야 할 파일"을 먼저 읽는다.
3. 변경 대상이 `config`, `CLI`, `template`, `docs` 중 어디인지 식별한다.
4. 회사 조사 관련 변경이면 crawler/intake와 research workflow를 섞지 않는지 먼저 확인한다.
5. 기능 변경이면 구현 파일과 문서를 함께 수정한다.
6. 변경 범위에 맞는 검증 명령을 실행한다.
7. smoke test 생성물을 삭제한다.
8. 작업이 끝나면 [PLAN.md](/Users/alex/project/career-ops-kr/PLAN.md)와 [PROGRESS.md](/Users/alex/project/career-ops-kr/PROGRESS.md)를 현재 상태에 맞게 업데이트한다.
9. 최종 보고에 변경 파일, 실행 명령, 남은 리스크를 적는다.

## 보고 규칙

- 최종 보고에는 바꾼 이유를 한 문단으로 먼저 요약한다.
- 그 다음 실제 변경 파일 경로를 적는다.
- 실행한 검증 명령을 적고, 통과/실패 여부를 명확히 적는다.
- 실행하지 못한 검증이 있으면 이유를 적는다.
- 네트워크, 인증서, 포털 구조 변경처럼 외부 요인에 의존하는 리스크가 있으면 별도로 적는다.

## 반드시 읽어야 할 파일

항상:

- [PLAN.md](/Users/alex/project/career-ops-kr/PLAN.md)
- [PROGRESS.md](/Users/alex/project/career-ops-kr/PROGRESS.md)
- [README.md](/Users/alex/project/career-ops-kr/README.md)
- [docs/architecture.md](/Users/alex/project/career-ops-kr/docs/architecture.md)
- [docs/workflows.md](/Users/alex/project/career-ops-kr/docs/workflows.md)
- [config/states.yml](/Users/alex/project/career-ops-kr/config/states.yml)
- [config/scorecard.kr.yml](/Users/alex/project/career-ops-kr/config/scorecard.kr.yml)
- [src/career_ops_kr/cli.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/cli.py)
- [src/career_ops_kr/commands](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands)

관련 작업 시 추가:

- 프로필/개인화 변경: [config/profile.example.yml](/Users/alex/project/career-ops-kr/config/profile.example.yml)
- 포털 관련 변경: [config/portals.kr.example.yml](/Users/alex/project/career-ops-kr/config/portals.kr.example.yml), [docs/portal-integration-strategy.md](/Users/alex/project/career-ops-kr/docs/portal-integration-strategy.md), [src/career_ops_kr/portals.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/portals.py)
- 회사 조사 workflow 변경: [src/career_ops_kr/research.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/research.py), [src/career_ops_kr/commands/research.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands/research.py), [prompts/company-research.md](/Users/alex/project/career-ops-kr/prompts/company-research.md), [docs/portal-integration-strategy.md](/Users/alex/project/career-ops-kr/docs/portal-integration-strategy.md), [docs/workflows.md](/Users/alex/project/career-ops-kr/docs/workflows.md), [.agents/skills/career-ops-company-research/SKILL.md](/Users/alex/project/career-ops-kr/.agents/skills/career-ops-company-research/SKILL.md)
- pipeline 처리 변경: [src/career_ops_kr/pipeline.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/pipeline.py), [src/career_ops_kr/jobs.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/jobs.py), [src/career_ops_kr/commands/intake.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands/intake.py), [src/career_ops_kr/cli.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/cli.py)
- tracker 흐름 변경: [src/career_ops_kr/tracker.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/tracker.py), [src/career_ops_kr/commands/tracker.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands/tracker.py), [src/career_ops_kr/cli.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/cli.py), [data/applications.md](/Users/alex/project/career-ops-kr/data/applications.md), [config/states.yml](/Users/alex/project/career-ops-kr/config/states.yml), [docs/workflows.md](/Users/alex/project/career-ops-kr/docs/workflows.md)
- pipeline 테스트 변경: [tests/test_pipeline.py](/Users/alex/project/career-ops-kr/tests/test_pipeline.py)
- 회사 조사 테스트 변경: [tests/test_research.py](/Users/alex/project/career-ops-kr/tests/test_research.py)
- 점수화 변경: [src/career_ops_kr/scoring.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/scoring.py), [config/scorecard.kr.yml](/Users/alex/project/career-ops-kr/config/scorecard.kr.yml), [docs/scoring-kr.md](/Users/alex/project/career-ops-kr/docs/scoring-kr.md)
- 회사 리서치 source 변경: [docs/portal-integration-strategy.md](/Users/alex/project/career-ops-kr/docs/portal-integration-strategy.md), [config/portals.kr.example.yml](/Users/alex/project/career-ops-kr/config/portals.kr.example.yml)
- 템플릿 변경: [templates/resume-ko.html](/Users/alex/project/career-ops-kr/templates/resume-ko.html), [templates/resume-en.html](/Users/alex/project/career-ops-kr/templates/resume-en.html)
- web 변경: [src/career_ops_kr/commands/web.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/commands/web.py), [src/career_ops_kr/web/app.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/app.py), [src/career_ops_kr/web/db.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/db.py), [src/career_ops_kr/web/search.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/search.py), [src/career_ops_kr/web/resume_tools.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/resume_tools.py), [src/career_ops_kr/web/ai.py](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/ai.py), [src/career_ops_kr/web/templates](/Users/alex/project/career-ops-kr/src/career_ops_kr/web/templates), [tests/test_web.py](/Users/alex/project/career-ops-kr/tests/test_web.py)
- 평가 프롬프트 변경: [prompts/evaluate-job.md](/Users/alex/project/career-ops-kr/prompts/evaluate-job.md)
- Codex 자동화 변경: [.codex/config.toml](/Users/alex/project/career-ops-kr/.codex/config.toml), [.codex/agents/career-ops-planner.toml](/Users/alex/project/career-ops-kr/.codex/agents/career-ops-planner.toml), [.codex/agents/career-ops-docs-researcher.toml](/Users/alex/project/career-ops-kr/.codex/agents/career-ops-docs-researcher.toml), [.codex/agents/career-ops-builder.toml](/Users/alex/project/career-ops-kr/.codex/agents/career-ops-builder.toml), [.codex/agents/career-ops-reviewer.toml](/Users/alex/project/career-ops-kr/.codex/agents/career-ops-reviewer.toml), [.codex/agents/career-ops-tester.toml](/Users/alex/project/career-ops-kr/.codex/agents/career-ops-tester.toml), [.agents/skills/career-ops-session-bootstrap/SKILL.md](/Users/alex/project/career-ops-kr/.agents/skills/career-ops-session-bootstrap/SKILL.md), [.agents/skills/career-ops-company-research/SKILL.md](/Users/alex/project/career-ops-kr/.agents/skills/career-ops-company-research/SKILL.md)
