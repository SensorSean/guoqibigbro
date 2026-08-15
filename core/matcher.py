"""
字段模糊匹配引擎 V8（增强版：3遍归一化预处理 + 同义词组 + Levenshtein + 分词 + 单位检测）

基于 guoqi-bigbro V7，新增来自国产大表哥的三遍归一化预处理：
  Pass 1: 全角→半角转换（U+FF01-U+FF5E → U+0021-U+007E，全角空格 U+3000 → U+0020）
  Pass 2: 折叠所有连续空白为单个空格（作为匹配第一候选）
  Pass 3: 去除所有空白（作为匹配第二候选）

V1.3.2 新增：可持久化用户同义词词典（exe 同目录 同义词词典.json），
由 main.py 在启动时 load、运行时 save/import/export/reload。
"""
import os
import re
import sys
import json
from typing import List, Dict, Any

try:
    import Levenshtein
    _HAS_LEVENSHTEIN = True
except ImportError:
    import difflib
    _HAS_LEVENSHTEIN = False

MatchResult = Dict[str, Any]


class UserDictError(Exception):
    """用户同义词词典加载/解析/校验失败（前端据此 Toast 提示）。"""
    pass


# 用户同义词词典文件名（固定，落于 exe 同目录，用户可见可读写）
USER_DICT_FILENAME = "同义词词典.json"


def _get_dict_path():
    """返回用户同义词词典的绝对路径。

    查找顺序（首个命中即用）：
    1. exe / python 所在目录（生产：exe 同目录）
    2. 当前工作目录 cwd（开发调试、用户从工程目录启动）
    3. 本模块文件所在目录的上级（源码开发：工程根目录）
    ⚠️ 绝不使用 sys._MEIPASS：那是 PyInstaller 解压的临时目录，用户不可见且只读。
    """
    fname = USER_DICT_FILENAME
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(sys.executable)), fname),
        os.path.join(os.getcwd(), fname),
    ]
    # 源码开发：从 core/matcher.py 往上两级找工程根
    try:
        _mod_dir = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(_mod_dir, fname))           # core/
        candidates.append(os.path.join(os.path.dirname(_mod_dir), fname))  # 工程根
    except Exception:
        pass
    for p in candidates:
        if os.path.isfile(p):
            return p
    # 都没找到，返回 exe 目录路径（保持向后兼容，让 load_user_dict 打"不存在"日志）
    return candidates[0]


