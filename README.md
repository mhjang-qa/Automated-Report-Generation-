# Automated Report Generation

노션 티켓 링크를 입력하면 티켓 내용을 읽고 Gemini로 작업 내용을 요약한 뒤, 지정된 노션 DB에 저장합니다. 저장된 요약을 기반으로 테스트 케이스 Markdown Table을 생성하고 같은 노션 페이지 하단에 업로드할 수 있습니다.

## 실행 방법

```bash
python3 app.py
```

브라우저에서 `http://127.0.0.1:8000`으로 접속합니다.

포트를 바꾸려면 다음처럼 실행합니다.

```bash
PORT=8010 python3 app.py
```

## 환경변수

`.env` 파일 또는 셸 환경변수로 설정합니다.

```bash
NOTION_TOKEN=secret_xxx
GEMINI_API_KEY=your_gemini_api_key
GEMINI_API_KEY_2=your_fallback_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash-lite
GEMINI_FALLBACK_MODELS=gemini-2.5-flash,gemini-3.1-flash-lite
NOTION_TARGET_DB_URL=https://app.notion.com/p/39673fbd1951801baa4dea29b16a155a?v=39673fbd19518011b206000c9f5cdcfb
NOTION_TARGET_DATABASE_ID=39673fbd-1951-801b-aa4d-ea29b16a155a
APP_LOGIN_PASSWORD=optional_password
FIGMA_ACCESS_TOKEN=figma_personal_access_token
FIGMA_IMAGE_MAX_BYTES=8388608
SUMMARY_CONTENT_LIMIT=12000
TC_SOURCE_LIMIT=6000
NOTION_IMAGE_LIMIT=4
NOTION_IMAGE_MAX_BYTES=4194304
GEMINI_429_COOLDOWN_SECONDS=60
PUBLIC_LANDING_URL=https://mhjang-qa.github.io/Automated-Report-Generation-/
ENABLE_PUBLIC_LANDING_REDIRECT=true
```

필수:

- `NOTION_TOKEN`: Notion Integration 토큰
- `GEMINI_API_KEY`: Gemini API Key

선택:

- `GEMINI_API_KEY_2`: `GEMINI_API_KEY`가 사용 제한을 반환할 때 재시도할 보조 Gemini API Key
- `GEMINI_MODEL`: 기본값 `gemini-2.5-flash-lite`
- `GEMINI_FALLBACK_MODELS`: 기본 모델이 429, 400, 503, 네트워크 오류를 반환할 때 순차 시도할 대체 모델 목록, 기본값 `gemini-2.5-flash,gemini-3.1-flash-lite`
- `NOTION_TARGET_DB_URL`: 요약 페이지를 생성할 대상 DB URL
- `NOTION_TARGET_DATABASE_ID`: DB ID를 직접 지정할 때 사용하며, 이 값이 있으면 `NOTION_TARGET_DB_URL`보다 우선합니다. DB URL의 `v=` 값은 view ID이므로 이 값으로 지정하지 않습니다.
- `APP_LOGIN_PASSWORD`: 설정하면 로그인 화면에서 해당 비밀번호를 입력해야 합니다. 미설정 시 로그인 버튼으로 바로 진입합니다.
- `FIGMA_ACCESS_TOKEN`: PixelAudit 탭에서 Figma Frame PNG를 생성할 때 사용합니다. 프론트엔드에는 노출하지 않습니다.
- `FIGMA_IMAGE_MAX_BYTES`: Figma PNG 다운로드 최대 바이트, 기본값 `8388608`
- `SUMMARY_CONTENT_LIMIT`: 요약 생성 시 Gemini에 전달할 노션 본문 최대 문자 수, 기본값 `12000`
- `TC_SOURCE_LIMIT`: TC 생성 시 원문 참고로 전달할 최대 문자 수, 기본값 `6000`
- `NOTION_IMAGE_LIMIT`: 요약 생성 시 Gemini에 함께 전달할 노션 이미지 최대 개수, 기본값 `4`
- `NOTION_IMAGE_MAX_BYTES`: 이미지 1개당 다운로드/전달 최대 바이트, 기본값 `4194304`
- `GEMINI_429_COOLDOWN_SECONDS`: Gemini 429 응답에 재시도 시간이 없을 때 분석 기능을 일시 중지할 기본 초 수, 기본값 `60`
- `PUBLIC_LANDING_URL`: Render 루트 접근 시 이동할 GitHub Pages 인트로 URL, 기본값 `https://mhjang-qa.github.io/Automated-Report-Generation-/`
- `ENABLE_PUBLIC_LANDING_REDIRECT`: Render 루트 접근을 GitHub Pages 인트로로 보낼지 여부, 기본값 `true`
- `PORT`: 웹 서버 포트, 기본값 `8000`

