# 기존 findol 사이트에 v3 적용하는 순서

## 전체 흐름

```text
기존 프로젝트 백업
→ v3 파일 덮어쓰기
→ 기존 .env 복원
→ 로컬 테스트
→ GitHub push
→ Render 자동 재배포
```

## 1. 기존 폴더 백업

현재 GitHub와 연결된 프로젝트 폴더를 통째로 복사합니다.

```text
findol-law-portal
→ findol-law-portal-backup
```

## 2. `.env` 보관

기존 파일을 별도로 복사합니다.

```text
backend/.env
```

이 ZIP에는 비밀값이 들어 있는 `.env`가 포함되지 않습니다.

## 3. v3 파일 덮어쓰기

ZIP을 압축 해제합니다. 안쪽 `law-portal` 폴더의 내용물을 기존 프로젝트 최상위 폴더에 복사합니다.

정상 구조:

```text
findol-law-portal/
├─ backend/
├─ frontend/
├─ README.md
├─ UPDATE_GUIDE.md
└─ SEARCH_MAP_GUIDE.md
```

잘못된 구조:

```text
findol-law-portal/
└─ law-portal/
   ├─ backend/
   └─ frontend/
```

## 4. `.env` 복원

보관한 `.env`를 다시 넣습니다.

```text
findol-law-portal/backend/.env
```

필요한 값:

```env
LAW_API_OC=기존_법제처_OC
ARCHIVE_ADMIN_TOKEN=본인만_아는_긴_문자열
```

## 5. 패키지 설치

프로젝트 최상위 폴더에서 PowerShell:

```powershell
py -m pip install -r backend\requirements.txt
```

## 6. 검색엔진 테스트

```powershell
cd backend
py -m unittest discover -s tests -v
```

`OK`가 나오면 검색어 사전과 법령지도 기본 연결이 정상입니다.

## 7. 로컬 실행

현재 PowerShell 위치가 `backend`일 때:

```powershell
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저:

```text
http://127.0.0.1:8000
```

확인 검색어:

```text
저장시설
보관시설
희석탱크 설치검사
탱크
탱크로리
```

확인할 화면:

- 검색 목적
- 먼저 확인할 사항
- 핵심 적용 규정
- 상위 법령
- 함께 확인할 규정
- API 추가 검색 결과
- 모호어 선택지
- 개정 아카이브
- 개정 캘린더

테스트 종료:

```text
Ctrl + C
```

## 8. GitHub에 반영

프로젝트 최상위 폴더로 이동합니다.

```powershell
cd ..
git add .
git commit -m "Add v3 law map search"
git push
```

## 9. Render 확인

GitHub push 뒤 Render가 자동으로 다시 배포합니다.

```text
Building
→ Deploying
→ Live
```

자동으로 시작되지 않으면:

```text
Manual Deploy
→ Deploy latest commit
```

기존 설정 유지:

```text
Root Directory
비워두기

Build Command
pip install -r backend/requirements.txt

Start Command
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

## 10. 운영 중 검색어 추가

검색어만 추가할 때:

```text
backend/app/data/search_dictionary.csv
```

새 시설·업무 주제 또는 핵심 고시 연결을 추가할 때:

```text
backend/app/data/law_map.json
```

수정 방법은 `SEARCH_MAP_GUIDE.md`를 확인합니다.

## 11. 데이터 보존 주의

개정 아카이브를 오래 쌓으려면 Render 로컬 SQLite가 아니라 외부 PostgreSQL을 연결해야 합니다.

```text
DATABASE_URL=Supabase 또는 PostgreSQL 연결 문자열
```
