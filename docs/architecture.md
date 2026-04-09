# Architecture

## Overview

`career-ops-kr`는 크게 6개 층으로 나뉩니다.

1. `config/`
   개인 프로필, 상태값, 포털, 점수화 규칙, live smoke target registry의 소스 오브 트루스입니다.
2. `jds/`, `reports/`, `research/`, `data/`
   공고 원문, 평가 리포트, 회사 조사 브리프, 지원 현황을 파일로 보관합니다.
3. `src/career_ops_kr/`
   공고 추출, 공통 점수 계산, resume 렌더링, tracker 정합성 유지 작업을 수행하는 Python CLI입니다. `cli.py`는 얇은 엔트리포인트이고, 실제 command group은 `commands/` 아래에 분리합니다.
4. `.codex/` + `.agents/skills/`
   Codex용 project-local 운영 계층입니다. `.codex/config.toml`은 런타임 기본값과 custom agent를 정의하고, `.agents/skills/`는 반복 작업 절차를 정의합니다.
5. `prompts/`
   Codex가 일관된 방식으로 평가와 작성 작업을 수행하도록 돕는 운영 프롬프트입니다.
6. `src/career_ops_kr/web/`
   선택적으로 띄울 수 있는 FastAPI 기반 product surface입니다. 홈 대시보드, 검색, 설정, 이력서 업로드, 산출물 inventory, tracker UI, 저장 공고 detail view를 제공합니다. 홈 대시보드는 최근 공고, 최근 업로드 이력서, 최근 생성 HTML/PDF를 web/CLI 구분과 함께 한 번에 보여주고, live smoke 상태는 짧은 요약만 노출합니다. 검색 화면은 provider health 요약, source별 query 상태, canonical URL 기준 import dedupe를 같이 보여줍니다. tracker/detail 화면은 raw 상태 조회만이 아니라 `다음에 할 일`, attention preset, tracker/web drift를 같이 보여주는 운영 화면입니다. detail view는 tracker row와 연결된 artifact를 다시 열거나 같은 공고 URL로 resume build를 재실행하는 entry point로 동작하며, context에 저장된 tailoring guidance도 다시 보여줍니다. 산출물 inventory는 sibling `.manifest.json`을 우선 읽고, manifest가 없는 예전 HTML은 legacy fallback으로 계속 보여줍니다. 이 계층은 local-only SQLite sidecar를 쓰지만, HTML/PDF resume 산출은 기존 CLI resume pipeline을 그대로 호출합니다. AI surface는 기본 비활성화이고, 필요할 때만 `serve-web --enable-ai`로 켭니다. 시각 규칙은 `/Users/alex/project/career-ops-kr/design-guidelines.md`를 기준으로 grayscale-first admin dashboard 패턴을 공유합니다.

## Core Flow

```text
portal sitemap
  -> career-ops-kr discover-jobs
  -> data/pipeline.md
  -> career-ops-kr process-pipeline --score
  -> jds/*.md
  -> reports/*.md + data/tracker-additions/*.tsv
  -> career-ops-kr finalize-tracker
  -> data/applications.md
```

수동 재실행이 필요하면 `career-ops-kr score-job jds/<job>.md`로 같은 점수화 로직을 다시 호출합니다. 세션 간 재현이 필요하면 `--profile-path`와 `--scorecard-path`를 명시합니다.

`process-pipeline --score`와 `score-job`는 같은 `src/career_ops_kr/scoring.py` 로직을 공유합니다.
`process-pipeline`가 `--score`를 쓰지 않으면 `- [x]`는 여전히 fetch/save 완료만 뜻합니다. optional scoring은 report와 tracker addition 생성만 추가하고 pipeline 의미는 바꾸지 않습니다.
`score-job`는 `--tracker-out`로 tracker addition 경로를 덮어쓸 수 있고, `--profile-path`, `--scorecard-path`로 scoring 입력 파일을 고정할 수 있습니다.
`process-pipeline`는 같은 pipeline 파일에 대해 `*.lock` sidecar를 잡고 실행합니다. 살아 있지 않은 PID가 남긴 stale lock은 자동 회수하고, metadata가 손상된 lock은 file age fallback으로 처리합니다. 실제로 다른 프로세스가 잡고 있는 lock은 즉시 실패시킵니다.
pipeline dedup과 processed matching은 raw URL이 아니라 canonical detail URL 기준으로 처리합니다. 현재는 Wanted, Jumpit, Remember, Indeed, RocketPunch detail URL을 canonicalize합니다.
`finalize-tracker`는 `merge-tracker -> normalize-statuses -> optional verify`를 묶은 기본 helper다. 개별 명령은 세밀한 운영이 필요할 때만 쓴다.

이력서 생성은 별도 흐름입니다.

```text
saved JD + score report
  -> career-ops-kr prepare-resume-tailoring
  -> output/resume-tailoring/*.json
  -> career-ops-kr apply-resume-tailoring
  -> output/resume-contexts/*.json
  -> career-ops-kr render-resume
  -> output/*.html
  -> career-ops-kr generate-pdf
  -> output/*.pdf
```

