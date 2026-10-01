#!/usr/bin/env python3
"""retrieval_pipeline 单元测试（纯标准库，主机 python3 直接运行）。

覆盖 legacy_hybrid 迁移的检索/答案侧确定性逻辑：
flags 缺省、问题拆解、novelty 排除、RRF 归并、重排、证据评估、
实体匹配与图谱扩展、claim 核验、答案状态、知识边界、安全扫描。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import retrieval_pipeline as rp


def _rec(rid, title, score=0.5, date="2025-06", cat="电池", snippet="", url=""):
    return {"title": title, "score": score, "date": date, "category": cat,
            "body_snippet": snippet, "url": url, "source": "测试源",
            "meta": {"record_id": rid}}


class TestFlags(unittest.TestCase):
    def test_defaults_match_legacy_hybrid(self):
        flags = rp.feature_flags({})
        self.assertEqual(sum(1 for v in flags.values() if v), 21)
        for name in rp.SHIPPED_FLAG_NAMES:
            self.assertTrue(flags[name], name)
        for name in rp.EXPERIMENTAL_FLAG_NAMES:
            self.assertFalse(flags[name], name)

    def test_env_override(self):
        flags = rp.feature_flags({"QA_GRAPH_V2_ENABLED": "1",
                                  "QA_SEMANTIC_GRAPH_ENABLED": "0"})
        self.assertTrue(flags["GRAPH_V2_ENABLED"])       # 实验 flag 可显式打开
        self.assertFalse(flags["SEMANTIC_GRAPH_ENABLED"])  # shipped flag 可关闭

    def test_real_env_does_not_flip_defaults(self):
        flags = rp.feature_flags({"PATH": "/usr/bin", "QA_UNRELATED": "1"})
        self.assertEqual(sum(1 for v in flags.values() if v), 21)


class TestDecomposition(unittest.TestCase):
    def test_split_on_separators(self):
        flags = rp.feature_flags({})
        subs, trace = rp.decompose_query("固态电池进展；钠离子电池 和 氢能补贴", flags)
        self.assertTrue(trace["decomposed"])
        self.assertEqual(subs[0], "固态电池进展；钠离子电池 和 氢能补贴")
        self.assertIn("固态电池进展", subs)
        self.assertIn("钠离子电池", subs)
        self.assertIn("氢能补贴", subs)
        self.assertLessEqual(len(subs), 4)

    def test_simple_query_not_split(self):
        subs, trace = rp.decompose_query("钠离子电池最新进展", rp.feature_flags({}))
        self.assertFalse(trace["decomposed"])
        self.assertEqual(subs, ["钠离子电池最新进展"])

    def test_flag_off_keeps_single_query(self):
        flags = rp.feature_flags({"QA_DECOMPOSITION_ENABLED": "0"})
        subs, trace = rp.decompose_query("A；B 和 C", flags)
        self.assertEqual(subs, ["A；B 和 C"])
        self.assertFalse(trace["decomposed"])


class TestQueryTerms(unittest.TestCase):
    def test_ascii_and_cjk_bigrams(self):
        terms = rp.extract_query_terms("4680电池量产")
        self.assertIn("4680", terms)
        self.assertIn("电池", terms)
        self.assertIn("量产", terms)
        self.assertNotIn("了", terms)  # 多字 span 不产生单字碎片

    def test_stopgram_filtered(self):
        terms = rp.extract_query_terms("数据库里有什么资料")
        self.assertNotIn("什么", terms)


class TestNoveltyAndFusion(unittest.TestCase):
    def test_rrf_merge_prefers_multi_round_hits(self):
        a, b, c = _rec(1, "A"), _rec(2, "B"), _rec(3, "C")
        merged = rp.rrf_merge_rounds([[a, b], [b, c]])
        ids = [r["title"] for r in merged]
        self.assertEqual(ids[0], "B")  # 两路都命中 → RRF 权重最高
        self.assertIn("A", ids)
        self.assertIn("C", ids)

    def test_novelty_excludes_history_records(self):
        results = [_rec(i, f"T{i}") for i in range(1, 11)]
        kept, excluded, ids = rp.novelty_filter(results, ["1", "2", "3"])
        self.assertEqual(excluded, 3)
        self.assertEqual(len(kept), 7)
        self.assertEqual(ids, ["1", "2", "3"])

    def test_novelty_floor_restores_when_starving(self):
        results = [_rec(1, "only")]
        kept, excluded, ids = rp.novelty_filter(results, ["1"], keep_floor=5)
        self.assertEqual(excluded, 0)
        self.assertEqual(len(kept), 1)
        self.assertEqual(ids, ["floor-restore"])

    def test_novelty_noop_without_excludes(self):
        results = [_rec(1, "A")]
        kept, excluded, ids = rp.novelty_filter(results, None)
        self.assertEqual((excluded, ids), (0, []))
        self.assertEqual(kept, results)

    def test_upload_identity_exclusion(self):
        up = {"title": "上传文档", "score": 0.6, "meta": {"kind": "upload",
              "document_id": "doc-9", "chunk_id": "c1"}}
        kept, excluded, _ = rp.novelty_filter([up], ["doc-9"], keep_floor=0)
        self.assertEqual(excluded, 1)
        self.assertEqual(kept, [])


class TestRerank(unittest.TestCase):
    def test_query_coverage_reorders(self):
        flags = rp.feature_flags({})
        results = [
            _rec(1, "氢能政策补贴解读", score=0.51),
            _rec(2, "固态电池量产产线曝光", score=0.50),
        ]
        ranked, trace = rp.rerank_results(results, "固态电池量产", flags)
        self.assertTrue(trace["reranked"])
        self.assertEqual(ranked[0]["title"], "固态电池量产产线曝光")

    def test_temporal_and_ai_picked_boost(self):
        flags = rp.feature_flags({})
        results = [
            _rec(1, "钠离子电池", score=0.50, date="2021-01"),
            _rec(2, "钠离子电池", score=0.50, date="2026-01"),
        ]
        ranked, _ = rp.rerank_results(results, "钠离子电池成本", flags)
        self.assertEqual(ranked[0]["date"], "2026-01")

    def test_reranker_off_preserves_order(self):
        flags = rp.feature_flags({"QA_RERANKER_ENABLED": "0"})
        results = [_rec(1, "氢能", score=0.9), _rec(2, "固态电池量产", score=0.5)]
        ranked, trace = rp.rerank_results(results, "固态电池量产", flags)
        self.assertFalse(trace["reranked"])
        self.assertEqual([r["title"] for r in ranked], ["氢能", "固态电池量产"])

    def test_selector_cap(self):
        flags = rp.feature_flags({})
        results = [_rec(i, f"T{i}", score=0.9 - i * 0.01) for i in range(40)]
        ranked, _ = rp.rerank_results(results, "电池", flags, cap=25)
        self.assertEqual(len(ranked), 25)


class TestGraphRetrieval(unittest.TestCase):
    NODES = [("n1", "固态电池", 90), ("n2", "硫化物电解质", 40), ("n3", "宁德时代", 200),
             ("n4", "钙钛矿", 30)]
    # 邻接表契约：node_id → [(邻居标签, 关系标签)]（server._graph_index 构建时
    # 已把邻居 ID 映射为标签，关系词直接可作 BM25 词项参与召回）
    ADJ = {"n1": [("硫化物电解质", "核心材料"), ("宁德时代", "主要厂商")],
           "n2": [("固态电池", "应用方向")],
           "n3": [("固态电池", "布局方向")]}

    def test_entity_match(self):
        ents = rp.match_entities("固态电池硫化物路线进展", self.NODES)
        labels = [e["label"] for e in ents]
        self.assertIn("固态电池", labels)
        self.assertIn("硫化物电解质", labels)

    def test_expand_one_hop(self):
        ents = rp.match_entities("固态电池", self.NODES)
        labels, paths = rp.graph_expand(ents, self.ADJ)
        self.assertIn("硫化物电解质", labels)
        self.assertIn("宁德时代", labels)
        self.assertTrue(any(p["relation"] == "核心材料" for p in paths))

    def test_no_match_no_crash(self):
        ents = rp.match_entities("量子点显示", self.NODES)
        labels, paths = rp.graph_expand(ents, self.ADJ)
        self.assertEqual(labels, [])
        self.assertEqual(paths, [])


class TestEvidenceGrading(unittest.TestCase):
    def test_sufficient(self):
        results = [_rec(1, "固态电池量产", score=0.55, snippet="固态电池量产"),
                   _rec(2, "固态电池成本", score=0.45, snippet="成本"),
                   _rec(3, "固态电池设备", score=0.40, snippet="设备")]
        grade = rp.grade_evidence(results, "固态电池量产进展")
        self.assertEqual(grade["status"], "sufficient")

    def test_insufficient_empty(self):
        self.assertEqual(rp.grade_evidence([], "任意")["status"], "insufficient")

    def test_partial_weak_scores(self):
        results = [_rec(1, "氢能", score=0.12, snippet="x"), _rec(2, "氢能2", score=0.1, snippet="y")]
        grade = rp.grade_evidence(results, "完全无关的量子问题")
        self.assertEqual(grade["status"], "partial")

    def test_numeric_facts(self):
        facts = rp.numeric_facts(["能量密度达500Wh/kg", "投资50亿元", "2026年扩产3倍"])
        self.assertIn("500Wh/kg", facts)
        self.assertIn("50亿", facts)
        self.assertIn("3倍", facts)

    def test_scale_robust_across_score_ranges(self):
        # BM25 量纲（0-N）下不因绝对阈值误判：相关词覆盖 + 相对强度 → sufficient
        results = [_rec(1, "固态电池量产进展", score=8.2, snippet="固态电池量产"),
                   _rec(2, "固态电池产线", score=6.5, snippet="产线"),
                   _rec(3, "固态电池设备招标", score=5.9, snippet="设备")]
        grade = rp.grade_evidence(results, "固态电池量产进展")
        self.assertEqual(grade["status"], "sufficient")
        # 无关证据：词覆盖 0 → 即使 BM25 高分也不得 sufficient
        noise = [_rec(1, "量子点显示", score=9.0, snippet=" unrelated "),
                 _rec(2, "钙钛矿光伏", score=7.0, snippet=" nothing "),
                 _rec(3, "氢能补贴", score=6.0, snippet=" noise ")]
        self.assertEqual(rp.grade_evidence(noise, "固态电池量产进展")["status"], "partial")


class TestAnswerSide(unittest.TestCase):
    def test_claim_check_valid_and_invalid_markers(self):
        cc = rp.check_claims("产能达120GWh [1]。另一项目产能为90GWh。错误引用[9]。", 2)
        self.assertEqual(cc["invalid_markers"], [9])
        self.assertEqual(cc["cited_sentences"], 1)
        self.assertEqual(cc["factual_sentences"], 2)
        self.assertEqual(cc["claim_citation_map"][0]["citation"], [1])

    def test_claim_check_no_marks(self):
        cc = rp.check_claims("产能达120GWh但没有引用标注。", 3)
        self.assertEqual(cc["citation_marks"], 0)
        self.assertEqual(cc["cited_ratio"], 0.0)

    def test_answer_status_verified(self):
        cc = rp.check_claims("产能为120GWh [1]，成本下降[2]。", 2)
        status = rp.compute_answer_status(2, "sufficient", cc, 2)
        self.assertEqual(status, "verified")

    def test_answer_status_insufficient_no_citations(self):
        status = rp.compute_answer_status(0, "sufficient", {}, 5)
        self.assertEqual(status, "insufficient")

    def test_answer_status_partial_weak_evidence(self):
        cc = rp.check_claims("产能达120GWh [1]。", 2)
        self.assertEqual(rp.compute_answer_status(1, "partial", cc, 2), "partial")

    def test_boundary_note_levels(self):
        self.assertIn("不足", rp.boundary_note("insufficient", "partial"))
        self.assertIn("部分覆盖", rp.boundary_note("partial", "sufficient"))
        self.assertIsNone(rp.boundary_note("verified", "sufficient"))

    def test_content_safety_scan(self):
        hits = rp.content_safety_scan("配置见 /home/rhett/x.env 或 sk-abcdefghijklmn123456")
        kinds = {h["kind"] for h in hits}
        self.assertIn("local_path", kinds)
        self.assertIn("api_key", kinds)
        self.assertEqual(rp.content_safety_scan("干净的回答 [1]。"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