STRICT_SYNONYMS = [
    ["项目名称", "项目名", "工程名称", "立项项目", "立项项目名称", "项目名称及编码"],
    ["项目编号", "项目号", "项目代码", "编码", "项目编码"],
    ["项目类型", "项目类别", "项目性质", "建设性质", "项目细分类型"],
    ["投资类型", "投资类别", "投资性质", "投资方式", "投资种类", "投资方向"],
    ["所属片区", "所属区域", "项目片区", "片区"],
    ["项目公司所属母公司", "项目公司", "母公司", "上级公司", "集团母公司", "上级单位"],
    ["子项目名称", "子项目", "子项目名", "子项名称", "分项工程名称", "分项名称"],
    ["项目级别", "项目等级", "项目层级"],
    ["建设单位", "业主单位", "项目业主", "甲方", "建设方"],
    ["施工单位", "承包商", "施工方", "乙方", "承建单位", "施工总承包单位"],
    ["设计单位", "设计方", "设计院", "可研报告编制单位", "可研编制单位", "初设单位", "勘察设计单位"],
    ["监理单位", "监理方", "监理公司", "监理工程师"],
    ["审计单位", "审计机构", "造价咨询单位"],
    ["主管单位", "主管部门", "行业主管部门", "归口部门", "监管单位"],
    ["负责人", "项目负责人", "项目经理", "项目责任人", "法人代表"],
    ["联系人", "联系人姓名", "经办人", "经办人姓名", "联系方式"],
    ["联系电话", "联系方式", "电话", "手机号码", "手机号"],
    ["立项时间", "立项日期", "项目立项时间", "立项批复时间"],
    ["批复时间", "审批时间", "批复日期", "批准时间", "核准日期"],
    ["开工时间", "开工日期", "实际开工时间", "实际开工日期", "开工令日期"],
    ["竣工时间", "竣工日期", "完工时间", "实际竣工时间", "实际竣工日期", "竣工验收时间"],
    ["计划开工时间", "计划开工日期", "预计开工时间"],
    ["计划竣工时间", "计划竣工日期", "预计竣工时间"],
    ["工期", "建设工期", "施工工期", "合同工期"],
    ["立项文号", "立项编号", "立项审批文号", "立项批准文号"],
    ["批复文号", "审批文号", "批准文号", "批复编号", "审批编号"],
    ["概算金额", "概算", "工程概算", "概算总投资", "设计概算", "初步设计概算"],
    ["预算金额", "预算", "工程预算", "年度预算", "施工图预算", "招标预算"],
    ["决算金额", "决算", "工程决算", "竣工决算", "财务决算", "结算"],
    ["总投资", "总金额", "项目总投资", "投资额", "项目投资总额"],
    ["合同金额", "合同价", "中标金额", "中标价", "合同总价"],
    ["工程费用", "建设费用", "项目费用", "建筑安装工程费", "工程总投资"],
    ["资金到位情况", "到位资金", "已拨付资金", "已完成投资"],
    ["地址", "地点", "所在地", "建设地点", "项目地址", "项目所在地"],
    ["建设规模", "项目规模", "规模", "建设内容", "主要建设内容", "建设规模及内容"],
    ["建筑面积", "总面积", "占地面积", "用地面积", "总建筑面积", "建筑总面积", "地上建筑面积"],
    ["状态", "当前状态", "项目状态", "进展", "进展状况"],
    ["备注", "说明", "描述", "备注说明", "其他说明", "情况说明"],
    ["序号", "编号", "行号", "NO"],
    ["年度", "年份", "所属年度", "计划年度"],
    ["资金来源", "出资方式", "资金筹措", "资金构成", "建设资金来源", "投资来源"],
    ["招标方式", "采购方式", "发包方式"],
    ["质量等级", "质量目标", "质量标准"],
    ["安全目标", "安全生产目标"],
    # ---- v8 新增同义词组：工程领域扩展 ----
    ["可研批复文号", "可研报告批复文号", "可研文号", "可研报告文号", "可研审批文号", "可研批复编号"],
    ["可研批复时间", "可研报告批复时间", "可研审批时间", "可研报告审批时间", "可研日期"],
    ["初设批复文号", "初步设计批复文号", "初设文号", "初设审批文号", "初设批准文号"],
    ["初设批复时间", "初步设计批复时间", "初设审批时间", "初设日期", "初步设计审批时间"],
    ["施工图审查", "施工图审查文号", "施工图审查时间", "施工图审查意见"],
    ["项目建议书", "项目建议书文号", "项目建议书批复文号", "建议书文号"],
    ["立项批复", "立项批复文号", "立项批文", "立项文件", "立项批复文件"],
    ["估算金额", "估算", "投资估算", "项目估算", "估算投资", "估算总投资"],
    ["结算金额", "结算", "工程结算", "竣工结算", "结算价", "竣工决算"],
    ["建安费", "建安工程费", "建筑安装工程费", "建安投资", "建筑安装费"],
    ["费用描述", "费用简要描述", "费用说明", "费用组成", "费用构成", "工程费用说明"],
    ["附件", "附件清单", "附件材料", "扫描件", "附件名称", "附件内容"],
    ["可研报告", "可行性研究报告", "可研报告名称", "可行性研究", "可研文件"],
    ["初设报告", "初步设计报告", "初步设计文件", "初设文件", "初设报告名称"],
    ["评估报告", "评估意见", "评估结论", "评估摘要", "项目评估"],
    ["论证报告", "论证意见", "专家论证", "论证结论"],
    ["财政资金", "财政拨款", "财政投资", "财政预算资金", "财政性资金"],
    ["自筹资金", "自筹", "自筹投资", "自有资金", "单位自筹"],
    ["银行贷款", "贷款", "银行借款", "融资", "信贷资金"],
    ["国债", "国债资金", "国债投资", "转贷国债"],
    ["土地出让金", "土地收益", "土地纯收益", "土地开发净收益"],
    ["用地面积", "占地面积", "用地规模", "红线面积", "土地面积"],
    ["容积率", "建筑容积率", "规划容积率"],
    ["建筑密度", "建筑系数", "密度"],
    ["绿地率", "绿化率", "绿地比例"],
    ["可研时间", "可研日期", "可研编制时间", "可研报告编制时间"],
    ["评估时间", "评估日期", "评审时间", "评审日期", "审查时间"],
    ["设计时间", "设计完成时间", "设计日期", "设计阶段", "施工图完成时间"],
    ["法人代表", "法人", "法定代表人", "项目法人", "单位法人"],
    ["项目责任人", "责任人", "项目主管", "分管领导", "项目联络人"],
    # ---- v9 新增：工程建设报表字段大总表（建筑行业）同义词组 ----
    # 一、项目基础信息
    ["项目全称", "项目名称", "工程项目名称", "立项项目名称", "项目全称及编码"],
    ["建设单位全称", "建设单位", "项目建设单位", "单位名称", "项目单位", "业主单位", "甲方", "建设方"],
    ["所属领域", "专业类别", "工程领域", "行业领域"],
    ["建设地点", "建设地址", "项目地址", "项目详细地址", "项目所在地", "建设地点地址", "地点", "地址"],
    ["项目联系人", "联系人及电话", "单位联系人", "联系手机号码", "项目联系人及电话", "联系人", "经办人"],
    ["起止年限", "建设起止年限", "项目起止年限"],
    # 二、投资金额
    ["总投资额", "总投资", "项目总投资", "项目投资总额", "预估总投资", "投资总额"],
    ["征拆投资", "征地拆迁投资", "征拆投资额", "拆迁投资", "征地投资"],
    ["建设投资不含征拆", "建设投资", "不含征拆建设投资", "建设投资不含征地拆迁"],
    ["年度计划投资", "年度建设目标", "年计划投资", "年度投资计划", "年度投资"],
    ["当月完成投资", "月完成投资", "月度完成投资", "本月完成投资", "当月投资"],
    ["累计完成投资", "开工至年底累计", "累计投资", "累计完成投资额", "累计完成投资"],
    ["方案投资估算", "投资估算", "估算投资", "方案估算", "估算金额"],
    ["概算批复金额", "概算编制金额", "批复概算", "概算批复", "概算金额"],
    ["结算审定金额", "结算金额", "审定金额", "结算审定", "审定结算金额"],
    ["已支付金额", "本合同已支付金额", "已支付", "已付金额", "已付款"],
    ["送审金额", "报送金额", "送审价", "报送结算金额"],
    ["审减金额", "审减额", "审减", "审减造价"],
    # 三、审批里程碑
    ["规划许可证办理状态", "规划许可证", "规划许可状态", "工规证", "工程规划许可证"],
    ["征拆完成状态", "征地状态", "征拆完成", "征地完成状态", "征地完成情况"],
    ["施工图审查备案", "施工图审查", "施工图审查备案完成", "施工图备案", "施工图审查意见"],
    ["招标控制价批复", "控制价批复", "招标上限值评审", "上限值批复", "招标控制价"],
    ["施工招标开标", "EPC招标开标", "施工/EPC招标开标", "招标开标", "开标"],
    ["资金来源论证", "资金来源论证完成", "资金论证", "资金来源论证状态"],
    ["是否开工", "开工状态", "开工与否", "已开工", "开工情况"],
    # 四、合同与招采
    ["合同名称", "合同标题", "合同名目", "合同名字"],
    ["合同编号", "合同号", "合同编码"],
    ["合同甲方", "甲方", "发包方", "建设单位甲方"],
    ["合同相对方", "相对方", "乙方", "承包方", "合同乙方"],
    ["合同签订日期", "合同签署日期", "签订日期", "合同日期", "签署日期"],
    ["补充协议金额", "补充协议金额", "补充金额", "补充协议额"],
    ["采购类别", "采购类型", "采购方式", "工程类/货物类/服务类"],
    # 五、参建单位
    ["勘察单位", "地质勘察单位", "勘测单位", "地质勘查单位"],
    ["设计监理单位", "设计监理", "设计监理单位名称"],
    ["编制事务所", "造价编制事务所", "编制单位", "造价咨询单位", "造价事务所"],
    ["一审事务所", "初审事务所", "一审单位"],
    ["二审事务所", "复审事务所", "二审单位"],
    ["审核事务所", "审计事务所", "审核单位"],
    # 六、进度与时效
    ["完成比例", "完成率", "进度比例", "形象进度比例", "工程完成比例"],
    ["主要存在问题", "存在问题", "主要问题", "问题描述", "工程问题"],
    ["计划完成节点数", "计划节点数", "计划完成节点", "计划节点"],
    ["实际完成节点数", "实际节点数", "实际完成节点", "实际节点"],
    ["滞后完成节点数", "滞后节点数", "滞后完成节点", "延迟节点数", "滞后节点"],
    ["形象进度描述", "项目形象进度", "截至月底项目形象进度", "形象进度", "工程形象进度"],
    ["编制开始时间", "开始编制时间", "编制启动时间"],
    ["编制完成时间", "完成编制时间", "编制结束时间"],
    ["是否超时", "超时状态", "是否逾期", "超时"],
    ["时效说明", "超时原因", "时效备注", "逾期原因"],
    ["进窗时间", "送审窗口时间", "进窗", "送审时间"],
    ["一审审减率", "初审审减率", "一审审减", "初审审减率"],
    ["二审审减率", "复审审减率", "二审审减", "复审审减率"],
    # 七、资金与财务
    ["双控金额", "双控", "资金双控金额"],
    ["非双控金额", "非双控", "非双控资金"],
    ["已付款比例", "付款比例", "支付比例", "已支付比例"],
    ["收付款情况", "收付款", "款项情况", "收付款状态"],
    ["最近一次申请金额", "最近申请金额", "本次申请金额", "最近申请额"],
    ["财务流程进度", "财务进度", "付款流程进度", "财务流程"],
    ["结算状态", "结算办理状态", "结算进度", "结算情况"],
    # 八、质量与责任
    ["总误差率", "误差率", "总体误差率", "累计误差率"],
    ["建设单位责任", "建设建设单位责任", "业主责任", "甲方责任"],
    ["事务所责任", "造价事务所责任", "咨询单位责任"],
    ["其他责任", "第三方责任"],
    ["责任划分", "责任归属", "责任判定"],
    ["项目分级", "第一类/第二类/第三类", "项目类别", "项目等级"],
    ["实施单位结算送审情况", "实施单位送审情况", "送审情况", "实施单位结算送审"],
    ["子公司审核情况", "子公司审核", "审核情况"],
    ["资料编号", "档案编号", "资料序号"],
    # 九、方案设计阶段
    ["方案比选数量", "比选数量", "方案数量", "方案数"],
    ["比选结论", "方案比选结论", "比选结果", "方案比选结果"],
    ["初勘成果质量确认", "初勘质量确认", "勘察质量确认", "初勘成果确认"],
    ["方案内审结论", "内审结论", "方案内审", "内审结果"],
    ["内审意见数量", "内审意见数", "内审轮次", "内审意见"],
    ["接收方确认结果", "接收方确认", "接收确认结果", "接收方确认"],
    ["方案编制实际工期", "方案编制工期", "方案实际工期", "方案编制时间"],
]


