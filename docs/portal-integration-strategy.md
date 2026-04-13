# Portal Integration Strategy

기준일: 2026-04-06

이 문서는 한국 채용 포털을 `career-ops-kr`에 어떻게 통합할지 정리한 구현 전략 문서다. 목표는 무리하게 모든 listing을 브라우저로 긁는 것이 아니라, 현재 공개적으로 안정적인 진입점부터 사용해 낮은 비용으로 수집 품질을 확보하는 것이다.

## 요약

| Source | 역할 | 현재 상태 | 권장 전략 |
|--------|------|-----------|-----------|
| Wanted | primary intake | 구현 완료 | `sitemap -> detail fetch` 우선 |
| Jumpit | primary intake | 구현 완료 | `sitemap -> detail fetch` 우선 |
| Remember | primary intake | 구현 완료 | `sitemap -> detail fetch` 우선 |
| Saramin | supplemental intake | 구현 완료(키 필요) | 공식 API 우선, `SARAMIN_ACCESS_KEY`가 있으면 `discover-jobs saramin` 사용 |
| JobKorea | manual intake | 조사 완료 | company recruit browse만 사용, detail 자동화는 보류 |
| LinkedIn | manual intake | 조사 완료 | guest page는 읽되 crawler는 쓰지 않음 |
| RocketPunch | manual intake | 일부 조사 완료 | v1에서는 수동/보조 소스로 제한 |
| Indeed | manual intake | 조사 완료 | detail URL만 수동 intake, `jk` 기준 canonicalization |
| JobPlanet | company research | workflow 구현 완료 | `prepare-company-research`의 수동 입력원으로 사용 |
| Blind | company research | workflow 구현 완료 | `prepare-company-research`의 수동 입력원으로 사용 |

## 역할 분류 규칙

- `primary intake`: `discover-jobs`나 향후 intake 명령의 직접 대상이 되는 소스
- `supplemental intake`: 공고를 가져올 수는 있지만, canonical URL과 dedup 정책이 먼저 필요한 보조 소스
- `manual intake`: 자동 crawler 대신 사용자가 직접 URL을 넣거나 수동 캡처로 처리하는 소스
- `intake candidate`: 가치가 높아 보이지만 아직 public entry point와 정책을 검증하지 않은 후보
- `company research`: 공고 수집보다 회사 평판, 인터뷰 경험, 조직 분위기 확인에 쓰는 소스

## 1. Wanted

### 관찰

- 대표 상세 페이지 `https://recruit.wanted.co.kr/wd/343686`는 2026-04-06 기준 `200` 응답을 반환했고, 현재 `career-ops-kr fetch-job`으로 본문 추출이 가능했다.
- `https://www.wanted.co.kr/robots.txt`는 공개되어 있으며 `/api/`와 개인화 영역을 차단하지만 사이트 전체를 막지는 않는다.
- `https://www.wanted.co.kr/sitemap.xml`는 공개 sitemap index를 제공한다.
- sitemap index 안에 `sitemap_kr_job_*.xml`이 있으며, 자식 sitemap에는 `https://www.wanted.co.kr/wd/<id>` 형식의 공고 상세 URL이 들어 있다.

### URL 패턴

- 상세 공고:
  - `https://www.wanted.co.kr/wd/<job_id>`
  - `https://recruit.wanted.co.kr/wd/<job_id>`
- discovery:
  - `https://www.wanted.co.kr/sitemap.xml`
  - `https://www.wanted.co.kr/sitemap_kr_job_<n>.xml`

### 권장 구현

v1:

1. sitemap index를 읽고 `sitemap_kr_job_*.xml`을 수집한다.
2. 자식 sitemap에서 `wd/<id>` 상세 URL을 추출한다.
3. 상세 URL을 현재 `fetch-job` 파이프라인으로 저장한다.
4. 추후 company filter 또는 title filter는 상세 페이지 저장 후 점수화 단계에서 적용한다.

v2:

- 필요하면 listing 페이지나 company-specific page 탐색을 추가한다.
- `wanted.co.kr/wd/<id>`와 `recruit.wanted.co.kr/wd/<id>`는 같은 공고일 수 있으므로 job id 기준 dedup을 둔다.

### 리스크

