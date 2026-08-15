# 国企大表哥 V1.1 · UI 调整设计说明（前端交付稿）

> 适用范围：`国产大表哥_v4/ui/`（pywebview 桌面应用）
> 设计目标：修复顶部导航窄窗错位、精简品牌区、合并预览/执行流程、补齐版本与更新日志。
> 配色与组件规范沿用现有 `style.css` 设计系统（`--primary #6C5CE7` 等），不另起炉灶。

## 0. 改动总览

| # | 改动 | 类型 | 影响文件 |
|---|------|------|---------|
| 1 | 顶部导航响应式：根治错位 | CSS | `style.css` |
| 2 | 删除首页「软件作者：LuoLei」标签 | HTML/CSS | `index.html`, `style.css` |
| 3 | 合并「预览确认」+「执行结果」为单页「预览执行」 | HTML/JS | `index.html`, `app.js` |
| 4 | 关于页版本号 V1.0→V1.1 + 新增「更新日志」 | HTML | `index.html` |
| 5 | 使用说明头部版本药丸（可选一致性增强） | HTML | `index.html` |

页签数量：**6 → 5**。合并页保留在**第 3 位（index 2）**，以最小化 `switchPage` / `renderPreview` 逻辑改动。

---

## 1. 顶部导航响应式优化

### 1.1 错位根因
原 `.topbar` 为单行 flex，`.logo`（含 logo + 标题 + 副标题 + 作者标签）与 `.nav-tabs`（`margin-left:auto`）同排。两者均**无 `min-width:0`、无收缩/滚动控制**，窄窗时文字不换行、不收缩 → 内容溢出 `.topbar` 边界（fixed 容器无 overflow 处理）→ 视觉错位/重叠。

### 1.2 核心修复（所有断点通用，不依赖 media query）
品牌区固定不收缩；导航区在剩余空间内横向滚动（隐藏滚动条），**永不重叠**。

```css
/* 在 style.css 的 .logo / .nav-tabs / .nav-tab 上增量修改 */
.logo {
  flex: 0 0 auto;      /* 原为 display:flex，新增：永不收缩 */
  min-width: 0;
  white-space: nowrap; /* 品牌永不换行 */
}
.nav-tabs {
  flex: 1 1 auto;      /* 占据剩余空间 */
  min-width: 0;        /* 允许收缩到能触发内部滚动 */
  margin-left: auto;
  justify-content: flex-end;
  overflow-x: auto;    /* 窄窗时 tab 横向滚动，代替换行/重叠 */
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.nav-tabs::-webkit-scrollbar { display: none; }
.nav-tab {
  flex: 0 0 auto;      /* tab 保持自然宽度，不被压扁 */
}
```
> 以上为**根因修复**：即使不写任何 media query，窗口缩到多窄都不会错位，只是 tab 会横向滚动。

### 1.3 渐进式视觉降级（media query，仅做美观压缩）

| 断点 | 行为 | 修改 |
|------|------|------|
| `≥961px` | 完整：品牌含英文副标题，5 个 tab 正常 | — |
| `≤960px` | 隐藏英文副标题，tab 内边距收紧 | `.subtitle{display:none}`；`.nav-tab{padding:8px 12px}` |
| `≤820px` | 顶栏内边距/间距收紧，tab 字号 12px | `.topbar{padding:0 16px;gap:12px}`；`.nav-tab{font-size:12px;padding:7px 10px}` |
| `≤680px` | logo 略缩，tab 进一步压缩（仍横向滚动） | `.logo{font-size:16px}`；`.logo .logo-img{height:28px}`；`.nav-tab{padding:6px 8px}` |
| `≤520px`（可选） | 仍走滚动；**不建议**加汉堡菜单（桌面工具 5 个短 tab 始终可见更优） | — |

**结论：推荐「横向滚动」方案（而非汉堡菜单）。** 理由：本产品为 Windows 桌面应用，5 个中文短标签在任意宽度下都易于容纳；滚动方案零 JS、零额外 DOM、可发现性最好；汉堡菜单会增加状态管理与点击成本，对桌面场景收益低。

---

## 2. 删除作者标签后的顶部布局

- **HTML**：删除 `<span class="app-author">软件作者：LuoLei</span>`（位于 `.logo` 内）。
- **CSS**：`.app-author` 规则可保留（不再被引用）或删除；建议删除避免死代码。
- **品牌区构成（左）**：`⚡ logo-img` + `国企大表哥`（标题） + `guoqibigbro · 填表表哥`（副标题，≤960px 隐藏）。
- **右侧**：5 个导航 tab，右对齐。
- **版本号位置**：不在顶栏（保持简洁），统一在「关于」页与「使用说明」头部呈现（见 §4）。
- 顶栏净高保持 56px，`.page` 的 `top:56px` 不变。

