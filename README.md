# Page by Page

사진으로 남긴 영어 공부를 **주차 → 수업/시험 → 원본과 필기 → 복습/점검** 순서로 보는 공개 열람 웹 앱입니다.

## 학습 흐름

1. 소유자가 주차를 만들고, 한 주에 수업 자료를 원하는 만큼 추가합니다.
2. 수업 사진의 원본을 보관하고 필기를 가능한 한 그대로 옮겨 적습니다. AI 옮겨 적기는 선택 기능이며 결과를 직접 수정할 수 있습니다.
3. 수업마다 별도 페이지에서 복습 문제를 만들고, 풀이할 때마다 작성 답·맞음·틀림·어려움을 기록합니다. 확인된 취약 문항과 문제 피드백은 다음 생성에 반영합니다.
4. 다음 주에 이전 주 공부의 시험지를 올립니다. 시험지 원본과 작성한 답을 보관합니다.
5. 시험 문항마다 **맞음/틀림/미확인**과 **어려웠음**을 따로 체크합니다. AI의 채점 제안은 최종 결과와 구분됩니다. 체크한 결과로 부족한 부분을 요약할 수 있습니다.
6. 모르는 단어와 문장을 자료에서 단어장에 저장합니다. 원문·뜻·메모·출처를 모아 검색하고, 뜻을 직접 수정하거나 AI로 한국어 번역할 수 있습니다.

수업과 시험에 강사를 지정할 수 있습니다. **설정 → 강사별 수업**에서 강사를 추가하고 문제 스타일을 적으면, 주차 화면에서 강사별로 묶어 보고 강사별 피드백을 구분할 수 있습니다.

로그인하지 않아도 모든 주차·수업·시험·원본 사진·단어장을 볼 수 있습니다. 로그인한 초대 사용자는 댓글을 남길 수 있습니다. 자료 수정, 시험 점검, 단어장 편집, 개인 학습 기록 열람은 소유자만 할 수 있습니다. 자료의 소속 주차는 수정 화면에서 바꿀 수 있습니다.

## 로컬 실행

