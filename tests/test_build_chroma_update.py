import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import build_chroma_update as b  # noqa: E402


def record(section="overview", record_type="search", searchable=True, rid="local:P1:search:overview:0", **extra):
    meta = {"section": section, "record_type": record_type, "searchable": searchable, "source_id": "P1",
            "has_attachments": True, "has_document_evidence": False, "document_evidence_status": "attachments_only", **extra}
    return {"id": rid, "document": "문서", "metadata": meta}


class ToOldFormatTest(unittest.TestCase):
    def test_attachments_become_searchable_documents_with_old_id(self):
        out = b.to_old_format(record("attachments", "detail", False, "local:P1:detail:attachments:2"))
        self.assertEqual(out["id"], "local:P1:search:documents:2")
        self.assertEqual(
            (out["metadata"]["section"], out["metadata"]["record_type"], out["metadata"]["searchable"]),
            ("documents", "search", True),
        )

    def test_extra_metadata_keys_are_removed_everywhere(self):
        for rec in (record("attachments", "detail", False, "local:P1:detail:attachments:0"), record()):
            self.assertFalse(set(b.EXTRA_METADATA) & set(b.to_old_format(rec)["metadata"]))

    def test_other_sections_keep_id_and_values(self):
        rec = record("benefit", "search", True, "local:P1:search:benefit:1")
        out = b.to_old_format(rec)
        self.assertEqual(out["id"], rec["id"])
        self.assertEqual(out["metadata"]["section"], "benefit")

    def test_input_record_is_not_mutated(self):
        rec = record("attachments", "detail", False, "local:P1:detail:attachments:0")
        b.to_old_format(rec)
        self.assertEqual(rec["metadata"]["section"], "attachments")
        self.assertIn("has_attachments", rec["metadata"])


class CompareTest(unittest.TestCase):
    def test_counts_identical_changed_and_missing_records(self):
        meta = {"source_id": "P1", "a": 1}
        base = {"x": ("d", meta), "y": ("d", meta), "z": ("d", meta), "gone": ("d", meta)}
        built = {"x": ("d", dict(meta)), "y": ("다른", meta), "z": ("d", {**meta, "a": 2}), "new": ("d", meta)}
        stat = b.compare(base, built, {"P1"})
        self.assertEqual(
            dict(stat),
            {"동일": 1, "문서 다름": 1, "메타데이터 다름": 1, "새 DB에만 있음": 1, "기존 DB에만 있음": 1},
        )

    def test_records_of_other_policies_are_ignored(self):
        base = {"x": ("d", {"source_id": "OTHER"})}
        self.assertEqual(dict(b.compare(base, {}, {"P1"})), {})


class ImporterPatchTest(unittest.TestCase):
    def test_label_patches_apply_to_the_current_importer(self):
        source = b.IMPORTER.read_text(encoding="utf-8")
        for old, new in b.LABEL_PATCHES:
            self.assertIn(old, source, "적재 스크립트가 바뀌어 패치 지점이 사라졌다")
            self.assertNotEqual(old, new)


if __name__ == "__main__":
    unittest.main()
