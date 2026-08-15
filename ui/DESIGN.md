# Design System — 国企大表哥 V1.1（迭代调整）

> 在 V1.0 紫色科技风基础上，修复顶部导航窄窗口错位、移除冗余作者标识、合并「预览确认/执行结果」为单页、升级至 V1.1 并新增更新日志。视觉语言（配色 / 圆角 / 阴影 / 间距基数 8px）保持与 V1.0 一致，不引入新变量。

---

## 1. 顶部导航响应式布局方案

### 根因
原 `.logo` 与 `.nav-tabs` 均未设 `flex-shrink: 0`，也未给 `.nav-tab` 设 `white-space: nowrap`。
窗口变窄时 flex 同时压缩两侧，tab 文字被挤压换行（数据\n源），并因 `.app-author` 占据 ~110px 进一步加剧。

### 修复原则
- **logo 区不压缩**：`flex-shrink: 0`，始终保留自身宽度。
- **tab 不换行**：`.nav-tab { white-space: nowrap; flex-shrink: 0 }`。
- **nav 区占剩余空间**：`.nav-tabs { flex: 1 1 auto; min-width: 0; overflow-x: auto }` —— 空间不足时内部横向滚动，绝不再换行堆叠。
- **删除 `.app-author`**，副标题在中宽屏收起。

### 行为分档
| 窗口宽度 | 顶部导航表现 |
|----------|--------------|
| ≥ 1080px | logo 完整（图 + 国企大表哥 + 副标题）；5 个 tab 全内边距（16px） |
| 860–1080px | 隐藏副标题；tab 全内边距 |
| 620–860px | 隐藏副标题；tab 内边距压缩至 12px、字号 12px；topbar 内边距收窄 |
| < 620px | logo 字号略缩、图标 28px；tab 横向滚动兜底（桌面端罕见，保证不崩） |

> 合并后 tab 数 6→5，全尺寸下总宽约 410px，较 V1.0 减少 ~75px，错位风险大幅降低。

---

## 2. 删除作者后的左侧区域新结构

```html
<div class="logo" onclick="easterEgg()" title="国企大表哥">
  <img src="logo-pixel.svg" class="logo-img" alt="国企大表哥">
  国企大表哥
  <span class="subtitle">guoqibigbro · 填表表哥</span>
</div>
```

- 移除 `<span class="app-author">软件作者：LuoLei</span>`（HTML 删除 + CSS `.app-author` 块删除）。
- 作者信息保留于「关于」页「开发人员：LuoLei」卡片，无信息损失。
- `.logo` 加 `flex-shrink: 0; min-width: 0`，`.subtitle` 加 `white-space: nowrap; flex-shrink: 0`。
- 彩蛋 `onclick="easterEgg()"` 保留，不受影响。

---

## 3. 「预览确认」+「执行结果」合并页面布局

### 推荐：默认左右分区，窄屏上下堆叠
- **宽屏（≥ 980px）**：左侧 `预览表格` 占满剩余宽度（内部滚动）；右侧 `执行面板` 固定 320px 侧栏（进度环 + 阶段文案 + 确认并执行 + 日志 + 打开结果/新建任务）。
- **窄屏（< 980px）**：上下堆叠，执行面板移到预览下方，整页滚动；执行按钮 `position: sticky; bottom: 0` 常驻可见。

### 理由
- 预览表为宽表，适合横向铺满；执行控件（进度/日志/按钮）纵向信息密集，适合侧栏。
- 合并后单页即完成「核对 → 执行 → 看结果」，路径更短；tab 数 6→5，也缓解导航拥挤。
- 复用既有 `.preview-table`、`.progress-ring-wrap`、`.log-item`、`.pill` 组件，零新视觉元素。

