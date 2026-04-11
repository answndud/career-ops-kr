# Workflows

## 1. 단일 공고 평가

1. 포털 URL discovery가 필요하면 `career-ops-kr discover-jobs wanted --limit 20`, `career-ops-kr discover-jobs jumpit --limit 20`, `career-ops-kr discover-jobs remember --limit 20`로 `data/pipeline.md`에 URL을 적재합니다. Saramin access-key가 있으면 `SARAMIN_ACCESS_KEY=... career-ops-kr discover-jobs saramin --limit 20`도 사용할 수 있습니다.
2. `career-ops-kr process-pipeline --limit N --score`로 pending URL을 `jds/`에 저장하고, 성공한 항목만 처리 완료로 표시하면서 가능한 경우 리포트와 tracker addition도 같이 생성합니다. `--report-dir`, `--tracker-dir`, `--profile-path`, `--scorecard-path`는 출력 위치와 scoring 입력을 분리할 때 사용합니다.
3. 저장된 JD를 다시 평가해야 하면 `career-ops-kr score-job`로 같은 점수화 로직을 수동 재실행합니다. fetch는 성공했지만 scoring만 실패한 경우에도 이 경로를 사용합니다. tracker addition 경로를 바꾸려면 `--tracker-out`를 붙이고, 재현 가능한 입력이 필요하면 `--profile-path`, `--scorecard-path`를 명시합니다.
4. 생성된 리포트를 Codex가 읽고 정성 코멘트를 보강합니다.
5. 기본 경로는 `career-ops-kr finalize-tracker`입니다. additions 병합, 상태 정규화, 선택적 verify까지 한 번에 수행합니다.
6. 더 세밀한 제어가 필요할 때만 `career-ops-kr merge-tracker`, `career-ops-kr normalize-statuses`, `career-ops-kr verify`를 개별 실행합니다.
7. tracker와 산출물을 운영 관점에서 다시 점검하고 싶으면 `career-ops-kr audit-jobs`를 실행합니다. report/resume 누락뿐 아니라 sibling manifest가 없는 legacy HTML, manifest가 가리키는 파일 누락, `artifact-index.json` drift도 같이 보여줍니다.

같은 pipeline 파일에 대해 동시에 `process-pipeline`를 실행하면 `*.lock` sidecar 때문에 즉시 실패합니다. stale lock은 자동 회수하고, metadata가 손상된 오래된 lock도 age fallback으로 정리합니다. 실제 실행 중인 프로세스가 잡고 있는 lock은 수동으로 건드리지 않는 것이 원칙입니다.

## 2. 수동 파이프라인 inbox

`data/pipeline.md`의 `- [ ]` 항목에 URL을 쌓아두고, 이후 `process-pipeline`이나 `fetch-job`로 처리합니다.

포털 discovery는 현재 listing scraping보다 sitemap-first 또는 공식 API 경로를 우선합니다. Wanted, Jumpit, Remember는 sitemap-first, Saramin은 access-key가 있을 때 공식 API를 사용합니다. 자세한 기준은 `docs/portal-integration-strategy.md`를 봅니다.

모든 source가 `discover-jobs` 대상은 아닙니다. `JobPlanet`, `Blind` 같은 company research source는 공고 intake가 아니라 회사 조사 입력원으로 분리합니다.
`Indeed`도 자동 discovery 대상이 아닙니다. 수동 intake 시에는 `viewjob?jk=<job_key>` detail URL만 사용하고, search/listing URL은 넣지 않습니다.
`RocketPunch`도 자동 discovery 대상이 아닙니다. 현재는 manual reference source이며, `jobs/<job_id>` canonical detail만 참고용으로 받고 `en-US/jobs/<job_id>`나 `jobs/<job_id>/<slug>` 변형은 canonical detail로 정규화합니다. listing/company recruit URL은 intake로 받지 않고, login/anti-crawl/WAF gate HTML이 오면 `fetch-job`가 실패합니다.

## 3. 회사 조사

