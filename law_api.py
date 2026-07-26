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
