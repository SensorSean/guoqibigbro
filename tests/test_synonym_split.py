"""回归测试：同义词词典「项目负责人」/「项目经理」分组（缺陷二）。

背景：这两个字段在真实数据里是**两列、两个不同的人**。旧版把它们
（连同 项目责任人、法人代表）放在同一个同义词组里，于是匹配目标列
「项目负责人」时，源列「项目经理」会因同义获得并列满分 95.0，
在源表没有同名「项目负责人」列时被按列顺序选中 → 整列填成错的人。

⚠️ 本测试同时覆盖**两处**分组来源，缺一不可：
  1. core/matcher.py 的写死 STRICT_SYNONYMS（**真正的根因**——
     即使完全不加载用户词典，旧版也会给出 95.0）
  2. 项目根的 同义词词典.json（用户可见、可被前端编辑并持久化）

只改 JSON 而不改写死列表，缺陷不会消失，这一点由
test_no_shared_group_BUILTIN_only 锁死。
"""
import json
import os

import pytest

from core.matcher import FieldMatcher, STRICT_SYNONYMS
from core.matcher import _get_dict_path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_DICT_PATH = os.path.join(PROJECT_ROOT, "同义词词典.json")
DIST_DICT_PATH = os.path.join(PROJECT_ROOT, "dist", "同义词词典.json")


# ============================================================
# 夹具
# ============================================================