```html
<div class="page" id="page-2">
  <div class="pe-layout">
    <section class="pe-preview">
      <header class="pe-head">
        <div>
          <div class="pe-title">📋 预览与执行</div>
          <div class="pe-sub" id="preview-info"></div>
        </div>
        <span class="pe-count" id="pe-count">待填充 0 行</span>
      </header>
      <div class="preview-table" id="preview-table">
        <div style="padding:40px;text-align:center;color:var(--text-secondary)">请先完成字段映射</div>
      </div>
    </section>

    <aside class="pe-exec">
      <div class="progress-ring-wrap">
        <svg class="progress-ring" width="140" height="140">
          <circle class="bg" cx="70" cy="70" r="60" fill="none" stroke-width="8"/>
          <circle class="fill" id="progress-circle" cx="70" cy="70" r="60" fill="none" stroke-width="8"
                  stroke-linecap="round" stroke-dasharray="377" stroke-dashoffset="377"/>
        </svg>
        <div class="progress-text" id="progress-text">0%</div>
      </div>
      <div class="pe-stage" id="pe-stage">待执行</div>
      <button class="pill pill-primary pill-lg run-btn" id="run-btn" onclick="confirmAndExecute()" style="width:100%;justify-content:center">
        ✅ 确认并执行
      </button>
      <div class="log-list" id="log-list" style="display:none"></div>
      <button class="pill pill-success pill-lg" id="export-btn" style="display:none;width:100%;justify-content:center" onclick="openResultFolder()">📂 打开结果文件</button>
      <button class="pill pill-outline pill-sm" id="reset-btn" style="display:none;width:100%;justify-content:center" onclick="resetAll()">🔄 新建任务</button>
    </aside>
  </div>
</div>
```

```css
.pe-layout {
  display: flex; gap: 20px; width: 100%;
  height: calc(100vh - 56px);
  padding: 24px; box-sizing: border-box; overflow: hidden;
}
.pe-preview { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 16px; overflow: hidden; }
.pe-head { display: flex; align-items: flex-end; justify-content: space-between; }
.pe-title { font-size: 20px; font-weight: 800; }
.pe-sub { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.pe-count { font-size: 12px; font-weight: 600; color: var(--primary); background: var(--primary-bg); padding: 4px 12px; border-radius: 999px; white-space: nowrap; }
.pe-preview .preview-table { flex: 1 1 auto; overflow: auto; }

.pe-exec {
  flex: 0 0 320px; width: 320px;
  background: var(--card); border-radius: 16px; padding: 24px;
  box-shadow: var(--shadow);
  display: flex; flex-direction: column; align-items: center; gap: 16px;
  overflow-y: auto;
}
.pe-stage { font-size: 13px; color: var(--text-secondary); font-weight: 600; }

@media (max-width: 980px) {
  .pe-layout { flex-direction: column; height: auto; overflow: visible; }
  .pe-preview { overflow: visible; }
  .pe-preview .preview-table { max-height: 50vh; }
  .pe-exec { flex: 1 1 auto; width: 100%; }
  .pe-exec .run-btn, .pe-exec #export-btn, .pe-exec #reset-btn { position: sticky; bottom: 0; }
}
```

---

## 4. V1.1 版本标识与更新日志

### 版本号
- 「关于」页顶部徽标：`版本 V1.0` → `版本 V1.1`。
- 「当前版本」卡片：`V1.0` → `V1.1`。
- 发布日期卡片保留 `2026-07`。

### 更新日志位置
放在「关于」页内（新增卡片），不新增顶栏 tab —— 关于页本就是版本/作者信息的自然归属，且合并后空出一个 tab 槽位也不必浪费。

```html
<div class="card" style="margin-bottom:14px">
  <div style="font-weight:700;margin-bottom:12px;display:flex;align-items:center;gap:8px">
    📝 更新日志
    <span class="ver-badge new">V1.1</span>
  </div>
  <div class="changelog">
    <div class="cl-item">
      <div class="cl-ver">V1.1</div>
      <div class="cl-body">
        <div class="cl-date">2026-07</div>
        <ul>
          <li>顶部导航响应式优化，窄窗口不再错位换行</li>
          <li>移除顶部冗余的「软件作者」标识（作者信息保留于关于页）</li>
          <li>「预览确认」与「执行结果」合并为「预览与执行」单页</li>
          <li>版本升级至 V1.1</li>
        </ul>
      </div>
    </div>
    <div class="cl-item">
      <div class="cl-ver old">V1.0</div>
      <div class="cl-body">
        <div class="cl-date">2026-07</div>
        <ul>
          <li>首个正式版：多源 Excel 智能归集</li>
          <li>字段智能匹配 + 同义词识别</li>
          <li>自动保留目标模板格式，结果自动落盘</li>
        </ul>
      </div>
    </div>
  </div>
</div>
```