1. 회사 조사가 필요하면 `career-ops-kr prepare-company-research "<company>"`를 실행합니다.
2. 알고 있는 URL이 있으면 `--homepage`, `--careers-url`, `--job-url`, `--jobplanet-url`, `--blind-url`를 같이 넘깁니다.
3. exact company URL을 아직 모르면 생성된 brief의 `Search Hints` 섹션에 있는 query와 search URL을 먼저 사용합니다.
4. 저장한 JD나 리포트를 연결할 때는 `--job-path`, `--report-path`를 사용합니다.
5. 추가 source가 있으면 `--extra-source label=https://...` 형태로 반복해서 붙입니다.
6. 필요하면 `--prompt-path`로 checklist seed prompt를 바꿀 수 있습니다.
7. 결과는 `research/<date>-<slug>.md` 또는 `--out` 경로에 생성됩니다.
8. 이 명령은 네트워크를 호출하지 않고 `data/pipeline.md`, `data/applications.md`, `data/tracker-additions/`도 수정하지 않습니다.
9. 후속 정리나 메시지 초안이 필요하면 `career-ops-kr prepare-company-followup <research-brief> --mode summary|outreach`를 실행합니다.
10. `prepare-company-followup`도 네트워크를 호출하지 않고, intake/tracker를 수정하지 않으며 `research/*.md` 기반 후속 scaffold만 생성합니다.

`JobPlanet`과 `Blind`는 여기서 URL과 조사 source를 정리하는 입력원입니다. crawler나 discovery 대상이 아닙니다.

## 4. 이력서 생성

1. 저장된 JD와 score report가 있으면 `career-ops-kr prepare-resume-tailoring <job.md> <report.md> --base-context <resume-context.json>`로 `output/resume-tailoring/*.json` packet을 생성합니다.
   시작점을 고를 때는 `examples/resume-context.backend.example.json`, `examples/resume-context.backend.ko.example.json`, `examples/resume-context.platform.example.json`, `examples/resume-context.platform.ko.example.json`, `examples/resume-context.data-platform.example.json`, `examples/resume-context.data-platform.ko.example.json`, `examples/resume-context.data-ai.example.json`, `examples/resume-context.data-ai.ko.example.json` 중 가장 가까운 파일을 복제합니다.
2. `career-ops-kr apply-resume-tailoring <packet>.json <resume-context.json> --out <tailored-context>.json`으로 render-ready context를 생성합니다.
3. 필요하면 생성된 tailored context의 `tailoringGuidance`를 보고 마지막 수동 미세조정을 합니다.
4. `career-ops-kr render-resume`로 HTML을 생성합니다.
5. `career-ops-kr generate-pdf`로 PDF를 생성합니다.
6. 지원 회사별 버전을 `output/`에 분리 저장합니다.
7. 경력기술서가 필요하면 `templates/career-description-ko.html` 또는 `templates/career-description-en.html`과 `examples/career-description-context.backend.ko.example.json`, `examples/career-description-context.backend.example.json`, `examples/career-description-context.platform.ko.example.json`, `examples/career-description-context.platform.example.json`, `examples/career-description-context.data-platform.ko.example.json`, `examples/career-description-context.data-platform.example.json`, `examples/career-description-context.data-ai.ko.example.json`, `examples/career-description-context.data-ai.example.json` 중 가장 가까운 예시를 시작점으로 같은 `render-resume` 흐름을 사용합니다.
8. 같은 3단계를 반복 실행할 때는 `career-ops-kr build-tailored-resume <job.md> <report.md> <resume-context.json> <template.html>`로 `prepare-resume-tailoring -> apply-resume-tailoring -> render-resume`를 한 번에 실행합니다. PDF는 필요할 때만 `--pdf-out`으로 추가합니다. 이 경로는 HTML 옆에 sibling `.manifest.json`도 같이 남겨 provenance와 selection/focus metadata를 기록합니다.
9. 아직 JD와 score report를 저장하지 않았다면 `career-ops-kr build-tailored-resume-from-url <url> <resume-context.json> <template.html>`로 `fetch-job -> score-job -> build-tailored-resume`를 한 번에 실행할 수 있습니다. 이 경로는 `--job-out`, `--report-out`, `--html-out` 같은 출력 경로를 먼저 preflight하고, `--tracker-out`을 준 경우에만 tracker addition을 생성합니다. web inventory는 새 산출물의 `.manifest.json`을 우선 읽고, manifest가 없는 예전 HTML은 legacy fallback으로 계속 보여줍니다.
10. 예전에 만든 `output/*.html`이 많다면 `career-ops-kr backfill-artifact-manifests`로 sibling `.manifest.json`을 일괄 생성해 inventory provenance를 최신 기준으로 맞춥니다. 기본은 manifest가 없는 HTML만 채우고, 이미 있는 manifest를 다시 쓰려면 `--overwrite`, 실제 쓰기 전에 목록만 보려면 `--dry-run`을 사용합니다. 같은 실행에서 `artifact-index.json` derived cache도 같이 맞춰지고 stale orphan entry도 정리됩니다.
11. 공개 공고를 기준으로 실제 네트워크 smoke가 필요하면 먼저 `career-ops-kr validate-live-smoke-targets`로 registry를 확인하고, `career-ops-kr list-live-smoke-targets`로 target을 본 뒤 `career-ops-kr smoke-live-resume --target <name>`를 사용합니다. 여러 target을 한 번에 볼 때는 `career-ops-kr smoke-live-resume-batch --target ...` 또는 target 없이 전체 registry를 실행합니다. 기본 registry는 `config/live-smoke-targets.yml`이고, 현재 Remember/Wanted/Jumpit target을 제공합니다. 각 target은 ordered fallback candidate URL을 가지며, single/batch smoke 모두 실제로 성공한 URL을 출력합니다. single smoke는 `--report-out <path>.json`으로 성공 manifest를 저장할 수 있고, batch stdout은 primary/fallback 여부와 winning candidate label을 같이 보여주며 `--report-out <path>.json`으로 결과를 저장할 수도 있습니다. single report는 성공 URL, fallback 사용 여부, artifact 경로를 담고, batch report는 실패 메시지도 같이 담습니다. 저장한 report가 많아지면 `career-ops-kr list-live-smoke-reports <dir>`로 inventory를 먼저 보고, 필요하면 `--type`, `--target`, `--failed-only`, `--used-fallback-only`, `--latest N`으로 바로 좁힙니다. target별 최신 상태를 한 번에 보려면 `career-ops-kr list-live-smoke-reports <dir> --latest-per-target`을 사용합니다. 개별 요약은 `career-ops-kr show-live-smoke-report <report.json>`로 확인하고, 가장 최근 matching report를 바로 읽고 싶으면 `career-ops-kr show-live-smoke-report --latest-from <dir>`에 같은 filter를 붙입니다. 최근 두 실행 차이를 바로 보고 싶으면 `career-ops-kr compare-live-smoke-reports --latest-from <dir>`에 같은 filter를 붙입니다. saved report 기준으로 모든 registry target이 최신 성공 상태인지 gate하려면 `career-ops-kr validate-live-smoke-reports <dir> --max-age-hours 24`를 사용합니다. 이 명령은 target별 최신 saved entry를 검사해서 `ok / stale / failed / missing`을 출력하고, 하나라도 문제가 있으면 nonzero로 끝납니다. filter 결과가 비었거나 손상된 JSON이 섞여 있으면 CLI는 현재 filter 요약과 ignored file 수를 같이 출력합니다. `validate-live-smoke-targets`는 fallback target 수와 single-candidate target 유무를 출력하고, candidate가 3개 이상인 crowded target도 경고합니다. 현재 기본 registry는 target당 최대 2개 candidate로 정리되어 있으며, `--strict`는 모든 target에 fallback candidate가 있을 때만 통과합니다. `--max-candidates <N>`은 target별 candidate 수 상한을 넘기면 실패합니다. 성공 후 artifact를 자동 정리하며, 산출물을 남겨서 확인하려면 `--keep-artifacts`를 사용합니다.

