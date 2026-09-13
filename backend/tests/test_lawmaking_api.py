from xml.etree import ElementTree as ET

from app import lawmaking_api


LIST_XML = '''
<result>
  <retMsg>200</retMsg>
  <totalCnt>6540</totalCnt>
  <pageIndex>1</pageIndex>
  <pageSize>20</pageSize>
  <list>
    <ApiList05Vo>
      <ogAdmPpSeq>47054</ogAdmPpSeq>
      <admRulNm><![CDATA[[진행]소방 공사감리원 업무대행자 지정 등에 관한 기준 고시 제정안행정예고]]></admRulNm>
      <lsClsNm>고시</lsClsNm>
      <asndOfiNm>소방청</asndOfiNm>
      <pntcNo>2026-138</pntcNo>
      <pntcDt>2026. 7. 23.</pntcDt>
      <stYd>2026. 7. 23.</stYd>
      <edYd>2026. 8. 12.</edYd>
      <FileName>기준 고시 제정안.hwpx</FileName>
      <FileDownLink>http://www.lawmaking.go.kr/file/download/1/ABC</FileDownLink>
      <readCnt>21742</readCnt>
      <announceType>TYPE6</announceType>
      <mappingAdmRulSeq>2000000329212</mappingAdmRulSeq>
    </ApiList05Vo>
  </list>
</result>
'''

DETAIL_XML = '''
<result>
  <retMsg>200</retMsg>
  <info>
    <ApiDetile05Vo>
      <ogAdmPpSeq>47054</ogAdmPpSeq>
      <admRulNm>소방 공사감리원 업무대행자 지정 등에 관한 기준 고시 제정안행정예고</admRulNm>
      <asndOfiNm>소방청공고 제2026-138호 (2026. 7. 23.)</asndOfiNm>
      <lmTpNm>제정</lmTpNm>
      <lsClsNm>고시</lsClsNm>
      <stYd>2026. 7. 23.</stYd>
      <edYd>2026. 8. 12.</edYd>
      <telNo>044-205-7507</telNo>
      <faxNo/>
      <email>hyun2868@korea.kr</email>
      <admPpCts><![CDATA[<p><strong>1. 제정이유</strong></p><p>세부 기준을 마련하려는 것임.</p>]]></admPpCts>
      <ogAdmFlList>
        <FileListVo>
          <FileName>기준 고시 제정안.hwpx</FileName>
          <FileDownUrl>http://www.lawmaking.go.kr/file/download/10942070/ABC</FileDownUrl>
        </FileListVo>
      </ogAdmFlList>
      <ptcpAdmPpFlList/>
    </ApiDetile05Vo>
  </info>
</result>
'''


def test_parse_administrative_list_item():
    root = ET.fromstring(LIST_XML)
    items = [lawmaking_api._parse_list_item(node, "administrative_notice") for node in lawmaking_api._list_nodes(root)]
    assert len(items) == 1
    item = items[0]
    assert item["seq"] == "47054"
    assert item["mapping_id"] == "2000000329212"
    assert item["announce_type"] == "TYPE6"
    assert item["file_url"].startswith("https://")


def test_parse_detail_attachments_and_body(monkeypatch):
    async def fake_get_xml(url, params=None, timeout=20.0):
        return ET.fromstring(DETAIL_XML)

    monkeypatch.setattr(lawmaking_api, "_get_xml", fake_get_xml)
    item = {
        "kind": "administrative_notice",
        "seq": "47054",
        "mapping_id": "2000000329212",
        "announce_type": "TYPE6",
        "department": "소방청",
    }

    import asyncio
    detail = asyncio.run(lawmaking_api.fetch_administrative_detail(item))
    assert detail["revision_type"] == "제정"
    assert "제정이유" in detail["body_text"]
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["group"] == "행정규칙안"
    assert detail["attachments"][0]["url"].startswith("https://")


def test_archive_payload_does_not_expose_oc():
    item = {
        "kind": "administrative_notice",
        "seq": "47054",
        "mapping_id": "2000000329212",
        "announce_type": "TYPE6",
        "title": "화학물질 관련 고시 행정예고",
        "rule_type": "고시",
        "revision_type": "일부개정",
        "department": "기후에너지환경부",
        "start_date": "2026. 7. 23.",
        "end_date": "2026. 8. 12.",
        "body_text": "화학물질 관련 주요내용",
        "attachments": [],
    }
    payload = lawmaking_api.to_archive_payload(item)
    assert payload["official_url"] == (
        "https://opinion.lawmaking.go.kr/gcom/admpp/47054"
        "?announceType=TYPE6&mappingAdmRulSeq=2000000329212"
    )
    assert "OC=" not in payload["official_url"]
    assert payload["deadline_date"] == "2026. 8. 12."
    assert "행정예고" in payload["material_type"]


def test_normalize_admrul_results_keeps_enforcement_date():
    from app import law_api

    raw = {
        "AdmRulSearch": {
            "admrul": {
                "행정규칙일련번호": "12345",
                "행정규칙명": "유해화학물질 사외배관 이송시설 설치 및 관리에 관한 고시",
                "행정규칙종류": "고시",
                "발령일자": "20260616",
                "시행일자": "20260701",
                "소관부처명": "화학물질안전원",
                "행정규칙상세링크": "/DRF/lawService.do?target=admrul&ID=12345",
            }
        }
    }
    [item] = law_api.normalize_admrul_results(raw)
    assert item["promulgation_date"] == "20260616"
    assert item["enforcement_date"] == "20260701"


def test_public_detail_url_for_legislative_notice():
    item = {
        "kind": "legislative_notice",
        "seq": "88352",
        "mapping_id": "2000000000000",
        "announce_type": "TYPE5",
    }
    assert lawmaking_api.public_detail_url(item) == "https://opinion.lawmaking.go.kr/gcom/ogLmPp/88352"
