# Notion 통합 결함 검색 구현 보고서

## 적용 위치와 기존 구조 분석

기존 `Automated Report Generation`의 소스를 끝에 공백이 있는 현재 작업 폴더 `Automated Report Generation `로 복사해 구현했습니다. 원본 소스는 수정하지 않았습니다. Git 메타데이터, 서브모듈, 생성된 의존성/캐시는 복사하지 않았습니다. 기존 `.env`는 현재 폴더에 권한 600으로 복사했으며 토큰은 서버에서만 읽습니다.

- Backend: Python 표준 라이브러리 `ThreadingHTTPServer` / `AppHandler`. Flask/FastAPI 및 별도 패키지 설치가 필요하지 않습니다.
- Frontend: `static/index.html`, `static/app.js`, `static/styles.css`. 기존 버튼/탭/패널 스타일을 유지했습니다.
- 기존 메뉴: 티켓 분석, 임베드 HTML 생성, PixelAudit, 다국어 검증, 결함 대시보드. 새 `결함 검색` 탭만 추가했습니다.
- 기존 API: `/api/analyze`, `/api/register-summary`, `/api/generate-tc`, `/api/upload-tc`, `/api/embed-html`, `/api/embed-jobs`, `/api/embed-target-versions`, PixelAudit/Figma 관련 API, health/login 등. 기존 기능의 처리 로직은 유지했습니다.
- Notion: `app.py`의 티켓 수집/댓글 지원과 `notion_html_gui_generator.py`의 DB 조회, 데이터 소스 fallback, 페이지네이션, 속성 및 ATM 관계형 제목 변환이 존재했습니다. 결함 수집은 후자의 API 유틸리티를 재사용합니다.
- 기존 캐시: 작업 상태/렌더링/관계형 제목의 메모리 캐시. 기존 결함 검색 API나 영속 검색 DB는 없었습니다.
- 기존 `docs/`는 정적 배포 자산입니다. 신규 검색은 Python 서버의 `static/` UI/API에서 실행됩니다. GitHub Pages만으로 Notion API 검색을 실행하지 않습니다.

## 실제 Notion 데이터 확인

2026-10-16에 원격 데이터를 변경하지 않는 방식으로 DB 스키마와 전체 페이지 목록을 조회했습니다. **1,972건**을 확인했습니다. 결과는 `defect-search-notion-schema.json`에 기록했습니다. Notion 토큰과 결함 제목/본문은 검증 보고서에 기록하지 않았습니다.

| 검색 필드 | 실제 속성/소스 |
|---|---|
| 제목 | `결함 제목` (title) |
| 심각도 | `심각도` (select) |
| 우선순위 | `우선순위` (status) |
| 상태 | `상태` (status) |
| 목표버전 | `목표버전` (select) |
| 화면/기능 | `ATM` (relation): 기존 관계형 제목 해석 재사용 |
| 담당자 | `조치 담당자` (people): 사용자 이름만 표시 |
| 등록일 | `생성 일시` / `생성일시`, 없으면 Notion created_time |
| 수정일 | Notion last_edited_time |
| OS | 별도 속성 없음. 제목의 명시적 AOS/iOS/공통 표기 또는 본문 환경정보에서 추출. 추측하지 않음 |
| 재현절차 | 본문 표의 `재현 단계 (Steps to Reproduce)` |
| 실제 결과 | 본문 표의 `실제 결과 (Actual Result)` |
| 예상 결과 | 본문 표의 `기대 결과 (Expected Result)` |
| 환경 | 본문 표의 `환경정보 (Environment)` |

헤딩 기반 형식도 지원합니다. 본문 표 항목명도 인식하고 Appendix/부록/작성 가이드/심각도 기준 이하의 템플릿 안내문은 검색에서 제외합니다. 실제 템플릿의 공통 심각도 예시에 들어 있는 로그인/결제 오류가 모든 결함에 검색되는 문제를 방지합니다. 없는 속성은 결과 화면에서 숨깁니다.

## 변경 파일

- `app.py`: 새 검색 GET API와 색인 갱신 POST API 연결, 선택적 로그인 세션 쿠키 발급/검증, 신규 검색어 접근 로그에서 쿼리 제거. 기존 JSON 응답 함수에 선택적 헤더 인자 추가.
- `static/index.html`: 기존 메뉴 뒤 결함 검색 탭과 별도 탭 화면 추가.
- `static/app.js`: 검색 탭 활성화와 기존 탭으로 복귀하는 연결만 추가.
- `static/styles.css`: 검색 화면에 한정된 스타일 추가.
- `.gitignore`: `data/`의 로컬 Notion 색인을 버전 관리에서 제외.
- `README.md`: 검색 실행 방법 및 보고서 링크 추가.

