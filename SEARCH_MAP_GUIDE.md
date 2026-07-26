# 검색어 사전과 법령지도 수정 안내

findol v3 검색은 두 파일을 중심으로 작동합니다.

```text
검색어 사전
backend/app/data/search_dictionary.csv

법령지도
backend/app/data/law_map.json
```

## 1. 검색어 사전 CSV

열 구성:

| 열 | 의미 |
|---|---|
| `user_expression` | 사용자가 입력할 표현 |
| `standard_expression` | 내부에서 사용할 표준 표현 |
| `topic` | 연결할 시설·업무 주제 |
| `handling` | 처리 방식 |
| `notes` | 관리 메모 |

### handling 값

```text
auto_correct
오타·약어를 표준 표현으로 실제 치환

auto_expand
원문은 유지하고 관련 주제·검색어 확장에 사용

choose
뜻이 여러 개여서 자동 확정하지 않고 선택질문 표시
```

예시:

```csv
희선탱크,희석탱크,제조·사용시설,auto_correct,오타 교정
저장탱크,저장시설,저장시설,auto_expand,시설 유형 연결
탱크,탱크,시설분류,choose,용도 선택 필요
```

### CSV 수정 시 주의

- 첫 행의 열 이름을 변경하지 않습니다.
- Excel 저장 시 CSV UTF-8 형식을 사용합니다.
- 같은 표현을 `auto_correct`와 `choose`에 동시에 넣지 않는 편이 안전합니다.
- 법적 의미가 다른 `저장시설`과 `보관시설`을 같은 표준어로 합치지 않습니다.

## 2. 법령지도 JSON

각 주제에는 다음 정보가 들어 있습니다.

```json
{
  "id": "storage",
  "label": "저장시설",
  "triggers": ["저장시설", "저장탱크", "저장조"],
  "search_terms": ["저장시설", "방유제", "액위계"],
  "intent_summary": "고정식 저장시설의 설치·관리기준과 검사·변경절차 확인",
  "checklist": ["용기가 아닌 고정식 탱크인지"],
  "primary_rules": [],
  "upper_laws": [],
  "related_rules": []
}
```

### 규정 역할

```text
primary_rules
검색 결과의 '핵심 적용 규정'에 표시

upper_laws
'상위 법령'에 표시

related_rules
'함께 확인할 규정'에 표시
```

규정 항목 예시:

```json
{
  "title": "유해화학물질 제조·사용·저장시설 설치 및 관리에 관한 고시",
  "role": "핵심 적용 고시",
  "kind": "admin_rule",
  "department": "화학물질안전원",
  "official_url": "공식 원문 주소"
}
```

### 새 주제를 추가하는 순서

1. `law_map.json`의 `topics` 배열에 새 주제를 추가합니다.
2. 대표 표현을 `triggers`에 넣습니다.
3. 법제처 API에서 사용할 표현을 `search_terms`에 넣습니다.
4. 핵심 적용 규정을 `primary_rules`에 넣습니다.
5. `search_dictionary.csv`에도 사용자 표현을 추가합니다.
6. 테스트 파일에 최소 한 건을 추가합니다.
7. 로컬에서 테스트 후 GitHub에 push합니다.

## 3. 모호어 선택지

`law_map.json`의 `ambiguities`에서 관리합니다.

```json
{
  "term": "탱크",
  "message": "사용 목적에 따라 적용 고시가 달라집니다.",
  "options": [
    {"label": "공정에서 사용하는 탱크", "query": "제조·사용시설 탱크"},
    {"label": "고정식 저장탱크", "query": "저장시설 저장탱크"}
  ]
}
```

## 4. 법령지도 갱신일

`law_map.json` 상단의 값을 갱신합니다.

```json
"verified_on": "2026-07-25"
```

실제로 현행 규정과 공식 원문 주소를 확인한 날만 변경합니다.

## 5. 수정 후 테스트

```powershell
cd backend
py -m unittest discover -s tests -v
```

그다음 사이트를 실행하고 아래 검색어를 직접 확인합니다.

```text
저장시설
보관시설
희석탱크 설치검사
탱크
탱크로리
사외배관 누출
원료 변경 시 신고
```