## 5. 정합성 유지

- `career-ops-kr finalize-tracker`: additions 병합, 상태 정규화, 선택적 verify를 한 번에 수행하는 기본 helper
- `career-ops-kr normalize-statuses`: 비표준 상태를 정규화
- `career-ops-kr merge-tracker`: additions를 tracker에 병합하는 저수준 명령
- `career-ops-kr verify`: 필수 파일, 중복, 누락 링크 검사
- `career-ops-kr audit-jobs`: tracker row와 `output/` 산출물을 같이 점검해 report/resume 누락, manifest referenced file 누락, artifact-index drift, legacy HTML을 출력
- `career-ops-kr process-pipeline`: pending URL을 fetch하고, 선택적으로 score/report/addition까지 생성한 뒤 성공한 항목만 처리 완료로 표시
- `career-ops-kr score-job`: 저장된 JD를 다시 점수화하고 `--tracker-out`, `--profile-path`, `--scorecard-path`로 출력과 scoring 입력을 제어할 수 있음
- `career-ops-kr prepare-resume-tailoring`: 저장된 JD와 score report를 resume tailoring JSON packet으로 구조화하고, 필요하면 `--base-context`로 현재 resume context와의 gap도 계산함
- `career-ops-kr apply-resume-tailoring`: tailoring packet을 base resume context에 안전하게 적용해서 render-ready context JSON을 생성함
- `career-ops-kr build-tailored-resume`: 저장된 JD와 score report, base resume context, template을 받아 prepare/apply/render를 한 번에 실행함
- `career-ops-kr build-tailored-resume-from-url`: URL에서 fetch/score를 먼저 수행하고, 이어서 build-tailored-resume까지 실행함. tracker addition은 `--tracker-out`을 준 경우에만 생성함
- `career-ops-kr backfill-artifact-manifests`: 기존 HTML 산출물 옆에 sibling manifest를 만들어 web inventory provenance를 최신 규칙으로 맞춤
- `career-ops-kr smoke-live-resume`: 공개 공고 기준 live smoke를 수행하고, 성공 시 기본적으로 artifact를 정리함. `--report-out`으로 성공 manifest JSON을 남길 수 있음
- `career-ops-kr show-live-smoke-report`: single 또는 batch live smoke JSON report를 사람이 읽기 쉬운 요약으로 출력함
- `career-ops-kr show-live-smoke-report --latest-from <dir>`: inventory에서 가장 최근 matching report를 찾아 바로 요약함
- `career-ops-kr compare-live-smoke-reports`: 두 single/batch live smoke JSON report를 비교해 added/removed/changed target을 출력함
- `career-ops-kr compare-live-smoke-reports --latest-from <dir>`: inventory에서 가장 최근 matching report 두 개를 골라 바로 비교함
- `career-ops-kr validate-live-smoke-reports`: saved report 기준으로 각 registry target의 최신 상태가 fresh success인지 검증함
- `career-ops-kr list-live-smoke-reports`: 디렉터리 아래 저장된 single/batch live smoke JSON report inventory를 출력함. `--type`, `--target`, `--failed-only`, `--used-fallback-only`, `--latest`로 inventory를 좁힐 수 있고, `--latest-per-target`으로 target별 최신 상태만 볼 수 있음
- `career-ops-kr list-live-smoke-targets`: live smoke target registry를 출력함
- `career-ops-kr validate-live-smoke-targets`: live smoke target registry를 네트워크 없이 검증함. single-candidate target과 crowded target을 같이 경고하고, 필요하면 `--max-candidates`로 candidate 수 상한을 gate할 수 있음
- `career-ops-kr smoke-live-resume-batch`: 여러 live smoke target을 순차 실행하고 target별 결과를 집계함. `--report-out`을 주면 운영 기록용 JSON report를 남김
- `career-ops-kr prepare-company-research`: 회사 조사 브리프를 생성하고 tracker/pipeline은 건드리지 않음
- `tests/test_pipeline.py`: pipeline lock 생성, live holder 차단, stale lock 회수 검증

