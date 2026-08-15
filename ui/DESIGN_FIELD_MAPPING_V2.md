# 字段映射 V2 — UI/UX 设计说明（国企大表哥 v4 · v2.1 定稿）

> 本文档为**设计说明，不含最终代码**，供前端（`ui/index.html` / `ui/style.css` / `ui/app.js`）与后端（`filler.py` / `main.py`）落地使用。
> 设计严格复用现有设计系统 token（见 `style.css :root`），不引入新主色。
> 已融合**评审确认的两项关键选择** + **产品评审 1 致命缺口 + 5 遗漏的修订**（见 §0.4）。

---

## 0. 变更总览

### 0.1 三条需求的落点（含修订）
| 需求 | 落点 |
|------|------|
| ① 执行超时处理 + 用户指定输出路径 | SECTION C「输出与执行」+ **前端看门狗 + 后端心跳/abort_fill/原子保存（P0 硬前置）** + 路径预填/覆盖确认 |
| ② 移除预览 + 增加「每一行项目名映射」 | 删除「预览确认」tab；新增 SECTION B 行级映射（**需补后端契约 P1**） |
| ③ 优化映射操作逻辑与样式 | 单栏「映射卡片」+ 状态色（自动/手动同绿带标签）+ **内联样例值替代预览** + 关键字段过滤开关（P2） |

### 0.2 评审确认的两个选择（终稿依据）
1. **行级匹配方式 = 自动配对 + 可纠偏列表**。
   - 不做「纯手工逐行下拉」；系统先按行标识键自动配对，结果以列表呈现，用户审阅。
   - **所有行均提供「改配 / 解绑」入口**（满足 AC3「自动配对错误的行可手动改配」，不限低置信）：低置信/未匹配行直接显示按钮；**高置信行默认锁定视觉，但保留次级入口（长按 / 次级菜单「强制改配·解绑」）可强制纠偏**，避免 92% 误匹配（同项目异写 / 重复行）被埋没。
2. **合同字段 = 两者都要**：
   - `合同编号` 可作为**行标识键**（类似项目名称，用于行对齐）。
   - `合同金额` / `合同日期` / `合同名称(文本)` 等作为**普通列**纳入 SECTION A 字段映射。
   - 即：行标识键下拉的可选项包含「项目名称」「合同编号」等候选列，由用户切换。

### 0.3 核心展示范式（贯穿全文）
- 列级：`源表 · 关键字段1  ──▶  [状态]  ──▶  目标表 · 关键字段1`  （卡片附**内联样例值**）
- 行级：`源项目/合同X  ──▶  目标项目/合同X  [状态]`

### 0.4 v2.1 评审修订（据此定稿）
产品评审提出 **1 处致命缺口 + 5 处遗漏**，均已修入本文（§4/§5/§6/§8/§9/§10/§11）。核心结论：
- **🔴 超时不能只做前端看门狗**：当前 `filler.execute`（filler.py:83）为单次同步返回、无进度回调、`abort_fill` 不存在、pywebview 无法从 JS 杀在途 Python。故**后端进度心跳 + 看门狗/abort_fill + 原子保存为 P0 硬前置**（否则 60s 仅弹横幅，后端仍在跑、文件可能写坏、取消无效——即「写了也白写」）。
- **🔴 行级映射缺后端契约**：`execute_fill` 当前只收 `matches`，无「目标行→源行」覆盖结构，无 `get_rowkey_candidates` / `auto_match_rows`。补后端契约为 **P1 硬前置**（需求② 落地前提）。
- **🟠 高置信行须可强制纠偏**（缺口3）；**🟠 列映射需内联样例值替代预览**（缺口4）；**🟡 关键字段过滤/显示全部开关**补回（遗漏5）；**🟡 输出路径须预填默认 + 覆盖确认 + 复用 `save_output_dialog`**（小问题6）。
- 优先级：**P0** 后端超时支撑；**P1** 行级后端契约 + 内联样例值；**P2/后续** 关键字段过滤（若砍掉须显式标注移至后续版本）。一致且正确部分全部保留。

---

## 1. 导航（删除预览，4 个 tab）

移除「预览确认」，tab 由 5 减为 **4**：

```
[ 数据源 ]  [ 字段映射(含执行) ]  [ 使用说明 ]  [ 关于 ]
   0               1                   2            3
```

- 删除 `index.html` 中 `page-2`（预览确认）整段 DOM、对应 `.nav-tab` / `.page-dot`。
- `switchPage` / 键盘左右切换边界改为 `< 3` / `> 0`。
- 「使用说明」第 4 步文案改为：「在『字段映射』页核对映射（含内联样例值）并直接执行，进度与日志同页展示」。
- **字段映射页（page-1）即唯一执行入口**：含 字段映射 + 项目/合同行映射 + 输出/执行 + 执行状态面板。
- 删除原 mapper 工具栏「确认并预览 →」按钮，改由页内「🚀 开始执行」触发。

