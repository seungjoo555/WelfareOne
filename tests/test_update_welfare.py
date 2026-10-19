import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from update_welfare_incremental import (  # noqa: E402
    ListEntry,
    QuotaReached,
    apply_plan,
    content_digest,
    detail_last_mod,
    finalize_lists,
    make_plan,
    parse_list,
)


def list_xml(*items):
    body = "".join(
        f"<servList><servId>{i}</servId><servNm>{t}</servNm>" + (f"<lastModYmd>{m}</lastModYmd>" if m else "") + "</servList>"
        for i, t, m in items
    )
    return f"<wantedList><totalCount>{len(items)}</totalCount>{body}</wantedList>".encode()


def detail_xml(pid, mod="", body="내용"):
    mod_tag = f"<lastModYmd>{mod}</lastModYmd>" if mod else ""
    return f"<wantedDtl><servId>{pid}</servId>{mod_tag}<tgtrDtlCn>{body}</tgtrDtlCn></wantedDtl>".encode()


class ParseTest(unittest.TestCase):
    def test_parse_list_reads_id_title_and_last_modified(self):
        entries = parse_list(list_xml(("A1", "정책 하나", "20260901"), ("B2", "정책 둘", "")))
        self.assertEqual(entries, [ListEntry("A1", "정책 하나", "20260901"), ListEntry("B2", "정책 둘", "")])

    def test_content_digest_ignores_whitespace_between_tags(self):
        self.assertEqual(content_digest(b"<a>\n  <b>1</b>\n</a>"), content_digest(b"<a><b>1</b></a>"))
        self.assertNotEqual(content_digest(b"<a><b>1</b></a>"), content_digest(b"<a><b>2</b></a>"))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.detail = Path(self.tmp.name) / "detail"
        self.detail.mkdir()

    def store(self, pid, mod=""):
        (self.detail / f"{pid}.xml").write_bytes(detail_xml(pid, mod))

    def test_new_changed_unchanged_and_removed_are_separated(self):
        self.store("SAME", "20260801")
        self.store("OLD", "20260801")
        self.store("GONE", "20260101")
        fresh = [
            ListEntry("SAME", "같음", "20260801"),
            ListEntry("OLD", "수정됨", "20260915"),
            ListEntry("NEW", "신규", "20260920"),
        ]
        plan = make_plan(fresh, self.detail)
        self.assertEqual([e.policy_id for e in plan.new], ["NEW"])
        self.assertEqual([e.policy_id for e in plan.changed], ["OLD"])
        self.assertEqual([e.policy_id for e in plan.unchanged], ["SAME"])
        self.assertEqual(plan.removed, ["GONE"])
        self.assertEqual([e.policy_id for e in plan.to_fetch], ["NEW", "OLD"])

    def test_policy_without_modified_date_is_compared_by_content(self):
        self.store("NAT", "")  # 중앙부처처럼 수정일이 없다
        plan = make_plan([ListEntry("NAT", "중앙", "")], self.detail)
        self.assertEqual([e.policy_id for e in plan.unknown], ["NAT"])
        self.assertEqual(plan.changed, [])

    def test_duplicate_ids_in_list_are_counted_once(self):
        plan = make_plan([ListEntry("D", "a", "1"), ListEntry("D", "a", "1")], self.detail)
        self.assertEqual(len(plan.new), 1)

    def test_detail_last_mod_handles_missing_and_broken_files(self):
        self.assertIsNone(detail_last_mod(self.detail / "none.xml"))
        (self.detail / "bad.xml").write_bytes(b"not xml")
        self.assertIsNone(detail_last_mod(self.detail / "bad.xml"))
        self.store("OK", "20260101")
        self.assertEqual(detail_last_mod(self.detail / "OK.xml"), "20260101")


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.detail, self.prev = self.root / "detail", self.root / "detail_prev" / "20261019"
        self.detail.mkdir()

    def test_new_changed_and_identical_details_are_handled_differently(self):
        (self.detail / "CHG.xml").write_bytes(detail_xml("CHG", "20260101", "옛 내용"))
        (self.detail / "SAME.xml").write_bytes(detail_xml("SAME", "", "그대로"))
        fetched = {
            "NEW": detail_xml("NEW", "20260930"),
            "CHG": detail_xml("CHG", "20260930", "새 내용"),
            "SAME": detail_xml("SAME", "", "그대로"),
        }
        entries = [ListEntry(pid, pid) for pid in fetched]
        result = apply_plan(entries, fetched.__getitem__, self.detail, self.prev)
        self.assertEqual((result.added, result.updated, result.same), (["NEW"], ["CHG"], ["SAME"]))
        self.assertIn("새 내용", (self.detail / "CHG.xml").read_text(encoding="utf-8"))
        self.assertIn("옛 내용", (self.prev / "CHG.xml").read_text(encoding="utf-8"))  # 옛 파일 보존
        self.assertFalse((self.prev / "SAME.xml").exists())

    def test_failure_is_recorded_and_does_not_stop_others(self):
        def fetch(pid):
            if pid == "BAD":
                raise RuntimeError("HTTP 500")
            return detail_xml(pid)

        result = apply_plan([ListEntry("BAD", "x"), ListEntry("GOOD", "y")], fetch, self.detail, self.prev)
        self.assertEqual(result.failed, {"BAD": "HTTP 500"})
        self.assertEqual(result.added, ["GOOD"])

    def test_quota_stops_and_reports_remaining(self):
        def fetch(pid):
            if pid == "B":
                raise QuotaReached("한도")
            return detail_xml(pid)

        entries = [ListEntry(p, p) for p in "ABC"]
        result = apply_plan(entries, fetch, self.detail, self.prev)
        self.assertEqual(result.added, ["A"])
        self.assertEqual(result.remaining, ["B", "C"])

    def test_invalid_id_is_rejected_without_fetching(self):
        calls = []
        result = apply_plan([ListEntry("../evil", "x")], lambda pid: calls.append(pid) or b"", self.detail, self.prev)
        self.assertEqual(calls, [])
        self.assertIn("../evil", result.failed)


class FinalizeTest(unittest.TestCase):
    def test_lists_are_replaced_and_previous_list_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp)
            (raw / "list").mkdir()
            (raw / "list" / "page_00001.xml").write_text("old", encoding="utf-8")
            (raw / "detail").mkdir()
            (raw / "detail" / "A.xml").write_bytes(detail_xml("A"))
            snapshot = raw / "list_snapshot"
            snapshot.mkdir()
            (snapshot / "page_00001.xml").write_text("new", encoding="utf-8")
            finalize_lists(raw, snapshot, [ListEntry("A", "가"), ListEntry("B", "나")], "20261019")
            self.assertEqual((raw / "list" / "page_00001.xml").read_text(encoding="utf-8"), "new")
            self.assertEqual((raw / "list_prev_20261019" / "page_00001.xml").read_text(encoding="utf-8"), "old")
            status = (raw / "status.csv").read_text(encoding="utf-8-sig")
            self.assertIn("A,가,완료", status)
            self.assertIn("B,나,미수집", status)


if __name__ == "__main__":
    unittest.main()