class FieldMatcher:
    """字段模糊匹配引擎。

    支持能力：
      - 全角→半角转换（3遍归一化预处理）
      - 100+ 组工程/建筑行业术语同义词
      - Levenshtein 编辑距离（difflib 后备）
      - 中文关键词分词匹配
      - 单位冲突检测（如"万元" vs "元"）
      - 排除规则（exclusions）：硬拦截指定字段对
      - 字段语义分类 + 跨类惩罚
    """

    # ---- 字段语义分类（V1.3.1 新增） ----
    # 用于在匹配时施加跨类惩罚，防止地名/路名被错误匹配到项目/公司类字段。

    # 位置/地名类特征词（含路名后缀、行政区划等）
    _LOCATION_MARKERS = (
        "路", "街", "大道", "道", "巷", "弄", "胡同",
        "片区", "区", "县", "市", "省", "乡", "镇", "村",
        "环线", "高速", "公路", "桥", "隧道", "涵洞",
    )
    # 项目/工程类特征词
    _PROJECT_MARKERS = (
        "项目", "工程", "立项", "子项", "标段", "建设",
    )
    # 实体/公司类特征词
    _ENTITY_MARKERS = (
        "公司", "企业", "单位", "集团", "部门", "机构",
        "事务所", "设计院",
    )
    # 金额/数值类特征词
    _AMOUNT_MARKERS = (
        "金额", "投资", "费用", "预算", "概算", "决算",
        "结算", "估算", "万元", "元",
    )
    # 日期类特征词
    _DATE_MARKERS = (
        "时间", "日期", "年限", "工期",
    )

    @classmethod
    def _field_category(cls, name: str) -> str:
        """分类字段语义类别。

        Returns one of: 'location', 'project', 'entity', 'amount', 'date', 'general'
        """
        if not name:
            return "general"
        s = str(name)
        # 检查各类特征词（按优先级：越具体的越先判定）
        has_location = any(m in s for m in cls._LOCATION_MARKERS)
        has_project = any(m in s for m in cls._PROJECT_MARKERS)
        has_entity = any(m in s for m in cls._ENTITY_MARKERS)
        has_amount = any(m in s for m in cls._AMOUNT_MARKERS)
        has_date = any(m in s for m in cls._DATE_MARKERS)

        # 纯位置特征（无项目/公司特征）→ location
        if has_location and not has_project and not has_entity:
            return "location"
        # 纯项目特征 → project
        if has_project and not has_entity:
            return "project"
        # 实体特征 → entity
        if has_entity:
            return "entity"
        if has_amount:
            return "amount"
        if has_date:
            return "date"
        return "general"

    # ---- 排除规则（V1.3.1 新增） ----
    # 跨类排除规则：当源字段与目标字段属于不同的「硬排斥」语义类别对时，
    # 即使算法得分高也强制归零。这些类别对在业务上不可能匹配。
    # 例如：地名→项目名、公司名→编号、地址→公司名。
    _CROSS_CATEGORY_EXCLUSIONS = frozenset({
        ("location", "project"),
        ("location", "entity"),
        ("location", "amount"),
        ("entity", "amount"),
        ("entity", "date"),
    })

    def __init__(self):
        self._synonym_map = {}
        self._synonym_groups = STRICT_SYNONYMS
        self._user_dict = {}  # 当前内存中的用户同义词词典（标准词→同义词数组）
        self._exclusion_pairs = []  # [(norm_a, norm_b), ...] 用户词典排除规则
        self._cross_category_enabled = True  # 跨类惩罚开关
        self._build_synonym_closure()
        self._sim_cache = {}
        # 预计算同义词组的归一化集合：避免每次匹配重复归一化 56 组词（原 hot path）
        self._synonym_group_sets = [
            set(self._normalize(g, remove_whitespace=True) for g in group)
            for group in self._synonym_groups
        ]

    # ---- 排除规则加载 ----

    def _load_exclusions(self, raw_dict: dict):
        """从用户词典 JSON 中加载排除规则。

        排除规则格式：
          {"exclusions": [{"a": "示范路", "b": "项目名称", "reason": "..."}, ...]}

        双向归一化保存，匹配时任一方向命中即拦截。
        """
        exclusions_raw = raw_dict.get("exclusions", [])
        if not isinstance(exclusions_raw, list):
            return
        self._exclusion_pairs = []
        for item in exclusions_raw:
            if not isinstance(item, dict):
                continue
            a = (item.get("a") or "").strip()
            b = (item.get("b") or "").strip()
            if not a or not b:
                continue
            # 归一化存储，与 _calc_similarity 中的归一化版本一致
            na = self._normalize(a, remove_whitespace=True)
            nb = self._normalize(b, remove_whitespace=True)
            if na and nb and na != nb:
                self._exclusion_pairs.append((na, nb))
        if self._exclusion_pairs:
            print(f"[INFO] 加载排除规则：{len(self._exclusion_pairs)} 条")

    def _check_exclusions(self, src: str, tgt: str) -> bool:
        """检查 (src, tgt) 是否被排除规则命中。

        匹配方式：归一化后的 src/tgt 与排除规则中的 (a,b) 双向比对。
        支持部分匹配：若 src 的末段（复合字段拆解后）或 tgt 的末段命中规则，同样拦截。

        Returns:
            True  = 被规则禁止，得分应强制归零
            False = 未命中规则，可继续正常匹配
        """
        if not self._exclusion_pairs:
            return False
        sn = self._normalize(src, remove_whitespace=True)
        tn = self._normalize(tgt, remove_whitespace=True)
        if not sn or not tn:
            return False
        # 同时检查末段（复合字段拆解后）
        sn_short = self._normalize(self._last_segment(src), remove_whitespace=True) if '>' in (src or '') else sn
        tn_short = self._normalize(self._last_segment(tgt), remove_whitespace=True) if '>' in (tgt or '') else tn
        for a, b in self._exclusion_pairs:
            if (a == sn and b == tn) or (a == tn and b == sn):
                return True
            if (a == sn_short and b == tn_short) or (a == tn_short and b == sn_short):
                return True
            # 部分包含检查：若排除规则中的 a 完全包含在 src 归一化名中，
            # 且 b 完全包含在 tgt 归一化名中（或反之），也拦截
            if (a in sn and b in tn) or (a in tn and b in sn):
                return True
        return False

    def _check_cross_category(self, src: str, tgt: str) -> bool:
        """检查源与目标是否属于互斥语义类别。

        若两者分类不同且属于硬排斥对，返回 True（应降低匹配分）。
        注意：仅当双方分类都≠'general'时才检查，避免误伤。

        Returns:
            True  = 跨类排斥，应施加惩罚
            False = 同类或至少一方为 general，正常匹配
        """
        if not self._cross_category_enabled:
            return False
        cat_src = self._field_category(src)
        cat_tgt = self._field_category(tgt)
        if cat_src == "general" or cat_tgt == "general":
            return False
        if cat_src == cat_tgt:
            return False
        pair = (cat_src, cat_tgt)
        return pair in self._CROSS_CATEGORY_EXCLUSIONS or (cat_tgt, cat_src) in self._CROSS_CATEGORY_EXCLUSIONS

    # ---- 3遍归一化预处理（来自国产大表哥） ----

    @staticmethod
    def _fullwidth_to_halfwidth(text: str) -> str:
        """将全角字符转换为半角字符。

        处理范围：
          - U+3000 (全角空格) → U+0020 (半角空格)
          - U+FF01-U+FF5E (全角标点/字母/数字) → U+0021-U+007E

        Args:
            text: 可能包含全角字符的字符串

        Returns:
            转换后的半角字符串
        """
        result = []
        for ch in text:
            code = ord(ch)
            if code == 0x3000:          # 全角空格
                result.append(' ')
            elif 0xFF01 <= code <= 0xFF5E:  # 全角 ASCII 范围
                result.append(chr(code - 0xFEE0))
            else:
                result.append(ch)
        return ''.join(result)

    def _normalize(self, s: str, remove_whitespace: bool = True) -> str:
        """标准化字段名。

        流程：
          1. 全角→半角转换 (Pass 1)
          2. 提取括号内单位信息
          3. 空白处理：
             - remove_whitespace=True  → 去除所有空白/下划线/连字符 (Pass 3)
             - remove_whitespace=False → 折叠连续空白为单空格 (Pass 2)
          4. 转小写
          5. 附加单位后缀

        Args:
            s: 原始字段名
            remove_whitespace: True=去空白(匹配候选2), False=折叠空白(匹配候选1)

        Returns:
            标准化后的字段名
        """
        s = str(s).strip()
        if not s:
            return ""

        # Pass 1: 全角→半角转换
        s = self._fullwidth_to_halfwidth(s)

        # 提取括号内的单位信息（如"金额（万元）"→提取"万元"）
        unit_in_paren = ""
        paren_match = re.search(r'[（(]([^）)]*)[）)]', s)
        if paren_match:
            paren_content = paren_match.group(1).strip()
            if re.search(
                r'(万元|元|千元|亿元|平方米|平方公里|亩|公顷|个|人|台|套|件|公里|米|吨|立方米|立方|%|％|千克|公斤|升|毫升|天|小时|月|年|次|项)',
                paren_content
            ):
                unit_in_paren = paren_content
            s = re.sub(r'[（(][^）)]*[）)]', '', s)

        # Pass 2/3: 空白处理
        if remove_whitespace:
            # Pass 3: 去除所有空白/下划线/连字符
            s = re.sub(r'[\s_\-]', '', s)
        else:
            # Pass 2: 折叠连续空白为单个空格，去除下划线/连字符
            s = re.sub(r'[\s]+', ' ', s)
            s = re.sub(r'[_\-]', '', s)

        # 转小写
        s = s.lower()

        # 附加单位信息
        if unit_in_paren:
            s = s + '_' + unit_in_paren

        return s.strip()

    # ---- 同义词闭包 ----

    def _build_synonym_closure(self):
        """构建同义词→标准键的映射表。"""
        for group in self._synonym_groups:
            key = self._normalize(group[0])
            for term in group:
                self._synonym_map[self._normalize(term)] = key

    # ---- 用户同义词词典（V1.3.2，可持久化叠加） ----

    def load_user_dict(self, path=None):
        """加载用户同义词词典并叠加进匹配引擎（整体重跑闭包）。

        词典位置：path 默认用 _get_dict_path()（exe 同目录 同义词词典.json）。

        返回 (success: bool, message: str)：
          - 文件不存在        → 静默成功（纯写死内置词典），(True, "")
          - JSON 解析/结构非法 → 回退纯写死（不加载任何用户组），(False, 错误信息)
          - 成功加载          → 以「写死全集 + 用户组」为完整输入整体重跑闭包，(True, "")

        R1 决策：用户组追加到 _synonym_groups 后整体重算闭包（非增量 add），
        从根上保证用户组权威、不会把两个无关写死组合并。
        """
        if path is None:
            path = _get_dict_path()

        # 先清空内存状态：保证 reload / 损坏降级时内存始终是「纯写死」或「完整新加载」
        self._user_dict = {}
        self._sim_cache = {}

        if not os.path.exists(path):
            print(f"[INFO] 用户同义词词典不存在，使用纯内置词典: {path}")
            return (True, "")

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, ValueError, OSError, UnicodeDecodeError) as e:
            msg = f"同义词词典读取失败，已使用内置词典: {e}"
            print(f"[WARN] {msg}")
            return (False, msg)

        # 校验顶层结构：须含 synonyms 字典
        if not isinstance(raw, dict) or "synonyms" not in raw \
                or not isinstance(raw["synonyms"], dict):
            msg = "同义词词典结构非法（顶层须含 synonyms 字典）"
            print(f"[WARN] {msg}，回退内置词典")
            return (False, msg)

        synonyms = raw["synonyms"]
        user_groups = []
        cleaned = {}
        for std, syns in synonyms.items():
            # 跳过空标准词 / 非字符串标准词
            if not isinstance(std, str) or not std.strip():
                print(f"[WARN] 跳过空/非字符串标准词: {std!r}")
                continue
            # 跳过非列表同义词
            if not isinstance(syns, list):
                print(f"[WARN] 跳过非列表同义词（标准词={std}）")
                continue
            # 过滤非字符串 / 空字符串同义词
            valid = []
            for s in syns:
                if isinstance(s, str) and s.strip():
                    valid.append(s.strip())
                else:
                    print(f"[WARN] 跳过非字符串同义词（标准词={std}）: {s!r}")
            # 跳过空数组
            if not valid:
                continue
            std_key = std.strip()
            # 去重（标准词自身不得出现在同义词数组里，避免闭环噪声）
            terms = [std_key]
            for s in valid:
                if s not in terms:
                    terms.append(s)
            # 每个用户条目当作一个「新同义词组」追加
            user_groups.append(terms)
            cleaned[std_key] = valid

        # 叠加进 _synonym_groups，并以「写死全集 + 用户组」为完整输入整体重跑闭包
        self._synonym_groups = STRICT_SYNONYMS + user_groups
        self._synonym_map = {}
        self._build_synonym_closure()
        self._synonym_group_sets = [
            set(self._normalize(g, remove_whitespace=True) for g in group)
            for group in self._synonym_groups
        ]
        self._user_dict = cleaned
        # 加载排除规则（V1.3.1 新增）
        self._load_exclusions(raw)
        print(f"[INFO] 用户同义词词典已加载：{len(user_groups)} 组，路径={path}")
        return (True, "")

    # ---- 单位检测 ----

    def _extract_unit(self, s: str) -> str:
        """从标准化字符串中提取单位后缀。"""
        if '_' in s:
            return s.split('_', 1)[1]
        return ''

    def _unit_conflict(self, src: str, tgt: str) -> bool:
        """检测两个字段是否存在单位冲突。

        例如："金额（万元）" vs "金额（元）" → 冲突。
        """
        sn = self._normalize(src)
        tn = self._normalize(tgt)
        su = self._extract_unit(sn)
        tu = self._extract_unit(tn)
        return bool(su and tu and su != tu)

    # ---- 分词 ----

    def _tokenize(self, s: str) -> List[str]:
        """中文关键词分词。

        使用预设的工程领域关键词库进行分词。
        """
        keywords = [
            "项目", "工程", "名称", "编号", "编码", "代码", "建设", "施工",
            "设计", "监理", "审计", "主管", "负责", "联系", "单位", "方",
            "公司", "机构", "部门", "时间", "日期", "年限", "工期", "金额",
            "投资", "概算", "预算", "决算", "合同", "费用", "文号", "批复",
            "审批", "核准", "备案", "立项", "登记", "地址", "地点", "所在地",
            "规模", "面积", "占地", "建筑", "状态", "进展", "备注", "说明",
            "电话", "手机", "序号", "年度", "年份", "资金", "招标", "采购",
            "质量", "安全", "开工", "竣工", "完工", "验收", "计划", "实际",
            # v8 新增工程术语关键词
            "可研", "初设", "施工图", "建议书", "论证", "评估", "评审", "审查",
            "估算", "决算", "结算", "建安", "建安费",
            "附件", "清单", "扫描件",
            "资金", "财政", "自筹", "贷款", "国债", "信贷", "融资",
            "用地", "占地", "建筑", "容积率", "密度", "绿地",
            "设计", "编制", "勘察",
            "法人", "责任人", "联络人", "代表",
            "可研报告", "初设报告", "评估报告", "论证报告",
            "投资估算", "设计概算", "施工图预算", "竣工决算", "竣工结算",
            "红线", "净收益", "土地", "出让金",
            # v9 新增：工程建设报表字段大总表关键词
            "全称", "建设单位", "所属领域", "专业类别", "详细地址",
            "总投资额", "征拆", "拆迁", "年度计划", "月度", "累计",
            "方案估算", "批复金额", "审定金额", "已支付", "送审", "审减",
            "规划许可", "工规证", "征地", "施工图审查", "控制价", "上限值",
            "招标开标", "开标", "资金论证",
            "相对方", "发包方", "承包方", "签署", "补充协议",
            "勘察", "编制事务所", "一审", "二审", "审核", "造价咨询",
            "完成比例", "节点数", "滞后", "形象进度", "超时", "时效", "进窗", "审减率",
            "双控", "非双控", "收付款", "财务流程", "结算状态",
            "误差率", "责任", "归属", "划分", "分级", "资料编号",
            "比选", "内审", "接收方", "实际工期",
        ]
        tokens = []
        remaining = s
        for kw in keywords:
            if kw in remaining:
                tokens.append(kw)
                remaining = remaining.replace(kw, '', 1)
        if remaining and len(remaining) >= 2:
            tokens.append(remaining)
        return tokens

    # ---- 编辑距离 ----

    def _levenshtein_ratio(self, s1: str, s2: str) -> float:
        """计算两个字符串的相似度（Levenshtein 或 difflib 后备）。"""
        if _HAS_LEVENSHTEIN:
            return Levenshtein.ratio(s1, s2)
        else:
            return difflib.SequenceMatcher(None, s1, s2).ratio()

    # ---- 同义词匹配 ----

    def _synonym_score(self, src: str, tgt: str) -> float:
        """同义词组匹配打分。

        如果两个字段属于同一同义词组，返回高分。
        使用折叠空白版本进行比对。
        """
        sn = self._normalize(src, remove_whitespace=True)
        tn = self._normalize(tgt, remove_whitespace=True)
        for gset in self._synonym_group_sets:
            if sn in gset and tn in gset:
                return 95.0
        src_key = self._synonym_map.get(sn)
        tgt_key = self._synonym_map.get(tn)
        if src_key and tgt_key and src_key == tgt_key:
            return 90.0
        return 0.0

    # ---- 复合字段拆解 ----

    def _decompound(self, s: str) -> List[str]:
        """尝试把复合字段拆成原子词组合。

        例如 "立项审批文号费用简要描述" → ["立项审批文号", "费用", "简要描述"]
        策略：连续用 synonyms map 里的整词匹配贪婪切分。

        Args:
            s: 原始字段名（复合字段）

        Returns:
            拆分后的原子词列表
        """
        s_norm = self._normalize(s, remove_whitespace=True)
        atoms: List[str] = []
        i = 0
        while i < len(s_norm):
            matched = False
            for length in range(min(8, len(s_norm) - i), 0, -1):
                candidate = s_norm[i:i+length]
                if candidate in self._synonym_map:
                    atoms.append(candidate)
                    i += length
                    matched = True
                    break
            if not matched:
                i += 1
        return atoms

    # ---- 方向原子（复合表头拆原子，防 开工↔竣工 错位互换）----
    @staticmethod
    def _direction_atom(name: str):
        """提取字段名中的「方向原子」，用于阻止跨阶段错位配对。

        复合表头（如 "实际开工时间" / "实际竣工日期" /
        "开工竣工时间>实际开工日期"）应拆成原子后比对：
          - "开工" → start（开工/开工令 等建设起始阶段）
          - "竣工" / "完工" → end（竣工/完工 等建设结束阶段）

        关键：多级表头的「方向原子」由**叶子段**决定。例如
        "开工竣工时间>实际开工日期" 的父级 "开工竣工时间" 同时含
        开工+竣工（合并列，ambiguous），但叶子 "实际开工日期" 才是真实方向，
        应判为 start；否则会被父级污染成 "both" 而漏拦 开工↔竣工 错位。
          - 叶子同时含 开工 与 竣工（如 "开工竣工时间" 作为列名）→ "both"（不拦）
          - 叶子无方向信息（如 "合同名称"）→ None
        """
        if name is None:
            return None
        s = str(name)
        # 取最后一段（">" 分隔的多级表头叶子），方向由叶子决定
        leaf = s.rsplit('>', 1)[-1].strip()
        seg = leaf if leaf else s
        has_start = "开工" in seg
        has_end = ("竣工" in seg) or ("完工" in seg)
        if has_start and has_end:
            return "both"
        if has_start:
            return "start"
        if has_end:
            return "end"
        return None

    # ---- 复合字段名辅助方法 ----

    @staticmethod
    def _last_segment(name: str) -> str:
        """取复合字段名的最后一段（> 分隔）。

        例: '一、建筑行业>1.房地产>立项>审批文号' → '审批文号'
            '姓名' → '姓名'
        """
        if not name:
            return ""
        parts = name.rsplit('>', 1)
        return parts[-1].strip()

    # ---- 核心相似度计算（增强3遍归一化） ----

    def _calc_similarity(self, src: str, tgt: str) -> float:
        """带记忆化的相似度入口：相同 (src, tgt) 只计算一次。

        内部递归（_decompound 拆出的子串）会反复出现相同组合，
        缓存将整体从 O(字段数^2 x 递归) 降到接近 O(不同组合)。

        V1.3.1：对模糊匹配结果施加跨类语义惩罚（仅影响 <95 分的非精确匹配）。
        """
        cache = self._sim_cache
        key = (src, tgt)
        v = cache.get(key)
        if v is None:
            v = self._calc_similarity_impl(src, tgt)
            cache[key] = v
        # 跨类语义惩罚：仅作用于模糊匹配（< 95 分），精确/高置信匹配不受影响
        if v > 0 and v < 95 and self._cross_category_enabled:
            if self._check_cross_category(src, tgt):
                # 末级字段名完全相同（同一字段，仅大类前缀不同）不算跨类，跳过惩罚。
                # 例：立项信息>所属片区>所属片区 ↔ 所属片区>所属片区 是同一字段，
                # 不应被「项目名称↔所属片区」排除规则误杀。
                ss = self._last_segment(src) if '>' in (src or '') else src
                ts = self._last_segment(tgt) if '>' in (tgt or '') else tgt
                if not (ss and ts and ss == ts):
                    v = v * 0.35
        return v

    def _calc_similarity_impl(self, src: str, tgt: str) -> float:
        """计算两个字段名的相似度。

        匹配策略（按优先级）：
          1. 3遍归一化后精确匹配（折叠空白版本）
          2. 去除所有空白后匹配
          3. ASCII 小写匹配
          4. 同义词组匹配
          5. 斜杠分割子字段匹配
          6. 子串匹配（startswith / endswith）
          7. Levenshtein 编辑距离（带单位冲突检测）
          8. 中文关键词分词重合匹配

        Args:
            src: 数据源字段名
            tgt: 目标字段名

        Returns:
            相似度分数 0.0-100.0
        """
        # 候选0: 复合字段拆解
        # 如果 tgt 是复合字段，拆成原子列表，看 src 是否与其中某个原子匹配
        tgt_atoms = self._decompound(tgt)
        if len(tgt_atoms) > 1:
            for atom in tgt_atoms:
                atom_score = self._calc_similarity(src, atom)
                if atom_score >= 70:
                    return atom_score * 0.95  # 复合字段命中扣点
            # 反向：如果 src 是复合字段，tgt 是原子
            src_atoms = self._decompound(src)
            if len(src_atoms) > 1:
                for atom in src_atoms:
                    atom_score = self._calc_similarity(atom, tgt)
                    if atom_score >= 70:
                        return atom_score * 0.95

        # 候选1: 折叠空白版本（Pass 1 + Pass 2）
        sn = self._normalize(src, remove_whitespace=False)
        tn = self._normalize(tgt, remove_whitespace=False)

        if not sn or not tn:
            return 0.0

        if sn == tn:
            return 100.0

        # 候选2: 去除所有空白版本（Pass 1 + Pass 3）
        sn_nw = self._normalize(src, remove_whitespace=True)
        tn_nw = self._normalize(tgt, remove_whitespace=True)

        if sn_nw == tn_nw:
            return 98.0

        # 候选3: ASCII 小写版本（保持去空白，额外做 ASCII 小写——已在 _normalize 中处理，
        # 这里再做一次显式的 .lower() 确保完整覆盖）
        if sn_nw.lower() == tn_nw.lower():
            return 96.0

        # ---- 排除规则硬拦截（V1.3.1 新增） ----
        # 在进入模糊匹配（同义词/Levenshtein/分词）之前，先检查是否被排除规则禁止。
        # 排除规则来自 同义词词典.json 的 exclusions 列表，用户可配置。
        if self._check_exclusions(src, tgt):
            return 0.0

        # 候选0.5: 复合字段名降级匹配
        # 多级表头检测产出复合字段名如 "一、建筑行业>1.房地产开发>项目名称"，
        # 但目标字段只有 "项目名称"，需要取最后一段做短名匹配
        src_short = self._last_segment(src) if '>' in (src or '') else None
        tgt_short = self._last_segment(tgt) if '>' in (tgt or '') else None

        if src_short or tgt_short:
            # 用短名重新跑一遍候选 1/2/3
            s2 = src_short if src_short else sn
            t2 = tgt_short if tgt_short else tn
            s2_nw = self._normalize(s2, remove_whitespace=True) if src_short else sn_nw
            t2_nw = self._normalize(t2, remove_whitespace=True) if tgt_short else tn_nw

            # 候选 0.5-1: 折叠空白精确匹配
            s2_fold = self._normalize(s2, remove_whitespace=False) if src_short else sn
            t2_fold = self._normalize(t2, remove_whitespace=False) if tgt_short else tn
            if s2_fold == t2_fold:
                if (src_short and not tgt_short) or (tgt_short and not src_short):
                    return 95.0
                return 98.0

            # 候选 0.5-2: 去空白精确匹配
            if s2_nw == t2_nw:
                if (src_short and not tgt_short) or (tgt_short and not src_short):
                    return 93.0
                return 96.0

            # 候选 0.5-3: ASCII 小写匹配
            if s2_nw.lower() == t2_nw.lower():
                return 92.0

            # 候选 0.5-4: 短名 vs 短名 的同义词匹配
            syn2 = self._synonym_score(s2, t2)
            if syn2 > 0:
                return syn2

            # 候选 0.5-5: 短名仍未命中，递归用短名重跑所有后续算法
            # （Levenshtein / 子串 / 分词等）。如果不递归，后续算法只能在
            # 完整复合名的 sn_nw/tn_nw 上运行，无法匹配短名目标。
            # 先于共享前缀，因为递归可能给出更高分数（如 substring 85.0）。
            if src_short or tgt_short:
                s_final = src_short if src_short else src
                t_final = tgt_short if tgt_short else tgt
                fallback = self._calc_similarity(s_final, t_final)
                if fallback > 0:
                    return fallback

            # 候选 0.5-6: 共享前缀检测（递归未命中时兜底）
            # 如 "施工单位" vs "施工总承包" 共享前缀 "施工"，给保守分数
            common_prefix_len = 0
            for a, b in zip(s2_nw, t2_nw):
                if a == b:
                    common_prefix_len += 1
                else:
                    break
            min_short = min(len(s2_nw), len(t2_nw))
            if common_prefix_len >= 2 and min_short > 0 and common_prefix_len >= min_short * 0.4:
                return 65.0

        # 单位感知匹配（R1 修复）："合同金额(万元)" ↔ "合同金额" 应自动匹配
        # 去掉单位后缀后的「基座名」相同/同义、且单位不冲突（非 万元 vs 元）时，
        # 视为同一字段，给 ≥90 自动匹配分；仅当单位真正冲突时硬拒（返回 0）。
        if '_' in sn_nw or '_' in tn_nw:
            base_s = sn_nw.split('_', 1)[0]
            base_t = tn_nw.split('_', 1)[0]
            if base_s and base_t:
                base_score = self._synonym_score(base_s, base_t)
                if base_score > 0:
                    if self._unit_conflict(src, tgt):
                        return 0.0
                    return base_score

        # 同义词匹配
        syn_score = self._synonym_score(src, tgt)
        if syn_score > 0:
            return syn_score

        # 斜杠分割子字段匹配（用于 "A/B" 这类复合字段）
        best_sub_score = 0.0
        for s_raw, t_raw in [(src, tgt), (tgt, src)]:
            if '/' in s_raw:
                parts = [p.strip() for p in s_raw.split('/') if p.strip()]
                for part in parts:
                    if part == t_raw:
                        best_sub_score = max(best_sub_score, 98.0)
                    else:
                        sub_score = self._calc_similarity(part, t_raw)
                        if sub_score > best_sub_score:
                            best_sub_score = sub_score
        # 仅返回部件自身的最佳匹配分，不再额外加分，避免
        # "立项审批依据文号/名称" 因包含 "名称" 而错误地高匹配 "项目名称"
        if best_sub_score >= 60:
            return best_sub_score

        # ===== 方向原子冲突拦截（修复 实际开工时间↔实际竣工日期 错位互换）=====
        # 复合表头需拆成原子比对：「开工/竣工」为方向原子、「时间/日期」为类型原子。
        # 若一方含纯方向原子 开工(start)、另一方含纯方向原子 竣工/完工(end)
        # （不同阶段），任何模糊匹配都应归零，避免 实际开工时间 被错配到
        # 实际竣工日期 类列，或反之互换。
        # 合并列（同时含 开工+竣工，如 "开工竣工时间"）视为 ambiguous(both)，不拦截，
        # 以便 实际开工时间 / 实际竣工时间 仍能命中该合并源列。
        _dir_a = self._direction_atom(src)
        _dir_b = self._direction_atom(tgt)
        if _dir_a in ("start", "end") and _dir_b in ("start", "end") and _dir_a != _dir_b:
            return 0.0

        # 子串匹配（使用去空白版本）
        min_len = min(len(sn_nw), len(tn_nw))
        if min_len >= 2:
            shorter = sn_nw if len(sn_nw) <= len(tn_nw) else tn_nw
            longer = tn_nw if len(sn_nw) <= len(tn_nw) else sn_nw
            # 短串越短、越通用，分数越保守，避免 "名称" 这种通用后缀
            # 被任意带后缀的字段匹配成 90 分
            if len(shorter) <= 2:
                if longer.endswith(shorter):
                    return 40.0 if self._unit_conflict(src, tgt) else 50.0
                if longer.startswith(shorter):
                    return 40.0 if self._unit_conflict(src, tgt) else 45.0
            else:
                if longer.endswith(shorter):
                    return 50.0 if self._unit_conflict(src, tgt) else 70.0
                if longer.startswith(shorter):
                    return 50.0 if self._unit_conflict(src, tgt) else 65.0

        # Levenshtein 编辑距离
        unit_conflict = self._unit_conflict(src, tgt)
        len_diff = abs(len(sn_nw) - len(tn_nw))
        if len_diff <= max(3, min(len(sn_nw), len(tn_nw)) * 0.5):
            ratio = self._levenshtein_ratio(sn_nw, tn_nw)
            if ratio >= 0.75:
                score = 75.0 + (ratio - 0.75) * 52.0
                return score if not unit_conflict else min(score, 60.0)
            if ratio >= 0.65:
                score = 65.0 + (ratio - 0.65) * 100.0
                return score if not unit_conflict else min(score, 50.0)

        # 子串包含
        if min_len >= 2 and (sn_nw in tn_nw or tn_nw in sn_nw):
            return 45.0

        # 分词重合
        src_tokens = self._tokenize(sn_nw)
        tgt_tokens = self._tokenize(tn_nw)
        if src_tokens and tgt_tokens:
            overlap = len(set(src_tokens) & set(tgt_tokens))
            total = len(set(src_tokens) | set(tgt_tokens))
            if total > 0 and overlap / total >= 0.5:
                return 60.0 + overlap / total * 20.0

        return 0.0

    # ---- 自动匹配 ----

    def score_field(self, src_name: str, tgt_name: str) -> float:
        """对外暴露的相似度计算接口。

        Args:
            src_name: 数据源字段名
            tgt_name: 目标字段名

        Returns:
            相似度分数 0.0-100.0
        """
        return self._calc_similarity(src_name, tgt_name)

    def auto_match(
        self, src_fields: List[Dict], tgt_fields: List[str]
    ) -> List[MatchResult]:
        """对目标字段列表进行自动匹配。

        为每个目标字段找到最佳的数据源字段。

        Args:
            src_fields: 数据源字段列表 [{"name":..., "source_file":..., ...}, ...]
            tgt_fields: 目标字段名列表 ["字段1", "字段2", ...]

        Returns:
            匹配结果列表，每个结果包含 src_field/tgt_field/confidence/matched 等
        """
        self._sim_cache = {}
        results = []
        print(f"[MATCHER] 开始匹配：{len(tgt_fields)} 个目标 vs {len(src_fields)} 个数据源")
        for tgt in tgt_fields:
            best_score = -1
            best_src = None
            for src in src_fields:
                src_name = src.get("name", "")
                score = self._calc_similarity(src_name, tgt)
                if score > best_score:
                    best_score = score
                    best_src = src
            if best_src and best_score >= 60:
                matched = best_score >= 85
                suggested = 60 <= best_score < 85
                results.append({
                    "src_field": best_src["name"],
                    "src_file": best_src.get("source_file", ""),
                    "src_sheet": best_src.get("source_sheet", ""),
                    "src_sample": best_src.get("sample_values", []),
                    "tgt_field": tgt,
                    "confidence": round(best_score, 1),
                    "auto": best_score >= 85,
                    "matched": matched,
                    "suggested": suggested,
                    "conflict": False,
                })
            else:
                results.append({
                    "src_field": None, "src_file": None,
                    "src_sheet": None, "src_sample": [],
                    "tgt_field": tgt, "confidence": 0,
                    "auto": False, "matched": False,
                    "suggested": False, "conflict": False,
                })

        # 冲突检测：同一个源字段被多个目标字段匹配
        src_field_count = {}
        for r in results:
            if r["matched"] and r["src_field"]:
                key = r["src_file"] + "||" + r["src_sheet"] + "||" + r["src_field"]
                src_field_count[key] = src_field_count.get(key, 0) + 1
        for r in results:
            if r["matched"] and r["src_field"]:
                key = r["src_file"] + "||" + r["src_sheet"] + "||" + r["src_field"]
                if src_field_count.get(key, 0) > 1:
                    r["conflict"] = True

        mc = sum(1 for r in results if r["matched"])
        sc = sum(1 for r in results if r["suggested"])
        print(f"[MATCHER] 完成：自动匹配{mc}个，建议确认{sc}个，共{len(results)}个字段")
        return results

    # ---- 手动更新匹配 ----

    def update_match(
        self, matches: List[MatchResult], tgt_field: str,
        new_src_field: str = None, new_src_file: str = None,
        new_src_sheet: str = None
    ) -> List[MatchResult]:
        """手动更新某个目标字段的匹配规则。

        Args:
            matches: 当前匹配列表
            tgt_field: 要更新的目标字段
            new_src_field: 新数据源字段名（None 表示取消匹配）
            new_src_file: 新数据源文件名
            new_src_sheet: 新数据源 Sheet 名

        Returns:
            更新后的匹配列表
        """
        for m in matches:
            if m["tgt_field"] == tgt_field:
                if new_src_field is None:
                    m["matched"] = False
                    m["suggested"] = False
                    m["src_field"] = None
                    m["src_file"] = None
                    m["src_sheet"] = None
                    m["confidence"] = 0
                else:
                    m["src_field"] = new_src_field
                    m["src_file"] = new_src_file
                    m["src_sheet"] = new_src_sheet
                    m["matched"] = True
                    m["suggested"] = False
                    m["auto"] = False
                    m["confidence"] = 100.0
                break

        # 重新检测冲突
        src_field_count = {}
        for r in matches:
            if r["matched"] and r["src_field"]:
                key = r["src_file"] + "||" + r["src_sheet"] + "||" + r["src_field"]
                src_field_count[key] = src_field_count.get(key, 0) + 1
        for r in matches:
            if r["matched"] and r["src_field"]:
                key = r["src_file"] + "||" + r["src_sheet"] + "||" + r["src_field"]
                r["conflict"] = src_field_count.get(key, 0) > 1
            else:
                r["conflict"] = False
        return matches
