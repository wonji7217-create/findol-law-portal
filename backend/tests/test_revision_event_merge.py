from app import models, storage


def make_entry(kind="law", date="20260901"):
    return models.ArchiveEntry(
        id=1,
        archive_key="test",
        kind=kind,
        title="테스트 일부개정",
        material_type="법령",
        department="기후에너지환경부",
        source_name="국가법령정보센터",
        promulgation_date=date,
        enforcement_date=date,
        tags_json="[]",
        related_laws_json="[]",
        related_tasks_json="[]",
        attachments_json="[]",
    )


def test_same_day_law_is_combined():
    events = storage._revision_events_for_entry(make_entry("law"))
    combined = [e for e in events if e["event_code"] == "promulgated_effective"]
    assert len(combined) == 1
    assert combined[0]["event_type"] == "공포·시행"
    assert not any(e["event_code"] == "promulgated" for e in events)
    assert not any(e["event_code"] == "effective" for e in events)


def test_same_day_admin_rule_uses_issue_label():
    events = storage._revision_events_for_entry(make_entry("admin_rule"))
    combined = [e for e in events if e["event_code"] == "promulgated_effective"]
    assert len(combined) == 1
    assert combined[0]["event_type"] == "발령·시행"


def test_different_dates_stay_separate():
    entry = make_entry("law", "20260901")
    entry.enforcement_date = "20261001"
    events = storage._revision_events_for_entry(entry)
    codes = {e["event_code"] for e in events}
    assert "promulgated" in codes
    assert "effective" in codes
    assert "promulgated_effective" not in codes