## 6. Codex 운영 방식

Codex에게는 아래 순서로 요청하는 것이 좋습니다.

1. 프로필을 먼저 정리
2. 공고를 저장하고 평가
3. 점수 4점 이상만 이력서/지원 문안 생성
4. 낮은 적합도 공고는 tracker에 `스킵` 또는 `검토중`으로만 남김

## 7. Codex 로컬 자동화

이 저장소의 Codex 로컬 자동화는 아래처럼 분리한다.

- `.codex/config.toml`: 런타임 기본값과 custom agent 등록
- `.codex/agents/`: planner, builder, reviewer, tester, docs researcher 같은 좁은 역할
- `.agents/skills/`: 반복 작업 절차

운영 규칙:

- 같은 책임을 config, agent, skill에 중복 정의하지 않는다.
- 반복 호출이 필요한 절차는 skill로 넣는다.
- 역할이 분명한 작업만 custom agent로 둔다.
- `planner`는 계획만, `builder`는 구현만, `reviewer`는 검토만, `tester`는 실행/재현만, `docs_researcher`는 조사만 맡긴다.

## 8. 선택적 웹 사용 흐름

터미널 대신 브라우저로 먼저 시작하고 싶으면 아래 흐름을 사용합니다.

1. `career-ops-kr serve-web`를 실행합니다.
2. 브라우저에서 `http://127.0.0.1:3001`을 열면 `홈` 대시보드가 먼저 보입니다.
3. 홈에서 `설정 -> 이력서 -> 검색 -> 산출물 -> 트래커` 순서로 들어가고, 최근 생성한 HTML/PDF와 preset 경로를 함께 확인합니다. 최근 저장 공고 카드에는 attention 요약과 `다음 액션`이 같이 보여서, 트래커로 들어가기 전에 우선순위를 먼저 고를 수 있습니다.
4. `설정` 페이지에서 웹 DB 경로를 확인하고 필요하면 `DB 백업 생성`, `JSON 내보내기`, `JSON 가져오기`를 사용합니다. 최근 saved live smoke 상태도 같은 화면에서 확인할 수 있습니다.
5. `이력서` 페이지에서 PDF/TXT/MD 이력서를 업로드합니다.
6. `검색` 페이지에서 공고를 검색합니다. 결과 위쪽의 provider status strip으로 사람인 / 원티드 / eFinancial의 `정상 / 결과 없음 / 실패`와 실제 사용 검색어를 같이 확인합니다. 자주 쓰는 입력어는 search preset으로 저장해 두고 `/search?preset=...` 링크로 다시 실행할 수 있습니다. 저장한 preset은 기본 검색으로 지정할 수 있고, 마지막 사용 시각도 화면에서 바로 확인할 수 있습니다.
7. 검색 결과에서 아래를 바로 실행할 수 있습니다.
   - local tracker DB 저장
   - 맞춤 이력서 HTML/PDF 생성
   같은 canonical detail URL을 다시 저장하면 새 row를 만들지 않고 기존 항목을 다시 엽니다. 저장 panel에서 `새 저장 / 기존 항목 보완 / 기존 항목 재사용`도 바로 확인합니다.