### 执行结果面板「内迁」方式
- 原 `page-2` 的 `#result-panel` 不再独立成页，整体**移入 page-1 的 SECTION C**。
- 进度**圆环 → 改为线性进度条**（更利于显示 % 与已用时长）；保留 `openResultFolder()` / `resetAll()` 逻辑。
- 移除 `renderPreview()` 相关调用（验证职责改由 §4 内联样例值承担，见缺口4）。

---

## 2. 字段映射页新结构（page-1）

```
┌──────────────────────────────────────────────────────────────────┐
│ 工具栏: [🤖 智能匹配] [＋ 手动添加]   统计: ✅12  ⚠3  ○2       │
├──────────────────────────────────────────────────────────────────┤
│ ▾ SECTION A  字段映射（列级 · 源列→目标列）  [仅关键 ▾]       │
│  ┌─ mapping-grid (宽屏双列) ─────────────────────────────────┐  │
│  │ [源·合同台账] 姓名 ─▶[🤖自动]▶ [目标·员工姓名] ✎ ✕    │  │
│  │    例：张三 / 138xxxx                              (内联样例值)│  │
│  │ [源·人员表]  手机号 ─▶[✋手动]▶ [目标·联系电话]   ✎ ✕    │  │
│  │ [源·—] —     ─✕─[⚠建议]▶ [目标·合同金额]    ✎ ✕    │  │
│  │ [源·—] —     ─✕─[○未匹配]▶ [目标·合同日期]  ✎ ✕    │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ▾ SECTION B  项目 / 合同行映射（行级）  [🤖 智能匹配行]          │
│   行标识键: [源:合同编号 ▾] 对应 [目标:合同编号 ▾]  (可切项目名) │
│  ┌─ rowmap-list ─────────────────────────────────────────────┐  │
│  │ [目标行·合同A(第3行)] → [源·合同A] [🤖自动 92%] [⋮强制]│  │ ← 高置信 锁定视觉,次级可强制纠偏
│  │ [目标行·合同B(第4行)] → [源·合同B] [⚠建议 61%][✎][⛓✕]│  │ ← 低置信 直接纠偏
│  │ [目标行·合同C(第5行)] → [— 未匹配] [○未匹配]   [✎][⛓✕]│  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ▾ SECTION C  输出与执行                                          │
│   保存路径: [ D:\报表\报表_已填充_20260715_143000.xlsx ] [📂 浏览] │ ← 预填默认(非placeholder)
│   超时设置: [ 60 秒 ▾ ]                                         │
│   [ 🚀 开始执行 ]                                               │
│   ┌─ 执行状态面板（原 page-2 结果区内迁）──────────────────┐   │
│   │ ▓▓▓▓▓▓▓▓▓▓░░░░ 64%   已用 22s   [取消]               │   │ ← 线性进度+%+已用时长
│   │ ● 已加载 3 个数据源 / 字段匹配 85% / 写入合同A…     │   │
│   │ ▆ 横幅：✅ 成功 / ⏱ 超时 / ❌ 失败（见 §6）        │   │
│   └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

**为何列级与行级同页分区（不分步骤）**：需求⑤明确「字段映射页即执行入口」，所有执行前配置（字段、行、输出路径）须集中一页，分步骤会破坏「确认即执行」。

---

## 3. 颜色语义（终稿 · 绿底必带「自动/手动」标签）

> 关键约束（评审确认）：**自动与手动同为绿色**，但绿底必须附带「🤖 自动 / ✋ 手动」文字+图标小标签，保证**可追溯、不只靠颜色区分**。

| 状态 | 底色 | 文字 | 图标 | 文字标签 | 使用场景 |
|------|------|------|------|----------|----------|
| 完全匹配（自动 ≥ 阈值） | `#E8FBF5` | `#00B894` | 🤖 | `自动` | 系统按相似度自动配对且置信度高 |
| 手动匹配成功 | `#E8FBF5` | `#00B894` | ✋ | `手动` | 用户手动确认/改配成功（同样绿） |
| 建议未确认 | `#FFF8E1` | `#E67E22` | ⚠ | `建议` | 低置信度，需用户确认（琥珀） |
| 未匹配 | `#F1F3F5` | `#868E96` | ○ | `未匹配` | 尚未指定源字段（灰） |
| 冲突 / 失败 | `#FFE8E8` | `#E17055` | ✕ | `冲突` | 字段冲突或执行失败（红） |

- **绿底两类仅靠「图标+文字标签（自动/手动）」区分，不靠色相**——这是无障碍与可追溯的硬要求。
- 卡片边框态：建议=`1.5px` 虚线 `--accent`+底 `#FFF8E1`；未匹配=`1.5px` `--border`+底 `#F1F3F5`；冲突=`1.5px` `--accent3`+底 `#FFE8E8`；自动/手动=默认透明边框。

---

## 4. SECTION A 列级映射卡片（交付② · 含样例值 + 关键字段开关）