## 신규 파일

- `config/search_synonyms.json`: QA가 편집할 수 있는 동의어/표현 그룹.
- `search/models.py`: 결함 모델과 필드 가중치.
- `search/query_normalizer.py`, `synonym_manager.py`, `keyword_extractor.py`: 유니코드/대소문자/공백/문장 정규화 및 핵심어 추출.
- `search/notion_indexer.py`: 읽기 전용 수집, 표/재귀 블록/페이지네이션/선택적 댓글 수집, 증분 본문 조회.
- `search/local_index.py`: SQLite 문서 저장 및 한글 공백에 강한 문자 bigram 역색인.
- `search/fuzzy_matcher.py`, `semantic_matcher.py`, `ranking.py`: 오타 유사도, 동의어 정규화 문자 TF-IDF cosine, 필드별 랭킹.
- `search/search_service.py`: 색인 작업 상태/TTL/후보 검색/정렬/필터/중복 경고/페이징.
- `static/defect-search.js`: 검색 상태, 하이라이트, 메타데이터, 검색 근거, 필터, 더 보기, 최근 검색.
- `static/notion-open.html`, `static/notion-open.js`: 앱 연결 및 웹 fallback 중간 페이지.
- `tests/test_defect_search.py`, `tests/test_defect_search_http.py`, `tests/test_notion_landing.cjs`: 단위/HTTP/링크 fallback 검증.
- `.env.example`: 기존 토큰 및 신규 설정 안내.
- 이 문서와 스키마/실데이터 smoke 결과 JSON 및 `defect-search-preview.png`: 분석과 검증 자료.

## 검색 구조

```text
Notion DB / Data Source
  → 기존 페이지네이션/API/ATM 변환 재사용
  → 속성 우선 색인 → 본문/표/선택적 댓글 수집
  → SQLite documents + 문자 bigram 역색인
  → 질의 정규화 + QA 동의어 + 핵심어
  → 제목 exact/부분일치 우선 + bigram 후보 최대 500건
  → 필드별 핵심어 + difflib fuzzy + TF-IDF cosine + OS 랭킹
  → 관련도 정렬 + ID 중복 제거 + 별도 페이지 간 유사 제목 경고
  → 필터 → 기본 20건 + 더 보기
```

검색 요청은 로컬 SQLite만 조회합니다. 최초 검색/갱신 버튼/TTL 만료는 백그라운드 수집을 시작합니다. 최초에는 제목/속성 색인을 먼저 검색할 수 있고 본문 수집 상태를 표시합니다. 기존 완성 색인이 있으면 갱신이 끝날 때까지 그대로 사용하고 트랜잭션으로 교체합니다. 오류 시 마지막 스냅샷을 보존합니다. 최초 속성 전용 스냅샷 상태에서 재시작되면 본문 수집을 재개합니다.

완성 색인 갱신 시 last_edited_time이 같은 페이지의 본문은 재조회하지 않습니다. 삭제/보관 페이지는 다음 전체 목록 갱신에서 제거합니다. 댓글을 켠 경우 댓글 변경 반영을 위해 본문/댓글을 재수집합니다. DB, 토큰 해시, 동의어 설정 및 댓글 모드별로 캐시 파일을 구분합니다. 토큰 원문은 캐시 키/DB에 저장하지 않습니다. 실행 프로세스 내 동시 색인 요청은 하나로 합칩니다.

SQLite bigram 역색인은 FTS5 기본 토크나이저의 한글 띄어쓰기 제약을 피하기 위해 선택했습니다. 외부 Vector DB나 모델 API를 호출하지 않으며 추가 라이브러리/LLM 비용이 없습니다.

## 일치율 계산

일반 점수:

`40 × 핵심어 포함 비율 + 20 × 필드 가중 포함률 + 15 × fuzzy 평균 + 20 × TF-IDF cosine + 5 × OS 일치`

