from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

from career_ops_kr.pipeline import (
    LOCK_STALE_SECONDS,
    PipelineLockError,
    acquire_pipeline_lock,
    list_pending_urls,
    mark_urls_processed,
    pipeline_lock_path,
)


class PipelineLockTest(unittest.TestCase):
    def test_acquire_pipeline_lock_blocks_second_acquire_for_same_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"

            with acquire_pipeline_lock(pipeline_path) as lock_path:
                self.assertTrue(lock_path.exists())
                with self.assertRaises(PipelineLockError):
                    with acquire_pipeline_lock(pipeline_path):
                        self.fail("second acquire should not succeed")

            self.assertFalse(pipeline_lock_path(pipeline_path).exists())

    def test_acquire_pipeline_lock_releases_after_exception(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"

            with self.assertRaises(RuntimeError):
                with acquire_pipeline_lock(pipeline_path):
                    raise RuntimeError("boom")

            self.assertFalse(pipeline_lock_path(pipeline_path).exists())

    def test_fresh_invalid_lock_file_is_not_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"
            lock_path = pipeline_lock_path(pipeline_path)
            lock_path.write_text("", encoding="utf-8")

            with self.assertRaises(PipelineLockError):
                with acquire_pipeline_lock(pipeline_path):
                    self.fail("fresh invalid lock file should still block acquisition")

            self.assertTrue(lock_path.exists())

    def test_stale_invalid_lock_file_is_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"
            lock_path = pipeline_lock_path(pipeline_path)
            lock_path.write_text("", encoding="utf-8")
            stale_time = time.time() - LOCK_STALE_SECONDS - 5
            os.utime(lock_path, (stale_time, stale_time))

            with acquire_pipeline_lock(pipeline_path) as acquired_lock_path:
                self.assertEqual(lock_path, acquired_lock_path)
                self.assertTrue(acquired_lock_path.exists())

            self.assertFalse(lock_path.exists())

    def test_list_pending_urls_deduplicates_canonical_variants(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"
            pipeline_path.write_text(
                "\n".join(
                    [
                        "# Pipeline Inbox",
                        "",
                        "## Pending",
                        "- [ ] https://www.indeed.com/viewjob?jk=abc123&from=shareddesktop_copy",
                        "- [ ] https://www.indeed.com/viewjob?jk=abc123",
                        "- [ ] https://recruit.wanted.co.kr/wd/12345?campaign=foo",
                        "",
                        "## Processed",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(
                [
                    "https://www.indeed.com/viewjob?jk=abc123",
                    "https://www.wanted.co.kr/wd/12345",
                ],
                list_pending_urls(pipeline_path),
            )

    def test_mark_urls_processed_matches_canonicalized_urls(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            pipeline_path = Path(temp_dir) / "pipeline.md"
            pipeline_path.write_text(
                "\n".join(
                    [
                        "# Pipeline Inbox",
                        "",
                        "## Pending",
                        "- [ ] https://www.indeed.com/viewjob?jk=abc123&from=shareddesktop_copy",
                        "",
                        "## Processed",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            changed = mark_urls_processed(
                pipeline_path,
                ["https://www.indeed.com/viewjob?jk=abc123"],
            )

            content = pipeline_path.read_text(encoding="utf-8")

            self.assertEqual(1, changed)
            self.assertIn("- [x] https://www.indeed.com/viewjob?jk=abc123", content)


if __name__ == "__main__":
    unittest.main()