### 4.1 卡片结构
```
.mapping-card (白卡 radius12 / 阴影 / flex 行 / align-center / gap12)
├─ .mc-source (flex:1, min-width:0, 点击=改配)
│    ├─ .mc-table  "源 · 合同台账.xlsx"   ← 10px, --text-secondary, 省略号
│    └─ .mc-field  "姓名"                 ← 13px, 600, --text
├─ .mc-link
│    ├─ .mc-arrow  "→"                    ← 18px, --primary
│    └─ .badge.badge-auto  "🤖 自动"     ← 状态徽章（见 §3 配色）
├─ .mc-target (flex:1, min-width:0)
│    ├─ .mc-table  "目标 · 月度报表.xlsx"
│    ├─ .mc-field  "员工姓名"             ← 13px, 600
│    └─ .mc-sample "例：张三 / 138xxxx"   ← 11px, --text-secondary（内联样例值，缺口4）
├─ .mc-actions
│    ├─ .icon-btn "✎"  (改配→复用 field-picker)
│    └─ .icon-btn.icon-btn-ghost "✕" (取消→转未匹配；手动添加行则删除整行)
```

### 4.2 四种视觉态
| 态 | 源端 | 箭头 | 徽章 | 卡片边框 |
|----|------|------|------|----------|
| 完全匹配(自动) | 正常字段名 | `→` 紫 | `🤖 自动` 绿 | 默认 |
| 手动匹配 | 正常字段名 | `→` 紫 | `✋ 手动` 绿 | 默认 |
| 建议未确认 | 正常（系统建议源） | `→` 琥珀 | `⚠ 建议` 琥珀 | 虚线琥珀+底 `#FFF8E1` |
| 未匹配 | `— 未选择` 灰 | `✕` 红 | `○ 未匹配` 灰 | `--border`+底 `#F1F3F5` |

### 4.3 内联样例值（缺口4 · 替代预览的最小验证）
- **每张映射卡追加 `.mc-sample` 一行**：取该源字段**首个非空样本值**展示，如 `例：张三 / 138xxxx`、`例：208,000.00`。
- 目的：预览移除后，用户在执行前**肉眼核对「填对没」**——这是替代预览的最小可行验证，不等同于「执行后打开结果文件」。
- 未匹配卡片样例区显示 `— 无样本`（灰），提示该目标列尚无可填数据。

### 4.4 合同字段在此处的处理
- `合同金额` / `合同日期` / `合同名称(文本)` 等**作为普通目标列**，出现在 SECTION A 的映射卡片中（与普通字段无异，含 `.mc-sample`）。
- `合同编号` **不在此处**作普通列映射，而是作为行标识键候选（见 §5）。若用户坚持把合同编号也当普通列填，允许，但默认推荐其作行键。

### 4.5 关键字段过滤 + 显示全部开关（需求③ 子项，P2/后续）
> 评审需求③ Scope/AC3 明确要求「提取关键字段优先 + 显示全部字段开关防误隐藏」。设计补回此开关；**若排期砍掉，须显式标注「关键字段过滤移至后续版本」**。
- SECTION A 头部加 **`[仅关键 ▾]` 切换**（§8 骨架 `#btn-key-toggle`）：默认「仅关键」（按业务权重提取关键字段优先展示）；切「显示全部」展开所有目标列卡片。
- **目标侧「未匹配必需字段」恒显**：无论开关状态，未匹配且为必填/关键的字段卡片始终可见，防止误隐藏导致漏填。
- 该子项优先级 **P2**，不阻塞 P0/P1 主链路；后端需配合返回 `is_key` / `is_required` 标记（见 §11 P2）。

---

## 5. SECTION B 行级映射（交付③ · 自动配对 + 可纠偏列表）

### 5.1 结论：**自动配对 + 可审阅/纠偏列表**（不做纯手工逐行下拉）
- 系统先按「行标识键」自动配对，结果以列表呈现，用户审阅。
- **高置信度行**：绿色锁定视觉（`🤖 自动 NN%`），默认不强制操作；但**保留次级入口**（`[⋮]` 次级菜单 / 长按）提供「强制改配 / 解绑」，满足 AC3「自动配对错误的行可手动改配」**不限低置信**——避免 92% 误匹配（同项目异写 / 重复行）被埋没。
- **低置信度行 / 未匹配行**：琥珀或灰色，直接提供 `[✎ 改配]` `[⛓✕ 解绑]` 按钮；点击改配弹出候选源项目列表（复用弹窗模式，非逐行内联下拉）。

### 5.2 区块结构
```
▾ SECTION B  项目 / 合同行映射（行级）        [🤖 智能匹配行]
   行标识键: [源:合同编号 ▾] 对应 [目标:合同编号 ▾]
             （可切换为「项目名称」或「合同编号」等对齐依据）
   ┌─ rowmap-list ───────────────────────────────────────┐
   │ [目标行·合同A(第3行)] → [源·合同A] [🤖自动 92%] [⋮强制]│ ← 高置信 锁定视觉,次级可强制纠偏
   │ [目标行·合同B(第4行)] → [源·合同B] [⚠建议 61%][✎][⛓✕]│ ← 低置信 直接纠偏
   │ [目标行·合同C(第5行)] → [— 未匹配] [○未匹配]  [✎][⛓✕]│
   └────────────────────────────────────────────────────────┘
```

