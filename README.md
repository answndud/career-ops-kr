# Career Ops KR

한국 개발자용 구직 작업을 정리해주는 Python CLI 도구입니다.

이 프로젝트는 아래 일을 파일 중심으로 처리합니다.

- 채용공고 저장
- 공고 적합도 평가
- 지원 현황 기록
- 회사 조사 메모 작성
- 한국어/영문 이력서 HTML/PDF 생성

기본은 터미널 도구입니다.  
다만 지금은 초보자도 쉽게 쓸 수 있도록, 선택적으로 브라우저에서 쓰는 로컬 웹 화면도 함께 제공합니다.
웹 화면은 `/Users/alex/project/career-ops-kr/design-guidelines.md` 기준의 grayscale admin dashboard 스타일로 정리되어 있습니다.

## 이 도구로 할 수 있는 것

- 공고 URL을 넣으면 `jds/*.md`에 공고 내용을 저장할 수 있습니다.
- 저장한 공고를 평가해서 `reports/*.md`에 리포트를 만들 수 있습니다.
- 평가 결과를 tracker에 반영할 준비 파일로 만들 수 있습니다.
- 회사 조사용 브리프를 `research/*.md`에 만들 수 있습니다.
- 공고에 맞춘 이력서 HTML/PDF를 `output/`에 만들 수 있습니다.

## 처음 보는 사람을 위한 핵심 개념

- `jds/`
  저장한 채용공고 원문입니다.
- `reports/`
  공고 평가 결과입니다.
- `research/`
  회사 조사 메모입니다.
- `output/`
  이력서 HTML/PDF와 중간 산출물이 들어갑니다.
- `data/applications.md`
  지원 현황 tracker입니다.
- `config/profile.yml`
  내 경력, 선호 조건, 타깃 역할을 적는 파일입니다.

이 프로젝트의 가장 기본 흐름은 아래입니다.

```text
공고 URL 저장
  -> 공고 평가
  -> 필요하면 tracker 반영
  -> 맞춤 이력서 생성
```

## 누가 쓰면 좋은가

- 여러 채용공고를 한 곳에서 정리하고 싶은 사람
- 지원 전 공고 적합도를 간단히 점수로 보고 싶은 사람
- 회사별로 이력서 버전을 따로 만들고 싶은 사람
- 노션이나 엑셀 대신 파일로 지원 현황을 관리하고 싶은 사람

## 준비물

- macOS 또는 Linux 터미널
- Python 3.11 이상
- 인터넷 연결
- 채용공고 URL

## 1. 설치

아래 명령어를 순서대로 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
career-ops-kr --help
```

마지막 `career-ops-kr --help`가 실행되면 설치가 된 것입니다.

브라우저 E2E 테스트까지 직접 돌릴 때만 아래를 추가로 설치하면 됩니다.

```bash
python -m playwright install chromium
```

## 2. 터미널이 어렵다면: 웹 화면으로 시작하기

브라우저에서 바로 쓰고 싶다면 아래 명령만 실행하면 됩니다.

```bash
source .venv/bin/activate
career-ops-kr serve-web
```

그 다음 브라우저에서 아래 주소를 엽니다.

- `http://127.0.0.1:3001`

가장 쉬운 웹 시작 순서는 아래 3단계입니다.

1. `설정`에서 DB 경로와 백업/내보내기 기능을 확인합니다.
2. `이력서`에서 내 PDF/TXT/MD 이력서를 업로드합니다.
3. `검색` 또는 `트래커 상세`에서 맞춤 이력서 HTML/PDF를 생성합니다.

처음 열리는 화면은 `홈`입니다. 여기서 아래를 바로 볼 수 있습니다.

- 무엇부터 해야 하는지 순서
- 업로드된 이력서 수
- 저장된 공고 수
- 최근 생성한 HTML/PDF 이력서 다시 열기
- web/CLI 산출물 구분
- resume preset 시작점
- 최근 saved live smoke 상태 요약