- 본문 상단에 숫자/페이지네이션 같은 잡음이 일부 섞인다.
- 실제 활성 공고와 sitemap 반영 사이에 지연이 있을 수 있다.
- 상세 호스트가 `wanted.co.kr`와 `recruit.wanted.co.kr`로 나뉘므로 canonicalization 규칙이 필요하다.

## 2. Jumpit

### 관찰

- 대표 상세 페이지 `https://jumpit.saramin.co.kr/position/48685313`는 2026-04-06 기준 `200` 응답을 반환했고, 현재 `career-ops-kr fetch-job`으로 본문 추출이 가능했다.
- `https://jumpit.saramin.co.kr/robots.txt`는 공개되어 있으며 로그인/내 계정 영역만 막고, sitemap을 공개한다.
- `https://jumpit.saramin.co.kr/sitemap.xml`는 index sitemap을 제공한다.
- 이 안의 `sitemap_position_view_1.xml`에는 `https://jumpit.saramin.co.kr/position/<id>` 형식의 상세 URL이 직접 들어 있다.
- `sitemap_position_1.xml`에는 `https://jumpit.saramin.co.kr/positions?jobCategory=<id>` 같은 카테고리 listing URL이 들어 있다.

### URL 패턴

- 상세 공고:
  - `https://jumpit.saramin.co.kr/position/<job_id>`
- discovery:
  - `https://jumpit.saramin.co.kr/sitemap.xml`
  - `https://jumpit.saramin.co.kr/sitemap/sitemap_position_view_1.xml`
  - `https://jumpit.saramin.co.kr/positions?jobCategory=<category_id>`

### 권장 구현

v1:

1. `sitemap.xml`에서 `sitemap_position_view_*.xml`을 읽는다.
2. 상세 공고 URL을 직접 추출한다.
3. `fetch-job`로 본문 저장 후 점수화 단계로 넘긴다.

v1.1:

- `sitemap_position_*.xml`의 카테고리 listing URL을 메타데이터로만 저장한다.
- 카테고리별 수집량 또는 필터링 실험에 사용한다.

### 리스크

- 점핏은 사람인이 운영하므로 일부 페이지 정책이 바뀔 수 있다.
- 취업축하금, 태그, 배지 같은 비직무 정보가 본문에 포함될 수 있다.
- category listing은 public이지만, 실제 discovery 효율은 상세 sitemap 쪽이 더 높다.

## 3. Remember

### 관찰

- `https://career.rememberapp.co.kr/job/postings`는 2026-04-06 기준 `200` 응답을 반환했다.
- `https://career.rememberapp.co.kr/robots.txt`는 공개되어 있으며 `User-agent: *`에 대해 `/job/`과 `sitemap*.xml`을 허용한다.
- `robots.txt`는 `Sitemap: https://career.rememberapp.co.kr/sitemap.xml`와 `sitemap-jobs.xml`를 직접 노출한다.
- `https://career.rememberapp.co.kr/sitemap.xml`는 sitemap index를 제공하고, `sitemap-jobs.xml`에 `https://career.rememberapp.co.kr/job/posting/<postingId>` 형식의 상세 URL이 들어 있다.
- `https://career.rememberapp.co.kr/job/posting/24786`는 2026-04-06 기준 현재 `career-ops-kr fetch-job`으로 본문 추출이 가능했다.
- 상세 페이지 HTML에는 canonical URL이 `/job/posting/<postingId>`로 잡혀 있고, query 형태인 `/job/postings?postingId=<id>`도 같은 상세 콘텐츠에 접근 가능하지만 canonical source로는 쓰지 않는 편이 맞다.

### URL 패턴

- 상세 공고:
  - `https://career.rememberapp.co.kr/job/posting/<posting_id>`
- discovery:
  - `https://career.rememberapp.co.kr/sitemap.xml`
  - `https://career.rememberapp.co.kr/sitemap-jobs.xml`
  - `https://career.rememberapp.co.kr/job/postings`
  - `https://career.rememberapp.co.kr/job/postings?search=<json-encoded-filter>`

### 권장 구현

v1:

- `sitemap.xml`에서 `sitemap-jobs.xml`을 읽는다.
- 상세 공고 URL을 직접 추출한다.
- `discover-jobs remember`로 `data/pipeline.md`에 넣는다.
- `fetch-job`는 canonical detail URL인 `/job/posting/<id>`를 사용한다.

v2 후보:

- `sitemap-b2c.xml`의 카테고리 listing URL을 메타데이터로 활용한다.
- `search=` 파라미터를 이용한 개발 직군 한정 discovery나 사전 필터링을 추가한다.