- **行标识键选择器（`.rowkey-bar`）**：两个 `<select>` 分别选「源行键列」与「目标行键列」。候选列来自源/目标表头（后端 `get_rowkey_candidates`，见 §11 P1）；**选项含「项目名称」「合同编号」等**，用户可切换对齐依据。默认后端按相似度自动选。
- **行标签随键变化**：选中「合同编号」时，行显示合同编号值（如 `合同A` 实为编号 `HT-2024-001`）；选中「项目名称」时显示项目名称。
- **[🤖 智能匹配行]**：按行键值相似度重跑自动配对（后端 `auto_match_rows`），回填列表并刷新徽章。
- **[✎ 改配]**：弹窗列出候选源项目（带相似度%），选后即「✋ 手动」绿标。
- **[⛓✕ 解绑]**：清空该行配对，转「○ 未匹配」灰。
- **[⋮ 强制纠偏]**（高置信行）：展开次级菜单「强制改配 / 解绑」，行为同低置信行。

### 5.3 与 SECTION A 的关系（供后端/前端理清）
- **列级（A）**：哪源列 → 哪目标列。
- **行级（B）**：哪源项目/合同行 → 哪目标项目/合同行（对齐依据 = 行标识键）。
- 执行时：对目标每一项目行，取已匹配源项目数据 → 套用 A 的列映射 → 填入。两者缺一都无法完整填表，故同页分区、统一执行。
- **后端契约（P1 硬前置，缺口2）**：当前 `execute_fill` 只收 `matches`（列映射），无「目标行→源行」覆盖结构。必须在入参扩展 `row_overrides`（用户行覆盖：`{tgt_row_idx: src_row_idx}`），并新增 `get_rowkey_candidates` / `auto_match_rows` 端点（详见 §11）。

---

## 6. SECTION C 执行面板新状态（交付④ · 含 P0 后端前置）

### 6.1 布局
```
▾ SECTION C  输出与执行
   ┌─ 输出设置 ──────────────────────────────────────┐
   │ 保存路径: [ D:\报表\报表_已填充_20260715_143000.xlsx ] [📂 浏览] │ ← 预填默认
   │ 超时设置: [ 60 秒 ▾ ]   (30/60/120/300)          │
   └─────────────────────────────────────────────────┘
   [ 🚀 开始执行 ]                      ← pill-primary lg
   ┌─ 执行状态面板（原 page-2 结果区内迁）────────────┐
   │ ▓▓▓▓▓▓▓▓▓▓░░░░ 64%   已用 22s   [取消]          │ ← 线性进度+%+已用时长
   │ ● 已加载 3 个数据源 / 字段匹配 85% / 写入合同A…   │
   │ ▆ 横幅（5 态之一，见下表）                         │
   └─────────────────────────────────────────────────┘
```

### 6.2 五种状态
| 状态 | 表现 |
|------|------|
| **IDLE 就绪** | 仅显示输出设置 + 「开始执行」；状态面板隐藏或显「就绪」。路径空时禁用执行钮。 |
| **RUNNING 执行中** | 线性进度条动画 + 实时 %；**已用时长计数**（如「已用 22s」每秒 +1）；[取消] 可点；路径输入禁用。 |
| **DONE 成功** | 进度 100% 转绿；绿色横幅「✅ 执行成功，已保存至 `<path>`」+ [📂 打开结果] [🔄 新建任务]。 |
| **TIMEOUT 超时** | 琥珀/红横幅「⏱ 执行超时（已用 Ns 超过设定 60s 且无进度更新）」+ [重试] [🔄 新建任务]。 |
| **ERROR 失败** | 红横幅「❌ 执行失败：<msg>」+ [重试] [🔄 新建任务]。 |

### 6.3 超时机制（**P0 硬前置：必须后端支撑**，需求①）
> ⚠️ **纯前端看门狗是假修复**：当前 `filler.execute`（filler.py:83）为单次同步返回、**无进度回调**、`abort_fill` **不存在**、pywebview **无法从 JS 杀掉在途 Python 调用**。若只做前端，60s 仅弹横幅——后端仍在跑、文件可能写坏、取消钮无效（即评审说的「写了也白写」）。故以下后端三项为 **P0 硬前置**，否则超时需求不成立。