```css
.ver-badge { font-size: 11px; font-weight: 700; color: #fff; background: var(--primary); padding: 2px 10px; border-radius: 999px; letter-spacing: 0.3px; }
.ver-badge.new::after { content: 'NEW'; margin-left: 6px; font-size: 9px; background: var(--accent); color: #2D3436; padding: 1px 5px; border-radius: 999px; }

.changelog { display: flex; flex-direction: column; gap: 16px; }
.cl-item { display: flex; gap: 14px; }
.cl-ver { flex: 0 0 56px; font-size: 12px; font-weight: 700; color: var(--primary); background: var(--primary-bg); border-radius: 8px; padding: 4px 0; text-align: center; height: fit-content; }
.cl-ver.old { color: var(--text-secondary); background: var(--bg); }
.cl-body { flex: 1; }
.cl-date { font-size: 11px; color: var(--text-secondary); margin-bottom: 6px; }
.cl-body ul { margin: 0; padding-left: 18px; color: var(--text-secondary); font-size: 13px; line-height: 1.8; }
```

### 可选增强（首启弹窗）
首次打开 V1.1 时弹「What's New」modal（localStorage 标记 `gqdb_seen_v11`），关闭后不再弹出。复用既有 `.modal-overlay` / `.modal` 组件。

### 关于页卡片网格防溢出（协同对齐）
关于页顶部 4 张信息卡原用 `repeat(auto-fit, minmax(180px, 1fr))`。极窄窗口下 `minmax` 最小值可能超过容器导致溢出，改为带 `min()` 防护：
```css
/* 关于页信息卡网格 */
.grid-info { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 12px; }
```
（与 designer-21 对齐采纳，纯防御性增强，不改变视觉与索引。）

### 使用说明页卡片防溢出（修复用户原报 bug）
用户最初报告的「小宽度下布局异常」正是「使用说明」页 5 张步骤卡：原内联 `grid-template-columns:repeat(auto-fit,minmax(240px,1fr))` 的 **240px 下限在窄容器会溢出**。必须同步修复：

把使用说明页那一段内联 grid 改为 class：
```html
<div class="doc-grid">
```
```css
.doc-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 14px; margin-bottom: 20px; }
.doc-grid > div { min-width: 0; }
```
> 说明：`.grid-info`（关于页）与 `.doc-grid`（使用说明页）用同一 `minmax(min(220px,100%),1fr)` 防护模式，避免窄屏下限溢出。

---

## 5. 需新增的断点 / 媒体查询（完整 CSS 片段）

替换原 `.logo` / `.nav-tabs` / `.nav-tab` 规则，并追加媒体查询：

```css
/* ===== 顶部导航（修复窄窗口错位） ===== */
.topbar {
  height: 56px; background: var(--card); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; padding: 0 24px; gap: 16px;
  position: fixed; top: 0; left: 0; right: 0; z-index: 100;
}
.logo {
  font-size: 18px; font-weight: 800; color: var(--primary);
  display: flex; align-items: center; gap: 8px; cursor: default;
  flex-shrink: 0; min-width: 0;
}
.logo .logo-img { height: 32px; width: auto; image-rendering: pixelated; transition: transform 0.3s; flex-shrink: 0; }
.logo .logo-img:hover { transform: rotate(4deg) scale(1.08); }
.subtitle { font-size: 11px; color: var(--text-secondary); font-weight: 400; letter-spacing: 0.5px; white-space: nowrap; flex-shrink: 0; }

.nav-tabs {
  display: flex; gap: 4px; margin-left: auto;
  flex: 1 1 auto; min-width: 0;
  overflow-x: auto; overflow-y: hidden;
  scrollbar-width: thin; -ms-overflow-style: none;
}
.nav-tabs::-webkit-scrollbar { height: 4px; }
.nav-tabs::-webkit-scrollbar-thumb { background: var(--border); border-radius: 999px; }

.nav-tab {
  padding: 8px 16px; border-radius: var(--radius);
  font-size: 13px; color: var(--text-secondary);
  white-space: nowrap; flex-shrink: 0;
  cursor: pointer; transition: all var(--transition); border: none; background: none;
}
.nav-tab.active, .nav-tab:hover { background: var(--primary-bg); color: var(--primary); font-weight: 500; }

/* ===== 响应式断点 ===== */
@media (max-width: 1080px) { .subtitle { display: none; } }

@media (max-width: 860px) {
  .topbar { padding: 0 16px; gap: 12px; }
  .nav-tab { padding: 8px 12px; font-size: 12px; }
}

@media (max-width: 620px) {
  .logo { font-size: 16px; }
  .logo .logo-img { height: 28px; }
  .nav-tabs { gap: 2px; }
}

/* 合并页窄屏堆叠（见第 3 节 .pe-layout） */
@media (max-width: 980px) { /* 见上 */ }
```