---

## 3. 「预览确认 + 执行结果」合并页

### 3.1 页签定位与命名
- **位置**：第 3 个 tab（index 2），即原「预览确认」所在位。这样 `switchPage(2)`、`if(idx===2) renderPreview()` 逻辑零改动；原「执行结果」(index 3) 删除，其后页签前移（使用说明→3，关于→4）。
- **命名（推荐）**：**「预览执行」**。
  - 备选（既有内部预览曾用）：「执行结果」。
  - 取舍：合并页同时承载「预览表格」与「执行」，叫「预览执行」更贴合双阶段语义，也与字段映射页的入口按钮「确认并预览」首尾呼应。如团队更看重与既有预览一致，可用「执行结果」。
- 页签数组（index: 文案）：`0 数据源 · 1 字段映射 · 2 预览执行 · 3 使用说明 · 4 关于`

### 3.2 页面信息架构（单页，纵向滚动）
```
┌───────────────────────────────────────────────┐
│ [📋 预览执行] 共 N 字段·已匹配 M 个  [✅ 确认执行]│  ← 页头：标题+状态 / 主操作
├───────────────────────────────────────────────┤
│ ▸ 预览表格（可折叠）                              │
│   ┌─────────────────────────────────────┐     │
│   │ 行号|姓名(来自…)|部门(来自…)|状态     │     │  ← 只读预览表（renderPreview 渲染）
│   │ ... 预览前 5 行 ...                   │     │
│   └─────────────────────────────────────┘     │
│   （折叠开关：预览表格 ▾ / ▸）                  │
├───────────────────────┴───────────────────────┤
│ ——————— 执行 ———————                          │  ← 分隔
├───────────────────────────────────────────────┤
│             ◯ 进度环 0%                         │  ← 执行态
│        [▶ 开始执行]（确认后自动进入）            │
│   ┌─────────────────────────────────────┐     │
│   │ ✅ 已加载 3 个数据源                   │     │  ← 日志（showExecutionResult/renderLogs）
│   │ ✅ 字段匹配完成，匹配率 92%            │     │
│   │ 📦 完成！结果已保存 …                  │     │
│   └─────────────────────────────────────┘     │
│   [📂 打开结果文件]   [🔄 新建任务]             │  ← 完成态操作
└───────────────────────────────────────────────┘
```

### 3.3 交互流程（字段映射 → 预览执行）
1. 用户在**字段映射**(page-1) 核对匹配，点右上「确认并预览 →」（`onclick="switchPage(2)"`）→ 跳转合并页。
2. `switchPage(2)` → 触发 `renderPreview()` 渲染预览表格（前 5 行 + 状态列）。
3. 用户审阅预览；可点「预览表格 ▾」折叠面板以预留空间（可选）。
4. 点「✅ 确认执行」（`class="run-btn"`，`onclick="confirmAndExecute()"`）：
   - `confirmAndExecute()` 改为**不再 `switchPage(3)`**，直接 `await doExecute()`（逻辑见 §3.5）。
   - `doExecute()` 隐藏所有 `.run-btn`（头部确认按钮随之隐藏），调用 `execute_fill`，`showExecutionResult()` 驱动进度环 0→100%。
   - 100% 后 `renderLogs()` 渲染日志，显示「打开结果文件」「新建任务」。
5. 「📂 打开结果文件」→ `openResultFolder()`（沿用）；「🔄 新建任务」→ `resetAll()`（沿用，内部 `switchPage(0)` 仍有效）。

### 3.4 必须保留的元素 id（保证 app.js 不改写）
`page-2`、`preview-table`、`preview-info`、`progress-circle`、`progress-text`、`.progress-ring`(done 态)、`log-list`、`export-btn`、`reset-btn`。合并页即把原 page-2 与 page-3 的 DOM 合并到 `page-2` 容器内。

### 3.5 需要的 JS 最小改动（app.js）
- `confirmAndExecute()`：删除 `switchPage(3);` 一行，仅保留 `await doExecute();`（其余不变，因执行 UI 现同页）。
- `switchPage()`：`if (idx === 2) renderPreview();` 保持不变（合并页就是 index 2）。
- 键盘导航：`if (currentPage < 3)` → 改为 `if (currentPage < 4)`（现共 5 页）。

> 以上改动可让合并页在**不重写任何执行/预览逻辑**的前提下落地。

---

## 4. V1.1 版本标识与更新日志

