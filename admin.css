import unittest

from app.search_engine import build_search_plan, inject_mapped_results


class SearchEngineTest(unittest.TestCase):
    def test_storage_maps_to_combined_facility_rule(self):
        plan = build_search_plan("저장시설")
        self.assertEqual(plan.topics[0]["label"], "저장시설")
        self.assertIn(
            "유해화학물질 제조·사용·저장시설 설치 및 관리에 관한 고시",
            [rule["title"] for rule in plan.primary_rules],
        )

    def test_keeping_is_not_storage(self):
        plan = build_search_plan("보관시설")
        self.assertEqual(plan.topics[0]["label"], "보관시설")
        titles = [rule["title"] for rule in plan.primary_rules]
        self.assertIn("유해화학물질 보관시설 설치 및 관리에 관한 고시", titles)
        self.assertNotIn("유해화학물질 제조·사용·저장시설 설치 및 관리에 관한 고시", titles)

    def test_dilution_tank_is_manufacturing_use(self):
        plan = build_search_plan("희석탱크 설치검사")
        self.assertEqual(plan.topics[0]["label"], "제조·사용시설")
        labels = [topic["label"] for topic in plan.topics]
        self.assertIn("검사·안전진단", labels)

    def test_generic_tank_asks_question(self):
        plan = build_search_plan("탱크")
        self.assertFalse(plan.primary_rules)
        self.assertTrue(plan.ambiguities)
        self.assertEqual(plan.ambiguities[0]["term"], "탱크")

    def test_tank_lorry_maps_to_vehicle_transport(self):
        plan = build_search_plan("탱크로리")
        self.assertEqual(plan.topics[0]["label"], "차량 운송시설")
        self.assertIn(
            "유해화학물질 차량 운송시설 설치 및 관리에 관한 고시",
            [rule["title"] for rule in plan.primary_rules],
        )

    def test_mapped_rule_is_injected_without_api(self):
        plan = build_search_plan("저장시설")
        result = inject_mapped_results([], [], plan)
        self.assertEqual(len(result["core_rules"]), 1)
        self.assertEqual(result["core_rules"][0]["source"], "law_map")


if __name__ == "__main__":
    unittest.main()
