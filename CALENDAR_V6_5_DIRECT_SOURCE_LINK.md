# findol v6.5 — 국민참여입법센터 개별 원문 직링크

## 변경사항
- 국민참여입법센터에서 수집한 행정예고/입법예고의 `official_url`을 사이트 메인 주소가 아니라 해당 게시글 상세 페이지로 저장합니다.
- 행정예고: `https://opinion.lawmaking.go.kr/gcom/admpp/{일련번호}?announceType=...&mappingAdmRulSeq=...`
- 입법예고: `https://opinion.lawmaking.go.kr/gcom/ogLmPp/{일련번호}`
- 정보공개 API 인증값 `OC`는 사용자용 링크에 포함하지 않습니다.

## 기존 DB 자료 갱신
배포 후 관리자에서 `국민참여입법센터 동기화 → 새 정보 가져오기`를 다시 실행하세요. 기존 source_key는 유지하면서 URL 변경이 새 버전으로 반영되고, 아카이브 화면에서는 최신 버전이 사용됩니다.

## 적용 파일
- `backend/app/lawmaking_api.py`
