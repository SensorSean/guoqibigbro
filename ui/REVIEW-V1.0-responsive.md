# 国企大表哥 V1.0 · 设计审查（响应式错位修复 + 方案）

> 审查对象：`国企大表哥_v4/ui/`（pywebview 桌面应用，最小窗口 800×600）
> 审查者：designer-27
> 范围：顶部导航窄窗错位、首页垂直布局、字段映射三栏窄屏、删除作者标签后的 logo 区重组、预览/执行合并交互
> 配套文档：本仓库已有 `DESIGN.md` / `DESIGN-V1.1.md`（覆盖导航、作者标签、合并页）。本审查在其基础上**补齐两处空白**：首页 `.home-center` 垂直布局（Q2）与字段映射 `.mapper-layout` 三栏窄屏（Q3），并对全部 5 问给出可执行 CSS。

---

## 0. 核心设计判断

V1.0 的错位根因不是「窗口太小」，而是**顶部 `.topbar` 是一个没有任何收缩/溢出控制的单行 flex**：`.logo`（含 logo 图 + 标题 + 副标题 + 作者标签，约 360px）和 `.nav-tabs`（`margin-left:auto`）同排，二者都是 `flex-shrink:1` 的默认值且没有 `min-width:0`、tab 文字未 `nowrap`，于是窗口一窄 → flex 同时挤压两侧 → tab 文字换行成「数据／源」、作者标签挤占 ~110px 进一步恶化、`.app-author` 与 nav 重叠溢出 fixed 容器 → 视觉错位。修复策略应当是**「根因修复（不依赖断点，永不重叠）+ 渐进式视觉降级」**：先让 logo 不收缩、nav 区占满剩余空间并 `overflow-x:auto` 横向滚动，再按断点隐藏副标题/压缩 tab；删除作者标签一次省出 ~110px，是性价比最高的单项改动。

其余两处空白（首页、映射页）采用同一原则：**让容器可滚动、让固定列有下限收缩、用断点触发堆叠/压缩，而不是靠 `overflow:hidden` 硬裁切**。桌面端最小窗口 800px 是硬约束，意味着三栏布局只要把侧栏从 280px 收到 ~220px、中心列加 `min-width:0`，在 800px 下仍可正常工作，不必上汉堡菜单或强制堆叠；堆叠只在窗口可低于 ~720px 时才需要。

---

## 1. 顶部导航（Q1）：窄屏响应式策略

**明确建议（三选一决策）：**
- ❌ **隐藏文字只留图标**：不推荐。5 个中文短标签（数据源/字段映射/预览/说明/关于）在任何宽度都易容纳，图标化反而降低可发现性，且需改 DOM + JS，收益低。
- ❌ **汉堡下拉菜单**：不推荐。桌面工具 5 个 tab 始终可见更优；汉堡增加状态管理与点击成本。
- ✅ **横向滚动 + 渐进压缩（推荐）**：零 JS、零额外 DOM、可发现性最好。这正是 `DESIGN.md` 已定的方向，本审查确认采用。

**根因修复（所有宽度通用，不写 media query 也绝不重叠）：**

```css
/* —— 替换原 .logo / .nav-tabs / .nav-tab 规则 —— */
.logo {
  font-size: 18px; font-weight: 800; color: var(--primary);
  display: flex; align-items: center; gap: 8px; cursor: default;
  flex-shrink: 0;            /* 关键：品牌区永不收缩 */
  min-width: 0;
  white-space: nowrap;       /* 品牌永不换行 */
}
.logo .logo-img { height: 32px; width: auto; image-rendering: pixelated; transition: transform .3s; flex-shrink: 0; }
.logo .logo-img:hover { transform: rotate(4deg) scale(1.08); }
.subtitle { font-size: 11px; color: var(--text-secondary); font-weight: 400; letter-spacing: .5px; white-space: nowrap; flex-shrink: 0; }

.nav-tabs {
  display: flex; gap: 4px; margin-left: auto;
  flex: 1 1 auto;            /* 占据剩余空间 */
  min-width: 0;              /* 允许收缩到能触发内部滚动 */
  justify-content: flex-end;
  overflow-x: auto;          /* 窄屏横向滚动，代替换行/重叠 */
  overflow-y: hidden;
  scrollbar-width: none; -ms-overflow-style: none;
}
.nav-tabs::-webkit-scrollbar { display: none; }

.nav-tab {
  padding: 8px 16px; border-radius: var(--radius);
  font-size: 13px; color: var(--text-secondary);
  white-space: nowrap; flex-shrink: 0;   /* 关键：tab 不压扁、不换行 */
  cursor: pointer; transition: all var(--transition); border: none; background: none;
}
.nav-tab.active, .nav-tab:hover { background: var(--primary-bg); color: var(--primary); font-weight: 500; }
```