### 리스크

- 상세 페이지에 추천 포지션, 보상금, 로그인 유도 블록이 섞여 있어 `fetch-job` 결과에 잡음이 일부 포함된다.
- detail 페이지가 `noindex,follow` 메타를 갖고 있어 검색엔진 노출 정책과 sitemap 운영 방식이 다를 수 있다.
- category listing의 `search=` 값은 JSON-encoded query이므로, 나중에 필터 자동화를 넣을 때 canonicalization 기준이 필요하다.

## 4. RocketPunch

### 관찰

- 2026-04-06 기준 browser-like header로 `https://www.rocketpunch.com/jobs`, `https://www.rocketpunch.com/robots.txt`, `https://www.rocketpunch.com/sitemap.xml`에 `200` 응답을 받을 수 있었다.
- 하지만 같은 조건에서 받은 응답이 AWS WAF challenge 또는 로그인/anti-crawl gate HTML인 경우가 있었고, 안정적인 crawl surface로 보기는 어려웠다.
- `https://www.rocketpunch.com/jobs/154190`도 현재 CLI에서 `200`을 받을 수 있었지만, 저장된 본문에는 실제 JD 대신 로그인/anti-crawl 안내 문구가 섞였다.
- 이전 조사 시점에는 direct fetch가 `403`이었기 때문에, RocketPunch의 응답 정책은 시점과 요청 형태에 따라 흔들린다.
- 같은 날 재검토에서는 `robots.txt`와 `sitemap.xml`이 `200`을 반환했지만, detail HTML에는 여전히 AWS WAF marker가 들어 있었고 sitemap index도 직접 XML parse에서 신뢰하기 어려운 응답이 나왔다.

### URL 패턴

- listing:
  - `https://www.rocketpunch.com/jobs`
- company recruit browse:
  - `https://www.rocketpunch.com/companies/<slug>/recruit`
- detail:
  - `https://www.rocketpunch.com/jobs/<job_id>`
  - `https://www.rocketpunch.com/en-US/jobs/<job_id>`
  - `https://www.rocketpunch.com/jobs/<job_id>/<slug>`
  - localized 또는 slug 변형은 canonical detail인 `https://www.rocketpunch.com/jobs/<job_id>`로 정규화한다.

### 권장 구현

v1:

- RocketPunch는 discovery 자동 수집 대상에 넣지 않는다.
- 허용 방식:
  - 사용자가 `jobs/<job_id>` canonical detail URL을 참고 source로만 보관
  - localized/slug detail URL은 canonical detail로 정규화해서 저장
  - 검색 엔진에서 찾은 URL을 수동 참고용으로 저장
- `fetch-job`는 listing이나 company recruit URL을 받으면 실패시켜 detail URL만 남기도록 유도한다.
- `fetch-job`는 RocketPunch가 로그인/anti-crawl gate HTML이나 AWS WAF challenge marker를 돌려주면 실패시키고 bogus JD 저장을 막는다.

v2 후보:

- WAF challenge 없이 실제 JD 본문을 안정적으로 받는 조건이 재현될 때만 재검토한다.
- listing/sitemap이 진짜 job detail feed로 이어지는지 검증된 뒤에만 crawler를 도입한다.

### 리스크

- 요청 형태에 따라 `403`, challenge HTML, 로그인/anti-crawl gate HTML이 섞여 fetch 안정성이 낮다.
- `200` 응답이어도 usable JD가 아닐 수 있어 naive fetch는 잘못된 원문을 저장할 수 있다.
- `robots.txt`와 `sitemap.xml`이 열려 있어도 실제 job-detail feed로 이어진다는 보장은 없고, 현재 응답은 여전히 변동성이 있다.
- 서비스 정책이나 anti-bot 기준을 어길 가능성이 있어 현재는 manual reference 수준으로만 두는 것이 맞다.

## 5. Saramin

### 관찰

- `https://www.saramin.co.kr/zf_user/jobs/list/job-category`는 2026-04-06 기준 공개 접근이 가능했고, 일반 채용 listing 진입점으로 쓸 수 있었다.
- listing에서 클릭한 공고는 `https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=<id>&view_type=list` 패턴의 상세 URL로 열렸다.
- 사람인은 공식 채용정보 API를 운영하고 있고, API 소개 문서와 `job-search` 가이드를 공개한다.
- 공식 API는 `access-key`를 요구하고, 문서상 승인 절차를 통과한 사용자만 이용 가능하다.
- 공식 API sample output은 상세 URL을 `zf_user/jobs/relay/view?rec_idx=<id>` 형태로 반환한다.