- **前端**：维护 `lastProgressTs` 与 `startTs`；每次收到**后端进度心跳**重置 `lastProgressTs` 并据 `startTs` 算已用时长；`setInterval(1s)` ① 已用时长 +1 显示，② 检测 `now - lastProgressTs > timeoutSec*1000` → 进 **TIMEOUT** 态并调用后端 `abort_fill()`（见下）；[取消] 立即调 `abort_fill()` 回 IDLE。
- **后端支撑（P0，缺一不可）**：
  - **(a) 进度回报**：`filler.execute` 改为**按行/按单元格心跳**回报（经 pywebview `evaluate_js` 或回调），`lastProgressTs` 才能真正工作。
  - **(b) 后端看门狗 + `abort_fill()`**：filler 在 **worker 线程**跑、带 `threading.Event` 停止事件；循环在**保存之前**检查事件、可控中断，返回 `{success:false, aborted:true}`；`abort_fill()` 置位事件。
  - **(c) 原子保存**：保存改为「写临时文件 → `os.replace` 原子改名」，否则 abort 落在 `wb.save()` 中途会留半截损坏文件。
- 超时/取消不损坏已落盘部分（依赖 (c) 原子保存）；横幅提示可「重试」或「新建任务」。

### 6.4 输出路径（需求①）
- **预填默认值**（非仅 placeholder，否则用户不知存哪）：输入框 `value` 直接填 `目标模板同目录 / <模板名>_已填充_<YYYYMMDD_HHMMSS>.xlsx`，用户可见可改。
- 用户可覆盖：编辑输入框 + [📂 浏览]；浏览**复用后端已有 `save_output_dialog`（main.py:152），不重复造 `select_output_path` 新 API**，返回路径强制 `.xlsx` 后缀。
- **覆盖确认（需求① 风险点）**：openpyxl 会**静默覆盖**，前端须在**执行前**判目标路径已存在 → 弹 `confirm()` 二次确认，不能靠系统对话框；用户取消则不出执行。
- 执行前校验：路径非空、可写、且（若已存在）已获覆盖确认，否则禁用「开始执行」并 Toast。

---

## 7. 响应式 / 窄屏（交付⑥）

原痛点：`.mapper-layout` 三栏各 280px 固定，窗口缩小中间被挤压。V2 改为**单栏卡片流**，天然弹性。

| 断点 | 策略 |
|------|------|
| ≥1100px | SECTION A 双列 Grid（`minmax(440px,1fr)`）；隐藏副标题（沿用现有）。 |
| 960–1100px | SECTION A 单列；工具栏 `flex-wrap`。 |
| 640–960px | 各 SECTION 垂直堆叠；执行面板/行映射占满宽；进度条 100% 宽。 |
| <640px | 操作按钮转图标-only（✎ / ✕ / ⋮）；徽章文字可缩；状态横幅堆叠；正文 -1px；最小内容宽约 360px（本页无重表格，基本不需横向滚动）。 |

通用：文字容器 `min-width:0` + `text-overflow:ellipsis` 防溢出；间距用 `clamp()`；`.nav-tabs` 已有横向滚动兜底，4 tab 更不易触发。移除旧三栏 CSS（`mapper-left/right/center`），换 `.mapping-grid/.mapping-card/.rowmap-list/.exec-panel` 等。

---

## 8. HTML 结构骨架（区块 id / class 命名，供前端直接落地）

> 仅结构骨架与类名，非完整代码。后端 API 见 §11。

