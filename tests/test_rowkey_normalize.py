"""回归测试：行标识归一化（core/rowkey_matcher.py）。

锁死两类行为：
  A. 缺陷修复 —— 「之/及」作为**并列连词**时不得被截断，
     否则不同项目会归一化成同一个键，在 score() 里被当成精确匹配(1.0)，
     导致 align() 的 1:1 贪心无法区分而互换（静默填错值）。
  B. 能力保留（防回潮）—— V1.2.5 引入的「区段/端点」归一化不得被本次改动破坏：
     「XX路之B段」仍须收敛到「XX路」，「A至B」仍须收敛到「A」。

B 组尤其重要：修复方式是「收窄规则」而非「删除规则」，
直接删掉那行 re.sub 会让无括号的「A路之B段」失去归一能力
（_ROAD_RE 只解析「某路（A-B）」这类**括号形态**，接管不了）。
"""
import itertools

import pytest

from core.rowkey_matcher import RowKeyMatcher


# ---- 缺陷一实证样本：三个不同的「示范城市之光…」项目 ----
# 旧规则 r'[之及至到][^之及至到]*$' 会把「之」之后到串尾的整段删掉，
# 三者全部塌陷成「示范城市」。
VANKE = [
    "示范城市之光医院门诊综合楼二期项目",
    "示范城市之光商业综合体项目",
    "示范城市之光写字楼三期项目",
]


@pytest.fixture(scope="module")
def matcher():
    return RowKeyMatcher()


# ============================================================
# A 组：缺陷修复
# ============================================================

def test_vanke_projects_normalize_to_distinct_keys(matcher):
    """三个不同的「示范城市之光…」项目，归一化后必须两两不同。"""
    norms = [matcher.normalize(name) for name in VANKE]
    assert len(set(norms)) == len(VANKE), (
        f"三个不同项目归一化后发生了塌陷（静默写错值的根因）：\n"
        + "\n".join(f"  {n!r} -> {v!r}" for n, v in zip(VANKE, norms))
    )


def test_vanke_projects_not_full_width_truncated(matcher):
    """归一化结果必须保留「之」之后的实质内容，而不是被砍成「示范城市」。"""
    for name in VANKE:
        norm = matcher.normalize(name)
        assert norm != "示范城市", (
            f"{name!r} 被归一化成 '示范城市'，说明「之」后的整段被误删"
        )
        assert "之光" in norm, f"{name!r} 归一化后丢失了「之光」: {norm!r}"


def test_vanke_pairs_score_strictly_below_one(matcher):
    """两两 score 必须严格小于 1.0 —— 1.0 会被视为「精确匹配」而绕过模糊比较。"""
    for a, b in itertools.combinations(VANKE, 2):
        sc = matcher.score(a, b)
        assert sc < 1.0, (
            f"{a!r} 与 {b!r} 的 score={sc}，等于 1.0 会被判定为精确相等，"
            f"使 1:1 贪心无法区分两者"
        )


def test_vanke_self_score_is_one(matcher):
    """自身对自身仍须是 1.0（保证修复没有破坏正常精确匹配）。"""
    for name in VANKE:
        assert matcher.score(name, name) == 1.0


def test_align_maps_each_vanke_project_to_itself(matcher):
    """align() 必须把三者各自映射到自己，不发生互换。"""
    result = matcher.align(VANKE, list(VANKE))
    assert result == {name: name for name in VANKE}, (
        f"align 发生了错配（数据会被填到错误的行）：{result}"
    )


def test_align_maps_each_vanke_project_to_itself_reversed_src_order(matcher):
    """打乱源键顺序后仍须一一对应（贪心 1:1 不应受输入顺序影响）。"""
    result = matcher.align(VANKE, list(reversed(VANKE)))
    assert result == {name: name for name in VANKE}, (
        f"源键顺序打乱后 align 发生错配：{result}"
    )