### URL 패턴

- listing:
  - `https://www.saramin.co.kr/zf_user/jobs/list/job-category`
- detail:
  - `https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx=<job_id>&view_type=list`
- official API:
  - `https://oapi.saramin.co.kr/introduce`
  - `https://oapi.saramin.co.kr/job-search`

### 권장 구현

v1:

- HTML crawler보다 공식 API를 우선한다.
- `SARAMIN_ACCESS_KEY`가 있으면 `discover-jobs saramin`이 공식 API를 사용해 `job_mid_cd=2 (IT개발·데이터)` 범위의 공고를 가져온다.
- API 응답의 detail URL은 `rec_idx` 기준 canonical URL로 정규화한다.
- `access-key`가 없으면 명확한 안내 메시지와 함께 fail-fast한다.

v2 후보:

- 직무/지역 코드표를 써서 개발 직군 필터를 먼저 건다.
- 현재 기본값인 `job_mid_cd=2` 외에 세분화된 직무/지역 필터를 추가한다.

### 리스크

- 공식 API가 가장 안정적이지만 승인형 access-key가 필요하다.
- HTML listing만으로도 접근은 가능하지만, 점핏과 역할이 겹치고 사람이 운영하는 일반 채용면의 구조 변경 위험이 있다.

## 6. JobKorea

### 관찰

- `https://www.jobkorea.co.kr/robots.txt`는 공개되어 있고, `User-agent: *`에 대해 `/Recruit/GI_Read/`를 차단한다.
- 같은 robots 파일은 `Sitemap: https://www.jobkorea.co.kr/sitemap.xml`를 노출하지만, 현재 조사에서는 sitemap 자체를 안정적인 진입점으로 검증하지 못했다.
- public company recruit 페이지 `https://www.jobkorea.co.kr/company/<company_id>/recruit`는 공개 접근이 가능했고, 진행중 공고 리스트를 보여준다.
- company recruit 페이지의 공고 클릭은 `https://www.jobkorea.co.kr/Recruit/GI_Read/<job_id>?Oem_Code=C1` 상세 URL로 이어진다.
- company recruit 페이지에는 `최근 1년 이내의 공고에 대해서만 상세 내용을 확인 할 수 있습니다.`라는 제한 문구가 보였다.

### URL 패턴

- listing:
  - `https://www.jobkorea.co.kr/company/<company_id>/recruit`
- detail:
  - `https://www.jobkorea.co.kr/Recruit/GI_Read/<job_id>?Oem_Code=C1`

### 권장 구현

v1:

- automated intake 대상에 넣지 않는다.
- 허용 방식:
  - 사용자가 JobKorea detail URL을 직접 pipeline에 넣음
  - 또는 company recruit 페이지를 사람 눈으로 보고 필요한 detail URL만 수동 캡처함
- `JobKorea`는 현재 `manual_intake`로 두는 것이 맞다.

v2 후보:

- robots 정책이 바뀌거나 공식/허용된 feed가 확인될 때만 재검토한다.

### 리스크

- 핵심 detail 경로가 robots에서 차단되어 있어 crawler 구현 근거가 약하다.
- company recruit listing만으로는 JD 전문 추출에 필요한 detail fetch가 해결되지 않는다.

## 7. LinkedIn

### 관찰

- `https://www.linkedin.com/robots.txt`는 자동화 접근이 express permission 없이 금지된다고 명시한다.
- `https://www.linkedin.com/jobs/`와 `https://kr.linkedin.com/jobs/view/...` 형태의 guest job page는 공개 접근이 가능하다.
- 공개 상세 페이지에는 JD 본문, location, employment type 등 정보가 보인다.
- LinkedIn의 공식 Talent Solutions 자료는 external career site/ATS의 공고를 LinkedIn Job Wrapping으로 반영하는 흐름을 설명한다.

### URL 패턴

- listing:
  - `https://www.linkedin.com/jobs/`
  - `https://kr.linkedin.com/jobs/<keyword>-jobs`
- detail:
  - `https://www.linkedin.com/jobs/view/<job_id>`
  - `https://kr.linkedin.com/jobs/view/<slug>-<job_id>`