웹 화면에서 할 수 있는 일:

- **설정**
  - 웹 DB 경로 확인
  - DB 백업 / JSON 내보내기 / JSON 가져오기
  - 최근 live smoke 상태 요약 확인
  - 현재 기본 검색 소스는 별도 API 키 없이 사용
- **이력서**
  - PDF/TXT/MD 업로드
  - URL에서 맞춤 이력서 HTML/PDF 생성
- **산출물**
  - 웹과 CLI에서 생성한 HTML/PDF 이력서 inventory 확인
  - 새 산출물은 HTML 옆 `.manifest.json`까지 같이 남겨 provenance를 추적
  - 같은 output root에는 `artifact-index.json` derived cache도 같이 갱신되어 build run 기준 inventory lookup을 돕습니다.
  - manifest에는 `build_run_id`와 `inventory_key`가 같이 기록됩니다.
  - manifest가 없는 예전 HTML도 legacy fallback으로 계속 보임
  - 예전 HTML을 새 inventory 기준으로 맞추고 싶으면 `career-ops-kr backfill-artifact-manifests`로 sibling manifest를 일괄 생성
  - 연결된 공고가 있으면 바로 상세 화면으로 이동
- **검색**
  - 사람인 / 원티드 / eFinancial 통합 검색
  - 자주 쓰는 검색어를 search preset으로 저장하고 다시 실행
  - preset별 기본 검색 지정과 마지막 사용 시각 확인
  - 검색 source 상태 strip에서 provider별 `정상 / 결과 없음 / 실패`와 실제 사용 검색어를 바로 확인
  - 검색 결과 저장
  - 같은 공고를 다시 저장해도 canonical URL 기준으로 기존 항목을 다시 열고 중복 row를 만들지 않음
  - 저장 결과 panel에서 `새 저장 / 기존 항목 보완 / 기존 항목 재사용`을 바로 확인
  - 검색 결과에서 바로 맞춤 이력서 HTML/PDF 생성
- **트래커**
  - 저장된 공고 목록 확인
  - `리포트 없음 / 이력서 없음 / 팔로업 overdue / tracker 미연결` attention preset으로 바로 좁혀 보기
  - 보이는 항목을 선택해서 상태 / 팔로업 / 출처를 일괄 변경
  - 선택한 항목 중 메모/위치에 미저장 변경이 있으면 먼저 개별 저장 후 bulk를 실행
  - 저장된 공고 상세 화면에서 tracker 상태와 생성 산출물 확인
  - 저장된 공고 상세 화면에서 다음에 할 일을 읽기 쉽게 확인
  - 저장된 공고 상세 화면에서 같은 URL로 맞춤 이력서 HTML/PDF 다시 생성
  - 수동 추가 / 상태 수정 / 삭제
  - `data/applications.md` 기준 tracker sync
- **팔로업**
  - overdue / 오늘 / 앞으로 7일 / 날짜 미설정 active 항목을 전용 inbox에서 확인
  - 오늘로 이동 / 3일 뒤 / 7일 뒤 / 미설정 quick action으로 팔로업 날짜를 바로 조정
  - 홈 대시보드의 팔로업 preview에서도 같은 quick action 지원
  - tracker 상세로 바로 이동해 상태와 메모를 갱신
  - 팔로업 날짜는 web sidecar 전용이며 tracker markdown 포맷은 바꾸지 않음

화면 구성 원칙:

- 색과 장식보다 가독성을 우선합니다.
- 카드, 테이블, 배지, 입력창은 모든 화면에서 같은 규칙을 사용합니다.
- 홈, 검색, 이력서, 트래커, 설정 화면을 같은 정보 밀도의 내부 운영 화면으로 맞췄습니다.

주의:

- 이 웹 화면은 **선택 기능**입니다.
- 기본 CLI/file workflow는 그대로 유지됩니다.
- 웹 화면은 편한 사용을 위해 로컬 SQLite 파일 `data/career-ops-web.db`를 같이 씁니다.
- 웹에서 공고를 추가/수정/삭제하면 tracker markdown도 같이 맞추고, 필요하면 `트래커` 화면에서 다시 sync할 수 있습니다.
- `트래커`에서 저장된 공고 상세 화면으로 들어가면 JD/report/context/HTML/PDF 연결 상태를 다시 확인할 수 있고, 저장된 공고 URL이 있으면 그 자리에서 다시 맞춤 이력서를 생성할 수 있습니다.
- 최종 HTML/PDF 이력서 산출은 기존 Python resume pipeline을 그대로 호출합니다.
- 웹에서 방금 만든 HTML/PDF는 `홈` 화면의 최근 생성 결과에서 다시 열 수 있습니다.
- `산출물` 화면에서는 웹에서 만든 결과와 CLI에서 만든 결과를 함께 다시 볼 수 있습니다.
- `홈` 화면의 최근 생성 결과는 웹과 CLI에서 만든 HTML/PDF 산출물을 함께 보여줍니다.
- `홈`은 live smoke 상태를 짧게 요약해서 보여주고, 자세한 target 상태와 report 정보는 `설정`에서 봅니다.

### 웹에서 쓰는 기본 루트

지금 이 프로젝트의 웹 화면은 아래 4가지만 써도 충분합니다.

1. `이력서`에서 이력서 업로드
2. `검색`에서 공고 저장과 search preset 저장, 기본 preset 지정
3. `팔로업`과 `트래커`에서 다음 액션 정리
4. `검색` 또는 `트래커 상세`에서 맞춤 이력서 HTML/PDF 생성

같은 공고를 저장 버튼으로 다시 눌러도 duplicate row를 만들지 않고, 이미 저장된 항목이면 기존 항목으로 연결됩니다.

## 3. 가장 먼저 해야 할 일

이 프로젝트를 처음 쓸 때는 아래 2가지만 먼저 하면 됩니다.

1. `config/profile.example.yml`을 참고해서 `config/profile.yml`을 채웁니다.
2. 내 역할에 맞는 이력서 예시 파일을 하나 고릅니다.

두 파일의 역할은 다릅니다.

- `config/profile.yml`
  내 경력, 선호 조건, 타깃 역할처럼 "나 자신"에 대한 설정입니다.
- `examples/resume-context.*.json`
  이력서 출력의 시작점이 되는 예시 데이터입니다.
  같은 사람이라도 백엔드용, 플랫폼용, 데이터/AI용으로 다른 파일을 고를 수 있습니다.
- `templates/resume-*.html`
  이력서 모양을 결정하는 틀입니다.
  한국어 이력서는 `resume-ko.html`, 영문 이력서는 `resume-en.html`을 쓰면 됩니다.

예전 `output/*.html` 산출물이 많다면 한 번 정리해 두는 것이 좋습니다.

```bash
source .venv/bin/activate
career-ops-kr backfill-artifact-manifests
```

이 명령은 기존 HTML 옆에 `.manifest.json`을 만들어서 웹 `산출물` 화면과 provenance 표시를 최신 기준으로 맞춰 줍니다.
이미 manifest가 있는 HTML도 같은 실행에서 `artifact-index.json` entry를 같이 맞추고, stale orphan entry가 있으면 함께 정리합니다.

역할별 이력서 예시:

- 백엔드: `examples/resume-context.backend.ko.example.json`
- 플랫폼: `examples/resume-context.platform.ko.example.json`
- 데이터 플랫폼: `examples/resume-context.data-platform.ko.example.json`
- 데이터/AI: `examples/resume-context.data-ai.ko.example.json`

영문 이력서가 필요하면 `.ko.`가 없는 파일을 사용하면 됩니다.

경력기술서는 아래 예시를 시작점으로 쓰면 됩니다.

