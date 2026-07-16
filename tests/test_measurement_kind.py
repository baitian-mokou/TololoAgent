import unittest

from src.source_quality.measurement_kind import infer_measurement_kind


class MeasurementKindTests(unittest.TestCase):
    def test_radius_kind_markers(self):
        self.assertEqual(
            infer_measurement_kind(relation="HAS_RADIUS", raw_text="平均半径: 3389.5 km")["measurement_kind"],
            "mean_radius",
        )
        self.assertEqual(
            infer_measurement_kind(relation="HAS_RADIUS", raw_text="赤道半径: 3396.2 km")["measurement_kind"],
            "equatorial_radius",
        )
        self.assertEqual(
            infer_measurement_kind(relation="HAS_RADIUS", raw_text="极半径: 3376.2 km")["measurement_kind"],
            "polar_radius",
        )

    def test_distance_from_sun_is_orbital_distance_warning(self):
        result = infer_measurement_kind(
            relation="ORBITS",
            source_field="Distance from Sun (10^6 km)",
        )

        self.assertEqual(result["measurement_kind"], "orbital_distance")
        self.assertIn("not a direct orbit-target", result["warning"])


if __name__ == "__main__":
    unittest.main()