### 권장 구현

v1:

- crawler 구현 대상에 넣지 않는다.
- `LinkedIn`은 downstream mirror 또는 수동 source로만 다룬다.
- 허용 방식:
  - 사용자가 detail URL을 직접 pipeline에 추가
  - 회사 careers page와 dedup/canonicalization 비교용 참고 source로만 사용

v2 후보:

- 명시적 허용이나 파트너 feed가 없는 한 자동 수집은 도입하지 않는다.

### 리스크

- robots와 이용 약관 수준에서 자동 접근 제한이 강하다.
- LinkedIn 자체가 외부 ATS/career site의 공고를 반영하는 경우가 있어 canonical source로 쓰기 어렵다.

## 8. Indeed

### 현재 판단

- 이 프로젝트에서는 `Indeed`를 자동 intake source가 아니라 `manual intake`로 다루는 것이 맞다.
- 이유는 `robots.txt` 기준으로 generic crawler에 대해 `/viewjob?`와 `/jobs`가 차단되어 있고, public search/listing surfaces를 자동 수집 대상으로 보기 어렵기 때문이다.
- 다만 사용자가 직접 확보한 detail URL은 `jk` 기준 canonicalization과 dedup에 유용하므로, 수동 입력 source로는 유지할 가치가 있다.

### 관찰

- public detail 페이지는 일반적으로 `https://www.indeed.com/viewjob?jk=<job_key>` 패턴을 쓴다.
- 공유 URL에는 `from`, `vjs`, `advn`, `adid` 같은 tracking query가 붙을 수 있지만, canonical key는 `jk`다.
- search/listing 표면은 `/jobs?...`, `q-...`, `cmp/<company>/jobs` 같은 패턴이 흔하다.
- 2026-04-06 기준 `https://www.indeed.com/robots.txt`는 `User-agent: *`에 대해 `/viewjob?`, `/m/viewjob?`, `/jobs`, `/q-`, `/cmp/`를 차단한다.
- Indeed Partner Docs는 direct employer/ATS용 XML feed 또는 Job Sync API를 설명하고 있어, 일반 HTML crawling 대신 partner integration이 정식 경로임을 시사한다.

### URL 패턴

- canonical detail:
  - `https://www.indeed.com/viewjob?jk=<job_key>`
- non-canonical detail variants:
  - `https://www.indeed.com/viewjob?jk=<job_key>&from=serp`
  - `https://www.indeed.com/viewjob?jk=<job_key>&vjs=3`
  - `https://m.indeed.com/viewjob?jk=<job_key>`
- non-detail listing/search:
  - `https://www.indeed.com/jobs?q=<query>&l=<location>`
  - `https://www.indeed.com/q-<keyword>-jobs.html`
  - `https://www.indeed.com/cmp/<company>/jobs`

### 권장 구현

v1:

- crawler 구현 대상에 넣지 않는다.
- 사용자가 detail URL을 직접 pipeline에 넣는 수동 intake만 허용한다.
- `viewjob?jk=<job_key>`만 canonical detail로 인정한다.
- extra query는 제거하고 `jk` 기준으로 dedup한다.
- `fetch-job`는 Indeed search/listing URL을 받으면 실패시켜 detail URL 사용을 강제한다.

v2 후보:

- Indeed partner integration(XML feed 또는 Job Sync API) 자격이 생기면 HTML crawler가 아니라 별도 connector로 붙인다.

### 리스크

- public detail URL을 수동으로 받을 수는 있지만, listing/search surface 자동 수집은 robots 정책과 충돌한다.
- Indeed는 aggregator 성격이 강해서 company careers, ATS, 다른 포털과 중복 유입될 가능성이 크다.
- 현재 dedup은 canonical URL 기준 1차 방어만 한다. cross-source canonicalization까지는 아직 아니다.

## 9. JobPlanet / Blind

### 현재 판단

- `JobPlanet`, `Blind`는 이 프로젝트에서 `company research` 소스로 다루는 것이 맞다.
- 즉, `discover-jobs`로 공고를 수집하는 포털이 아니라, 회사 평판과 인터뷰/조직 신호를 보강하는 리서치 입력원으로 분리한다.

### 관찰