```html
<!-- ===== 字段映射页 page-1（执行入口） ===== -->
<div class="page" id="page-1">

  <!-- 工具栏 -->
  <div class="mapper-toolbar">
    <button class="pill pill-primary pill-sm" id="btn-auto-match" onclick="doAutoMatch()">🤖 智能匹配</button>
    <button class="pill pill-outline pill-sm" id="btn-add-map" onclick="addManualMapping()">＋ 手动添加</button>
    <div class="mapper-stat" id="mapper-stat">
      <span class="stat-pill stat-green">✅ <b id="stat-matched">0</b> 已匹配</span>
      <span class="stat-pill stat-amber">⚠ <b id="stat-suggest">0</b> 建议</span>
      <span class="stat-pill stat-gray">○ <b id="stat-unmatched">0</b> 未匹配</span>
    </div>
  </div>

  <!-- SECTION A：列级字段映射 -->
  <section class="map-section" id="sec-field">
    <header class="section-head">
      <span class="section-title">▾ 字段映射（列级）</span>
      <button class="pill pill-outline pill-sm" id="btn-key-toggle" onclick="toggleKeyFields()">仅关键 ▾</button>
      <span class="section-hint">源列 → 目标列 · 未匹配必需恒显</span>
    </header>
    <div class="mapping-grid" id="mapping-grid"><!-- JS 注入 .mapping-card --></div>
  </section>

  <!-- SECTION B：行级项目/合同映射 -->
  <section class="map-section" id="sec-row">
    <header class="section-head">
      <span class="section-title">▾ 项目 / 合同行映射（行级）</span>
      <button class="pill pill-outline pill-sm" id="btn-auto-row" onclick="autoMatchRows()">🤖 智能匹配行</button>
    </header>
    <div class="rowkey-bar">
      <label>行标识键：</label>
      <select class="select-sm" id="rowkey-src"></select>
      <span>对应</span>
      <select class="select-sm" id="rowkey-tgt"></select>
      <span class="rowkey-note">可切换「项目名称」或「合同编号」等对齐依据</span>
    </div>
    <div class="rowmap-list" id="rowmap-list"><!-- JS 注入 .rowmap-row --></div>
  </section>

  <!-- SECTION C：输出与执行 -->
  <section class="map-section" id="sec-exec">
    <header class="section-head"><span class="section-title">▾ 输出与执行</span></header>

    <div class="exec-settings">
      <label class="exec-label">保存路径</label>
      <div class="path-row">
        <!-- 预填默认（非 placeholder），覆盖前 confirm() 确认 -->
        <input class="text-input" id="output-path" value="D:\报表\月度报表_已填充_20260715_143000.xlsx">
        <button class="pill pill-outline pill-sm" id="btn-browse" onclick="openSaveDialog()">📂 浏览</button>
      </div>
      <label class="exec-label">超时设置</label>
      <select class="select-sm" id="timeout-select">
        <option value="30">30 秒</option>
        <option value="60" selected>60 秒</option>
        <option value="120">120 秒</option>
        <option value="300">300 秒</option>
      </select>
    </div>

    <button class="pill pill-primary pill-lg run-btn" id="btn-run" onclick="confirmAndExecute()">🚀 开始执行</button>

    <!-- 执行状态面板（原 page-2 结果面板内迁） -->
    <div class="exec-panel" id="exec-panel" style="display:none">
      <div class="exec-panel-head">
        <span class="section-title">🚀 执行状态</span>
        <button class="pill pill-ghost pill-sm" id="btn-cancel" style="display:none" onclick="cancelExecute()">取消</button>
        <button class="pill pill-outline pill-sm" id="btn-reset" style="display:none" onclick="resetAll()">🔄 新建任务</button>
      </div>
      <div class="progress-wrap">
        <div class="progress-bar"><div class="progress-fill" id="progress-fill"></div></div>
        <span class="progress-pct" id="progress-pct">0%</span>
        <span class="progress-elapsed" id="progress-elapsed">已用 0s</span>
      </div>
      <div class="exec-banner" id="exec-banner" style="display:none"></div>
      <div class="log-list" id="exec-log"></div>
      <button class="pill pill-success pill-lg" id="btn-open-result" style="display:none" onclick="openResultFolder()">📂 打开结果文件</button>
    </div>
  </section>
</div>

<!-- 映射卡片模板（JS 克隆） -->
<div class="mapping-card" data-idx="0">
  <div class="mc-source">
    <div class="mc-table">源 · 合同台账.xlsx</div>
    <div class="mc-field">姓名</div>
  </div>
  <div class="mc-link">
    <div class="mc-arrow">→</div>
    <span class="badge badge-auto">🤖 自动</span>  <!-- badge-manual / badge-suggest / badge-unmatched / badge-conflict -->
  </div>
  <div class="mc-target">
    <div class="mc-table">目标 · 月度报表.xlsx</div>
    <div class="mc-field">员工姓名</div>
    <div class="mc-sample">例：张三 / 138xxxx</div>  <!-- 内联样例值：取源字段首个非空样本，执行前肉眼核对 -->
  </div>
  <div class="mc-actions">
    <button class="icon-btn" title="修改">✎</button>
    <button class="icon-btn icon-btn-ghost" title="取消">✕</button>
  </div>
</div>

<!-- 行映射行模板（JS 克隆） -->
<div class="rowmap-row" data-idx="0">
  <div class="rm-target">目标行 · 合同A（第3行）</div>
  <div class="rm-arrow">→</div>
  <div class="rm-source">源 · 合同A</div>
  <span class="badge badge-auto">🤖 自动 92%</span>  <!-- 低置信: badge-suggest -->
  <div class="rm-actions">
    <button class="icon-btn" title="强制改配/解绑（次级菜单）">⋮</button>  <!-- 高置信行：次级入口强制纠偏 -->
    <button class="icon-btn" title="改配">✎</button>
    <button class="icon-btn icon-btn-ghost" title="解绑">⛓✕</button>
  </div>
</div>
```

---

## 9. 关键 CSS 类参考（设计属性，供前端实现）

> 仅给出关键视觉属性；复用 `:root` token。非完整 CSS。

