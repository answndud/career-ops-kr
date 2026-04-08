from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from career_ops_kr.tracker import merge_tracker_additions, normalize_tracker_statuses


class TrackerMergeTest(unittest.TestCase):
    def test_merge_tracker_additions_supports_recursive_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            tracker_path = temp_path / "applications.md"
            additions_dir = temp_path / "tracker-additions" / "batch-1"
            additions_dir.mkdir(parents=True, exist_ok=True)
            (additions_dir / "entry.tsv").write_text(
                "\t".join(
                    [
                        "2026-04-06",
                        "Example Corp",
                        "Platform Engineer",
                        "4.2/5",
                        "review",
                        "remember",
                        "",
                        "reports/example.md",
                        "선별 검토",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            merged = merge_tracker_additions(
                tracker_path,
                temp_path / "tracker-additions",
                recursive=True,
            )
            changed = normalize_tracker_statuses(tracker_path)
            content = tracker_path.read_text(encoding="utf-8")

            self.assertEqual(1, merged)
            self.assertEqual(0, changed)
            self.assertIn("Example Corp", content)
            self.assertIn("Platform Engineer", content)
            self.assertIn("검토중", content)


if __name__ == "__main__":
    unittest.main()