> 删除原 `.app-author` CSS 块（约 style.css 第 20–31 行）。

### 窄屏 `.page` 内边距（修复内联样式压过媒体查询）
「使用说明」页（page-4）与「关于」页（page-5）目前带内联 `style="padding:32px;overflow-y:auto;height:calc(100vh - 110px)"`。内联样式优先级高于样式表，**会导致任何 `.page` padding 媒体查询失效**。两处必须处理：

**推荐做法**：删掉两页内联的 `padding:32px`（`overflow-y:auto` 与 `height` 可保留），统一交给 `.page` 与媒体查询管理：
```html
<!-- page-4 / page-5 去掉 padding:32px -->
<div class="page" id="page-4" style="overflow-y:auto;height:calc(100vh - 110px)">
```
```css
/* 窄屏收紧页面内边距（依赖已移除内联 padding，否则被内联压过） */
@media (max-width: 620px) {
  .page { padding: 16px; }
}
@media (max-width: 860px) {
  .page { padding: 24px; }
}
```

**兜底做法**（若不便改 HTML）：用 `!important` 强行压过内联：
```css
@media (max-width: 620px) { .page { padding: 16px !important; } }
@media (max-width: 860px) { .page { padding: 24px !important; } }
```
> 优先采用推荐做法（清理内联），`!important` 兜底仅当 HTML 不便改动时使用。

---

## 6. 设计风险提示（含跨端协调）

1. **JS 索引漂移（高）**：合并后页面 6→5，`switchPage(n)` 的所有调用需同步：
   - 字段映射页「确认并预览 →」`switchPage(2)` 维持（现为合并页）；
   - 键盘右键 `if (currentPage < 3)` 必须改为 `< 4`；
   - `page-dot` 与 `nav-tab` 数量由 6 改为 5（HTML 删除一个 dot 与一个 tab）。
2. **confirmAndExecute 行为变更（高）**：原 `switchPage(3); await doExecute();` 的 `switchPage(3)` 必须删除，改为原地执行，否则跳到不存在的 page-3。进度/日志/导出/重置元素现已在 page-2，按 ID 取用不变。
3. **元素 ID 迁移回归（中）**：progress-circle / progress-text / log-list / export-btn / reset-btn 从 page-3 移入 page-2，需回归 `showExecutionResult` 等逻辑。
4. **横向滚动可发现性（低）**：极窄时 nav 滚动，`scrollbar-width: thin` 已处理；可加轻微阴影提示边缘。
5. **pywebview 最小窗口（中）**：桌面端建议设最小宽 ≥ 720px，与 CSS 配合；低于则靠 `overflow-x` 兜底。
6. **视觉回归（中）**：合并页右侧面板为新组件，必须复用 `--card / --shadow / --radius` 变量，禁止引入新颜色或圆角，保持设计系统一致。
7. **空态保护（中）**：合并页左侧预览表空态「请先完成字段映射」保留；`confirmAndExecute` 前校验 preview 已渲染，防止无可执行数据时误触。
8. **关于页高度（低）**：新增 changelog 后 page-5 内容变长，已设 `overflow-y:auto; height:calc(100vh - 110px)`，需确认滚动正常。
9. **无障碍（低）**：nowrap + 横向滚动的 tab 仍可用键盘 Tab/方向键聚焦；进度环与日志保留语义文本。
10. **彩蛋不受影响（无）**：logo 的 `onclick="easterEgg()"` 保留，删除作者文本不影响。