**渐进式视觉降级（仅做美观压缩，粘贴到 style.css 末尾）：**

```css
@media (max-width: 1080px) { .subtitle { display: none; } }            /* 省 ~150px */
@media (max-width: 860px)  { .topbar { padding: 0 16px; gap: 12px; }
                              .nav-tab { padding: 8px 12px; font-size: 12px; } }
@media (max-width: 620px)  { .logo { font-size: 16px; }
                              .logo .logo-img { height: 28px; }
                              .nav-tabs { gap: 2px; } }
/* ≤520px 维持横向滚动即可，无需汉堡 */
```

> **关于「压缩 logo 区宽度」**：删除作者标签已省 ~110px；副标题在 ≤1080px 隐藏再省 ~150px。窄屏下 logo 区几乎只剩「⚡ 国企大表哥」约 150px，无需额外压缩——这正是优先删作者标签的原因。

---

## 2. 删除「软件作者：LuoLei」后的 logo 区重组（Q4）

**建议：副标题保持与标题同一行（inline），不单独换第二行。**

- 顶栏固定 56px、`align-items:center`。若副标题换到第二行，`.logo` 需变纵向，会抬高 logo 区视觉重心、在 56px 栏内显得拥挤；inline 一行更紧凑、横向更省空间。
- 副标题在 ≤1080px 已隐藏（见 §1），所以窄屏 logo 区极简，不会因副标题换行制造第二行。
- 若未来想在大屏强调副标题，可改为「标题 + 副标题同行，副标题用 `·` 连接」的紧凑写法：`国企大表哥 · guoqibigbro 填表表哥`，但当前 `.subtitle` 独立 span 已足够，无需改结构。

**改动清单：**
- `index.html`：删除 `<span class="app-author">软件作者：LuoLei</span>`（位于 `.logo` 内）。
- `style.css`：删除 `.app-author` 整块（第 20–31 行）避免死代码。作者信息唯一归属处为「关于」页「开发人员：LuoLei」卡片，无信息损失。
- 顶栏净高保持 56px，`.page` 的 `top:56px` 不变。

---

## 3. 首页 `.home-center` 垂直布局（Q2）★本审查新增

**问题定位（原 CSS 风险）：**
```css
.home-center {
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  max-width: 460px; width: 100%; margin: 0 auto;
  justify-content: flex-start;        /* 内容贴顶 */
  height: calc(100vh - 56px);         /* 与 .page 高度重复 */
  padding: 8px 16px 0 16px;
  overflow: hidden;                   /* ⚠ 风险：文件标签多时整块被裁切 */
}
```
- `overflow:hidden` + 固定高度：当用户选了多个数据源，`#src-tags` 换行累积，内容高度超过容器即被**静默截断**（看不到底部「开始智能匹配」按钮）。这是真实可用性问题，当前 V1.0 未处理。
- `justify-content:flex-start` + 顶部 `padding:8px`：在**高窗口**（如 1080p 全屏，home-center≈960px）下，全部内容贴顶，下方留出大片空白，hero 感差。

**修复（安全不裁切 + 高屏有呼吸感）：**
```css
.home-center {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  max-width: 460px; width: 100%; margin: 0 auto;
  height: 100%;                       /* 改用 100%，由 .page 绝对定位撑高，避免重复计算 */
  min-height: 0;
  padding: clamp(16px, 6vh, 56px) 16px 16px;   /* 高屏顶部留白，矮屏不裁切顶部 */
  overflow-y: auto;                   /* ⚠ 关键：内容超长可滚动，不再截断 */
  box-sizing: border-box;
}
/* 文件标签区允许自身滚动，避免撑爆整页 */
.file-tags { display: flex; flex-wrap: wrap; gap: 8px; width: 100%; max-height: 132px; overflow-y: auto; }
```
> 用 `height:100%` 替代 `calc(100vh - 56px)`：`.page` 已是 `top:56px; bottom:0` 的绝对定位容器，home-center 直接吃满即可，语义更对、且删除顶栏高度硬编码后未来若改 topbar 高度无需同步改这里。
> 不用 `justify-content:center`：flex 居中 + `overflow:auto` 在内容溢出时会**裁掉顶部**（经典 flexbox 坑），故用 `flex-start` + `clamp()` 顶部留白，既安全又有 hero 感。

