import unittest

from src.source_adapters.nasa import NasaPipelineAdapter, html_to_text, parse_nasa_fact_sheet_candidates


NASA_TABLE_FIXTURE = """
<html><body>
<table>
  <tr><th>Field</th><th>Mars</th></tr>
  <tr><td>Mass (10^24 kg)</td><td>0.64171</td></tr>
  <tr><td>Mean radius (km)</td><td>3389.5</td></tr>
  <tr><td>Atmospheric composition</td><td>Carbon dioxide; Nitrogen; Argon</td></tr>
  <tr><td>Distance from Sun (10^6 km)</td><td>227.9</td></tr>
</table>
</body></html>
"""


class NasaFactSheetParserTests(unittest.TestCase):
    def test_strict_table_parser_extracts_required_fields(self):
        facts = parse_nasa_fact_sheet_candidates(
            NASA_TABLE_FIXTURE,
            payload={
                "source_record_id": "nasa-mars-test",
                "source_url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
            },
            fetched_at="2026-01-01T00:00:00+00:00",
            schema_version="nasa_shadow_ready_v1",
        )

        by_relation = {fact["relation"]: fact for fact in facts}
        self.assertEqual(set(by_relation), {"HAS_MASS", "HAS_RADIUS", "HAS_ATMOSPHERE", "ORBITS"})
        self.assertTrue(by_relation["HAS_MASS"]["normalized_value"].startswith("6.4171"))
        self.assertEqual(by_relation["HAS_MASS"]["unit"], "kg")
        self.assertEqual(by_relation["HAS_RADIUS"]["normalized_value"], "3389.5")
        self.assertEqual(by_relation["HAS_RADIUS"]["unit"], "km")
        self.assertEqual(by_relation["HAS_ATMOSPHERE"]["normalized_value"], "CO2;N2;Ar")
        self.assertTrue(by_relation["ORBITS"]["derived"])
        self.assertEqual(by_relation["ORBITS"]["derived_from"], "Distance from Sun (10^6 km)")
        self.assertTrue(by_relation["ORBITS"]["relation_semantics_warning"])
        for fact in facts:
            self.assertEqual(fact["source_name"], "nasa")
            self.assertEqual(fact["schema_version"], "nasa_shadow_ready_v1")
            self.assertIn("table_field", fact)
            self.assertIn("source_url", fact)

    def test_fact_sheet_record_uses_atmosphere_narrative_when_available(self):
        adapter = NasaPipelineAdapter(mode="dry-run")
        record = adapter._record_from_fact_sheet({
            "title": "火星",
            "source_url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
            "html": NASA_TABLE_FIXTURE,
            "fetched_at": "2026-01-01T00:00:00+00:00",
        })

        self.assertEqual(record["narratives"][0]["section"], "大气")
        self.assertIn("CO2", record["narratives"][0]["content"])
        self.assertIn("火星", record["narratives"][0]["keywords"])

    def test_offline_raw_record_keeps_numeric_facts_without_promoting_distance_to_orbits(self):
        adapter = NasaPipelineAdapter(mode="dry-run")
        record = adapter._record_from_offline_raw(
            {
                "title": "火星",
                "url": "https://nssdc.gsfc.nasa.gov/planetary/factsheet/marsfact.html",
                "html": NASA_TABLE_FIXTURE,
                "text": "火星大气以二氧化碳为主。",
                "raw_text": "火星大气以二氧化碳为主。",
            },
            "2026-01-01T00:00:00+00:00",
        )

        by_relation = {fact["relation"]: fact for fact in record["triples"]}
        self.assertIn("HAS_MASS", by_relation)
        self.assertIn("HAS_RADIUS", by_relation)
        self.assertIn("HAS_ATMOSPHERE", by_relation)
        self.assertNotIn("ORBITS", by_relation)

    def test_offline_raw_satellite_record_infers_parent_system_for_added_moons(self):
        adapter = NasaPipelineAdapter(mode="dry-run")
        record = adapter._record_from_offline_raw(
            {
                "title": "土卫六",
                "url": "https://science.nasa.gov/saturn/moons/titan/",
                "text": "土卫六是土星的天然卫星。土卫六绕土星公转，并拥有以氮气为主的浓厚大气。",
                "raw_text": "土卫六是土星的天然卫星。土卫六绕土星公转，并拥有以氮气为主的浓厚大气。",
            },
            "2026-01-01T00:00:00+00:00",
        )

        by_relation = {fact["relation"]: fact for fact in record["triples"]}
        self.assertEqual(by_relation["ORBITS"]["object"], "土星")
        self.assertEqual(by_relation["PART_OF"]["object"], "土星系统")
        self.assertEqual(by_relation["HAS_ATMOSPHERE"]["object"], "CO2;N2;Ar")

    def test_html_to_text_drops_script_and_style_noise(self):
        text = html_to_text("""
        <html><head><style>.x{color:red}</style><script>var gform = 1;</script></head>
        <body><main>火星大气以二氧化碳为主。</main></body></html>
        """)

        self.assertIn("火星大气", text)
        self.assertNotIn("gform", text)
        self.assertNotIn("color:red", text)

    def test_offline_raw_record_cleans_html_when_text_is_absent(self):
        adapter = NasaPipelineAdapter(mode="dry-run")
        record = adapter._record_from_offline_raw(
            {
                "title": "火星",
                "url": "https://science.nasa.gov/mars/",
                "html": """
                <html><head><script>var gform = 1;</script></head>
                <body><main>火星绕太阳公转。</main></body></html>
                """,
            },
            "2026-01-01T00:00:00+00:00",
        )

        content = record["narratives"][0]["content"]
        self.assertIn("火星绕太阳公转", content)
        self.assertNotIn("gform", content)
        self.assertNotIn("<main>", content)


if __name__ == "__main__":
    unittest.main()