`prepare-resume-tailoring`는 새 scoring을 하지 않는다. 기존 `jds/*.md`와 `reports/*.md`를 읽어 선택된 domain / role profile / score summary를 resume-tailoring packet으로 옮긴다. `--base-context`가 주어지면 현재 resume context 기준의 matched skill과 missing focus keyword도 같이 계산한다.

`apply-resume-tailoring`는 packet을 base resume context에 반영하되, 없는 기술을 임의로 추가하지 않는다. 기본적으로 `headline`, `summary`, `skills` 순서, `experience/projects` 정렬만 바꾸고, 나머지 guidance는 `tailoringGuidance` metadata로 남긴다.

`build-tailored-resume`와 `build-tailored-resume-from-url`는 HTML 옆에 sibling `.manifest.json`도 같이 남긴다. web inventory는 이 manifest를 우선 읽어 provenance와 selection/focus metadata를 보여주고, manifest가 없는 예전 HTML만 legacy fallback으로 취급한다.

회사 조사는 별도 흐름입니다.

```text
company name + optional URLs
  -> career-ops-kr prepare-company-research
  -> research/*.md
  -> career-ops-kr prepare-company-followup
  -> research/*-summary.md or research/*-outreach.md
  -> JobPlanet / Blind / official sources manual review
```

`prepare-company-research`와 `prepare-company-followup`는 네트워크 fetch를 하지 않고, 이미 알고 있는 URL과 로컬 산출물 경로만 묶어 조사 브리프와 후속 scaffold를 만듭니다. 공고 intake와 tracker 병합 흐름에 직접 쓰지 않습니다.

선택적 web product surface는 아래처럼 작동합니다.

```text
browser
  -> career-ops-kr serve-web
  -> src/career_ops_kr/web/app.py
  -> local SQLite sidecar (settings, jobs, resumes, ai_outputs)
  -> search / tracker / web DB operations
  -> build-tailored-resume-from-url
  -> jds/*.md + reports/*.md + output/*.html/pdf
```

여기서 중요한 점은 두 가지입니다.

- CLI/file workflow는 여전히 canonical core입니다.
- web layer는 초보자용 product surface이므로 local DB를 써도 되지만, deterministic JD/report/resume 산출은 core helper를 재사용해야 합니다.
- web DB는 settings/jobs/resumes와 운영용 backup/export/import를 위한 sidecar입니다. tracker canonical source는 여전히 `data/applications.md`입니다.
- web import는 canonical detail URL 기준으로 idempotent하게 동작해야 합니다. 같은 공고를 다시 저장할 때 duplicate row를 만들기보다 기존 job row를 재사용하고, 필요한 경우만 missing metadata를 보완합니다.

## Why Codex-First

원본 `career-ops`는 `claude -p`와 slash command 기반의 모드 시스템이 핵심입니다. 이 저장소는 그 방식을 버리고, Codex가 다음을 하도록 설계합니다.

- 파일을 직접 읽고 수정
- 필요할 때만 스크립트를 실행
- 프롬프트보다 데이터 모델을 우선
- 한국 시장 규칙을 config 파일로 명시

## Codex Local Surfaces

이 저장소에서 Codex 관련 로컬 설정은 세 층으로 분리합니다.

1. `.codex/config.toml`
   런타임 기본값과 custom agent registry만 둡니다.
2. `.codex/agents/*.toml`
   planner, builder, reviewer, tester, docs researcher 같은 좁은 역할을 정의합니다.
3. `.agents/skills/*/SKILL.md`
   반복 가능한 절차를 정의합니다. Codex에서 사실상 command surface로 취급합니다.

규칙:

- config는 절차를 담지 않습니다.
- agent는 역할과 관점만 담습니다.
- skill은 실제 작업 절차를 담습니다.
- 같은 책임을 config, agent, skill에 중복 정의하지 않습니다.

## Data Model

### `data/applications.md`

기본 tracker입니다.

| ID | Date | Company | Role | Score | Status | Source | Resume | Report | Notes |

### `data/pipeline.md`

나중에 자동 스캐너가 채워 넣을 inbox입니다.

### `data/pipeline.md.lock`

`process-pipeline` 실행 중에만 존재하는 sidecar lock입니다. 같은 inbox 파일에 대한 동시 실행을 막고, stale 여부는 lock metadata의 PID 기준을 우선하며 필요하면 file age fallback을 씁니다.

### `data/tracker-additions/**/*.tsv`

평가 결과를 tracker에 안전하게 병합하기 전 임시로 쌓는 디렉터리입니다. 기본 helper인 `finalize-tracker`는 하위 디렉터리까지 재귀적으로 병합합니다.

### `research/*.md`

회사별 조사 브리프입니다. `prepare-company-research`가 생성하며, JobPlanet / Blind / 공식 홈페이지 / 채용 페이지 같은 source를 정리하고 조사 checklist를 seed합니다.

## Scope Boundaries

1차 MVP에서 하지 않는 것:

- 포털별 로그인 자동화
- 한국 채용 사이트별 동적 렌더링 대응
- 대규모 병렬 처리
- 자동 지원 제출

1차 MVP에서 반드시 유지하는 것:

- 사람이 검토하는 구조
- 중복 방지와 상태 정규화
- 한글/영문 산출물 분리 가능성
- 설정 파일 중심의 확장성