- 필드 가중치: 제목 1.0, 화면/기능 0.9, 실제 결과 0.9, 재현절차 0.7, 예상 결과 0.5, 본문 0.45, 댓글 0.25.
- 같은 핵심어가 여러 필드에 있으면 가장 높은 필드 가중치를 사용합니다.
- exact 제목은 100점. 제목 부분 문자열 일치는 `85 + 10 × 핵심어 포함률 + 5 × cosine`을 최소 점수로 사용합니다.
- fuzzy는 포함일 때 1, 아니면 제목/화면/실제 결과에서 문자 창별 SequenceMatcher 유사도 중 최대값을 사용합니다. 0.66 미만은 0으로 처리합니다.
- 명시적으로 다른 OS이면 일반 점수에 0.8을 곱합니다. OS 속성이 없고 제목/환경에도 명시되지 않은 경우 OS를 만들어 표시하지 않습니다.
- 최종 0~100 범위, 소수점 한 자리. 매우 높은 일치 ≥90, 높은 일치 ≥80, 관련 결함 ≥65, 나머지는 참고 가능입니다.
- **점수는 관련도 지표이며 정답 확률이나 통계적 신뢰도가 아닙니다.** 예시 숫자를 임의로 고정하지 않습니다.
- 동의어로 일치한 근거는 `유사 표현 일치`로 표시합니다. 별도 페이지의 제목 유사도가 0.90 이상일 때만 유사 결함 경고를 표시합니다. 자동 병합/삭제하지 않습니다.

## API 및 디버그

- `GET /api/defects/search?q=...&offset=0&limit=20`
- 필터: `platform`, `severity`, `status`, `target_version`, `date_from`, `date_to`.
- `GET /api/defects/status`: 색인 상태/건수/진행/경고/속성 매핑.
- `POST /api/defects/refresh` + JSON `{}`: 백그라운드 수집 시작. 처리 중이면 기존 작업 재사용.
- `DEFECT_SEARCH_DEBUG=true`와 `debug=1`을 함께 설정해야 정규화 질의, 핵심어, 동의어, 후보 수, 단계 점수, 가중치, 최종 점수, 검색 시간을 반환합니다. 운영 UI에는 내부 점수를 기본 노출하지 않습니다.
- `APP_LOGIN_PASSWORD` 설정 시 기존 로그인 성공으로 발급되는 HttpOnly/SameSite 쿠키로 신규 검색 API를 보호합니다. 세션은 12시간이며 서버 재시작 시 다시 로그인합니다. 기존 API의 인증 구조는 변경하지 않았습니다.
- 최근 검색은 브라우저 Local Storage에 최대 8개만 저장하며 기록 삭제를 제공합니다. 신규 검색 API 접근 로그에서는 검색어를 제외합니다.

## Notion App / Web 이동

클릭 시 `/notion-open.html?id=<검증된 UUID>`를 사용자 클릭으로 새 탭에 엽니다. 이 페이지에서 `notion://www.notion.so/<id>` 실행을 시도하고, 1.8초 후 페이지가 여전히 보이면 실제 `https://www.notion.so/<id>`로 이동합니다. 앱으로 전환되어 페이지가 숨겨지면 타이머를 중단합니다. 사용자가 직접 선택할 앱 재시도/웹 링크를 항상 제공합니다. 웹 링크를 결과 카드에도 별도로 제공합니다.

브라우저에서 설치 여부/앱 실행 성공을 정확히 판별할 수 없으므로 성공을 단정하지 않습니다. 타임아웃 중 사용자가 다른 탭으로 이동한 경우에도 fallback이 중지될 수 있으며, 중간 페이지의 명시적 웹 링크로 이동할 수 있습니다. macOS/Windows의 실제 외부 앱 실행은 OS, 브라우저 허용, Notion 로그인/링크 설정에 의존합니다. 양쪽 OS의 실물 앱 실행 검증은 수행하지 않았습니다.