- 백엔드: `examples/career-description-context.backend.ko.example.json`
- 백엔드 English: `examples/career-description-context.backend.example.json`
- 플랫폼: `examples/career-description-context.platform.ko.example.json`
- 플랫폼 English: `examples/career-description-context.platform.example.json`
- 데이터 플랫폼: `examples/career-description-context.data-platform.ko.example.json`
- 데이터 플랫폼 English: `examples/career-description-context.data-platform.example.json`
- 데이터/AI: `examples/career-description-context.data-ai.ko.example.json`
- 데이터/AI English: `examples/career-description-context.data-ai.example.json`

## 4. 가장 쉬운 시작 방법: 공고 URL 하나로 이력서 만들기

초보자에게 가장 쉬운 방법은 `공고 1개`로 시작하는 것입니다.

이 방법은 아래처럼 생각하면 됩니다.

- `config/profile.yml`: 내 조건
- `examples/resume-context...json`: 이력서 내용의 시작점
- `templates/resume-*.html`: 이력서 디자인

처음에는 이 3개를 바꾸지 말고 예시 그대로 써도 됩니다.

예시:

```bash
source .venv/bin/activate
career-ops-kr build-tailored-resume-from-url \
  "https://career.rememberapp.co.kr/job/posting/293599" \
  examples/resume-context.platform.ko.example.json \
  templates/resume-ko.html \
  --job-out jds/my-first-job.md \
  --report-out reports/my-first-report.md \
  --html-out output/my-first-resume.html \
  --profile-path config/profile.example.yml
```

이 명령이 하는 일:

1. 공고 내용을 저장합니다.
2. 공고를 평가합니다.
3. 맞춤 이력서용 데이터를 만듭니다.
4. 최종 HTML 이력서를 만듭니다.

결과로 보게 되는 파일:

- `jds/my-first-job.md`
- `reports/my-first-report.md`
- `output/my-first-resume.html`

PDF도 만들고 싶으면 아래를 추가로 실행합니다.

```bash
source .venv/bin/activate
career-ops-kr generate-pdf output/my-first-resume.html output/my-first-resume.pdf
```

## 5. 공고를 여러 개 관리하는 기본 루트

공고를 하나씩 넣는 대신, 여러 개를 pipeline에 쌓아두고 처리할 수도 있습니다.

언제 이 방법을 쓰면 되나:

- 공고 1개만 바로 보고 싶다
  `build-tailored-resume-from-url`
- 여러 공고를 모아두고 순서대로 평가하고 싶다
  `discover-jobs -> process-pipeline -> finalize-tracker`

### 4-1. 공고 찾기

```bash
source .venv/bin/activate
career-ops-kr discover-jobs wanted --limit 10
career-ops-kr discover-jobs jumpit --limit 10
career-ops-kr discover-jobs remember --limit 10
```

이 명령은 `data/pipeline.md`에 공고 URL을 넣습니다.

### 4-2. pipeline 처리하기

```bash
source .venv/bin/activate
career-ops-kr process-pipeline --limit 3 --score --profile-path config/profile.example.yml
```

이 명령은:

- `data/pipeline.md`의 대기 중 URL을 읽고
- `jds/`에 공고를 저장하고
- `reports/`에 평가 결과를 만들고
- tracker addition 파일도 같이 생성할 수 있습니다

## 6. tracker 반영하기

지원 현황을 한 파일로 정리하고 싶으면 tracker를 씁니다.

기본 명령:

```bash
source .venv/bin/activate
career-ops-kr finalize-tracker
career-ops-kr audit-jobs
```

이 명령은 보통 아래를 한 번에 처리합니다.

- additions 병합
- 상태값 정리
- 기본 검증

`career-ops-kr audit-jobs`는 tracker row와 `output/` 산출물을 같이 점검해서 아래 같은 운영 이슈를 바로 보여줍니다.

