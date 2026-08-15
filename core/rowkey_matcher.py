"""
行标识（项目名 / 合同名）模糊 + 同义匹配引擎  V1

解决问题：
    目标模板中的行标识（如 "示范家园三期保障性住房"）与数据源中的
    行标识（如 "示范家园三期保障房"）往往字面不同但指代同一对象。
    原 filler 仅用精确字符串相等（==）做行对齐，导致跨表对应失败。
    本模块提供归一化 + 多维相似度 + 贪心 1:1 对齐，作为行级匹配层。

匹配策略（按优先级，取最高分）：
  1. 归一化后精确相等 → 1.0
  2. 较长串包含较短串（去空白后，长度均 >=4） → 0.97
  3. 最长公共子串比例(lcs/min_len) 与 编辑距离比例(Levenshtein/difflib) 联合判定：
        若 lcs_ratio >= 0.6 且 lev_ratio >= 0.7 → 0.85~1.0
  4. 领域关键词 token 集合重合（>=2 个共享 token 且 Jaccard >= 0.5） → 0.85~0.95
  低于阈值视为不同行。

典型命中示例：
    "示范家园三期保障房"  vs  "示范家园三期保障性住房"  → 0.97（命中策略3）
"""
import re
import functools
from typing import List, Dict, Tuple, Optional

try:
    import Levenshtein
    _HAS_LEV = True
except ImportError:
    import difflib
    _HAS_LEV = False


# 常见项目名"可变"成分——这些字/词在不同单位的报表里常被增删，
# 但不改变项目指代。用于 token 提取与柔性比对。
_FLEX_TOKENS = [
    "项目", "工程", "建设", "安置", "保障", "房", "区", "县", "市", "省",
    "一期", "二期", "三期", "四期", "五期",
    "南片", "北片", "东片", "西片",
    "城东", "城西", "城南", "城北", "中心区", "示范区", "开发区", "新城区",
    "安置房", "保障房", "经济适用房", "公租房", "廉租房",
]

# 语义域关键字：用于避免「某某某项目」被错误匹配到「某某某公司」这类跨域误配。
# 注意：同一域内仍按原有模糊/同义策略匹配；域不同则直接拒绝（auto 场景下）。
_DOMAIN_KWS = {
    "project": ["项目", "工程", "立项", "子项", "标段"],
    "contract": ["合同", "协议", "合同书", "协议书"],
    "entity": ["公司", "企业", "单位", "部门", "集团"],
}

# 期次（阶段）识别：国企表中 "一期/二期/三期…" 区分不同项目，
# 不能像普通柔性 token 一样被忽略。用于行匹配时的硬约束。
_PHASE_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}
_PHASE_RE = re.compile(r'([一二三四五六七八九十\d])\s*期')

# 标段识别：第X标段 / X标段（数字或中文数字）—— 不同标段是不同对象，硬拒绝
_SECTION_MAP = {
    '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
    '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
}
_SECTION_RE = re.compile(r'第?([一二三四五六七八九十\d])\s*标段')

# 通用前后缀（V1.2.8）：这些词几乎出现在所有项目中，不能作为项目身份。
# 旧策略4 直接用 _FLEX_TOKENS（含 项目/建设…）做集合重合，导致
# 「某市旅游基础设施」与「某市省级森林公园保护性开发」
# 因共享通用词被误判为同一项目。现先剥掉这些词，仅用「身份核」比对。
_GENERIC_PREFIXES = ["示例市", "示例县", "示例省", "示例新区", "示"]
_GENERIC_SUFFIXES = [
    "旅游基础设施", "保护性开发", "基础设施", "建设项目", "建设工程",
    "工程项目", "开发项目", "项目沿线", "工程沿线", "保护性", "保障性",
    "沿线", "开发", "建设", "工程", "项目", "省级", "市级", "区级",
    "县级", "房",
]
# 道路类后缀 + 端点解析（V1.2.8）：某条路（A路-B路）↔ 某条路（B路-A路）视为同一项目
_ROAD_SUFFIX = ("路", "街", "大道", "道", "高速", "公路")
_ROAD_RE = re.compile(
    r'([^\s（(]*?(?:路|街|大道|道|高速|公路))\s*[（(]([^（）()]+)[）)]'
)