```css
/* 布局 */
.mapper-toolbar   { display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
.map-section      { margin-bottom:24px; max-width:1100px; }
.section-head     { display:flex; justify-content:space-between; align-items:center;
                    gap:8px; flex-wrap:wrap; margin-bottom:12px; }  /* flex-wrap 容纳切换钮 */
.section-title    { font-size:15px; font-weight:700; }
.section-hint     { font-size:11px; color:var(--text-secondary); }

/* SECTION A 网格 */
.mapping-grid     { display:grid; grid-template-columns:repeat(auto-fill,minmax(440px,1fr)); gap:12px; }

/* 映射卡片 */
.mapping-card     { display:flex; align-items:center; gap:12px; background:var(--card);
                    border-radius:12px; padding:12px 16px; box-shadow:var(--shadow);
                    border:1.5px solid transparent; }
.mapping-card.suggest  { border:1.5px dashed var(--accent); background:#FFF8E1; }
.mapping-card.unmatched{ border:1.5px solid var(--border); background:#F1F3F5; }
.mapping-card.conflict { border:1.5px solid var(--accent3); background:#FFE8E8; }
.mc-source, .mc-target { flex:1; min-width:0; }
.mc-table         { font-size:10px; color:var(--text-secondary); overflow:hidden;
                    text-overflow:ellipsis; white-space:nowrap; }
.mc-field         { font-size:13px; font-weight:600; color:var(--text); }
.mc-sample        { font-size:11px; color:var(--text-secondary); margin-top:2px; }  /* 内联样例值 */
.mc-arrow         { color:var(--primary); font-size:18px; }

/* 状态徽章（绿底必带自动/手动标签，见 §3） */
.badge            { display:inline-flex; align-items:center; gap:4px;
                    font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px; }
.badge-auto, .badge-manual { background:#E8FBF5; color:#00B894; }  /* 同绿，图标/文字区分 */
.badge-suggest   { background:#FFF8E1; color:#E67E22; }
.badge-unmatched { background:#F1F3F5; color:#868E96; }
.badge-conflict  { background:#FFE8E8; color:#E17055; }

/* 操作按钮 */
.icon-btn         { width:32px; height:32px; border-radius:999px; border:1.5px solid var(--primary);
                    background:transparent; color:var(--primary); cursor:pointer; }
.icon-btn-ghost   { border-color:var(--border); color:var(--text-secondary); }

/* SECTION B 行映射 */
.rowkey-bar       { display:flex; flex-wrap:wrap; gap:8px; align-items:center;
                    font-size:12px; margin-bottom:12px; }
.select-sm        { height:32px; border-radius:10px; border:1.5px solid var(--border);
                    padding:0 10px; font-size:12px; }
.rowmap-list      { display:flex; flex-direction:column; gap:8px; }
.rowmap-row       { display:flex; align-items:center; gap:12px; padding:10px 14px;
                    background:var(--card); border-radius:12px; border:1.5px solid transparent; }
.rowmap-row.suggest { border:1.5px dashed var(--accent); }
.rm-target, .rm-source { font-size:13px; font-weight:600; }

/* SECTION C 执行 */
.exec-settings    { display:flex; flex-direction:column; gap:10px; max-width:640px; margin-bottom:16px; }
.path-row         { display:flex; gap:8px; }
.text-input       { flex:1; height:36px; border-radius:10px; border:1.5px solid var(--border);
                    padding:0 12px; font-size:13px; }
.run-btn          { margin-bottom:16px; }

/* 执行状态面板 */
.exec-panel       { background:var(--card); border-radius:16px; box-shadow:var(--shadow);
                    padding:20px; border:1px solid var(--border); }
.exec-panel-head  { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
.progress-wrap    { display:flex; align-items:center; gap:12px; }
.progress-bar     { flex:1; height:10px; border-radius:999px; background:var(--border); overflow:hidden; }
.progress-fill    { height:100%; width:0%; background:var(--primary); transition:width .4s ease; }
.progress-fill.done { background:var(--accent2); }
.progress-pct     { font-weight:600; color:var(--primary); }
.progress-pct.done{ color:var(--accent2); }
.progress-elapsed { font-size:12px; color:var(--text-secondary); }

/* 状态横幅（5 态） */
.exec-banner      { margin-top:12px; padding:12px 16px; border-radius:12px;
                    font-size:13px; font-weight:600; }
.exec-banner.done   { background:#E8FBF5; color:#00B894; border-left:3px solid #00B894; }
.exec-banner.timeout{ background:#FFF8E1; color:#E67E22; border-left:3px solid #E67E22; }
.exec-banner.error  { background:#FFE8E8; color:#E17055; border-left:3px solid #E17055; }

/* 日志 */
.log-list         { display:flex; flex-direction:column; gap:8px; margin-top:12px; }
.log-item         { padding:10px 16px; border-radius:12px; background:var(--card);
                    font-size:13px; box-shadow:0 1px 4px rgba(0,0,0,.04); }
.log-item.success { border-left:3px solid var(--accent2); }
.log-item.warn    { border-left:3px solid var(--accent); }
.log-item.error   { border-left:3px solid var(--accent3); }

/* 响应式 */
@media (max-width:960px){
  .mapping-grid { grid-template-columns:1fr; }      /* 单列 */
  .mapper-toolbar { flex-wrap:wrap; }
}
@media (max-width:640px){
  .icon-btn { width:28px; height:28px; }            /* 图标按钮更紧凑 */
  .progress-wrap { flex-wrap:wrap; }
  .exec-banner { font-size:12px; }
}
```