- report 경로 누락
- report 파일 누락
- active row의 resume 경로 누락
- resume 파일 누락
- sibling manifest가 없는 legacy HTML 산출물
- manifest가 가리키는 context/report/pdf/html 같은 파일 누락
- `artifact-index.json` 누락 또는 manifest/index drift

지원 현황 원본 파일은 `data/applications.md`입니다.

## 7. 이력서를 단계별로 만들고 싶을 때

위의 one-shot 명령 대신, 단계별로 나눠서 작업할 수도 있습니다.

### 6-1. 맞춤 이력서용 packet 만들기

```bash
source .venv/bin/activate
career-ops-kr prepare-resume-tailoring \
  jds/<job>.md \
  reports/<report>.md \
  --base-context examples/resume-context.platform.ko.example.json
```

### 6-2. render용 context 만들기

```bash
source .venv/bin/activate
career-ops-kr apply-resume-tailoring \
  output/resume-tailoring/<packet>.json \
  examples/resume-context.platform.ko.example.json \
  --out output/my-context.json
```

### 6-3. HTML 만들기

```bash
source .venv/bin/activate
career-ops-kr render-resume \
  templates/resume-ko.html \
  output/my-context.json \
  output/my-resume.html
```

### 6-4. PDF 만들기

```bash
source .venv/bin/activate
career-ops-kr generate-pdf output/my-resume.html output/my-resume.pdf
```

## 8. 회사 조사 메모 만들기

지원 전에 회사 조사 메모를 만들고 싶다면:

```bash
source .venv/bin/activate
career-ops-kr prepare-company-research \
  Toss \
  --homepage https://toss.im \
  --careers-url https://toss.im/career/jobs
```

그 다음 요약 초안이 필요하면:

```bash
source .venv/bin/activate
career-ops-kr prepare-company-followup research/<brief>.md --mode summary
```

결과는 `research/` 아래에 저장됩니다.

## 8. 어떤 명령을 언제 쓰는가

가장 자주 쓰는 명령만 쉽게 정리하면 아래와 같습니다.

- `career-ops-kr --help`
  전체 명령 목록 보기
- `career-ops-kr fetch-job <url>`
  공고 1개 저장
- `career-ops-kr score-job jds/<job>.md`
  저장한 공고 1개 평가
- `career-ops-kr discover-jobs wanted --limit 10`
  포털에서 공고 URL 모으기
- `career-ops-kr process-pipeline --limit 3 --score`
  모아둔 공고 여러 개 처리
- `career-ops-kr finalize-tracker`
  tracker 반영
- `career-ops-kr audit-jobs`
  tracker와 산출물의 운영 이슈 점검
- `career-ops-kr build-tailored-resume-from-url ...`
  공고 URL 하나로 바로 이력서 만들기
- `career-ops-kr prepare-company-research <company>`
  회사 조사 메모 시작
- `career-ops-kr verify`
  기본 정합성 확인

## 9. 초보자에게 추천하는 실제 사용 순서

처음에는 아래 순서만 기억하면 됩니다.

1. 설치
2. `config/profile.yml` 작성
3. 공고 URL 하나로 `build-tailored-resume-from-url` 실행
4. 결과로 나온 `jds/`, `reports/`, `output/` 파일 확인
5. 익숙해지면 `discover-jobs` + `process-pipeline` 사용
6. 마지막에 `finalize-tracker`로 지원 현황 정리

## 10. 자주 보는 폴더

- `config/`
  내 설정
- `jds/`
  저장한 공고
- `reports/`
  공고 평가 결과
- `research/`
  회사 조사 메모
- `output/`
  이력서 HTML/PDF와 중간 산출물
- `data/`
  pipeline과 tracker

## 11. 초보자가 자주 하는 실수

- `config/profile.yml`을 안 만들고 바로 실행함
  이 경우 예시 프로필을 먼저 참고해서 채워야 합니다.
- 한 번 만든 출력 파일 위에 같은 이름으로 다시 쓰려고 함
  출력 경로를 바꾸거나 `--overwrite`가 필요한지 확인하세요.