# ============================================================
# A2 组：真实数据里的「及」并列结构（同类缺陷，一并锁死）
# ============================================================

@pytest.mark.parametrize("short_name, coord_name", [
    ("示例学校", "示例学校及周边道路填土夯实工程"),
    ("示范河排渍泵站", "示范河排渍泵站及配套管网建设工程"),
])
def test_coordinating_及_not_truncated(matcher, short_name, coord_name):
    """「及」作并列连词时不得截断：A 与「A及B」是两个不同项目，不得塌陷同键。"""
    assert matcher.normalize(short_name) != matcher.normalize(coord_name), (
        f"{coord_name!r} 被截断成与 {short_name!r} 相同的键"
    )


def test_phase_distinguished_after_及_removal(matcher):
    """一期 与 「二期及配套道路」不得塌陷成同一个键。"""
    a = "示范新城片保障性住房(一期)"
    b = "示范新城片保障性住房(二期)及配套道路"
    assert matcher.normalize(a) != matcher.normalize(b)


# ============================================================
# B 组：V1.2.5 既有能力防回潮
# ============================================================

@pytest.mark.parametrize("segment_name, road_name", [
    ("示范大道之南段", "示范大道"),
    ("示范南路之北段", "示范南路"),
    ("示范路之A段", "示范路"),
    ("A路之B段", "A路"),
])
def test_之_section_still_converges_to_road(matcher, segment_name, road_name):
    """「XX路之B段」仍须归一化为「XX路」（避免「B段」反向误匹配主项目）。"""
    assert matcher.normalize(segment_name) == matcher.normalize(road_name), (
        f"区段归一化能力被破坏：{segment_name!r} -> {matcher.normalize(segment_name)!r}"
        f"，期望与 {road_name!r} -> {matcher.normalize(road_name)!r} 相同"
    )


@pytest.mark.parametrize("segment_name, road_name", [
    ("示范路及示范北路段", "示范路"),
    ("示范大道及南段", "示范大道"),
])
def test_及_section_still_converges_to_road(matcher, segment_name, road_name):
    """「XX及Y段」（尾部为区段标记）也仍须收敛到主名称。"""
    assert matcher.normalize(segment_name) == matcher.normalize(road_name)


@pytest.mark.parametrize("range_name, expected", [
    ("A至B", "a"),
    ("A到B", "a"),
    ("示范大道至示范路", "示范大道"),
    ("示范大道到示范路", "示范大道"),
])
def test_range_connector_至到_still_truncates(matcher, range_name, expected):
    """「至 / 到」是真正的区间连接词，保留无条件截断：「A至B」→「A」。"""
    assert matcher.normalize(range_name) == expected, (
        f"区间截断能力被破坏：{range_name!r} -> {matcher.normalize(range_name)!r}"
    )


def test_bracket_paren_content_still_removed(matcher):
    """括号内容移除（V1.2.8 道路端点解析依赖的前置步骤）不受影响。"""
    assert matcher.normalize("某路（A路-B路）") == matcher.normalize("某路")


def test_road_endpoints_still_parsed_for_bracket_form(matcher):
    """括号形态的道路端点解析（_ROAD_RE）仍然可用。"""
    ep = RowKeyMatcher._road_endpoints("某路（A路-B路）")
    assert ep is not None
    assert ep["road"] == "某路"
    assert set(ep["ends"]) == {"a路", "b路"}


# ============================================================
# C 组：其它归一化不变量
# ============================================================

def test_fullwidth_to_halfwidth_and_case_folding(matcher):
    assert matcher.normalize("Ａ路Ｂ段") == matcher.normalize("A路B段")
    assert matcher.normalize(" 示范 城市 ") == matcher.normalize("示范城市")


def test_none_and_empty_are_safe(matcher):
    assert matcher.normalize(None) == ""
    assert matcher.normalize("") == ""
    assert matcher.score("", "某项目") == 0.0