## Notion 설정

1. Notion Integration을 생성하고 `NOTION_TOKEN`에 토큰을 설정합니다.
2. 원본 티켓 페이지와 대상 DB를 해당 Integration에 공유합니다.
3. 대상 DB URL은 기본 요구사항의 DB URL을 사용합니다. 다른 DB를 쓰려면 `NOTION_TARGET_DB_URL` 또는 `NOTION_TARGET_DATABASE_ID`를 설정합니다.
4. DB가 비어 있어도 괜찮습니다. 앱이 신규 row를 만들고 필요한 속성(`원본 노션 링크`, `요약 상태`, `생성 일시`, `TC 생성 여부`)을 자동 추가합니다.

기본 대상 DB URL의 실제 DB ID는 path에 포함된 `39673fbd-1951-801b-aa4d-ea29b16a155a`입니다. URL 쿼리의 `v=39673fbd19518011b206000c9f5cdcfb`는 데이터베이스 view ID라서 Notion `/databases/{id}` 조회에 사용할 수 없습니다.

대상 DB에 아래 속성이 없으면 서버가 자동으로 추가합니다.

- `원본 노션 링크`: URL
- `요약 상태`: Select
- `생성 일시`: Date
- `TC 생성 여부`: Checkbox

DB의 제목 속성은 Notion DB에 기본으로 존재하는 Title 속성을 자동 탐색해 사용합니다.

## 사용 순서

1. GitHub Pages 인트로(`https://mhjang-qa.github.io/Automated-Report-Generation-/`)로 접속합니다.
2. 인트로가 `logding/index.html` 애니메이션을 9.2초 단위로 반복하면서 Render `/api/health`를 확인합니다.
3. 서버 준비가 끝나면 Render 앱으로 이동하고 로그인 화면을 바로 표시합니다.
4. 로그인 화면에서 진입합니다.
5. 웹 화면에 노션 티켓 링크를 입력합니다.
6. `분석 요약`을 눌러 티켓 본문과 이미지 블록 조회, Gemini 요약 생성을 실행합니다.
7. 결과를 확인한 뒤 `노션 등록`을 눌러 대상 DB에 신규 페이지를 생성합니다.
8. `TC 생성하기`를 눌러 Markdown Table 형식의 테스트 케이스를 생성합니다.
9. `TC 업로드`를 눌러 생성된 TC를 저장된 노션 페이지의 요약 콜아웃 하단에 `테스트 케이스 - 초안` 표로 추가합니다.

## PixelAudit

상단 `PixelAudit` 탭에서 Figma 디자인과 실제 웹 화면을 같은 viewport에 배치해 비교할 수 있습니다.

1. Figma 링크를 입력합니다. `https://www.figma.com/design/{fileKey}/{name}?node-id=7006-6818` 형식을 지원하며, `node-id`는 Figma API 호출용 `7006:6818` 형식으로 자동 변환합니다.
2. 실제 웹 URL을 입력합니다.
3. viewport 프리셋 또는 직접 width/height를 지정합니다.
4. `비교 시작`을 누르면 서버가 Figma API로 Frame PNG를 생성하고, 실제 URL iframe 위에 오버레이합니다.
5. Opacity, X/Y offset, Scale 값을 조절해 UI 차이를 검수합니다.

