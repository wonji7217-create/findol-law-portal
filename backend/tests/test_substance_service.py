from app.substance_service import search_substances


def first(query: str):
    result = search_substances(query)
    assert result["items"], query
    return result["items"][0]


def test_phosphoric_acid_alias_and_notice():
    item = first("인산 85%")
    assert item["cas_no"] == "7664-38-2"
    assert item["display_name"] == "인산"
    assert item["notices"]
    assert item["notices"][0]["status_label"] == "행정예고"
    assert item["concentration_analysis"]["state"] == "no_threshold"


def test_sodium_hypochlorite_concentration():
    item = first("차아염소산나트륨 12%")
    assert item["cas_no"] == "7681-52-9"
    analysis = item["concentration_analysis"]
    assert analysis["state"] == "threshold_met"
    assert {x["threshold"] for x in analysis["comparisons"]} == {10.0, 2.5}
    assert all(x["met"] for x in analysis["comparisons"])


def test_common_typo_alias():
    item = first("차야염소산나트륨")
    assert item["cas_no"] == "7681-52-9"
    assert item["matched_by"] == "alias"


def test_cas_exact_search():
    item = first("7681-52-9")
    assert item["matched_by"] == "cas"


def test_matched_status_labels_are_summarized():
    item = first("차아염소산나트륨 12%")
    labels = {x["label"] for x in item["concentration_analysis"]["matched_statuses"]}
    assert labels == {"인체급성유해성", "생태유해성"}


def test_accident_and_restricted_categories_are_preserved():
    accident = first("벤질 클로라이드 30%")
    accident_labels = {x["label"] for x in accident["concentration_analysis"]["matched_statuses"]}
    assert {"인체급성유해성", "인체만성유해성", "사고대비물질"} <= accident_labels

    restricted = first("크로뮴산화물 1%")
    restricted_labels = {x["label"] for x in restricted["concentration_analysis"]["matched_statuses"]}
    assert {"인체만성유해성", "제한물질"} <= restricted_labels
    assert "인체급성유해성" not in restricted_labels