---

## 10. 实现检查清单（前端 + 后端，按优先级）

### 前端
- [ ] 删除 `page-2`（预览确认）DOM + nav-tab/page-dot + `renderPreview()`。
- [ ] `switchPage` / 键盘边界改为 0–3；「使用说明」第 4 步文案更新（含「内联样例值核对」）。
- [ ] page-1 重写为 §8 骨架（工具栏 + SECTION A/B/C）。
- [ ] SECTION A：`.mapping-grid` + `.mapping-card`，状态徽章套 §3（自动/手动同绿+标签）；**每张卡加内联样例值 `.mc-sample`**（缺口4，替代预览）。
- [ ] SECTION A 头部加 `仅关键/显示全部` 切换（`#btn-key-toggle`）；未匹配必需字段恒显（遗漏5，P2）。
- [ ] SECTION B：行标识键双 `<select>`（候选来自 `get_rowkey_candidates`）+ 自动配对列表；低置信行直接 `[✎改配][⛓✕解绑]`；**高置信行保留 `[⋮]` 次级强制纠偏入口**（缺口3）。
- [ ] SECTION C：输出路径输入（**预填默认值**）+ 浏览、**超时下拉**、开始执行、执行状态面板（线性进度 + 已用时长 + 取消 + 5 态横幅）。
- [ ] **输出路径覆盖确认**：执行前判目标已存在 → `confirm()` 二次确认（小问题6）；浏览**复用 `save_output_dialog`（main.py:152）** 而非新 API。
- [ ] 前端看门狗（`lastProgressTs`/`startTs` + 1s 计时 + 调 `abort_fill()`）——**须在 §11 后端支撑就绪后才有意义**。
- [ ] 合同字段：编号作行键候选；金额/日期作普通列进 A。
- [ ] 响应式断点按 §7 / §9（移除旧三栏 CSS）；`.section-head` 加 `flex-wrap` 容纳切换钮。
- [ ] 复用现有 `.pill` / `.modal` / `field-picker` 等组件，不新增主色。

### 后端（硬前置，详见 §11）
- [ ] **P0**：`filler.execute` 加**进度心跳**（per-row/per-cell）；worker 线程 + `stop-event` 看门狗 + `abort_fill()`（保存前中断，返回 `{success:false, aborted:true}`）；**原子保存**（临时文件 → `os.replace`）。
- [ ] **P1**：行级契约 `get_rowkey_candidates` / `auto_match_rows`（带置信度）/ `execute_fill` 接收行覆盖 `row_overrides`（缺口2）。
- [ ] **P2**：关键字段提取 + 显示全部开关（遗漏5）；若砍掉须显式标注「移至后续版本」。

---

## 11. 后端契约与优先级（硬前置，P0/P1）

> 纯前端无法实现超时真中止与行级映射，以下为需求①/②落地的后端硬前置。前端 §8/§10 依赖本节。

### P0 — 超时真支撑（需求①，否则超时=假修复）
- `filler.execute` 改造为**心跳回报**：每写完若干行/单元格，经 pywebview 回调（或 `window.pywebview.api` 暴露的进度方法）上报 `{pct, row, msg}`，驱动前端 `lastProgressTs` 与进度条/已用时长。
- **worker 线程 + `threading.Event` 停止事件**：主执行循环在**每次写入前** `if stop_event.is_set(): return {success:False, aborted:True}`；`abort_fill()` 置位事件。JS 侧 `cancelExecute()` / 看门狗超时均调 `abort_fill()`。
- **原子保存**：`wb.save(tmp_path)` → `os.replace(tmp_path, final_path)`；abort 发生在 replace 之前，不会留半截文件。

### P1 — 行级映射契约（需求② 落地前提，缺口2）
- `get_rowkey_candidates(tgt_fields)` → 候选「行标识键」列（含 `项目名称` / `合同编号` 等）。
- `auto_match_rows(rowkey_src, rowkey_tgt)` → `[{tgt_row, src_row, confidence}]`（按行键值相似度配对）。
- `execute_fill` 入参扩展：在原有 `matches`（列映射）之外，增加 `row_overrides`（用户行覆盖：`{tgt_row_idx: src_row_idx}`）。

### P2 — 关键字段过滤（遗漏5）
- `get_fields` 返回带 `is_key` / `is_required` 标记；前端据此做「仅关键」默认与未匹配必需恒显。若本期砍掉，须在文档显式标注移至后续版本。

---

*设计说明 v2.1 定稿。已融合评审两项关键选择，并修入产品评审 1 致命缺口（后端超时支撑 P0）+ 5 遗漏（行级后端契约 P1、高置信强制纠偏、内联样例值替代预览、关键字段过滤、输出路径预填+覆盖确认）。一致且正确部分全部保留。如需可交互 HTML 原型，可调用 design-html skill 基于本说明生成。*