- `https://www.jobplanet.co.kr/companies`는 2026-04-06 기준 공개 접근이 가능했고, 회사 탐색 진입점으로 사용할 수 있었다.
- JobPlanet 공개 리뷰 페이지는 `https://www.jobplanet.co.kr/companies/<id>/reviews/<slug>` 패턴으로 접근 가능했다.
- `https://www.jobplanet.co.kr/robots.txt`는 `/info` 등 일부 경로를 차단하고 있어 crawler보다 수동 조사 source로 다루는 편이 안전하다.
- `https://www.teamblind.com/company/`는 2026-04-06 기준 공개 접근이 가능했고, 회사 페이지 탐색의 시작점으로 사용할 수 있었다.
- Blind 공개 회사 페이지는 `https://www.teamblind.com/company/<slug>` 패턴으로 접근 가능했다.
- Blind help 문서에는 company reviews가 웹 기능으로 명시되어 있었다.

### 권장 구현

v1:

- crawler 구현 대상에 넣지 않는다.
- `career-ops-kr prepare-company-research <company>`로 `research/*.md`를 생성한다.
- exact company URL을 아직 모르면 brief의 `Search Hints` 섹션에서 JobPlanet / Blind 보조 탐색 링크와 homepage/job URL 기반 official URL 후보를 같이 사용한다.
- final exact company URL 확정은 아직 자동화하지 않고, 사람이 후보를 검토해 선택한다.
- 후속 정리나 메시지 초안이 필요하면 `career-ops-kr prepare-company-followup <research-brief> --mode summary|outreach`를 사용한다.
- 알려진 회사 페이지 URL이 있으면 `--jobplanet-url`, `--blind-url`로 연결한다.
- exact company URL을 아직 모르면 browse root만 남기고, 사람이 JobPlanet/Blind UI에서 수동 탐색한다.
- 이 workflow는 pipeline, tracker, discovery와 분리한다.

v2 후보:

- 필요하면 official source와 research source를 구분한 structured metadata를 추가한다.

### 리스크

- 공고 intake 소스와 회사 리서치 소스를 섞으면 command 역할이 불분명해지고, 구현 우선순위가 흐려진다.

## 구현 우선순위

완료:

1. Wanted sitemap 수집기
2. Jumpit sitemap 수집기
3. Remember sitemap 수집기

다음 우선순위:

1. 상세 URL dedup 규칙
2. Indeed supplemental intake policy
3. JobPlanet / Blind research workflow 확장

## 코드 반영 후보

- `src/career_ops_kr/`
  - `portals.py`에 portal discovery 로직 분리
  - `cli.py`에 `discover-jobs` 커맨드 연결
  - `research.py`에 company research brief 생성 로직 분리
- `config/portals.kr.example.yml`
  - source role과 research status 추가
- `docs/workflows.md`
  - intake source와 research source의 역할 분리 반영
- `prompts/company-research.md`
  - 조사 checklist seed prompt 유지

## 검증 방식

최소 검증:

```bash
source .venv/bin/activate
career-ops-kr fetch-job https://recruit.wanted.co.kr/wd/343686 --out jds/_smoke_wanted.md --source wanted-smoke
career-ops-kr fetch-job https://jumpit.saramin.co.kr/position/48685313 --out jds/_smoke_jumpit.md --source jumpit-smoke
career-ops-kr fetch-job https://career.rememberapp.co.kr/job/posting/24786 --out jds/_smoke_remember.md --source remember-smoke
rm -f jds/_smoke_wanted.md jds/_smoke_jumpit.md jds/_smoke_remember.md
```

발견 로직을 추가한 뒤에는:

```bash
source .venv/bin/activate
career-ops-kr discover-jobs wanted --limit 5 --out data/pipeline-smoke.md
career-ops-kr discover-jobs jumpit --limit 5 --out data/pipeline-smoke.md
career-ops-kr discover-jobs remember --limit 5 --out data/pipeline-smoke.md
SARAMIN_ACCESS_KEY=... career-ops-kr discover-jobs saramin --limit 5 --out data/pipeline-smoke.md
rm -f data/pipeline-smoke.md
career-ops-kr verify
python -m compileall src
```

company research workflow 검증:

```bash
source .venv/bin/activate
career-ops-kr prepare-company-research Toss --homepage https://toss.im --careers-url https://toss.im/career/jobs --out research/_smoke_toss.md
rm -f research/_smoke_toss.md
career-ops-kr verify
python -m unittest discover -s tests
```