---

## 4. 字段映射 `.mapper-layout` 三栏窄屏（Q3）★本审查新增

**问题定位：** 左右固定 `280px`，中心 `flex:1` 但**没有 `min-width:0`**。窗口缩到 ~900px 时中心列被压到 ~340px（280+280+340=900），`match-row` 内 `src/tgt` 各 `flex:1`，`match-area` `min-height:300px` 尚可；但若窗宽继续逼近 800px（最小窗口）中心仅剩 ~240px，匹配行文字会严重挤压。原布局无收缩下限、无堆叠兜底。

**修复（桌面最小 800px 下保持三栏，侧栏收缩 + 中心允许收缩）：**
```css
/* —— 在现有 .mapper-center 上补 min-width:0 —— */
.mapper-center {
  flex: 1; min-width: 0;              /* 关键：中心可收缩并在内部滚动，而非把侧栏挤出 */
  padding: 24px; display: flex; flex-direction: column; gap: 16px;
  background: var(--bg); overflow-y: auto;
}

/* 窄屏：侧栏从 280 收到 220，保住中心可用宽度 */
@media (max-width: 900px) {
  .mapper-left, .mapper-right { width: 220px; padding: 16px; }
  .mapper-center { padding: 16px; }
}
```
> 计算：800px 最小窗口 − 220 − 220 = **360px 中心列**，配合 `min-width:0` 内部滚动，三栏不破。无需堆叠。

**可选增强（仅当窗口可低于 ~720px 才需要）：上下堆叠**
```css
@media (max-width: 720px) {
  .mapper-layout { flex-direction: column; height: auto; overflow: visible; }
  .mapper-left, .mapper-right { width: 100%; border: none; border-bottom: 1px solid var(--border); }
  .mapper-center { min-height: 50vh; }
}
```
> 当前 pywebview 最小 800px，堆叠为「可选增强」，优先级 P2。若产品后续放宽为可拖到更小，再启用。

---

## 5. 预览 / 执行合并交互（Q5）

**建议：采用纵向「预览表在上、执行态在下」同页内完成（与 team-lead 描述的「预览表格放在执行结果页上方，点确认执行后在该页内显示进度和结果」一致）。** 这与本仓库 `DESIGN-V1.1.md` 的方案吻合；`DESIGN.md` 的左右分栏方案也可行，但纵向堆叠更贴合现有 `app.js` 结构（执行 UI 直接 append 进 page-2，无需新增侧栏组件）。

**页签定位**：合并页放在**第 3 位（index 2）**，即原「预览确认」位置。`switchPage(2)` 与 `if(idx===2) renderPreview()` 零改动；原 index 3「执行结果」删除，其后页签前移（使用说明→3，关于→4）。tab 文案：`0 数据源 · 1 字段映射 · 2 预览执行 · 3 使用说明 · 4 关于`。

**交互流程**：
1. 字段映射页点「确认并预览 →」`switchPage(2)` → `renderPreview()` 渲染前 5 行预览表。
2. 用户审阅；点「✅ 确认执行」（`confirmAndExecute()`）。
3. `confirmAndExecute()` 改为**不再 `switchPage(3)`**，直接 `await doExecute()`，进度环 0→100% 在原页内显示，完成后 `renderLogs()` 渲染日志、显示「打开结果文件」「新建任务」。
4. 复用全部既有 id：`page-2` / `preview-table` / `preview-info` / `progress-circle` / `progress-text` / `log-list` / `export-btn` / `reset-btn`——app.js 执行逻辑不改写。

