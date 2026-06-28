import unittest

from src.gui.main_window import (
    QUALITY_REVIEW_WORKBENCH_BOTTOM_BUTTONS,
    QUALITY_REVIEW_WORKBENCH_GEOMETRY,
    QUALITY_REVIEW_WORKBENCH_MIN_SIZE,
    QUALITY_REVIEW_WORKBENCH_TITLE,
)
from src.source_quality.review_labels import format_relation_label


class QualityReviewGuiLayoutTests(unittest.TestCase):
    def test_workbench_window_geometry_is_configured(self):
        self.assertEqual(QUALITY_REVIEW_WORKBENCH_TITLE, "质量复查工作台")
        self.assertEqual(QUALITY_REVIEW_WORKBENCH_GEOMETRY, "1180x760")
        self.assertEqual(QUALITY_REVIEW_WORKBENCH_MIN_SIZE, (1000, 650))

    def test_workbench_bottom_buttons_include_primary_actions(self):
        expected = {
            "通过",
            "暂缓",
            "拒绝",
            "保存修正建议",
            "清除修正建议",
            "预演合并",
            "合并低风险标注",
            "导出复查报告",
            "刷新",
        }
        self.assertEqual(set(QUALITY_REVIEW_WORKBENCH_BOTTOM_BUTTONS), expected)

    def test_relation_label_still_uses_chinese_display_only(self):
        raw_relation = "HAS_RADIUS"
        self.assertEqual(format_relation_label(raw_relation), "HAS_RADIUS（半径）")
        self.assertEqual(raw_relation, "HAS_RADIUS")


if __name__ == "__main__":
    unittest.main()