### 4.1 关于页
- 标题区版本徽标：`版本 V1.0` → **`版本 V1.1`**。
- 信息卡「当前版本」：`V1.0` → **`V1.1`**；「发布日期」更新为 **2026-07**（或实际发布月）。
- 「开发人员：LuoLei」保留（作者信息唯一归属处，呼应删除顶栏标签的决定）。
- 新增「📝 更新日志」区块（手风琴/静态列表均可），含 V1.1 与 V1.0 两条。

### 4.2 更新日志内容（文案可直接用）
**V1.1 · 2026-07**
- 顶部导航响应式适配，窗口缩小时不再错位（窄窗隐藏副标题、tab 横向滚动）
- 移除首页「软件作者：LuoLei」标签，作者信息统一在「关于」页
- 合并「预览确认」与「执行结果」为单页「预览执行」，减少来回切换
- 新增「更新日志」
- 若干体验细节优化与已知问题修复

**V1.0 · 2026-07**
- 首个正式版本：多源 Excel 智能归集、同义词识别、模板格式保留、结果自动落盘

### 4.3 版本药丸（可选一致性增强）
在「使用说明」页标题旁加 `<span class="version-pill">V1.1</span>` 小药丸（样式沿用 `--primary` 圆角药丸），与关于页风格呼应。

---

## 5. Media Query 清单（可直接粘贴）
```css
/* ===== V1.1 响应式（追加到 style.css 末尾）===== */
@media (max-width: 960px) {
  .subtitle { display: none; }
  .nav-tab { padding: 8px 12px; }
}
@media (max-width: 820px) {
  .topbar { padding: 0 16px; gap: 12px; }
  .nav-tab { font-size: 12px; padding: 7px 10px; }
}
@media (max-width: 680px) {
  .logo { font-size: 16px; }
  .logo .logo-img { height: 28px; }
  .nav-tab { padding: 6px 8px; }
}
/* ≤520px 维持横向滚动即可，无需额外处理 */
```

---

## 6. 前端实现清单（Checklist）
- [ ] `style.css`：`.logo`/`.nav-tabs`/`.nav-tab` 增量修复（§1.2）；追加 media query（§5）；删除/保留 `.app-author`。
- [ ] `index.html` 顶栏：删除 `.app-author`；导航改为 5 个 tab，第 3 个为「预览执行」。
- [ ] `index.html`：`.page-dot` 由 6 个减为 5 个。
- [ ] `index.html`：删除原 `page-3`（执行结果）独立页；将其执行 UI 合并进 `page-2`，保留全部 id。
- [ ] `index.html` 关于页：版本号改 V1.1；新增「更新日志」区块；可选使用说明版本药丸。
- [ ] `app.js`：`confirmAndExecute()` 去掉 `switchPage(3)`；键盘上限 `3→4`。
- [ ] 验证：窄窗（拖动/缩放）顶栏不串位；从字段映射「确认并预览」进入合并页预览→确认执行→打开文件夹全链路正常。

---

## 7. 与既有 V1.1 预览方案的差异与取舍
仓库已存在两份内部预览（`preview-v1.1.html` 方案A、`v1.1-preview.html` 方案B）。本说明在二者基础上做如下拍板：
- **响应式**：采用方案A 的「横向滚动」而非方案B 的「汉堡菜单」——更适合桌面应用，零 JS。
- **合并页命名**：推荐「预览执行」（方案B 用「执行结果」）；位置一致（第 3 tab / index 2）。
- **合并页结构**：采用「预览表格可折叠 + 执行态」组合（融合二者优点：方案A 的纵向分区 + 方案B 的折叠交互），保留全部 id 以保证 app.js 逻辑不变。
- **使用说明步骤**：维持原 5 步（不强行精简为 4 步），避免与既有文案冲突；仅追加版本药丸。

---

## 8. 修正与补充（designer-15 审阅 · 2026-07）

### 8.1 顶部导航滚动方案的关键 CSS 修正（修正 §1.2）
§1.2 的 `.nav-tabs { flex:1 1 auto; justify-content:flex-end }` 有两个问题：
(a) `flex:1 1 auto` 让 nav-tabs 撑满剩余宽度；内部 `justify-content:flex-end` 在**内容溢出触发横向滚动时，会把最左侧 tab 初始滚出且无法回滚**（flex+overflow 已知缺陷）；即便不溢出，tab 也被推到 nav-tabs 盒子右端，与 logo 间出现大片空隙，不像"顶栏右侧导航"。
(b) 应改为"nav-tabs 自身不撑满、靠 `margin-left:auto` 在顶栏级右对齐；内部默认左对齐（首 tab 始终可达）；溢出时滚动"：