공식 참고: [Notion 데스크톱과 링크 설정](https://www.notion.com/help/notion-for-desktop), [Notion 링크](https://www.notion.com/help/create-links-and-backlinks), [데이터 소스 API 업그레이드 안내](https://developers.notion.com/guides/get-started/upgrade-guide-2025-09-03). 특히 Windows MSIX는 OS의 Apps for websites 설정에 의해 HTTPS 링크가 앱으로 연결될 수 있습니다. URI 타이머는 앱 설치 감지가 아니라 최선의 실행 시도입니다.

## 실행 방법

현재 작업 폴더에서:

```bash
python3 app.py
```

`http://127.0.0.1:8000`에서 기존 로그인 후 상단 **결함 검색**을 선택합니다. 복사한 `.env`의 기존 NOTION_TOKEN을 사용합니다. 결함 검색 자체에는 Gemini 키가 필요하지 않습니다. 기존 AI 요약/TC 생성은 기존 요구대로 Gemini 설정이 필요합니다.

처음에는 검색어 입력 또는 `Notion 색인 갱신`을 선택합니다. 본문 전체 수집은 Notion 호출량 때문에 시간이 걸립니다. 초기 제목/속성 검색 중이라는 상태를 확인할 수 있습니다. 완료된 색인이 있으면 이후 검색은 Notion 호출 없이 수행하며, 기본 1시간 간격으로 백그라운드 갱신합니다. `data/`는 정적 서버 경로 밖에 있으며 재시작 후에도 보존됩니다. 배포 시 이 경로를 영속 디스크에 두어야 합니다.

선택 설정:

```dotenv
NOTION_DEFECT_DATABASE_URL=https://app.notion.com/p/21473fbd1951800d8321fc2e34c2548e
DEFECT_SEARCH_TTL_SECONDS=3600
DEFECT_SEARCH_COMMENTS=false
DEFECT_SEARCH_DEBUG=false
```

댓글 검색은 `DEFECT_SEARCH_COMMENTS=true` 및 Integration의 comment read 권한이 필요합니다. API가 허용하는 페이지/블록 댓글만 읽고, 접근 실패는 경고로 표시합니다. 동의어 JSON 수정 후 서버를 재시작하면 새 설정의 별도 색인을 만듭니다.

## 검증 및 한계

- Python 단위 테스트와 HTTP 통합 테스트: **45개 전체 통과**, 기존 회귀 15개 포함. Notion 링크 fallback **6개 시나리오 통과**, JavaScript 문법 검사 통과.
- 요구된 QA 자연어 5개와 최종 AOS 비밀번호 문장의 fixture 기대 문서 1위 검증. exact/부분/화면/기능/현상/OS/오타/띄어쓰기/혼합 언어/동의어/존재하지 않는 질의/특수문자/500자 초과 검증.
- 필터/페이징/중복/실패 복구/동시 작업 합치기/옵션 디버그/실제 표 템플릿과 Appendix 제외 검증.
- 브라우저에서 검색 결과, 근거 펼치기, OS 필터, 결과 없음, 티켓 분석/임베드 메뉴 복귀 확인. 화면 스크린샷은 fixture 데이터입니다.
- Notion 앱 URI 생성/웹 fallback/숨김 시 타이머 취소/잘못된 UUID 차단 등 Node 가상 환경 6개 시나리오 검증. 실물 앱 실행 확인과 구분합니다.
- 2,000건의 짧은 fixture 문서에서 로컬 색인 생성 약 0.23초, 네 가지 검색 약 44~152ms 관측. 실제 긴 본문 성능 보장은 아니며 원격 Notion 수집 시간은 제외했습니다.
- 후보 상한은 500건입니다. 결과 total은 전체 Notion DB의 확정 총 일치 건수가 아니라 이 후보 중 관련성이 있는 필터 적용 결과 수입니다. 상한 도달 시 UI에서 검색어를 구체화하도록 안내합니다.
- TF-IDF는 동의어 정규화 문자 유사도입니다. 임의 문장의 깊은 의미를 이해하는 embedding/LLM 검색은 도입하지 않았습니다. 새 QA 표현은 사전에 추가하고 실제 정답 라벨로 평가/튜닝해야 합니다.
- OS는 실제 문서에서 확인되는 경우에만 표시합니다. 서로 다른 OS에서도 현상이 비슷한 문서는 점수를 낮춰 참고 결과에 남을 수 있으며 OS 필터로 좁힐 수 있습니다.
- 실제 DB에서 검색 패턴별 최대 2건씩 총 **10건**을 수집한 smoke test: 제목 완전 일치 **10/10건 100점**, 요청 자연어 문장 5개 모두 표본 내 후보 반환. 표본 검색 약 11~18ms 관측. 이는 정답 라벨을 사용한 정확도 평가가 아닙니다. 상세 결과는 `defect-search-live-smoke.json`에 있습니다.
- 전체 1,972건의 본문 색인은 검증 중 자동 생성하지 않았습니다. 실제 전체 수집은 앱에서 시작합니다. 실데이터 검증은 읽기 전용 일부 표본의 통합 smoke test이며 전체 precision/recall을 보장하지 않습니다.

검증 명령:

```bash
python3 -m unittest discover -v
node tests/test_notion_landing.cjs
node --check static/app.js
node --check static/defect-search.js
node --check static/notion-open.js
```