현재 통합 버전은 기존 프로젝트 정책에 맞춰 Python 표준 라이브러리만 사용합니다. 따라서 서버 측 Playwright 캡처와 픽셀 단위 Difference 계산은 포함하지 않았고, iframe 차단 정책이 있는 사이트는 `URL 새 탭`으로 열어 별도 확인해야 합니다. Playwright 기반 캡처/이미지 diff가 필요하면 Render 빌드에 `playwright` 브라우저 설치 단계를 추가하는 별도 Phase로 확장합니다.

## GitHub Pages 인트로

`docs/` 폴더는 Render cold start를 가리는 정적 인트로 페이지입니다. `.github/workflows/static.yml` workflow가 `docs/` 폴더를 GitHub Pages로 배포합니다.

```text
https://mhjang-qa.github.io/Automated-Report-Generation-/
```

Render URL(`/`)로 직접 접근하면 기본적으로 이 GitHub Pages 인트로로 이동합니다. 인트로는 `docs/logding/index.html`을 iframe으로 표시하고 9.2초마다 다시 로드해 애니메이션을 반복합니다. 동시에 `https://automated-report-generation-dh2g.onrender.com/api/health`를 2.5초 간격으로 확인하고, 준비 완료 후 `https://automated-report-generation-dh2g.onrender.com/?app=1&skipIntro=1`로 이동해 로그인 화면을 바로 표시합니다.

Pages URL이 404라면 GitHub Pages 배포가 실패했거나, 배포 루트에 `index.html`이 없는 상태입니다. 저장소 `Settings > Pages`에서 Source를 `GitHub Actions`로 설정한 뒤 `Deploy static content to Pages` workflow를 실행합니다. 대안으로 Source를 `Deploy from a branch`로 설정하고 Branch를 `main`, Folder를 `/docs`로 지정해도 됩니다.

GitHub가 자동 생성한 `Deploy static content to Pages` workflow를 쓰는 경우에도 artifact path는 반드시 `docs`여야 합니다. 루트 배포 설정으로 전환되어도 동작하도록 저장소 루트의 `index.html`과 `404.html`은 `/docs/` 인트로로 리다이렉트합니다.

## 오류 처리

화면에는 사용자용 메시지를 표시하고, 상세 오류는 서버 콘솔에 기록합니다.

- 노션 링크 미입력 또는 형식 오류
- 노션 페이지 접근 실패 또는 본문 없음
- `NOTION_TOKEN`, `GEMINI_API_KEY` 누락
- Gemini API 오류, 429 사용 제한, 응답 형식 오류
- 대상 노션 DB 저장 실패
- TC 생성 또는 업로드 실패

## 구현 메모

- 외부 패키지 설치 없이 Python 표준 라이브러리만 사용합니다.
- 로딩 애니메이션은 `logding/` 폴더의 Three.js/Anime.js 기반 화면을 `/logding/` 경로로 노출해 사용합니다.
- Notion API는 `2022-06-28` 버전으로 호출합니다.
- 노션 이미지 블록은 본문에 `[이미지 n]`으로 표시하고, 제한 개수/용량 안에서 Gemini 멀티모달 입력으로 함께 전달합니다.
- TC는 Markdown Table 결과를 Notion 표 블록으로 변환해 업로드합니다.
- Gemini 호출은 `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `GEMINI_API_KEY`, `GEMINI_API_KEY_2` 조합을 순차 시도합니다.
- 모든 모델/키 조합에서 Gemini 429가 발생하면 `RetryInfo` 또는 `Retry-After` 기준으로 분석 기능을 일시 중지하고, 이 시간 동안 추가 Gemini 호출을 차단합니다.
- 민감정보는 코드에 하드코딩하지 않고 환경변수에서만 읽습니다.