# ---- 归一化缓存（V1.3.0 性能优化）----
# normalize 在 align / best_match / compute_alignment 中对同一字符串被反复调用
# （O(n²) 配对时尤其严重：每个键在内外两层循环里各自 normalize 一次）。
# 归一化是纯函数（仅依赖输入字符串），用 lru_cache 把重复归一化降到一次，
# 复杂度由 O(n² · |s|) 降到 O((n) · |s|)（n=键数），n 大时收益显著，且不影响任何匹配结果。
@functools.lru_cache(maxsize=8192)
def _norm_core(s: str) -> str:
    s = RowKeyMatcher._fw2hw(s)
    s = re.sub(r'[（(][^）)]*[）)]', '', s)
    s = re.sub(r'[之及至到][^之及至到]*$', '', s)
    s = re.sub(r'[\s_\-]', '', s)
    return s.lower()


class RowKeyMatcher:
    """行标识模糊/同义匹配器。"""

    def __init__(self, threshold: float = 0.85):
        # 低于该分数的匹配视为"不同行"，避免误合并。
        self.threshold = threshold

    # ---- 归一化（与 matcher.py / filler.py 保持一致） ----

    @staticmethod
    def _fw2hw(text: str) -> str:
        """全角 → 半角（含全角空格 U+3000）。"""
        res = []
        for ch in text:
            c = ord(ch)
            if c == 0x3000:
                res.append(' ')
            elif 0xFF01 <= c <= 0xFF5E:
                res.append(chr(c - 0xFEE0))
            else:
                res.append(ch)
        return ''.join(res)

    @staticmethod
    def _phase_of(s: str):
        """提取名称中的期次（1/2/3…），无则返回 None。"""
        m = _PHASE_RE.search(s)
        if not m:
            return None
        ch = m.group(1)
        if ch.isdigit():
            return int(ch)
        return _PHASE_MAP.get(ch)

    @staticmethod
    def _section_of(s: str):
        """提取名称中的标段（第X标段），无则返回 None。不同标段是不同对象。"""
        m = _SECTION_RE.search(s)
        if not m:
            return None
        ch = m.group(1)
        if ch.isdigit():
            return int(ch)
        return _SECTION_MAP.get(ch)

    @staticmethod
    def _domain_of(s: str) -> Optional[str]:
        """根据关键字判断行标识的语义域（project/contract/entity/unknown）。

        判定优先级：
        - 含「合同/协议/合同书/协议书」→ contract（最明确）
        - 含「项目/工程/立项/子项/标段」→ project
        - 含「公司/企业/单位/部门/集团」→ entity
        - 无命中 → unknown
        """
        if not s:
            return None
        if any(kw in s for kw in _DOMAIN_KWS["contract"]):
            return "contract"
        if any(kw in s for kw in _DOMAIN_KWS["project"]):
            return "project"
        if any(kw in s for kw in _DOMAIN_KWS["entity"]):
            return "entity"
        return "unknown"

    def normalize(self, s: str) -> str:
        """归一化：去括号内容 → 范围连接词截断 → 全角转半角 → 折叠空白/下划线/连字符 → 小写。

        范围连接词（之/及/至/到）截断的目的是：项目名如「A路之B段」归一化为
        「A路」，避免「B段」反向误匹配主项目。
        V1.3.0：实际归一化工作委托给带 lru_cache 的模块级 _norm_core，避免重复计算。
        """
        if s is None:
            return ""
        s = str(s).strip()
        return _norm_core(s)

    # ---- 最长公共子串 ----

    @staticmethod
    def _lcs_len(a: str, b: str) -> int:
        if not a or not b:
            return 0
        prev = [0] * (len(b) + 1)
        best = 0
        for i in range(1, len(a) + 1):
            cur = [0] * (len(b) + 1)
            ai = a[i - 1]
            for j in range(1, len(b) + 1):
                if ai == b[j - 1]:
                    cur[j] = prev[j - 1] + 1
                    if cur[j] > best:
                        best = cur[j]
                else:
                    cur[j] = 0
            prev = cur
        return best

    def _lev_ratio(self, a: str, b: str) -> float:
        if _HAS_LEV:
            return Levenshtein.ratio(a, b)
        return difflib.SequenceMatcher(None, a, b).ratio()

    # ---- 领域 token ----

    def _tokens(self, s: str) -> set:
        return {t for t in _FLEX_TOKENS if t in s}

    # ---- 通用词剥离 / 道路端点（V1.2.8） ----

    @staticmethod
    def _strip_generics(s: str) -> str:
        """剥掉项目名中的通用前后缀，保留「身份核」（如 示范山、示范湖、
        示范南片三期）。通用词（项目/建设/开发…）几乎出现在所有
        项目中，不能作为项目身份。
        """
        core = s
        changed = True
        while changed:
            changed = False
            for p in _GENERIC_PREFIXES:
                if core.startswith(p) and len(core) > len(p):
                    core = core[len(p):]
                    changed = True
                    break
            if changed:
                continue
            for sfx in _GENERIC_SUFFIXES:
                if core.endswith(sfx) and len(core) > len(sfx):
                    core = core[:len(core) - len(sfx)]
                    changed = True
                    break
        return core

    @staticmethod
    def _road_endpoints(raw: str):
        """解析道路类名称中的端点，如「某条路（A路-B路）」→
        {"road": "某条路", "ends": ["A路", "B路"]}。非道路或无端点返回 None。
        """
        if not raw:
            return None
        m = _ROAD_RE.search(raw)
        if not m:
            return None
        road = RowKeyMatcher._fw2hw(m.group(1)).lower()
        road = re.sub(r'[\s_\-]', '', road)
        ends = [
            re.sub(r'[\s_\-]', '', RowKeyMatcher._fw2hw(e).lower())
            for e in re.split(r'[-~至到]', m.group(2))
        ]
        ends = [e for e in ends if e]
        if not ends:
            return None
        return {"road": road, "ends": ends}

    # ---- 核心相似度 ----

    @staticmethod
    def _code_tokens(s: str) -> list:
        """提取非中文的字母数字段（如 P10、C58、-1），用于判断编号差异。"""
        import re as _re
        return _re.findall(r'[A-Za-z0-9]+', s)

    @staticmethod
    def _longest_digit_run(s: str) -> str:
        """提取字符串中最长的连续数字串（用于跨类型行键的编号归一化）。

        例如 "2024-001 某某项目" -> "2024001"（normalize 已去连字符）；
        "XM-2024001" -> "2024001"。无数字则返回空串。
        """
        runs = re.findall(r'\d+', s)
        if not runs:
            return ""
        return max(runs, key=len)

    def score(self, a: str, b: str) -> float:
        """返回 a 与 b 的相似度 0.0~1.0。"""
        na = self.normalize(a)
        nb = self.normalize(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0

        # 期次硬约束
        pa, pb = self._phase_of(na), self._phase_of(nb)
        if pa is not None and pb is not None and pa != pb:
            return 0.0

        # 标段硬约束：两名称都含标段且标段不同 → 必为不同对象
        sa, sb = self._section_of(na), self._section_of(nb)
        if sa is not None and sb is not None and sa != sb:
            return 0.0

        # 语义域硬约束
        da, db = self._domain_of(na), self._domain_of(nb)
        if da and db and da != "unknown" and db != "unknown" and da != db:
            return 0.0

        # 道路端点倒置识别（V1.2.8）：双方都是道路类且含端点（X-Y）/（X至Y），
        # 路名相同且端点集合（顺序无关）相同 → 同一项目；否则不同项目。
        ra, rb = self._road_endpoints(a), self._road_endpoints(b)
        if ra and rb:
            if ra["road"] == rb["road"] and set(ra["ends"]) == set(rb["ends"]):
                return 0.97
            return 0.0

        # ---- 嵌入编号归一化（V1.2.8 回归修复）----
        # 跨类型行键（如目标 "2024-001 立项A" ↔ 源 "2024-001 某某项目"）字面几乎无
        # 共享字符，会被下方三道惩罚（身份核≤0.40 / 编号≤0.60 / 长度比≤0.72）死死压到
        # 0.72 以下，导致源2/3（文字名称）无法对齐到目标（数字编号）→ 整源漏填。
        # 若双方内嵌的最长连续数字编号完全一致且 ≥4 位，是极强的同一实体信号，
        # 直接给 0.92 高分并提前返回，绕过那三道过严惩罚。
        # 安全护栏：仅"数字编号精确相等且 ≥4 位"触发；仍受上方期次/标段/语义域硬约束保护。
        _dig_a = self._longest_digit_run(na)
        _dig_b = self._longest_digit_run(nb)
        if _dig_a and _dig_b and _dig_a == _dig_b and len(_dig_a) >= 6:
            return 0.92

        base = 0.0

        # 策略2：包含
        if len(na) >= 4 and len(nb) >= 4:
            if na in nb or nb in na:
                base = 0.97

        # 策略3：LCS 比例 + 编辑距离比例 联合判定
        if base < 0.97:
            lev = self._lev_ratio(na, nb)
            min_len = min(len(na), len(nb))
            lcs_ratio = (self._lcs_len(na, nb) / min_len) if min_len > 0 else 0.0
            if lcs_ratio >= 0.6 and lev >= 0.7:
                base = 0.85 + min(lev, 1.0) * 0.15

        # 策略4（V1.2.8 重写）：通用词剥离后的「身份核」相似度。
        # 旧逻辑直接用 _FLEX_TOKENS（项目/建设…）做集合重合，导致
        # 「某市旅游基础设施」与「某市省级森林公园保护性开发」
        # 因共享通用词「项目」被误判为同一项目（0.9 分）。
        # 现先剥掉通用前后缀，仅用「身份核」比对；身份核无 2 字以上共享
        # 片段则强判不同项目。
        if base < 0.85:
            ca = self._strip_generics(na)
            cb = self._strip_generics(nb)
            if ca and cb:
                core_min = min(len(ca), len(cb))
                core_lcs = self._lcs_len(ca, cb)
                core_ratio = (core_lcs / core_min) if core_min else 0.0
                core_lev = self._lev_ratio(ca, cb)
                if core_ratio >= 0.6 and core_lev >= 0.7:
                    base = 0.85 + min(core_lev, 1.0) * 0.15
                elif core_lcs < 2:
                    # 身份核几乎无重叠 → 不同项目，压到阈值以下
                    base = min(base, 0.4)

        # 兜底：极高编辑距离相似度
        if base < 0.85 and _HAS_LEV:
            lev = self._lev_ratio(na, nb)
            if lev >= 0.9:
                base = lev

        # ---- 惩罚：编号/代码差异 ----
        ca, cb = self._code_tokens(na), self._code_tokens(nb)
        if (ca or cb) and ca != cb:
            base = min(base, 0.60)  # 编号不同=不同对象，强制降为建议/未匹配

        # ---- 惩罚：长度比差异过大 ----
        maxl = max(len(na), len(nb))
        if maxl:
            lr = abs(len(na) - len(nb)) / maxl
            if lr > 0.34:
                base = min(base, 0.72)

        return base

    # ---- 最佳匹配（单目标键 vs 多源键） ----

    def best_match(
        self, target: str, candidates: List[str]
    ) -> Tuple[Optional[str], float]:
        """在 candidates 中为目标键找最佳匹配。

        Returns:
            (最佳源键, 分数) 或 (None, 最高分) 当最高分 < 阈值时。
        """
        best_key = None
        best_score = 0.0
        nt = self.normalize(target)
        t_chars = set(nt) if nt else set()
        # 【V1.3.0 性能优化】预计算归一化候选 + 字符集门控，跳过无共享字符的候选，
        # 避免对明显不匹配的配对跑昂贵 LCS/Levenshtein；阈值与正确性不变。
        norm_cands: Dict[str, str] = {}
        for c in candidates:
            if c is None or not str(c).strip():
                continue
            nc = self.normalize(c)
            if nc and nc not in norm_cands:
                norm_cands[nc] = c
        for nc, c in norm_cands.items():
            if t_chars and not (t_chars & set(nc)):
                continue
            sc = self.score(target, c)
            if sc > best_score:
                best_score = sc
                best_key = c
        if best_key is not None and best_score >= self.threshold:
            return best_key, best_score
        return None, best_score

    # ---- 贪心 1:1 行对齐（目标键集合 vs 源键集合） ----

    def align(self, tgt_keys: List[str], src_keys: List[str]) -> Dict[str, str]:
        """返回 {tgt_key: src_key}，保证每个源键最多被一个目标键占用。

        用于避免两个目标行模糊命中同一个源行。精确相等（归一化后）
        自然获得最高分，因此原精确匹配行为被完整保留。
        """
        # 【V1.3.0 性能优化】预计算归一化源键及其字符集合，避免 O(n²) 配对中对同一
        # 个键反复 normalize；并用「无共享字符则不可能达阈值(0.85)」的廉价预筛跳过
        # 必然不匹配的配对，仅在快速通道无法判定时才跑完整 score。阈值(0.85)与匹配
        # 正确性不变，仅提速。
        # 复杂度：原 align = O(|T|·|S|) 次 score，每次 score 含 O(L²) 的 LCS +
        # Levenshtein（L=键长）；优化后 normalize 预计算 O(|T|+|S|)、字符集门控把
        # 完整 score 的调用量从 |T|·|S| 降到「有共享字符的候选对」k（k ≪ |T|·|S|），
        # 整体约 O((|T|+|S|)·L + k·L²)。
        # 注意：按「原始源键」去重（而非按归一化值），否则两个归一化后相同但字面不同的
        # 源键（如 "白庭路" 与 "白庭路（...）"）会被合并，破坏 1:1 贪心分配。
        src_norm = []  # [(原始源键, 归一化值, 字符集合)]
        seen_s = set()
        for s in src_keys:
            if s is None or not str(s).strip() or s in seen_s:
                continue
            seen_s.add(s)
            ns = self.normalize(s)
            if not ns:
                continue
            src_norm.append((s, ns, set(ns)))

        pairs = []
        for t in tgt_keys:
            if not t or not t.strip():
                continue
            nt = self.normalize(t)
            if not nt:
                continue
            t_chars = set(nt)
            for s, ns, nchars in src_norm:
                # 廉价预筛：归一化后完全无共享字符 → 不可能达 0.85（LCS=0、lev=0，
                # 且 digit-run / code-token 等加分路径也因共享数字/字母而被保留，
                # 不会误杀），直接跳过完整 score。
                if not (t_chars & nchars):
                    continue
                sc = self.score(t, s)
                if sc >= self.threshold:
                    pairs.append((t, s, sc))
        pairs.sort(key=lambda x: -x[2])
        used_src: set = set()
        result: Dict[str, str] = {}
        for t, s, _sc in pairs:
            if t in result:
                continue
            if s in used_src:
                continue
            result[t] = s
            used_src.add(s)
        return result
