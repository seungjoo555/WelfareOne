import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "make_labeling_sheet.py"
spec = importlib.util.spec_from_file_location("make_labeling_sheet", SCRIPT)
sheet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sheet)

REGIONS = {"서울특별시": ["관악구"], "세종특별자치시": []}
HEADER = "id,author,region_level1,region_level2,age,question,type,note\n"


def questions(authors: str) -> list[dict]:
    """author 문자열(예: 'AAAABBBCC')의 글자마다 질문 1개씩 만든다."""
    counts: dict[str, int] = {}
    rows = []
    for author in authors:
        counts[author] = counts.get(author, 0) + 1
        rows.append({"id": f"{author}{counts[author]:02d}", "author": author})
    return rows


class AssignLabelersTest(unittest.TestCase):
    def test_author_never_labels_own_question(self):
        result = sheet.assign_labelers(questions("AAAABBBBCCCC"), ["A", "B", "C"])
        for name, assigned in result.items():
            self.assertTrue(all(q["author"] != name for q in assigned), name)

    def test_primary_labeler_is_previous_in_order(self):
        result = sheet.assign_labelers(questions("ABC"), ["A", "B", "C"])
        ids = {name: {q["id"] for q in assigned} for name, assigned in result.items()}
        self.assertIn("B01", ids["A"])  # B의 질문은 A가 라벨링
        self.assertIn("C01", ids["B"])
        self.assertIn("A01", ids["C"])

    def test_one_in_three_questions_gets_a_second_labeler(self):
        qs = questions("AAAAAA")
        result = sheet.assign_labelers(qs, ["A", "B", "C"])
        counts = {q["id"]: sum(q in assigned for assigned in result.values()) for q in qs}
        self.assertEqual(sorted(counts.values()), [1, 1, 1, 1, 2, 2])  # 6개 중 인덱스 0, 3이 이중 라벨

    def test_unknown_author_exits(self):
        with self.assertRaises(SystemExit):
            sheet.assign_labelers(questions("Z"), ["A", "B", "C"])


class ReadQuestionsTest(unittest.TestCase):
    def read(self, body: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "q.csv"
            path.write_text(HEADER + body, encoding="utf-8-sig")
            return sheet.read_questions(path, REGIONS)

    def test_skips_example_rows_and_parses_age(self):
        rows = self.read("예시1,예시,서울특별시,관악구,24,예시 질문,상황서술,\nA01,A,서울특별시,관악구,24,월세가 부담돼요,상황서술,\nA02,A,세종특별자치시,,,배고파,구어체,\n")
        self.assertEqual([r["id"] for r in rows], ["A01", "A02"])
        self.assertEqual(rows[0]["age"], 24)
        self.assertIsNone(rows[1]["age"])
        self.assertEqual(rows[1]["region"].level2, "")

    def test_unknown_region_exits(self):
        with self.assertRaises(SystemExit):
            self.read("A01,A,없는도,,24,질문,상황서술,\n")

    def test_non_numeric_age_exits(self):
        with self.assertRaises(SystemExit):
            self.read("A01,A,서울특별시,관악구,스물,질문,상황서술,\n")

    def test_empty_question_exits(self):
        with self.assertRaises(SystemExit):
            self.read("A01,A,서울특별시,관악구,24,  ,상황서술,\n")


class HelperTest(unittest.TestCase):
    def test_candidate_summary_drops_title_line_and_truncates(self):
        text = "정책명: 가나다\n개요: " + "가" * 400
        out = sheet.candidate_summary(text)
        self.assertNotIn("정책명", out)
        self.assertTrue(out.endswith("…"))
        self.assertLessEqual(len(out), sheet.SUMMARY_CHARS + 1)

    def test_write_csv_uses_utf8_sig_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.csv"
            sheet.write_csv(path, ["a", "b"], [{"a": "한글", "b": 1}])
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig") as handle:
                self.assertEqual(list(csv.DictReader(handle))[0]["a"], "한글")


if __name__ == "__main__":
    unittest.main()