Python과 [uv](https://docs.astral.sh/uv/)가 필요합니다.

```bash
uv sync
uv run python app.py init-owner
uv run python app.py
```

`http://127.0.0.1:8000`에서 접속합니다. `init-owner`는 첫 실행 때 한 번만 사용합니다. 사진 필사·문제 생성·시험 분석에는 `OPENAI_API_KEY`가 필요합니다. 단어장의 자동 번역은 `DEEPL_API_KEY`가 있으면 DeepL을 우선 사용하고, 없을 때 `OPENAI_API_KEY`가 있으면 OpenAI를 사용합니다. 두 키가 없어도 사진 업로드, 필기 입력, 수동 문제 작성, 수동 시험 점검, 단어장과 뜻 직접 입력은 됩니다. 로컬에서는 프로젝트 폴더의 Git 제외 파일 `.env`에 키를 넣으면 앱이 읽습니다. [현재 DeepL Developer 가입 화면](https://www.deepl.com/en/pro#api)은 무료 번역 100만 자를 **일회성**으로 표시하며 카드·주소 입력과 이메일 인증을 요구합니다. 기존 API Free의 월별 50만 자 안내와 계정별 제공 조건이 다를 수 있으므로 가입 화면의 조건을 확인하세요. OpenAI API 호출에는 별도 요금이 생길 수 있습니다. API 키는 서버 환경 변수, Git 제외 `.env`, 또는 소유자 설정 화면에서 등록하는 비공개 서버 파일에만 두세요.

## 현재 배포

한 수업 안에서도 `did` 2장, `when` 3장처럼 학습지 묶음을 따로 등록할 수 있습니다. 새 수업 작성 화면에서 **묶음 추가**를 눌러 각 묶음의 이름과 사진을 입력하고 한 번에 저장하세요. 한 번에 총 12장까지 올릴 수 있습니다. 저장 전에 묶음별 사진 미리보기를 보며 `순서 올리기/내리기`와 `삭제`를 할 수 있습니다. 수업 화면에서도 사진 한 장 삭제, 묶음 사진 전체 비우기, 새 사진 추가, 순서 변경, 다른 묶음으로 옮기기가 가능합니다. 종이에 적힌 필기는 사진으로 보존하며 묶음별 필기 입력란은 없습니다. 기존 사진은 `미분류`로 남아 필요할 때 옮길 수 있습니다.

사진 업로드 후 **정리본 이어 읽기**에서 쪽별 인쇄 내용·예문·문제·손글씨 필기와 필기 해설을 HTML로 이어 읽습니다. 각 쪽의 **원본 사진 확인**을 펼쳐 판독을 검토하고, 소유자는 **이 쪽 내용·필기 수정**에서 블록을 직접 고칠 수 있습니다. 같은 정리본을 HTML/PDF로 저장할 수 있습니다. 아직 변환하지 않은 쪽은 원본 사진을 표시합니다. 유료 OpenAI API 자동 변환은 현재 꺼져 있어 실제 업로드한 9장은 아직 글과 필기 해설로 변환되지 않았습니다. 촬영 원본은 검수와 재변환을 위해 보존합니다.

Oracle Cloud의 Japan East (Tokyo) 홈 리전에 있는 Always Free 대상 `VM.Standard.E2.1.Micro`에서 실행 중입니다. 휴대폰·아이패드 브라우저에서 [Page by Page](https://161-33-169-174.sslip.io/)에 접속할 수 있습니다. 소유자 아이디는 `oscar2272`이고, 초기 비밀번호는 이 컴퓨터의 `~/.ssh/page-by-page-owner-login` 두 번째 줄에만 보관했습니다. 로그인 후 **계정** 화면에서 비밀번호를 변경하세요. 이 파일과 SSH 개인키 `~/.ssh/page-by-page-oci`를 안전하게 보관하세요.

현재 서버에는 DeepL 번역 키와 소유자가 직접 등록한 OpenAI API 키가 설정되어 있습니다. ChatGPT Plus 요금과 API 키 요금은 별개이므로, 추가 과금을 막기 위해 **OpenAI API 자동 기능은 중지**했습니다. 추가 API 요금 없이 사진을 정리하려면 Plus에 포함된 Codex에서 소유자가 작업을 요청하고 결과를 사이트에 반영할 수 있습니다. 이 방식은 업로드 직후 자동 변환은 아니며 Plus 이용량 제한을 따릅니다. 공식 Sign in with ChatGPT를 통한 Plus 이용량 연결은 별도 OAuth 동의가 필요합니다. 공개 소스 앱의 개인 VM 실행은 공식 문서에 안내되어 있으나, 현재 웹앱에서의 실제 연결은 검증 중입니다. `sslip.io` 주소는 VM의 공인 IP에 연결되므로 공인 IP가 바뀌면 새 주소를 설정해야 합니다.

앱 코드는 [공개 GitHub 저장소](https://github.com/oscar2272/page-by-page-english)에 MIT 라이선스로 공개했습니다. 사진·계정 DB·API 키·백업은 저장소에 포함하지 않습니다. Plus OAuth 연결은 소유자 컴퓨터에서 `uv run python scripts/chatgpt_plan_auth.py login`을 실행해 공식 동의 화면을 여는 시험 단계입니다. `instance/chatgpt-plan.json`에 저장되는 OAuth 자격 정보는 공유하거나 Git에 올리지 마세요. 아직 VM의 자동 AI 기능과 연결되지 않았고, 유료 API 기능은 계속 꺼져 있습니다.

사진별 자동 정리 기능은 비용을 줄이기 위해 GPT-4.1 mini와 최대 출력 8,000토큰으로 준비해 두었습니다. 매주 약 10장의 사용량을 고려해 한 번의 변환 비용을 낮추되, 실제 필기 인식 품질은 시험 전입니다. API 사용 설정은 계속 꺼져 있으며, 소유자의 동의 없이는 유료 요청을 보내지 않습니다.

서버 코드는 `/home/ubuntu/page-by-page`, SQLite DB와 사진은 Docker의 `page-by-page_study_data` 볼륨에 있습니다. Caddy가 HTTPS 인증서를 자동 관리합니다. 1GB 메모리 VM에 맞춰 Gunicorn 작업자는 1개입니다. 재시작 뒤에도 소유자 로그인이 유지되는 것을 확인했습니다.

서버 밖 백업은 이 컴퓨터에서 `bash scripts/backup_remote.sh`로 만듭니다. SQLite의 일관된 스냅샷과 사진·앱 비밀키·등록한 OpenAI API 키가 Git 제외 폴더 `backups/`에 권한 600으로 저장됩니다. 초기 백업을 만들고 DB 무결성 검사를 마쳤습니다. 자료를 올리기 시작하면 이 명령을 정기적으로 실행하고 파일을 안전하게 보관하세요.

## 무료 서버 배포 방법

`Dockerfile`, `compose.yaml`, `Caddyfile`은 영구 저장 볼륨과 HTTPS를 포함합니다. [Oracle Cloud Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) VM에서 재배포할 수 있습니다. 도메인 구매 없이 [sslip.io](https://sslip.io/)의 IP 기반 무료 DNS 이름을 사용할 수 있습니다. 무료 VM은 지역에 따라 용량이 없을 수 있습니다. Always Free 범위를 넘는 리소스를 만들지 않도록 계정의 표시를 확인하세요.

서버에서 Docker Compose를 설치하고 저장소를 복사한 뒤, DNS A 레코드가 서버 IP를 가리키게 합니다. 서버 방화벽에서 80/443 포트를 열고 프로젝트 폴더에 `.env`를 작성합니다.

```dotenv
DOMAIN=study.example.com
OPENAI_API_KEY=
DEEPL_API_KEY=
```

```bash
docker compose build
docker compose run --rm app uv run python app.py init-owner
docker compose up -d
```

`DOMAIN`은 실제 DNS 이름으로 바꿔야 합니다. Caddy가 해당 이름의 HTTPS 인증서를 발급합니다. `study_data` 볼륨에 SQLite DB, 사진, 앱 비밀키와 직접 등록한 OpenAI API 키가 저장되므로 서버를 다시 시작해도 남습니다. 운영 중에는 볼륨을 정기적으로 백업하세요. 사진 원본도 로그인 없이 다운로드할 수 있습니다. 소유자의 풀이 기록과 설정은 로그인 보호를 받습니다.

HTML 저장 파일에는 사진 미리보기가 포함됩니다. PDF는 자료 화면의 **PDF 인쇄**를 눌러 브라우저에서 저장합니다. 보안상 내보낸 파일은 로그인 보호 바깥에 있으므로 공유 범위를 직접 관리해야 합니다.

테스트: `uv run python -m unittest discover -s tests -v`

요구사항은 [docs/requirements.md](docs/requirements.md), 프로젝트 전용 Codex 스킬은 `~/.codex/skills/english-study-organizer/SKILL.md`에 있습니다.