```css
.logo { flex: 0 0 auto; min-width: 0; white-space: nowrap; }   /* 品牌不收缩、不换行 */
.nav-tabs {
  flex: 0 1 auto;        /* 不撑满，按需收缩 */
  min-width: 0;          /* 允许收缩到能触发内部滚动 */
  margin-left: auto;     /* 右侧对齐（顶栏级） */
  overflow-x: auto;      /* 窄窗 tab 横向滚动，不重叠 */
  scrollbar-width: none; -ms-overflow-style: none;
}
.nav-tabs::-webkit-scrollbar { display: none; }
.nav-tab { flex: 0 0 auto; white-space: nowrap; }   /* tab 保持自然宽度 */
```
> 任意宽度下都不会错位/重叠，且首 tab 始终可滚动到达。

> 同步：仓库内 `v11-preview.html` 的 `.nav-tabs`（line 42）仍为 `flex:1 1 auto; margin-left:auto`（未写 flex-end，故未触发"首 tab 不可达"，但写法不够干净），收口时一并改为本形式以保持全仓库一致。

### 8.2 修复潜在 bug：`--card-bg` 未定义
`index.html` 的「使用说明」「关于」页大量使用 `var(--card-bg)`，但 `style.css :root` 只定义了 `--card:#FFFFFF`，**未定义 `--card-bg`**。这些卡片 `background:var(--card-bg)` 失效 → 卡片无填充背景（仅剩边框），与全站白卡风格不一致（Major 级视觉问题）。
修复（二选一，推荐前者）：
- 在 `:root` 增加 `--card-bg: #FFFFFF;`
- 或把 HTML 中所有 `var(--card-bg)` 改为 `var(--card)`。

### 8.3 合并页交互细节补强（补充 §3）
1. **执行中锁定预览**：`doExecute()` 开头给 `.preview-panel` 加 `.locked`（`pointer-events:none; opacity:.55`），禁止执行期间误触；`.run-btn` 隐藏沿用现有逻辑。
2. **完成后自动滚动到日志**：`showExecutionResult()` 在 100% 时 `document.getElementById('log-list').scrollIntoView({behavior:'smooth', block:'start'})`，并自动 `previewPanel.classList.add('collapsed')` 收起预览以聚焦结果（v1.1-preview 已实现折叠，建议补滚动）。
3. **预览表格高度收敛**：`.preview-table` 容器加 `max-height:360px; overflow:auto`，避免行多时整页过长、执行区被推太远。
4. **返回修改入口**：预览区加次要按钮「✏️ 返回修改」（`onclick="switchPage(1)"`），方便回字段映射调整。
5. **命名统一**：见 §8.4。

### 8.4 合并页命名 / 结构需统一（待 team-lead 定方向，勿抢改）
经 designer-11 全量核对，仓库现有 **两套结构 + 三种合并页命名**，命名分歧是"方向未定"的症状而非单纯改字：
- **5-tab 结构**（使用说明/关于仍为主 tab，圆点 6→5）：
  - DESIGN-V1.1.md →「**预览执行**」
  - `v1.1-preview.html` →「**执行结果**」（汉堡菜单方案）
  - `v11-preview.html` →「**执行填表**」（横向滚动方案）
  → 连 5-tab 派内部都三名字不统一。
- **3+2 结构**（使用说明/关于降为工具图标，圆点 6→3）：`v1.1-designer16.html` v3（团队当前收敛推荐），合并页叫「**执行**」。
结论：方向未定前不要逐个改名（会做两遍）。待 team-lead 拍板：
- 若选 **3+2**：DESIGN-V1.1.md 需整体重写（现为 5-tab「预览执行」，与 3+2 不符），所有预览统一到「执行」+ 3+2。
- 若选 **5-tab**：再把三份预览统一到文档的「预览执行」。
由 designer-11 在方向确认后牵头收口（含 §1.2 改正、nav CSS 统一为 §8.1、--card-bg 写入真实 style.css）。

### 8.5 断点取值依据（支撑 §5）
5 个 tab 在完整内边距(16px)/13px 下约 410px；含副标题的 logo 约 240px；顶栏 padding+gap 约 64px → **完整布局临界 ≈ 714px**（故 ≥961px 留足余量、`≤960px` 隐藏副标题合理）。隐藏副标题后 logo≈120px → **≈594px 仍可单行**（故 `≤820/680` 仅压缩、无需更早收起）。横向滚动在 `≤520px` 仍可用，无需汉堡菜单。

### 8.6 a11y 小补
`.nav-tab:focus-visible { outline:2px solid var(--primary); outline-offset:2px; }`，提升键盘可达性（现有仅 hover/active）。