@pytest.fixture(scope="module")
def user_dict_raw():
    """加载项目根的用户同义词词典 JSON（synonyms 段）。"""
    with open(USER_DICT_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return raw["synonyms"]


@pytest.fixture(scope="module")
def matcher_builtin():
    """仅写死内置词典，不加载用户词典。"""
    return FieldMatcher()


@pytest.fixture(scope="module")
def matcher_with_dict():
    """写死内置词典 + 用户词典。"""
    m = FieldMatcher()
    ok, msg = m.load_user_dict(USER_DICT_PATH)
    assert ok, f"用户词典加载失败: {msg}"
    return m


def _effective_groups(matcher):
    """把「组的 KEY 本身也算作成员」展开后的有效分组集合。

    依据 core/matcher.py::load_user_dict：terms = [std_key] + syns，
    即标准词 KEY 是组的第 0 个成员；_build_synonym_closure 亦把 group[0]
    作为规范键并让全部成员（含 group[0] 自身）映射过去。
    """
    return [set(group) for group in matcher._synonym_groups]


# ============================================================
# A 组：两个字段不得同组
# ============================================================

def test_no_shared_group_in_user_json(user_dict_raw):
    """用户词典中，「项目负责人」与「项目经理」不得出现在同一个组里。"""
    for key, syns in user_dict_raw.items():
        members = {key, *syns}
        if "项目负责人" in members:
            assert "项目经理" not in members, (
                f"用户词典分组 {key!r} 同时包含「项目负责人」与「项目经理」: {sorted(members)}"
            )


def test_no_shared_group_effective(matcher_with_dict):
    """叠加用户词典后的有效分组中，二者不得同组（KEY 本身须按成员计）。"""
    for group in _effective_groups(matcher_with_dict):
        if "项目负责人" in group:
            assert "项目经理" not in group, f"有效分组同时包含二者: {sorted(group)}"


def test_no_shared_group_BUILTIN_only(matcher_builtin):
    """纯写死内置词典（不加载用户词典）也不得同组 —— 这是原缺陷的真正根因。"""
    for group in _effective_groups(matcher_builtin):
        if "项目负责人" in group:
            assert "项目经理" not in group, (
                f"写死 STRICT_SYNONYMS 分组同时包含二者: {sorted(group)}"
            )


def test_score_between_them_is_zero(matcher_with_dict):
    """二者相似度必须归零，不再触发同义满分（旧值 95.0）。"""
    assert matcher_with_dict.score_field("项目负责人", "项目经理") == 0.0
    assert matcher_with_dict.score_field("项目经理", "项目负责人") == 0.0


def test_score_between_them_is_zero_builtin_only(matcher_builtin):
    """纯内置时同样必须归零。"""
    assert matcher_builtin.score_field("项目负责人", "项目经理") == 0.0


def test_target_项目负责人_not_automatched_to_source_项目经理(matcher_with_dict):
    """缺陷场景：源表只有「项目经理」列时，目标「项目负责人」不得被自动匹配过去。"""
    srcs = [{"name": "项目经理", "source_file": "S", "source_sheet": "1"}]
    results = matcher_with_dict.auto_match(srcs, ["项目负责人"])
    assert len(results) == 1
    assert results[0]["matched"] is False, (
        f"目标「项目负责人」被自动匹配到源「项目经理」，整列会填成错的人"
        f"（confidence={results[0]['confidence']}）"
    )


# ============================================================
# B 组：拆分后原本正确的能力必须保留
# ============================================================

def test_负责人_still_resolves_to_项目负责人(matcher_with_dict):
    """「负责人」仍须解析到「项目负责人」。"""
    assert matcher_with_dict.score_field("负责人", "项目负责人") >= 85.0
    assert matcher_with_dict.score_field("项目负责人", "负责人") >= 85.0


def test_负责人_still_resolves_to_项目负责人_builtin_only(matcher_builtin):
    assert matcher_builtin.score_field("负责人", "项目负责人") >= 85.0


def test_项目经理_exact_match_is_perfect(matcher_with_dict):
    """目标「项目经理」仍须精确命中源「项目经理」（100 分）。"""
    assert matcher_with_dict.score_field("项目经理", "项目经理") == 100.0
    srcs = [
        {"name": "技术负责人", "source_file": "S", "source_sheet": "1"},
        {"name": "项目经理", "source_file": "S", "source_sheet": "1"},
    ]
    results = matcher_with_dict.auto_match(srcs, ["项目经理"])
    assert results[0]["src_field"] == "项目经理"
    assert results[0]["confidence"] == 100.0


def test_项目经理_variants_still_grouped(matcher_with_dict):
    """「项目经理」的变体写法仍与其同组。"""
    for variant in ("项目经理人", "项目经手人"):
        assert matcher_with_dict.score_field("项目经理", variant) >= 85.0, (
            f"变体 {variant!r} 未与「项目经理」同组"
        )


# ============================================================
# C 组：法人代表 / 项目责任人的归属
# ============================================================

def test_法人代表_has_its_own_group(matcher_with_dict):
    """「法人代表」移出负责人组后，仍须有自己独立的组并保持可解析。"""
    groups = [g for g in _effective_groups(matcher_with_dict) if "法人代表" in g]
    assert groups, "「法人代表」失去了所有同义词组，将无法匹配"
    # 不得与项目负责人/项目经理 重新耦合
    for g in groups:
        assert "项目负责人" not in g
        assert "项目经理" not in g
    assert matcher_with_dict.score_field("法人代表", "法定代表人") >= 85.0


def test_项目责任人_still_resolvable(matcher_with_dict):
    assert matcher_with_dict.score_field("项目责任人", "责任人") >= 85.0


def test_法人代表_not_synonym_of_项目经理(matcher_with_dict):
    assert matcher_with_dict.score_field("法人代表", "项目经理") == 0.0


# ============================================================
# D 组：dist 编译副本一致性
# ============================================================

@pytest.mark.skipif(
    not os.path.isfile(DIST_DICT_PATH),
    reason="dist/同义词词典.json 不存在（尚未构建过 exe）",
)
def test_dist_copy_in_sync_with_source():
    """dist/ 下的编译副本须与源文件一致（spec/build_exe_v4.py 构建时复制）。

    两份不一致会导致「改了源码但打包产物仍是旧词典」的静默回潮。
    """
    with open(DIST_DICT_PATH, "r", encoding="utf-8") as f:
        dist_raw = json.load(f)
    with open(USER_DICT_PATH, "r", encoding="utf-8") as f:
        src_raw = json.load(f)
    assert dist_raw == src_raw, "dist/同义词词典.json 与源词典不一致"


# ============================================================
# E 组：词典整体结构健康度
# ============================================================

def test_dict_loads_without_error_and_discovery_path(matcher_with_dict):
    """词典路径可被发现，且加载无错。"""
    path = _get_dict_path()
    assert path and os.path.isfile(path)


def test_no_group_contains_both_负责人_family_and_项目经理(user_dict_raw):
    """整份词典层面兜底：任何组都不得同时含「负责人」与「项目经理」。"""
    bad = []
    for key, syns in user_dict_raw.items():
        members = {key, *syns}
        if "负责人" in members and "项目经理" in members:
            bad.append(sorted(members))
    assert not bad, f"存在同时含「负责人」与「项目经理」的分组: {bad}"


def test_builtin_groups_are_non_empty_lists():
    """写死分组结构未被误改（每组至少 1 个成员、且是字符串列表）。"""
    assert isinstance(STRICT_SYNONYMS, list) and len(STRICT_SYNONYMS) > 100
    for g in STRICT_SYNONYMS:
        assert isinstance(g, list) and len(g) >= 1
        assert all(isinstance(t, str) and t.strip() for t in g)