**必须保留的 JS 最小改动（app.js）**：
- `confirmAndExecute()`：删除 `switchPage(3);`，仅保留 `await doExecute();`。
- `switchPage()`：`if (idx === 2) renderPreview();` 不变。
- 键盘导航：`if (currentPage < 3)` → `if (currentPage < 4)`（现共 5 页）。
- `page-dot` 与 `nav-tab` 数量 6→5（HTML 各删一个）。

> 详细 DOM/结构与更新日志见 `DESIGN-V1.1.md` §3、§4。本审查不重复，仅做交互拍板与对齐。

---

## 6. 针对响应式错位的最小改动方案（P0 实施清单）

只改 3 处即可根治顶栏错位，零 JS：

1. **`.logo`**：加 `flex-shrink:0; min-width:0; white-space:nowrap;`
2. **`.nav-tabs`**：加 `flex:1 1 auto; min-width:0; overflow-x:auto; overflow-y:hidden;`（含隐藏滚动条伪元素）
3. **`.nav-tab`**：加 `white-space:nowrap; flex-shrink:0;`
4. **删除 `.app-author`** 标签（HTML）+ 删除对应 CSS 块 → 一次省 ~110px
5. **追加 §1 末尾三段 media query**（隐藏副标题 / 压缩 tab / 缩 logo）

完成以上，窗口拖到多窄顶栏都不会错位，只是 tab 横向滚动。

---

## 7. 需要开发团队注意的实现细节 / 风险

1. **JS 索引漂移（高）**：合并后页面 6→5，所有 `switchPage(n)` 调用、键盘 `currentPage` 上限、`.page-dot` 数量须同步更新，否则跳到不存在的 page-3。
2. **`confirmAndExecute` 删 `switchPage(3)`（高）**：若不删会跳空页；进度/日志/导出/重置元素现已在 page-2 按 id 取用。
3. **`.home-center` 改 `height:100%` 后依赖 `.page` 定位**：确认 `.page` 仍为 `top:56px; bottom:0`（是），否则高度塌缩。
4. **`.mapper-center` 补 `min-width:0`**：否则窄屏仍会挤出侧栏（经典 flex 坑）。
5. **pywebview 最小窗口（中）**：建议代码中设 `min_size(800, 600)`，与 CSS 配合；若放宽到 <720px，启用 §4 堆叠增强。
6. **横向滚动可发现性（低）**：极窄时 nav 滚动已隐藏滚动条；可在 `.nav-tabs` 两侧加轻微渐隐阴影提示边缘可滚（可选）。
7. **视觉回归（中）**：合并页、堆叠布局须复用 `--card/--shadow/--radius` 变量，禁止引入新颜色/圆角。
8. **空态保护（中）**：合并页预览表空态「请先完成字段映射」保留；`confirmAndExecute` 前校验 preview 已渲染，避免无可执行数据误触。
9. **彩蛋不受影响（无）**：logo `onclick="easterEgg()"` 保留，删作者文本不影响。

---

## 8. 优先级建议

| 优先级 | 改动 | 理由 |
|--------|------|------|
| **P0** | 顶栏根因修复（§1）+ 删除 `.app-author`（§2）+ §1 media query | 直接解决 lead 反馈的错位；零 JS、低风险、收益最高 |
| **P0** | 预览/执行合并（§5） | lead 明确的交互诉求；减页签缓解导航拥挤 |
| **P1** | `.home-center` 修溢出（§3） | 真实截断 bug（多文件时看不到按钮），当前 V1.0 未处理；改动小 |
| **P1** | `.mapper-center` 加 `min-width:0` + 侧栏 220px（§4） | 防止窄屏挤出侧栏，桌面最小窗口下保可用性 |
| **P2** | `.mapper-layout` 堆叠增强（§4 ≤720px） | 仅当窗口可低于 720px 时需要；当前最小 800px 非必需 |
| **P2** | 导航边缘渐隐阴影、使用说明版本药丸 | 体验抛光，可选 |

---

### 与既有文档的关系
- 顶栏（Q1）、作者标签（Q4）、合并（Q5）与 `DESIGN.md` / `DESIGN-V1.1.md` 方向一致，本审查确认采用并给出可粘贴 CSS。
- **首页垂直布局（Q2）与字段映射三栏窄屏（Q3）为本次新增**，填补了 V1.1 文档的空白（原文档未覆盖这两个容器的响应式/溢出行为）。