8. `산출물` 페이지에서 웹과 CLI에서 생성한 HTML/PDF inventory를 함께 확인하고, 연결된 공고가 있으면 상세 화면으로 바로 이동할 수 있습니다. 새 산출물은 manifest 기반으로 provenance를 보여주고, manifest가 없는 예전 HTML은 legacy로 구분합니다.
9. `팔로업` 페이지에서는 overdue / 오늘 / 앞으로 7일 / 날짜 미설정 active 항목을 전용 inbox로 모아 봅니다. tracker markdown 포맷은 유지하고, 일정 정리만 web sidecar 기준으로 돕습니다. 같은 화면에서 `오늘로`, `3일 뒤`, `7일 뒤`, `미설정` quick action으로 팔로업 날짜를 바로 조정할 수 있습니다.
10. `홈` 대시보드의 follow-up preview에서도 같은 quick action을 제공하므로, inbox로 이동하지 않고도 가장 급한 일정만 바로 밀거나 비울 수 있습니다.
11. `트래커` 페이지에서 상태와 메모를 정리합니다. `리포트 없음`, `이력서 없음`, `팔로업 overdue`, `tracker 미연결` preset으로 attention item만 바로 좁힐 수 있습니다.
12. 여러 항목을 한 번에 정리할 때는 `트래커`에서 보이는 row만 선택해서 상태, 팔로업, 출처를 일괄 변경할 수 있습니다. 이 bulk update도 기존 update 경로를 재사용하므로 상태와 출처는 markdown tracker가 같이 맞춰지고, 팔로업은 web sidecar에서만 관리합니다. 선택한 row에 메모/위치 미저장 draft가 있으면 먼저 개별 저장을 요구해서 다른 draft를 잃지 않게 유지합니다. tracker-linked field를 바꿀 때 `tracker_id`가 없는 row는 먼저 막아서 잘못된 markdown row를 건드리지 않게 유지합니다.
13. 저장한 공고를 다시 볼 때는 `트래커` 목록에서 상세 화면으로 들어가 tracker 상태와 연결된 JD/report/context/HTML/PDF를 확인하고, 공고 URL이 있으면 그 자리에서 맞춤 이력서를 다시 생성합니다.
14. 상세 화면에는 `다음에 할 일`과 tracker/web drift 요약이 같이 보여서, 단순 조회가 아니라 다음 액션 결정 화면으로 사용합니다.
15. `홈`으로 돌아오면 최근 생성한 HTML/PDF 이력서와 preset 경로를 다시 바로 확인할 수 있습니다. 이 목록은 웹에서 만든 산출물과 CLI에서 만든 산출물을 함께 보여줍니다.
16. `홈`은 recent live smoke 상태를 짧게 요약하고, `설정`은 target별 문제/dir/report 수를 자세히 보여줍니다.
17. 웹 화면은 검색, 저장, 팔로업 정리, tracker 정리, deterministic resume build 중심으로 사용합니다.

규칙:

- web layer는 편한 product surface일 뿐, core pipeline을 대체하지 않습니다.
- web layer는 local SQLite sidecar를 사용합니다.
- deterministic 이력서 산출은 `build-tailored-resume-from-url`를 내부에서 호출해 `jds/`, `reports/`, `output/` 경로를 그대로 사용합니다.
- tracker source of truth는 여전히 CLI/file workflow 쪽 `data/applications.md`입니다. web jobs table은 product-side local state로 취급합니다.
- 브라우저 E2E는 선택 검증입니다. 기본 회귀 기준은 `tests.test_web`, `python -m unittest discover -s tests`, `career-ops-kr verify`입니다. 실제 브라우저까지 확인하려면 `CAREER_OPS_RUN_BROWSER_E2E=1 python -m unittest tests.test_web_e2e`를 따로 실행합니다.