- `discover-jobs`와 `process-pipeline`를 같은 개념으로 생각함
  `discover-jobs`는 URL만 모으고, 실제 저장/평가는 `process-pipeline`가 합니다.
- live smoke 명령을 일반 사용 명령으로 오해함
  `smoke-live-resume`, `validate-live-smoke-*`는 운영/점검용 고급 기능입니다.

## 12. 문제 생겼을 때

### 명령 목록이 안 보일 때

```bash
source .venv/bin/activate
career-ops-kr --help
```

### 기본 검증이 필요할 때

```bash
source .venv/bin/activate
career-ops-kr verify
career-ops-kr audit-jobs
```

### 웹 DB를 백업하거나 옮기고 싶을 때

웹의 `설정` 화면에서 아래 3가지를 구분해서 쓰면 됩니다.

- `DB 백업 생성`
  현재 SQLite 파일을 그대로 복사해 둡니다.
  가장 안전한 기본 백업입니다.
- `JSON 내보내기`
  현재 웹 DB 내용을 JSON snapshot으로 저장합니다.
  다른 로컬 환경으로 옮기거나 내용을 확인할 때 편합니다.
- `JSON 가져오기`
  이전에 내보낸 JSON snapshot을 다시 불러옵니다.
  가져오기 전에 자동 백업도 함께 만듭니다.

처음에는 아래처럼 이해하면 됩니다.

- 그냥 안전하게 보관하고 싶다: `DB 백업 생성`
- 다른 곳으로 옮기고 싶다: `JSON 내보내기`
- 예전에 저장한 상태로 되돌리고 싶다: `JSON 가져오기`

### TLS 인증서 문제로 fetch가 실패할 때

```bash
career-ops-kr fetch-job "<url>" --insecure
career-ops-kr discover-jobs wanted --insecure
```

### 더 자세한 상태를 보고 싶을 때

- 현재 작업 계획: `PLAN.md`
- 최근 작업 기록: `PROGRESS.md`
- 자세한 운영 설명: `docs/workflows.md`
- 구조 설명: `docs/architecture.md`

## 13. 고급 기능

일반 사용에는 꼭 필요하지 않지만, 운영 점검용으로 아래 명령도 있습니다.

### live smoke target 확인

```bash
source .venv/bin/activate
career-ops-kr list-live-smoke-targets
career-ops-kr validate-live-smoke-targets
career-ops-kr validate-live-smoke-targets --max-candidates 2
```

### 실제 공개 공고로 smoke 실행

```bash
source .venv/bin/activate
career-ops-kr smoke-live-resume --target remember_platform_ko --report-out output/single-live-smoke-report.json
career-ops-kr smoke-live-resume-batch --report-out output/live-smoke-report.json
```

### saved report 보기

```bash
source .venv/bin/activate
career-ops-kr list-live-smoke-reports output
career-ops-kr list-live-smoke-reports output --latest-per-target
career-ops-kr show-live-smoke-report --latest-from output --type batch --target remember_platform_ko
career-ops-kr compare-live-smoke-reports --latest-from output --type batch --target remember_platform_ko
career-ops-kr validate-live-smoke-reports output --max-age-hours 24
```

## 14. 이 프로젝트가 조금 더 익숙해졌다면

아래 문서를 보면 더 자세히 이해할 수 있습니다.

- [workflows.md](/Users/alex/project/career-ops-kr/docs/workflows.md)
- [architecture.md](/Users/alex/project/career-ops-kr/docs/architecture.md)
- [scoring-kr.md](/Users/alex/project/career-ops-kr/docs/scoring-kr.md)

## 참고

이 저장소는 [santifer/career-ops](https://github.com/santifer/career-ops)의 개념에서 출발했지만, 그대로 포크하지 않고 Codex와 한국 개발자 구직 흐름에 맞게 새로 설계했습니다.
