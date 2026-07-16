import unittest

from src.source_quality.value_normalizer import normalize_value


class ValueNormalizerTests(unittest.TestCase):
    def test_mass_supports_e_notation_scientific_notation_and_chinese_unit(self):
        e_value = normalize_value("6.4171e23 kg", "HAS_MASS")
        sci_value = normalize_value("6.4169 × 10 23 kg", "HAS_MASS")
        chinese_value = normalize_value("5.972 37 × 10 24 千克", "HAS_MASS")

        self.assertEqual(e_value["normalized_unit"], "kg")
        self.assertAlmostEqual(e_value["numeric_value"], 6.4171e23)
        self.assertAlmostEqual(sci_value["numeric_value"], 6.4169e23)
        self.assertAlmostEqual(chinese_value["numeric_value"], 5.97237e24)

    def test_mass_supports_earth_and_jupiter_mass_units(self):
        earth = normalize_value("1 地球质量", "HAS_MASS")
        jupiter = normalize_value("1 Jupiter mass", "HAS_MASS")

        self.assertEqual(earth["normalized_unit"], "kg")
        self.assertGreater(jupiter["numeric_value"], earth["numeric_value"])

    def test_radius_supports_km_chinese_km_and_meters(self):
        km = normalize_value("3389.5 km", "HAS_RADIUS")
        chinese = normalize_value("3389.5 千米", "HAS_RADIUS")
        meters = normalize_value("3389500 m", "HAS_RADIUS")

        self.assertEqual(km["normalized_unit"], "km")
        self.assertAlmostEqual(km["numeric_value"], chinese["numeric_value"])
        self.assertAlmostEqual(km["numeric_value"], meters["numeric_value"])

    def test_atmosphere_synonyms_normalize_to_component_set(self):
        zh = normalize_value("二氧化碳;氮气;氩气;水蒸气", "HAS_ATMOSPHERE")
        en = normalize_value("CO2, nitrogen, argon, water vapor", "HAS_ATMOSPHERE")

        self.assertEqual(zh["normalized_unit"], "component_set")
        self.assertEqual(zh["normalized_value"], "CO2;N2;Ar;H2O")
        self.assertEqual(en["normalized_value"], "CO2;N2;Ar;H2O")

    def test_wikidata_unit_qid_maps_to_canonical_unit(self):
        radius = normalize_value("3389.50 Q828224", "HAS_RADIUS")
        mass = normalize_value("641.691 Q613726", "HAS_MASS")

        self.assertEqual(radius["unit_qid"], "Q828224")
        self.assertEqual(radius["normalized_unit"], "km")
        self.assertAlmostEqual(radius["numeric_value"], 3389.5)
        self.assertEqual(mass["unit_qid"], "Q613726")
        self.assertEqual(mass["normalized_unit"], "kg")
        self.assertAlmostEqual(mass["numeric_value"], 6.41691e23)

    def test_unknown_wikidata_unit_qid_is_not_silent(self):
        unknown = normalize_value("123 Q999999999", "HAS_RADIUS")

        self.assertEqual(unknown["parse_status"], "unknown_unit")
        self.assertEqual(unknown["unit_qid"], "Q999999999")


if __name__ == "__main__":
    unittest.main()
