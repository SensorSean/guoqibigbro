/* ========= 全局状态 ========= */
let state = {
    srcFiles: [],
    tgtFile: null,
    srcFields: [],
    tgtFields: [],
    matches: [],
    resultPath: null,
    samples: {},                 // {源字段名: "样例1 / 样例2"}
    rowKeys: { src: null, tgt: null },
    rowAlignment: [],            // [{tgt_row_idx, tgt_key, src_key, score, status}]
    srcRowKeys: [],              // 所有可用源行键值（改配候选）
    rowOverrides: {},            // {tgt_key: src_key 或 null(解绑)}
    filter: 'all',               // 字段映射筛选：all/matched/suggest/unmatched
    rowFilter: 'all',            // 行映射筛选：all/matched/suggest/unmatched
    collapsed: { 'sec-field': true, 'sec-row': true, 'sec-exec': false },
    headerZones: { target: { start: 0, end: 0 }, sources: {} },   // 每数据源/目标表头区域（1-based行号）
    headerCandidates: { target: [], sources: {} },                // 候选行号/范围选项
    dictData: {},                 // V1.3.2 用户同义词词典内存镜像 {标准词: [同义词]}
};
let currentPage = 0;
let currentPickIdx = -1;        // 当前正在手动选择的字段映射项索引
let currentRowPickKey = null;   // 当前正在改配的行标识键
let rowPickSelected = null;     // 行改配弹窗中当前选中的源键
let execTimer = null;           // 前端看门狗计时器
let tipTimer = null;            // 进度条下方虚拟轮播提示计时器
let execState = { running: false, startTs: 0, lastTs: 0, timeoutSec: 60 };
// 需求2：执行进度条下方的虚拟动态轮播提示语（轻松口吻，与填表/匹配/归集相关）
const PROGRESS_TIPS = [
    '正在实现字段匹配映射中，老兄别着急',
    '数据源解析中，稍安勿躁~',
    '按行对齐项目，马上就好',
    '智能归集进行中，先喝口水',
    '校正单元格格式，稳如老狗',
    '数据搬运中，表哥在努力',
    '匹配同义词，别催别催',
    '即将大功告成，请保持期待',
    '表哥正在把列对齐，别眨眼',
    '正在把数据请进表格，请稍候',
];

/* ========= PyWebView API 调用 ========= */
async function apiCall(method, args = []) {
    args = args || [];
    if (!window.pywebview || !window.pywebview.api) {
        console.error('[API] pywebview not ready');
        showToast("API 未就绪，请稍候重试");
        return null;
    }
    try {
        const fn = window.pywebview.api[method];
        if (!fn) { showToast("API方法不存在: " + method); return null; }
        const rawResult = await fn.apply(window.pywebview.api, args);
        if (typeof rawResult === 'string') {
            try { return JSON.parse(rawResult); } catch (e) { return rawResult; }
        }
        return rawResult;
    } catch (e) {
        console.error(`[API] ${method} 异常:`, e);
        showToast("调用失败: " + e.message);
        return null;
    }
}

/* ========= 页面切换 ========= */
function switchPage(idx) {
    if (idx < 0 || idx > 2) return;
    if (idx === currentPage) return;
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    currentPage = idx;
    const pageEl = document.getElementById('page-' + idx);
    if (pageEl) pageEl.classList.add('active');
    document.querySelectorAll('.page-dot').forEach((d, i) => d.classList.toggle('active', i === idx));
    document.querySelectorAll('.nav-tab').forEach((t, i) => t.classList.toggle('active', i === idx));
}

function showToast(msg) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.style.opacity = '1';
    t.style.transform = 'translateX(-50%) translateY(0)';
    setTimeout(() => { t.style.opacity = '0'; t.style.transform = 'translateX(-50%) translateY(20px)'; }, 2200);
}

/* ========= 顶栏 logo 三态联动 ========= */
function setLogoState(state) {
    const img = document.getElementById('app-logo');
    if (!img) return;
    let src = '大表哥Logo-头大.png';
    if (state === 'filling') src = '大表哥Logo-填表中.png';
    else if (state === 'done') src = '大表哥Logo-开心.png';
    img.src = src;
    // 切换时轻微"弹一下"反馈
    img.classList.remove('logo-bounce');
    void img.offsetWidth; // 触发重排以重启动画
    img.classList.add('logo-bounce');
}

/* ========= 彩蛋 ========= */
let clickCount = 0;
let eggTimer = null;
let runClickCount = 0;     // 彩蛋④：开始执行按钮连点计数
let runClickTimer = null;

// 撒花（抽取自原 easterEgg，供多个彩蛋复用）
function spawnConfetti() {
    const container = document.getElementById('easter-egg');
    if (!container) return;
    const emojis = ['⚡','📊','✨','🎉','📼','📋','🚀'];
    for (let i = 0; i < 30; i++) {
        const c = document.createElement('div');
        c.className = 'confetti';
        c.textContent = emojis[Math.floor(Math.random() * emojis.length)];
        c.style.left = Math.random() * 100 + '%';
        c.style.top = '-30px';
        c.style.animationDelay = Math.random() * 0.5 + 's';
        c.style.animationDuration = (1 + Math.random()) + 's';
        container.appendChild(c);
        setTimeout(() => c.remove(), 2000);
    }
}

// logo 连点 5 次：大表哥之力（保留原行为）
function easterEgg() {
    clickCount++;
    clearTimeout(eggTimer);
    eggTimer = setTimeout(() => { clickCount = 0; }, 2000);
    if (clickCount >= 5) {
        clickCount = 0;
        spawnConfetti();
        showToast('🎉 大表哥之力已激活！');
    }
}

/* ========= 彩蛋初始化（pywebview ready 时调用一次） ========= */
function initEasterEggs() {
    // 彩蛋②：空数据眩晕 —— 就绪 ~10s 后若还没拖表进来，表哥也懵了
    setTimeout(() => {
        if (!state || state.srcFiles.length === 0) {
            showToast('😵 大表哥也懵了，先拖点表进来~');
            const logo = document.getElementById('app-logo');
            if (logo) {
                logo.classList.remove('logo-bounce', 'logo-spin');
                void logo.offsetWidth;
                logo.classList.add('logo-spin');
                setTimeout(() => logo.classList.remove('logo-spin'), 1200);
            }
        }
    }, 10000);

    // 彩蛋③：深夜陪伴 —— 23/0/1/2/3/4 点，表哥陪你加班
    const h = new Date().getHours();
    if (h === 23 || h <= 4) {
        setTimeout(() => showToast('🌙 表哥陪你加班，喝口水歇会儿~'), 1200);
    }

    // 彩蛋⑤：键盘暗号 —— 缓冲最近输入字母，命中 "dabiaoge"/"dabiao" 触发撒花
    let keys = '';
    document.addEventListener('keydown', (e) => {
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
        const k = e.key ? e.key.toLowerCase() : '';
        if (!/^[a-z]$/.test(k)) return;
        keys = (keys + k).slice(-8); // 仅保留最近 8 个字符
        if (keys.includes('dabiaoge') || keys.includes('dabiao')) {
            keys = '';
            spawnConfetti();
            showToast('🎉 你发现了表哥的暗号！');
        }
    });
}

/* ========= 工具函数 ========= */
function escapeHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function truncate(s, len) {
    if (!s) return '';
    return s.length > len ? s.slice(0, len) + '...' : s;
}
function _convertToArray(obj) {
    if (obj === null || obj === undefined) return [];
    if (Array.isArray(obj)) return obj;
    if (typeof obj === 'object' && typeof obj.length === 'number') {
        const arr = [];
        for (let i = 0; i < obj.length; i++) { if (i in obj) arr.push(obj[i]); }
        return arr;
    }
    return [];
}
function fileBase(p) { return p ? p.split('/').pop().split('\\').pop() : '—'; }
function tsStamp() {
    const d = new Date();
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`;
}

/* ========= 页面0: 数据源 ========= */
function buildManualZones() {
    const zones = {};
    (state.srcFiles || []).forEach((f, i) => {
        const z = state.headerZones.sources[i];
        if (z && z.start > 0 && z.end > 0) {
            zones[f] = { start: z.start, end: z.end };
        }
    });
    return zones;
}

async function selectSourceFiles() {
    const files = await apiCall('select_files');
    if (files && Array.isArray(files) && files.length > 0) {
        // R1：累加模式——新选的文件追加到已有列表（去重），不替换
        const existing = new Set((state.srcFiles || []).map(f => f.toLowerCase()));
        const newOnes = files.filter(f => !existing.has(f.toLowerCase()));
        if (newOnes.length === 0) {
            showToast('ℹ 所选文件已加载，无需重复添加');
            return;
        }
        const merged = (state.srcFiles || []).concat(newOnes);
        state.srcFiles = merged;
        renderSrcTags(merged);
        const res = await apiCall('load_sources', [merged, buildManualZones()]);
        if (res && res.success === true) {
            state.srcFields = res.fields || [];
            // 合并后端返回的表头候选与默认区域
            const hi = res.header_info || {};
            merged.forEach((f, i) => {
                const info = hi[f];
                if (info) {
                    state.headerCandidates.sources[i] = info.candidates || defaultHeaderCandidates();
                    const det = info.detected || {};
                    if (!state.headerZones.sources[i] || state.headerZones.sources[i].start === 0) {
                        state.headerZones.sources[i] = { start: det.start || 1, end: det.end || 1 };
                    }
                } else {
                    state.headerCandidates.sources[i] = defaultHeaderCandidates();
                    if (!state.headerZones.sources[i]) {
                        state.headerZones.sources[i] = { start: 1, end: 1 };
                    }
                }
            });
            // 重新渲染标签以显示每个文件的字段数
            renderSrcTags(merged);
            renderHeaderZonePerSource();
            updateMatchBtn();
            showToast('✅ 新增 ' + newOnes.length + ' 个文件，累计 ' + merged.length + ' 个，共 ' + state.srcFields.length + ' 个字段');
        } else if (res) {
            showToast('❌ 读取数据源失败: ' + (res.error || '未知错误'));
        }
    }
}

function defaultHeaderCandidates() {
    const opts = [];
    for (let r = 1; r <= 5; r++) opts.push({ value: String(r), label: '第' + r + '行' });
    // 支持 2~3 行表头区间（与文案一致）：i-(i+1) 与 i-(i+2)
    for (let i = 1; i <= 4; i++) {
        opts.push({ value: i + '-' + (i + 1), label: '第' + i + '-' + (i + 1) + '行' });
        if (i + 2 <= 5) opts.push({ value: i + '-' + (i + 2), label: '第' + i + '-' + (i + 2) + '行' });
    }
    return opts;
}

async function selectTargetFile() {
    const file = await apiCall('select_target');
    if (file) {
        state.tgtFile = file;
        renderTgtZone(file);
        const zones = state.headerZones.target || {};
        const manualZone = zones.start > 0 && zones.end > 0 ? { start: zones.start, end: zones.end } : null;
        const res = await apiCall('load_target', [file, manualZone]);
        if (res && res.success === true) {
            state.tgtFields = res.fields || [];
            const hi = res.header_info || {};
            state.headerCandidates.target = hi.candidates || defaultHeaderCandidates();
            const det = hi.detected || {};
            if (!state.headerZones.target || state.headerZones.target.start === 0) {
                state.headerZones.target = { start: det.start || 1, end: det.end || 1 };
            }
            renderHeaderZonePerSource();
            updateMatchBtn();
            showToast('✅ 目标模板已加载，共 ' + state.tgtFields.length + ' 个字段');
        } else if (res) {
            showToast('❌ 加载目标失败: ' + (res.error || '未知错误'));
        }
    }
}

function renderSrcTags(files) {
    const el = document.getElementById('src-tags');
    if (!el) return;
    el.innerHTML = '';
    if (!files || files.length === 0) {
        const hint = document.createElement('div');
        hint.className = 'src-tags-empty';
        hint.textContent = '尚未选择数据源';
        el.appendChild(hint);
        return;
    }
    // 按文件统计字段数（从 state.srcFields 中按 source_file 分组）
    const fileFieldCount = {};
    (state.srcFields || []).forEach(f => {
        const sf = f.source_file || '';
        fileFieldCount[sf] = (fileFieldCount[sf] || 0) + 1;
    });
    files.forEach((f, i) => {
        const tag = document.createElement('div');
        tag.className = 'file-tag file-tag-rich';
        const count = fileFieldCount[f] || 0;
        tag.innerHTML =
            '<span class="file-tag-icon">📊</span>' +
            '<span class="file-tag-name" title="' + escapeHtml(f) + '">' + escapeHtml(fileBase(f)) + '</span>' +
            (count > 0 ? '<span class="file-tag-count">' + count + ' 字段</span>' : '') +
            '<span class="remove" onclick="removeSrcFile(' + i + ')">✕</span>';
        el.appendChild(tag);
    });
    // 总计
    const total = document.createElement('div');
    total.className = 'file-tag-total';
    total.textContent = '共 ' + files.length + ' 个文件 · ' + (state.srcFields || []).length + ' 个字段';
    el.appendChild(total);
}

function removeSrcFile(idx) {
    state.srcFiles.splice(idx, 1);
    renderSrcTags(state.srcFiles);
    // 同步移除该源的表头区域配置，并重建索引
    const newSrcZones = {};
    const newSrcCands = {};
    (state.srcFiles || []).forEach((f, i) => {
        const oldIdx = Object.keys(state.headerZones.sources).find(k => state.srcFiles[parseInt(k)] === f);
        // 简单按原顺序保留：删除 idx 后，后面的索引前移
        if (i < idx) {
            newSrcZones[i] = state.headerZones.sources[i];
            newSrcCands[i] = state.headerCandidates.sources[i];
        } else {
            newSrcZones[i] = state.headerZones.sources[i + 1];
            newSrcCands[i] = state.headerCandidates.sources[i + 1];
        }
    });
    state.headerZones.sources = newSrcZones;
    state.headerCandidates.sources = newSrcCands;
    renderHeaderZonePerSource();
    updateMatchBtn();
}

/* ========= R2 每数据源表头区域选择器 ========= */
function zoneValueKey(z) {
    if (!z || z.start <= 0 || z.end <= 0) return '';
    return z.start === z.end ? String(z.end) : (z.start + '-' + z.end);
}
function parseZoneValue(v) {
    if (!v) return { start: 0, end: 0 };
    if (v.indexOf('-') !== -1) {
        const parts = v.split('-');
        return { start: parseInt(parts[0]) || 1, end: parseInt(parts[1]) || parseInt(parts[0]) || 1 };
    }
    const n = parseInt(v) || 1;
    return { start: n, end: n };
}
async function applyHeaderZones() {
    if (state.srcFiles.length === 0 && !state.tgtFile) return;
    const res = await apiCall('load_sources', [state.srcFiles, buildManualZones()]);
    if (res && res.success) {
        state.srcFields = res.fields || [];
        const hi = res.header_info || {};
        state.srcFiles.forEach((f, i) => {
            const info = hi[f];
            if (info) state.headerCandidates.sources[i] = info.candidates || defaultHeaderCandidates();
        });
        renderSrcTags(state.srcFiles);
        renderFieldMappings();
    }
    if (state.tgtFile) {
        const tz = state.headerZones.target || {};
        const manualZone = tz.start > 0 && tz.end > 0 ? { start: tz.start, end: tz.end } : null;
        const tres = await apiCall('load_target', [state.tgtFile, manualZone]);
        if (tres && tres.success) {
            state.tgtFields = tres.fields || [];
            const hi = tres.header_info || {};
            state.headerCandidates.target = hi.candidates || defaultHeaderCandidates();
        }
        renderHeaderZonePerSource();
    }
}
function renderHeaderZonePerSource() {
    const el = document.getElementById('header-zone-per-source');
    if (!el) return;
    el.innerHTML = '';
    const sources = state.srcFiles || [];
    if (sources.length === 0) return;
    const title = document.createElement('div');
    title.className = 'header-zone-title';
    title.innerHTML = '📌 表头区域（每数据源）— <span class="hint">为每个数据源指定表头所在行；支持 2~3 行表头 / 局部合并</span>';
    el.appendChild(title);
    sources.forEach((f, idx) => {
        const srcZone = state.headerZones.sources[idx] || { start: 1, end: 1 };
        const tgtZone = state.headerZones.target || { start: 1, end: 1 };
        const srcCands = state.headerCandidates.sources[idx] || defaultHeaderCandidates();
        const tgtCands = state.headerCandidates.target || defaultHeaderCandidates();
        const row = document.createElement('div');
        row.className = 'header-zone-row';
        row.innerHTML =
            '<span class="header-zone-name" title="' + escapeHtml(f) + '">' +
                '<span class="header-zone-idx">' + (idx + 1) + '</span>' +
                '<span class="header-zone-fname">' + escapeHtml(fileBase(f)) + '</span>' +
            '</span>' +
            '<select class="select-sm hzs-src" data-idx="' + idx + '" title="数据源表头行">' +
                srcCands.map(c => '<option value="' + escapeHtml(c.value) + '"' + (c.value === zoneValueKey(srcZone) ? ' selected' : '') + '>' + escapeHtml(c.label) + '</option>').join('') +
            '</select>' +
            '<span class="header-zone-arrow">源→目标</span>' +
            '<select class="select-sm hzs-tgt" data-idx="' + idx + '" title="目标表头行">' +
                tgtCands.map(c => '<option value="' + escapeHtml(c.value) + '"' + (c.value === zoneValueKey(tgtZone) ? ' selected' : '') + '>' + escapeHtml(c.label) + '</option>').join('') +
            '</select>';
        el.appendChild(row);
    });
    el.querySelectorAll('.hzs-src').forEach(sel => {
        sel.addEventListener('change', function () {
            const i = parseInt(this.dataset.idx);
            state.headerZones.sources[i] = parseZoneValue(this.value);
            applyHeaderZones();
        });
    });
    el.querySelectorAll('.hzs-tgt').forEach(sel => {
        sel.addEventListener('change', async function () {
            const z = parseZoneValue(this.value);
            state.headerZones.target = z;
            // 同步所有目标下拉框
            el.querySelectorAll('.hzs-tgt').forEach(s => {
                s.value = zoneValueKey(z);
            });
            applyHeaderZones();
        });
    });
}

/* ========= R4 模糊搜索 ========= */
function fuzzyMatch(text, query) {
    if (!query) return true;
    const t = String(text || '').toLowerCase();
    const tokens = String(query).toLowerCase().split(/\s+/).filter(Boolean);
    return tokens.every(tok => {
        // 优先：子串匹配
        if (t.indexOf(tok) !== -1) return true;
        // 兜底：长度>2 时按子序列匹配（每个字符按序在 t 中出现，不要求连续）
        if (tok.length <= 2) return false;
        let ti = 0;
        for (let i = 0; i < t.length && ti < tok.length; i++) {
            if (t[i] === tok[ti]) ti++;
        }
        return ti === tok.length;
    });
}

function renderTgtZone(file) {
    const zone = document.getElementById('tgt-zone');
    if (!zone) return;
    zone.className = 'upload-zone loaded';
    zone.innerHTML = '<div class="icon">📋</div><div class="label">✓ 目标模板已加载</div><div class="hint">' + fileBase(file) + '</div>';
}

function updateMatchBtn() {
    const btn = document.getElementById('btn-match');
    if (btn) btn.disabled = !(state.srcFiles.length > 0 && state.tgtFile);
}

function goMatch() {
    if (state.srcFields.length > 0 && state.tgtFields.length > 0) {
        switchPage(1);
        setTimeout(() => doAutoMatch(), 300);
    } else {
        showToast('⚠ 请先选择数据源和目标模板');
    }
}

/* ========= 页面1: 字段映射（V2 卡片式） ========= */
async function doAutoMatch() {
    showToast('🤖 正在进行智能匹配...');
    const res = await apiCall('auto_match', [state.srcFields, state.tgtFields]);
    if (res && res.success === true) {
        let matches = res.matches || [];
        if (!Array.isArray(matches)) matches = _convertToArray(matches);
        state.matches = matches;
        // 预取样例值（供映射卡内联展示，替代预览）
        const sres = await apiCall('get_all_samples', []);
        if (sres && sres.success) state.samples = sres.samples || {};
        state.filter = 'all';
        renderFieldMappings();
        updateRuleBlock();
        // 智能匹配完成后默认折叠 A/B 两区，C 区保持展开
        state.collapsed['sec-field'] = true;
        state.collapsed['sec-row'] = true;
        state.collapsed['sec-exec'] = false;
        refreshSectionCollapseUI();
        // 进入行级映射区初始化
        initSectionB();
        showToast('✅ 智能匹配完成，请在下方核对映射');
    } else if (res) {
        showToast('❌ 匹配失败: ' + (res.error || '未知错误'));
    } else {
        showToast('❌ 匹配失败: API 返回空');
    }
}

/* SECTION A：列级字段映射卡片 */
function renderFieldMappings() {
    const grid = document.getElementById('mapping-grid');
    if (!grid) return;
    grid.innerHTML = '';
    if (!state.matches || state.matches.length === 0) {
        grid.innerHTML = '<div style="padding:24px;color:#999">请点击「🤖 智能匹配」生成字段映射，或点「＋ 手动添加」新建映射</div>';
        updateStatBadges(0, 0, 0);
        return;
    }
    let matched = 0, suggest = 0, unmatched = 0;
    const tgtName = fileBase(state.tgtFile);
    const filter = state.filter || 'all';

    // 收集可见项并按来源分组（按 confidence 降序排列）
    const groups = {};
    const groupOrder = [];
    const sortedMatches = state.matches
        .map((m, i) => ({ m, origIdx: i }))
        .sort((a, b) => (b.m.confidence || 0) - (a.m.confidence || 0));
    sortedMatches.forEach(({ m, origIdx: idx }) => {
        const conf = m.confidence || 0;
        let status = 'unmatched';
        if (m.matched && m.auto) { matched++; status = 'matched'; }
        else if (m.matched && !m.auto) { matched++; status = 'matched'; }
        else if (m.suggested) { suggest++; status = 'suggest'; }
        else { unmatched++; status = 'unmatched'; }

        if (filter !== 'all' && filter !== status) return;

        const gKey = (m.src_file || '未选择') + '||' + (m.src_sheet || '');
        if (!groups[gKey]) {
            groups[gKey] = { file: m.src_file || '未选择', sheet: m.src_sheet || '', items: [] };
            groupOrder.push(gKey);
        }
        groups[gKey].items.push({ m, idx, status });
    });

    groupOrder.forEach(gKey => {
        const grp = groups[gKey];
        if (grp.items.length === 0) return;
        const hdr = document.createElement('div');
        hdr.className = 'mapping-group-header';
        hdr.innerHTML = '📊 ' + escapeHtml(fileBase(grp.file)) + (grp.sheet ? ' <span class="mg-sheet">/ ' + escapeHtml(grp.sheet) + '</span>' : '');
        grid.appendChild(hdr);

        grp.items.forEach(({ m, idx, status }) => {
            const card = buildMappingCard(m, idx, status, tgtName);
            grid.appendChild(card);
        });
    });
    renderFieldStats(matched, suggest, unmatched);
}

function renderFieldStats(matched, suggest, unmatched) {
    const total = matched + suggest + unmatched;
    const el = document.getElementById('sec-field-stats');
    if (!el) return;
    const make = (key, label, cls, count) => {
        const active = state.filter === key ? ' active' : '';
        return '<span class="stat-pill stat-' + cls + active + '" onclick="event.stopPropagation();setFilter(\'' + key + '\')">' + label + ' <b>' + count + '</b></span>';
    };
    el.innerHTML =
        make('all', '全部', 'all', total) +
        make('matched', '✅ 已匹配', 'green', matched) +
        make('suggest', '⚠ 建议', 'amber', suggest) +
        make('unmatched', '○ 未匹配', 'gray', unmatched);
    el.style.display = total === 0 ? 'none' : '';
}

function updateStatBadges(matched, suggest, unmatched) {
    const em = document.getElementById('stat-matched'); if (em) em.textContent = matched;
    const es = document.getElementById('stat-suggest'); if (es) es.textContent = suggest;
    const eu = document.getElementById('stat-unmatched'); if (eu) eu.textContent = unmatched;
    const et = document.getElementById('stat-total'); if (et) et.textContent = matched + suggest + unmatched;
    document.querySelectorAll('#mapper-stat .stat-pill').forEach(pill => {
        const f = pill.getAttribute('data-filter');
        pill.classList.toggle('active', f === state.filter);
    });
}

function setFilter(f) {
    state.filter = f;
    renderFieldMappings();
}

function renderMatchSummary() {
    const bar = document.getElementById('match-summary-bar');
    if (!bar) return;
    const total = state.matches.length;
    const matched = state.matches.filter(m => m.matched).length;
    const suggest = state.matches.filter(m => m.suggested).length;
    const unmatched = total - matched - suggest;
    if (total === 0) { bar.style.display = 'none'; return; }
    bar.style.display = 'inline-flex';
    bar.innerHTML = '<span class="msi msi-green">' + matched + ' 已匹配</span>' +
        '<span class="msi msi-amber">' + suggest + ' 建议确认</span>' +
        '<span class="msi msi-gray">' + unmatched + ' 未匹配</span>';
}

function updateRuleBlock() {
    const hint = document.getElementById('rule-hint');
    const example = document.getElementById('rule-example');
    if (!hint) return;
    if (!state.matches || state.matches.length === 0) {
        hint.textContent = '加载数据后，将在此展示具体映射路径。';
        if (example) example.style.display = 'none';
        return;
    }
    hint.textContent = '每张映射卡左上角显示「阶段标签（立项/可研/设计…）」；目标关键字段在左，数据源字段在右，箭头「源→目标」表示数据流向。';
    if (example) {
        example.style.display = 'block';
        example.innerHTML =
            '<b>示例 1（立项阶段）：</b>目标 · 目标模板.xlsx → <b>项目名称</b> <span class="rule-arrow">源→目标</span> 源 · 数据源表.xlsx / 立项 > <b>立项名称</b> ' +
            '<span class="badge badge-cat phase">立项</span><br>' +
            '<b>示例 2（多层嵌套）：</b>源字段路径 <code>可研>投资估算>总投资</code> → 卡片只显示主字段「<b>总投资</b>」，左上角标签「<b>可研</b>」';
    }
}

function toggleSection(id) {
    state.collapsed[id] = !state.collapsed[id];
    refreshSectionCollapseUI();
}

function toggleAllSections() {
    const ids = ['sec-field', 'sec-row', 'sec-exec'];
    const anyOpen = ids.some(id => !state.collapsed[id]);
    ids.forEach(id => { state.collapsed[id] = anyOpen; });
    refreshSectionCollapseUI();
}

function refreshSectionCollapseUI() {
    ['sec-field', 'sec-row', 'sec-exec'].forEach(id => {
        const sec = document.getElementById(id);
        const body = document.getElementById(id + '-body');
        const head = sec ? sec.querySelector('.section-head') : null;
        const arrow = head ? head.querySelector('.section-toggle') : null;
        if (!sec || !body) return;
        const collapsed = !!state.collapsed[id];
        sec.classList.toggle('collapsed', collapsed);
        body.style.display = collapsed ? 'none' : 'block';
        if (arrow) arrow.textContent = collapsed ? '▸' : '▾';
    });
    const btn = document.getElementById('btn-collapse-all');
    if (btn) {
        const anyCollapsed = Object.values(state.collapsed).some(v => v);
        btn.textContent = anyCollapsed ? '▾ 全部展开' : '▸ 全部折叠';
    }
}

function fieldCategoryTag(name) {
    if (!name) return '';
    const n = String(name);
    if (/合同|协议|合同书|协议书/.test(n)) return '<span class="badge badge-cat contract">合同</span>';
    if (/项目|工程|立项|子项/.test(n)) return '<span class="badge badge-cat project">项目</span>';
    if (/标段/.test(n)) return '<span class="badge badge-cat project">标段</span>';
    if (/公司|企业|单位|集团/.test(n)) return '<span class="badge badge-cat entity">主体</span>';
    return '';
}

// R1：从源字段路径顶层段派生工程建设阶段标签（立项/可研/设计/...）
const PHASE_KEYWORDS = ['立项', '可研', '设计', '勘察', '招标', '施工', '监理', '竣工', '验收', '运维', '前期', '建设', '规划'];
function fieldPhaseTag(srcField) {
    if (!srcField) return '';
    const top = String(srcField).split(/>|＞|→/)[0].trim();
    if (!top) return '';
    for (const p of PHASE_KEYWORDS) {
        if (top === p || top.indexOf(p) !== -1) {
            return '<span class="badge badge-cat phase">' + escapeHtml(p) + '</span>';
        }
    }
    return '<span class="badge badge-cat phase">' + escapeHtml(top) + '</span>';
}

// R1：取路径最后一段作为主字段名（精简层级显示）
function _lastSegment(name) {
    if (!name) return '';
    const parts = String(name).split(/>|＞|→/);
    return parts[parts.length - 1].trim();
}

function buildMappingCard(m, idx, status, tgtName) {
    let badgeClass = 'badge-unmatched', badgeText = '○ 未匹配', cardClass = '';
    if (status === 'matched' && m.auto) { badgeClass = 'badge-auto'; badgeText = '🤖 自动'; }
    else if (status === 'matched' && !m.auto) { badgeClass = 'badge-manual'; badgeText = '✋ 手动'; }
    else if (status === 'suggest') { badgeClass = 'badge-suggest'; badgeText = '⚠ 建议'; cardClass = 'suggest'; }
    else { badgeClass = 'badge-unmatched'; badgeText = '○ 未匹配'; cardClass = 'unmatched'; }

    const card = document.createElement('div');
    card.className = 'mapping-card' + (cardClass ? ' ' + cardClass : '');

    const srcName = m.src_field || '— 未选择';
    const srcFile = m.src_file || '';
    const srcSheet = m.src_sheet || '';
    const tgtField = m.tgt_field || '（未命名）';
    const sample = (m.matched && m.src_field && state.samples[m.src_field])
        ? ('例：' + state.samples[m.src_field]) : '';

    // R1: 阶段标签（源路径顶层）
    const phaseTag = fieldPhaseTag(m.matched ? srcName : tgtField);
    // R1: 精简层级——主字段只显示末段
    const srcLast = _lastSegment(srcName) || srcName;
    const tgtLast = _lastSegment(tgtField) || tgtField;
    const srcPath = formatFieldPath('源', srcFile, srcSheet, srcName);
    const tgtPath = formatFieldPath('目标', tgtName, '', tgtField);

    // R2: 目标关键字段在前（左），数据源字段在后（右），箭头 源→目标
    card.innerHTML =
        (phaseTag ? '<div class="mc-domain">' + phaseTag + '</div>' : '') +
        '<div class="mc-target">' +
            '<div class="mc-field mc-key">' + escapeHtml(tgtLast) + '</div>' +
            '<div class="mc-table">' + tgtPath + '</div>' +
            (sample ? '<div class="mc-sample">' + escapeHtml(sample) + '</div>' : '') +
        '</div>' +
        '<div class="mc-link">' +
            '<div class="mc-arrow">源→目标</div>' +
            '<span class="badge ' + badgeClass + '">' + badgeText + '</span>' +
        '</div>' +
        '<div class="mc-source">' +
            '<div class="mc-field">' + escapeHtml(srcLast) + '</div>' +
            '<div class="mc-table">' + srcPath + '</div>' +
        '</div>' +
        '<div class="mc-actions">' +
        (status === 'suggest' ? '<button class="icon-btn icon-btn-confirm" title="确认建议" onclick="confirmFieldSuggestion(' + idx + ')">✓</button>' : '') +
        '<button class="icon-btn" title="修改映射" onclick="openFieldPicker(' + idx + ')">✎</button>' +
        '<button class="icon-btn icon-btn-ghost" title="取消匹配" onclick="unmatchField(' + idx + ')">✕</button>' +
        '</div>';
    return card;
}

function confirmFieldSuggestion(idx) {
    const m = state.matches[idx];
    if (!m) return;
    if (!m.matched) { m.matched = true; m.auto = false; m.suggested = false; }
    renderFieldMappings();
    showToast('✅ 已确认建议：' + (m.tgt_field || '') + ' ← ' + (m.src_field || ''));
}

function formatFieldPath(label, file, sheet, field) {
    file = file || '—';
    sheet = sheet || '';
    field = field || '—';
    // 把「立项>立项名称>立项单位」这种嵌套压平为同行三节点
    const parts = String(field).split(/>|＞|→/);
    if (parts.length > 1) {
        field = parts.map(p => '<span class="path-part">' + escapeHtml(p.trim()) + '</span>').join('<span class="path-sep">›</span>');
    } else {
        field = '<span class="path-part">' + escapeHtml(field) + '</span>';
    }
    let html = escapeHtml(label) + ' · ' + escapeHtml(file);
    if (sheet) html += '<span class="path-sep">/</span>' + escapeHtml(sheet);
    html += '<span class="path-sep">→</span>' + field;
    return html;
}

function unmatchField(idx) {
    const m = state.matches[idx];
    if (!m) return;
    m.matched = false; m.src_field = null; m.src_file = null; m.src_sheet = null;
    m.suggested = false; m.confidence = 0; m.auto = false;
    renderFieldMappings();
    showToast('已取消该字段匹配');
}

/* ========= 字段选择器弹窗（保留） ========= */
async function openFieldPicker(tgtIdx) {
    currentPickIdx = tgtIdx;
    const overlay = document.getElementById('field-picker-overlay');
    const list = document.getElementById('picker-field-list');
    const searchBox = document.getElementById('picker-search');
    const title = document.getElementById('picker-tgt-name');
    if (!overlay || !list || !title) return;
    const m = state.matches[tgtIdx];
    if (!m) return;
    title.textContent = m.tgt_field || '（请在下方选择数据源字段）';
    list.innerHTML = '<div style="padding:40px;text-align:center;color:#999">⏳ 加载候选源字段...</div>';
    overlay.classList.add('show');
    const res = await apiCall('get_candidates', [m.tgt_field || '']);
    if (!res || !res.success) {
        list.innerHTML = '<div style="padding:20px;text-align:center;color:var(--accent3)">❌ 加载失败: ' + ((res && res.error) || '未知') + '</div>';
        return;
    }
    state._candidates = res.candidates;
    renderPickerCandidates('');
    if (searchBox) {
        searchBox.value = '';
        searchBox.oninput = function (e) { renderPickerCandidates(e.target.value); };
        setTimeout(function () { searchBox.focus(); }, 100);
    }
}

function renderPickerCandidates(filterText) {
    const list = document.getElementById('picker-field-list');
    if (!list) return;
    list.innerHTML = '';
    const cands = state._candidates || [];
    const ft = (filterText || '').trim().toLowerCase();
    const filtered = ft
        ? cands.filter(function (c) {
            return fuzzyMatch(c.name, ft) || fuzzyMatch(c.source_file, ft);
          })
        : cands;

    const noneOpt = document.createElement('div');
    noneOpt.className = 'picker-item none-option';
    noneOpt.innerHTML = '<span class="none-icon">✕</span> 不填写此字段（留空）';
    noneOpt.addEventListener('click', function () { confirmFieldPick(-1); });
    list.appendChild(noneOpt);

    if (filtered.length === 0) {
        const noResult = document.createElement('div');
        noResult.style.cssText = 'padding:20px;text-align:center;color:#999';
        noResult.textContent = '🔍 无匹配项';
        list.appendChild(noResult);
        return;
    }

    const displayLimit = ft ? filtered.length : Math.min(30, filtered.length);
    const hasMore = !ft && filtered.length > 30;
    filtered.slice(0, displayLimit).forEach(function (c) {
        const item = document.createElement('div');
        item.className = 'picker-item';
        const origIdx = cands.indexOf(c);
        const isRecommended = origIdx < 3 && c.similarity >= 85;
        const confClass = c.similarity >= 85 ? 'high' : c.similarity >= 60 ? 'mid' : 'low';
        item.innerHTML =
            (isRecommended ? '<span class="picker-rec">⭐ 推荐</span>' : '<span class="picker-rec-empty"></span>') +
            '<span class="picker-src-name">' + escapeHtml(c.name) + '</span>' +
            '<span class="picker-src-file">' + escapeHtml(c.source_file || '') + '</span>' +
            '<span class="conf ' + confClass + '">' + (c.similarity > 0 ? c.similarity + '%' : '-') + '</span>';
        item.addEventListener('click', function () { confirmFieldPick(c); });
        list.appendChild(item);
    });
    if (hasMore) {
        const more = document.createElement('div');
        more.style.cssText = 'padding:10px;text-align:center;color:var(--text-secondary);font-size:11px';
        more.textContent = '... 还有 ' + (filtered.length - 30) + ' 个候选，请使用搜索框过滤 ...';
        list.appendChild(more);
    }
}

function confirmFieldPick(srcIdxOrField) {
    if (currentPickIdx < 0) return;
    const m = state.matches[currentPickIdx];
    if (!m) return;
    if (srcIdxOrField === -1) {
        m.matched = false; m.src_field = null; m.src_file = null; m.src_sheet = null;
        m.confidence = 0; m.auto = false;
    } else if (typeof srcIdxOrField === 'object' && srcIdxOrField !== null) {
        const isNewManual = !m.tgt_field;
        m.matched = true;
        m.src_field = srcIdxOrField.name || '';
        m.src_file = srcIdxOrField.source_file || '';
        m.src_sheet = srcIdxOrField.source_sheet || '';
        m.confidence = srcIdxOrField.similarity || 100;
        m.auto = false;
        if (!m.tgt_field) m.tgt_field = srcIdxOrField.name || '';  // 手动新增时以源名作目标名
        closeFieldPicker();
        renderFieldMappings();
        updateRuleBlock();
        showToast(isNewManual ? '✅ 已添加手动映射：' + m.src_field + ' → ' + m.tgt_field : '✅ 已更新映射');
        return;
    } else {
        const f = state.srcFields[srcIdxOrField];
        if (f) {
            m.matched = true;
            m.src_field = (f && typeof f === 'object') ? (f.name || '') : String(f || '');
            m.src_file = (f && typeof f === 'object') ? (f.source_file || '') : '';
            m.src_sheet = (f && typeof f === 'object') ? (f.source_sheet || '') : '';
            m.confidence = 100; m.auto = false;
        }
    }
    closeFieldPicker();
    renderFieldMappings();
    showToast('✅ 已更新映射');
}

function closeFieldPicker() {
    const overlay = document.getElementById('field-picker-overlay');
    if (overlay) overlay.classList.remove('show');
    currentPickIdx = -1;
}

function showMatchModal(matches) {
    const overlay = document.getElementById('auto-match-modal');
    const list = document.getElementById('match-result-list');
    const summary = document.getElementById('match-summary');
    if (!overlay || !list || !summary) return;
    list.innerHTML = '';
    let autoCount = matches.filter(m => m.matched && m.auto).length;
    let suggestCount = matches.filter(m => m.suggested).length;
    summary.textContent = '共 ' + matches.length + ' 个字段，自动匹配 ' + autoCount + ' 个，建议确认 ' + suggestCount + ' 个';
    matches.forEach((m, idx) => {
        const row = document.createElement('div');
        row.className = 'match-result-row';
        row.style.cursor = 'pointer';
        row.title = '点击手动选择/修改映射';
        const conf = m.confidence || 0;
        let icon = '✗', color = 'var(--accent3)';
        if (m.matched) { icon = '✓'; color = 'var(--accent2)'; }
        else if (m.suggested) { icon = '⚠'; color = 'var(--accent)'; }
        row.innerHTML = '<span><span style="color:' + color + '">' + icon + '</span> ' +
            (m.src_field || '(无)') + ' → ' + (m.tgt_field || '') + '</span>' +
            '<span class="conf ' + (conf >= 80 ? 'high' : conf >= 55 ? 'mid' : 'low') + '">' +
            ((m.matched || m.suggested) ? Math.round(conf) + '%' : '-') + '</span>';
        row.addEventListener('click', () => { closeAutoMatch(); openFieldPicker(idx); });
        list.appendChild(row);
    });
    overlay.classList.add('show');
}
function closeAutoMatch() {
    const overlay = document.getElementById('auto-match-modal');
    if (overlay) overlay.classList.remove('show');
}
function acceptMatch() {
    closeAutoMatch();
    showToast('✨ 已接受智能匹配结果');
    renderFieldMappings();
}

/* ========= SECTION B：项目/合同行映射 ========= */
const ROWKEY_PRIORITY = ['项目', '工程', '立项', '标段', '合同', '协议', '编号', '名称'];
function deriveRowKeys(matches) {
    if (!matches || !matches.length) return { src: null, tgt: null };
    const usable = matches.filter(m => m.matched && m.src_field);
    for (const kw of ROWKEY_PRIORITY) {
        const hit = usable.find(m => String(m.tgt_field || '').indexOf(kw) !== -1);
        if (hit) return { src: hit.src_field, tgt: hit.tgt_field };
    }
    if (usable.length) return { src: usable[0].src_field, tgt: usable[0].tgt_field };
    return { src: null, tgt: null };
}
function pickDefaultKey(list) {
    if (!list || !list.length) return null;
    const pri = ['项目', '合同', '名称'];
    for (const kw of pri) {
        const hit = list.find(k => k.indexOf(kw) !== -1);
        if (hit) return hit;
    }
    return list[0];
}
function populateSelect(id, items) {
    const sel = document.getElementById(id);
    if (!sel) return;
    sel.innerHTML = '';
    (items || []).forEach(k => {
        const o = document.createElement('option');
        o.value = k; o.textContent = k; o.title = k;
        sel.appendChild(o);
    });
}
async function initSectionB() {
    prefillOutputPath();
    const cand = await apiCall('get_rowkey_candidates', [state.srcFields, state.tgtFields]);
    if (cand && cand.success) {
        populateSelect('rowkey-src', cand.src);
        populateSelect('rowkey-tgt', cand.tgt);
    }
    // 优先从字段映射派生出行键（目标字段 + 其映射到的源字段）
    const derived = deriveRowKeys(state.matches);
    const sEl = document.getElementById('rowkey-src');
    const tEl = document.getElementById('rowkey-tgt');
    const hintEl = document.getElementById('rowkey-lock-hint');
    if (derived.tgt && tEl) tEl.value = derived.tgt;
    if (derived.src && sEl) sEl.value = derived.src;
    if (sEl) sEl.onchange = () => { autoMatchRows(); renderRowkeyHint(); };
    if (tEl) tEl.onchange = () => { autoMatchRows(); renderRowkeyHint(); };
    renderRowkeyHint();
    await autoMatchRows();
}

function renderRowkeyHint() {
    const sEl = document.getElementById('rowkey-src');
    const tEl = document.getElementById('rowkey-tgt');
    const hintEl = document.getElementById('rowkey-lock-hint');
    if (!hintEl) return;
    const src = sEl ? sEl.value : '';
    const tgt = tEl ? tEl.value : '';
    if (!src || !tgt) {
        hintEl.innerHTML = '⚠ 未能从字段映射自动识别出行键，请手动选择源/目标行标识列';
        hintEl.className = 'rowkey-lock-hint warn';
    } else {
        hintEl.innerHTML = '🔒 已根据字段映射自动锁定行键：目标 <b>' + escapeHtml(tgt) + '</b> ↔ 源 <b>' + escapeHtml(src) + '</b>';
        hintEl.className = 'rowkey-lock-hint ok';
    }
}
async function autoMatchRows() {
    const sk = document.getElementById('rowkey-src');
    const tk = document.getElementById('rowkey-tgt');
    if (!sk || !tk || !sk.value || !tk.value) { showToast('请先选择行标识键'); return; }
    state.rowKeys = { src: sk.value, tgt: tk.value };
    const res = await apiCall('compute_row_alignment', [sk.value, tk.value]);
    if (res && res.success) {
        state.rowAlignment = res.alignment || [];
        state.srcRowKeys = res.src_keys || [];
        renderRowMappings();
    } else {
        showToast('行匹配失败: ' + ((res && res.error) || ''));
    }
}
function effectiveSrcKey(tgtKey) {
    const ov = state.rowOverrides[tgtKey];
    if (ov === null) return null;          // 已解绑
    if (ov !== undefined) return ov;        // 手动改配
    const item = state.rowAlignment.find(a => a.tgt_key === tgtKey);
    return item ? item.src_key : null;
}
function renderRowMappings() {
    const list = document.getElementById('rowmap-list');
    if (!list) return;
    list.innerHTML = '';
    if (!state.rowAlignment || state.rowAlignment.length === 0) {
        list.innerHTML = '<div style="padding:16px;color:#999">暂无行数据，请先加载含项目/合同行的模板</div>';
        renderRowStats(0, 0, 0);
        return;
    }
    let matched = 0, suggest = 0, unmatched = 0;
    const rows = state.rowAlignment.map(item => {
        const tgtKey = item.tgt_key;
        const ovSrc = effectiveSrcKey(tgtKey);
        let status = item.status || 'unmatched';
        if (ovSrc === null) { status = 'unmatched'; }
        else if (state.rowOverrides[tgtKey] !== undefined && state.rowOverrides[tgtKey] !== null) { status = 'matched'; }
        else if (status === 'auto') { status = 'matched'; }
        else if (status === 'suggest') { status = 'suggest'; }
        else { status = 'unmatched'; }
        if (status === 'matched') matched++;
        else if (status === 'suggest') suggest++;
        else unmatched++;
        return { ...item, _ovSrc: ovSrc, _status: status };
    }).filter(r => {
        const f = state.rowFilter || 'all';
        if (f === 'all') return true;
        return r._status === f;
    });
    if ((state.rowFilter || 'all') === 'suggest') {
        rows.sort((a, b) => (b.score || 0) - (a.score || 0));
    }
    rows.forEach(item => {
        const tgtKey = item.tgt_key;
        const ovSrc = item._ovSrc;
        const status = item._status;
        let badgeClass, badgeText;
        let isManualConfirm = false;
        if (ovSrc === null) { badgeClass = 'badge-unmatched'; badgeText = '○ 未匹配'; }
        else if (state.rowOverrides[tgtKey] !== undefined && state.rowOverrides[tgtKey] !== null) {
            badgeClass = 'badge-confirmed'; badgeText = '✅ 已确认'; isManualConfirm = true;
        } else if (status === 'matched') { badgeClass = 'badge-auto'; badgeText = '🤖 自动 ' + Math.round(item.score * 100) + '%'; }
        else if (status === 'suggest') { badgeClass = 'badge-suggest'; badgeText = '⚠ 建议 ' + Math.round(item.score * 100) + '%'; }
        else { badgeClass = 'badge-unmatched'; badgeText = '○ 未匹配'; }

        const row = document.createElement('div');
        row.className = 'rowmap-row' + (status === 'suggest' ? ' suggest' : '') + (isManualConfirm ? ' confirmed' : '');
        row.innerHTML =
            '<div class="rm-target">目标行 · ' + escapeHtml(tgtKey || '(空)') + '</div>' +
            '<div class="rm-arrow">→</div>' +
            '<div class="rm-source">' + (ovSrc ? escapeHtml(ovSrc) : '— 未匹配') + '</div>' +
            '<span class="badge ' + badgeClass + '">' + badgeText + '</span>' +
            '<div class="rm-actions">' +
            (status === 'suggest' ? '<button class="icon-btn icon-btn-confirm" title="确认建议" onclick="confirmRowSuggestion(\'' + escapeHtml(tgtKey) + '\')">✓</button>' : '') +
            '<button class="icon-btn" title="改配/强制改配" onclick="openRowPicker(\'' + escapeHtml(tgtKey) + '\')">✎</button>' +
            '<button class="icon-btn icon-btn-ghost" title="解绑（不匹配此行）" onclick="unbindRow(\'' + escapeHtml(tgtKey) + '\')">⛓✕</button>' +
            '</div>';
        list.appendChild(row);
    });
    renderRowStats(matched, suggest, unmatched);
}

function setRowFilter(f) {
    state.rowFilter = f;
    renderRowMappings();
}

function renderRowStats(matched, suggest, unmatched) {
    const total = matched + suggest + unmatched;
    const el = document.getElementById('sec-row-stats');
    if (!el) return;
    const make = (key, label, cls, count) => {
        const active = state.rowFilter === key ? ' active' : '';
        return '<span class="stat-pill stat-' + cls + active + '" onclick="event.stopPropagation();setRowFilter(\'' + key + '\')">' + label + ' <b>' + count + '</b></span>';
    };
    el.innerHTML =
        make('all', '全部', 'all', total) +
        make('matched', '✅ 已匹配', 'green', matched) +
        make('suggest', '⚠ 建议', 'amber', suggest) +
        make('unmatched', '○ 未匹配', 'gray', unmatched);
    el.style.display = total === 0 ? 'none' : '';
}
function confirmRowSuggestion(tgtKey) {
    const ov = effectiveSrcKey(tgtKey);
    if (ov === null || ov === undefined) { showToast('该建议无可用源，无法确认'); return; }
    state.rowOverrides[tgtKey] = ov;
    renderRowMappings();
    showToast('✅ 已确认建议 → ' + ov);
}
function unbindRow(tgtKey) {
    state.rowOverrides[tgtKey] = null;
    renderRowMappings();
    showToast('已解绑该行');
}
function openRowPicker(tgtKey) {
    currentRowPickKey = tgtKey;
    rowPickSelected = null;
    const overlay = document.getElementById('row-picker-overlay');
    const list = document.getElementById('row-picker-list');
    const title = document.getElementById('row-picker-tgt');
    if (!overlay || !list || !title) return;
    title.textContent = tgtKey || '';
    renderRowPickerList('');
    overlay.classList.add('show');
    const sb = document.getElementById('row-picker-search');
    if (sb) {
        sb.value = '';
        sb.oninput = e => renderRowPickerList(e.target.value);
        setTimeout(() => sb.focus(), 100);
    }
}
function renderRowPickerList(filter) {
    const list = document.getElementById('row-picker-list');
    if (!list) return;
    list.innerHTML = '';
    const keys = state.srcRowKeys || [];
    const ft = (filter || '').trim().toLowerCase();
    const cur = effectiveSrcKey(currentRowPickKey);

    const none = document.createElement('div');
    none.className = 'picker-item none-option';
    none.innerHTML = '<span class="none-icon">✕</span> 解绑（不匹配此行）';
    none.onclick = () => { state.rowOverrides[currentRowPickKey] = null; closeRowPicker(); renderRowMappings(); showToast('已解绑'); };
    list.appendChild(none);

    const filtered = ft ? keys.filter(k => fuzzyMatch(k, ft)) : keys;
    filtered.forEach(k => {
        const item = document.createElement('div');
        item.className = 'picker-item';
        item.innerHTML = '<span class="picker-src-name">' + escapeHtml(k) + '</span>' +
            (k === cur ? ' <span class="picker-rec">当前</span>' : '');
        item.onclick = () => {
            rowPickSelected = k;
            Array.from(list.children).forEach(c => c.classList.remove('selected'));
            item.classList.add('selected');
        };
        list.appendChild(item);
    });
    if (filtered.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = 'padding:16px;text-align:center;color:#999';
        empty.textContent = '🔍 无可用源';
        list.appendChild(empty);
    }
}
function confirmRowPick() {
    if (rowPickSelected !== null && currentRowPickKey !== null) {
        state.rowOverrides[currentRowPickKey] = rowPickSelected;
        renderRowMappings();
        showToast('已改配 → ' + rowPickSelected);
    }
    closeRowPicker();
}
function closeRowPicker() {
    const overlay = document.getElementById('row-picker-overlay');
    if (overlay) overlay.classList.remove('show');
    currentRowPickKey = null;
    rowPickSelected = null;
}

/* ========= 5 分钟忙碌提示 ========= */
function showBusyTip() {
    const overlay = document.getElementById('busy-tip-overlay');
    if (overlay) overlay.classList.add('show');
    setTimeout(function () { closeBusyTip(); }, 20000);
}
function closeBusyTip() {
    const overlay = document.getElementById('busy-tip-overlay');
    if (overlay) overlay.classList.remove('show');
}


/* (R4 手动匹配表头/项目列 已废弃，V1.2.7 移除) */

/* ========= SECTION C：输出与执行 ========= */
function prefillOutputPath() {
    const el = document.getElementById('output-path');
    if (!el || el.value) return;
    let name = '匹配结果_' + tsStamp() + '.xlsx';
    if (state.tgtFile) {
        name = state.tgtFile.replace(/(\.[^.]+)$/, '_已填充_' + tsStamp() + '$1');
    }
    el.value = name;
}
async function selectOutputPath() {
    const el = document.getElementById('output-path');
    if (!el) return;
    const def = el.value || ('匹配结果_' + tsStamp() + '.xlsx');
    const res = await apiCall('save_output_dialog', [fileBase(def)]);
    if (res) el.value = res;
}
async function confirmAndExecute() {
    // 彩蛋④：开始执行按钮连点炸毛
    runClickCount++;
    clearTimeout(runClickTimer);
    runClickTimer = setTimeout(() => { runClickCount = 0; }, 3000);
    if (runClickCount >= 10) {
        runClickCount = 0;
        showToast('🙈 别戳啦！表哥在跑，急不来~');
        return;
    }
    const el = document.getElementById('output-path');
    if (!el || !el.value.trim()) { showToast('请先指定保存路径'); return; }
    const path = el.value.trim();
    // 覆盖确认（openpyxl 静默覆盖，需前端二次确认）
    const ex = await apiCall('path_exists', [path]);
    if (ex && ex.success && ex.exists) {
        if (!confirm('目标文件已存在：\n' + path + '\n\n确定要覆盖吗？')) return;
    }
    await startExecution(path);
}
async function startExecution(path) {
    const panel = document.getElementById('exec-panel');
    const banner = document.getElementById('exec-banner');
    const cancelBtn = document.getElementById('btn-cancel');
    const resetBtn = document.getElementById('btn-reset');
    const openBtn = document.getElementById('btn-open-result');
    if (panel) panel.style.display = 'block';
    if (banner) { banner.style.display = 'none'; banner.className = 'exec-banner'; }
    if (cancelBtn) cancelBtn.style.display = 'inline-flex';
    if (resetBtn) resetBtn.style.display = 'none';
    if (openBtn) openBtn.style.display = 'none';
    setProgress(0, '');
    startProgressTips();
    showToast('🚀 开始执行填表...');
    setLogoState('filling');

    const timeoutSec = 600;
    execState = { running: true, startTs: Date.now(), lastBackendTs: 0, timeoutSec, busyTipTimeout: null };

    // 5 分钟温馨提示（20 秒后自动退出，不影响后台匹配）
    execState.busyTipTimeout = setTimeout(function () {
        if (execState.running) showBusyTip();
    }, 300000);

    // 后台线程执行，立即返回 started；前端靠轮询 get_exec_status 掌握进度
    const fillRes = await apiCall('execute_fill', [
        state.matches, path, timeoutSec,
        state.rowKeys.src, state.rowKeys.tgt, state.rowOverrides,
    ]);
    if (!fillRes || !fillRes.success) {
        if (execState.busyTipTimeout) { clearTimeout(execState.busyTipTimeout); execState.busyTipTimeout = null; }
        execState.running = false;
        stopProgressTips();
        showBanner('error', (fillRes && fillRes.error) ? fillRes.error : '自动填表执行失败，请查看控制台');
        return;
    }

    if (execTimer) clearInterval(execTimer);
    execTimer = setInterval(async () => {
        if (!execState.running) return;
        const now = Date.now();
        const res = await apiCall('get_exec_status', []);
        if (res && res.success) {
            setProgress(res.pct || 0, res.msg || '');
            execState.lastBackendTs = (res.last_progress_ts || 0) * 1000;
            if (res.done) { finishExecution(res); return; }
            // 超时判定：自上次进度起超过设定时长，或总时长超过 2 倍兜底
            const sinceProgress = execState.lastBackendTs
                ? (now - execState.lastBackendTs)
                : (now - execState.startTs);
            if (sinceProgress > execState.timeoutSec * 1000 ||
                (now - execState.startTs) > execState.timeoutSec * 2000) {
                execState.running = false;
                stopProgressTips();
                if (execTimer) { clearInterval(execTimer); execTimer = null; }
                apiCall('abort_fill', []);
                showBanner('timeout', '⏱ 执行超时（已超过 ' + execState.timeoutSec + 's 无进度更新），已中止。');
                const cb = document.getElementById('btn-cancel'); if (cb) cb.style.display = 'none';
                const rb = document.getElementById('btn-reset'); if (rb) rb.style.display = 'inline-flex';
                return;
            }
        }
        const elapsed = Math.floor((now - execState.startTs) / 1000);
        const el = document.getElementById('progress-elapsed');
        if (el) el.textContent = '已用 ' + elapsed + 's';
    }, 1000);
}
function finishExecution(res) {
    execState.running = false;
    stopProgressTips();
    if (execTimer) { clearInterval(execTimer); execTimer = null; }
    if (execState.busyTipTimeout) { clearTimeout(execState.busyTipTimeout); execState.busyTipTimeout = null; }
    closeBusyTip();
    const cb = document.getElementById('btn-cancel'); if (cb) cb.style.display = 'none';
    const pctEl = document.getElementById('progress-pct');
    const fillEl = document.getElementById('progress-fill');
    if (res.aborted) {
        showBanner('timeout', '⏱ ' + (res.error || '执行已取消/超时，未写入文件'));
    } else if (res.error) {
        showBanner('error', '❌ 执行失败：' + res.error);
    } else {
        setProgress(100, '');
        if (pctEl) pctEl.classList.add('done');
        if (fillEl) fillEl.classList.add('done');
        const out = (res.result && res.result.output_path) || '';
        state.resultPath = out;
        showBanner('done', '✅ 执行成功，已保存至 ' + out);
        apiCall('open_output', [out]).catch(() => {});
        const ob = document.getElementById('btn-open-result'); if (ob && out) ob.style.display = 'inline-flex';
        setLogoState('done');
        // 彩蛋①：进度满格，表哥立功
        spawnConfetti();
        showToast('🥰 全部填完，表哥立功！');
    }
    const rb = document.getElementById('btn-reset'); if (rb) rb.style.display = 'inline-flex';
}
function cancelExecute() {
    execState.running = false;
    stopProgressTips();
    if (execTimer) { clearInterval(execTimer); execTimer = null; }
    if (execState.busyTipTimeout) { clearTimeout(execState.busyTipTimeout); execState.busyTipTimeout = null; }
    closeBusyTip();
    apiCall('abort_fill', []);
    showBanner('timeout', '⏱ 已取消执行。');
    const cb = document.getElementById('btn-cancel'); if (cb) cb.style.display = 'none';
    const rb = document.getElementById('btn-reset'); if (rb) rb.style.display = 'inline-flex';
}
function setProgress(pct, msg) {
    pct = Math.max(0, Math.min(100, pct | 0));
    const fillEl = document.getElementById('progress-fill');
    const pctEl = document.getElementById('progress-pct');
    if (fillEl) fillEl.style.width = pct + '%';
    if (pctEl) pctEl.textContent = pct + '%';
}

/* ========= 需求2：进度条下方虚拟动态轮播提示 ========= */
function startProgressTips() {
    if (tipTimer) clearInterval(tipTimer);
    const el = document.getElementById('progress-tip');
    if (!el) return;
    let i = 0;
    const show = () => {
        el.textContent = PROGRESS_TIPS[i % PROGRESS_TIPS.length];
        // 先移除再强制重排后添加，使每次切换都有 200ms 淡入
        el.classList.remove('tip-show');
        void el.offsetWidth;
        el.classList.add('tip-show');
        i++;
    };
    show();
    tipTimer = setInterval(show, 2600);
}
function stopProgressTips() {
    if (tipTimer) { clearInterval(tipTimer); tipTimer = null; }
    const el = document.getElementById('progress-tip');
    if (el) el.textContent = '';
}
function showBanner(type, text) {
    const b = document.getElementById('exec-banner');
    if (!b) return;
    b.style.display = 'block';
    b.className = 'exec-banner ' + type;
    b.textContent = text;
}
function addLog(msg, type) {
    const list = document.getElementById('exec-log');
    if (!list) return;
    const div = document.createElement('div');
    div.className = 'log-item' + (type ? ' ' + type : '');
    div.textContent = msg;
    list.appendChild(div);
}

/* ========= 结果查看 / 重置 ========= */
async function openResultFolder() {
    if (!state.resultPath) { showToast('尚未生成结果文件'); return; }
    const res = await apiCall('open_output_folder', [state.resultPath]);
    if (res && res.success) showToast('已在文件管理器中打开 📂');
    else showToast('无法打开文件夹: ' + ((res && res.error) ? res.error : '未知'));
}

function resetAll() {
    state = {
        srcFiles: [], tgtFile: null, srcFields: [], tgtFields: [], matches: [],
        resultPath: null, samples: {}, rowKeys: { src: null, tgt: null },
        rowAlignment: [], srcRowKeys: [], rowOverrides: {},
        filter: 'all', rowFilter: 'all', collapsed: { 'sec-field': true, 'sec-row': true, 'sec-exec': false },
        headerZones: { target: { start: 0, end: 0 }, sources: {} },
        headerCandidates: { target: [], sources: {} },
    };
    currentPickIdx = -1; currentRowPickKey = null; rowPickSelected = null;
    execState = { running: false, startTs: 0, lastTs: 0, timeoutSec: 60, busyTipTimeout: null };
    if (execTimer) { clearInterval(execTimer); execTimer = null; }
    stopProgressTips();
    closeBusyTip();
    setLogoState('idle');

    const fillEl = document.getElementById('progress-fill');
    const pctEl = document.getElementById('progress-pct');
    const elapsed = document.getElementById('progress-elapsed');
    if (fillEl) { fillEl.style.width = '0%'; fillEl.classList.remove('done'); }
    if (pctEl) { pctEl.textContent = '0%'; pctEl.classList.remove('done'); }
    if (elapsed) elapsed.textContent = '已用 0s';
    const panel = document.getElementById('exec-panel');
    const banner = document.getElementById('exec-banner');
    const runBtn = document.getElementById('btn-run');
    const openBtn = document.getElementById('btn-open-result');
    const resetBtn = document.getElementById('btn-reset');
    const cancelBtn = document.getElementById('btn-cancel');
    if (panel) panel.style.display = 'none';
    if (banner) { banner.style.display = 'none'; banner.className = 'exec-banner'; }
    if (runBtn) runBtn.style.display = '';
    if (openBtn) openBtn.style.display = 'none';
    if (resetBtn) resetBtn.style.display = 'none';
    if (cancelBtn) cancelBtn.style.display = 'none';
    const srcTags = document.getElementById('src-tags');
    const tgtZone = document.getElementById('tgt-zone');
    if (srcTags) srcTags.innerHTML = '';
    if (tgtZone) {
        tgtZone.className = 'upload-zone';
        tgtZone.innerHTML = '<div class="icon">📋</div><div class="label">选择目标模板</div><div class="hint">点击选择空白表格模板</div>';
    }
    const hzEl = document.getElementById('header-zone-per-source');
    if (hzEl) hzEl.innerHTML = '';
    const btn = document.getElementById('btn-match');
    if (btn) btn.disabled = true;
    const outEl = document.getElementById('output-path');
    if (outEl) outEl.value = '';
    const summaryBar = document.getElementById('match-summary-bar');
    if (summaryBar) summaryBar.style.display = 'none';
    const rowList = document.getElementById('rowmap-list');
    if (rowList) rowList.innerHTML = '';
    renderRowkeyHint();
    refreshSectionCollapseUI();
    updateRuleBlock();
    renderFieldMappings();
    switchPage(0);
    showToast('🔄 已重置，可以新建任务');
}

/* ========= 键盘切换 ========= */
document.addEventListener('keydown', e => {
    if (e.key === 'ArrowRight' || e.key === 'd') { if (currentPage < 3) switchPage(currentPage + 1); }
    if (e.key === 'ArrowLeft' || e.key === 'a') { if (currentPage > 0) switchPage(currentPage - 1); }
});

/* ========= PyWebView 就绪回调 ========= */
window.addEventListener('pywebviewready', function () {
    console.log('⚡ pywebview ready');
    setLogoState('idle');
    showToast('国企大表哥已就绪 ⚡');
    initEasterEggs();   // 彩蛋②空数据眩晕 / ③深夜陪伴 / ⑤键盘暗号
});

refreshSectionCollapseUI();
/* ========= V1.3.2 同义词词典管理 ========= */
async function openDictModal() {
    const o = document.getElementById('dict-overlay');
    if (!o) return;
    o.classList.add('show');
    await refreshDictFromServer();
}
async function refreshDictFromServer() {
    const res = await apiCall('get_user_dict', []);
    if (res && res.success) {
        const d = (res.dict !== undefined) ? res.dict : res;
        state.dictData = (d && typeof d === 'object' && !Array.isArray(d)) ? d : {};
    } else if (res) {
        showToast('❌ 加载词典失败: ' + (res.error || '未知'));
        if (!state.dictData) state.dictData = {};
    }
    renderDictList();
}
function renderDictList() {
    const list = document.getElementById('dict-list');
    if (!list) return;
    list.innerHTML = '';
    const data = state.dictData || {};
    const keys = Object.keys(data);
    const totalTerms = keys.reduce((s, k) => s + (Array.isArray(data[k]) ? data[k].length : 0), 0);
    const stat = document.getElementById('dict-stat');
    if (stat) stat.textContent = '共 ' + keys.length + ' 组 · 覆盖 ' + totalTerms + ' 术语';
    if (keys.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'dict-empty';
        empty.textContent = '词典为空，点「＋ 新增标准词」开始添加';
        list.appendChild(empty);
        return;
    }
    keys.forEach(function (key) {
        const syns = Array.isArray(data[key]) ? data[key] : [];
        const group = document.createElement('div');
        group.className = 'dict-group';

        const head = document.createElement('div');
        head.className = 'dict-group-head';
        const title = document.createElement('span');
        title.className = 'dict-std';
        title.textContent = key;
        const actions = document.createElement('div');
        actions.className = 'dict-group-actions';
        const editBtn = document.createElement('button');
        editBtn.className = 'dict-mini-btn';
        editBtn.textContent = '✎';
        editBtn.title = '重命名标准词';
        editBtn.onclick = function () { editDictGroup(key, title); };
        const delBtn = document.createElement('button');
        delBtn.className = 'dict-mini-btn';
        delBtn.textContent = '🗑';
        delBtn.title = '删除整组';
        delBtn.onclick = function () { removeDictGroup(key); };
        actions.appendChild(editBtn);
        actions.appendChild(delBtn);
        head.appendChild(title);
        head.appendChild(actions);

        const chips = document.createElement('div');
        chips.className = 'dict-chips';
        syns.forEach(function (syn, i) {
            const chip = document.createElement('span');
            chip.className = 'dict-chip';
            chip.textContent = syn;
            const x = document.createElement('span');
            x.className = 'dict-chip-x';
            x.textContent = '×';
            x.title = '删除该同义词';
            x.onclick = function () { removeSynonym(key, i); };
            chip.appendChild(x);
            chips.appendChild(chip);
        });
        const addBtn = document.createElement('button');
        addBtn.className = 'dict-add-syn';
        addBtn.textContent = '＋ 添加同义词';
        addBtn.onclick = function (e) { showAddSynInput(key, e.currentTarget); };
        chips.appendChild(addBtn);

        group.appendChild(head);
        group.appendChild(chips);
        list.appendChild(group);
    });
}
function addDictGroup() {
    const list = document.getElementById('dict-list');
    if (!list) return;
    const existing = list.querySelector('.dict-new-group');
    if (existing) { const inp = existing.querySelector('input'); if (inp) inp.focus(); return; }
    const empty = list.querySelector('.dict-empty');
    if (empty) empty.remove();
    const form = document.createElement('div');
    form.className = 'dict-group dict-new-group';
    const wrap = document.createElement('span');
    wrap.className = 'dict-add-wrap';
    const inp = document.createElement('input');
    inp.className = 'dict-add-input';
    inp.placeholder = '输入标准词名称';
    const ok = document.createElement('button');
    ok.className = 'dict-mini-ok'; ok.textContent = '✓';
    const no = document.createElement('button');
    no.className = 'dict-mini-no'; no.textContent = '✕';
    const commit = function () {
        const v = inp.value.trim();
        if (!v) { form.remove(); if (Object.keys(state.dictData || {}).length === 0) renderDictList(); return; }
        if ((state.dictData || {})[v] !== undefined) { showToast('该标准词已存在'); inp.focus(); return; }
        state.dictData[v] = [];
        renderDictList();
    };
    ok.onclick = commit;
    no.onclick = function () { form.remove(); if (Object.keys(state.dictData || {}).length === 0) renderDictList(); };
    inp.onkeydown = function (e) { if (e.key === 'Enter') commit(); else if (e.key === 'Escape') no.onclick(); };
    wrap.appendChild(inp); wrap.appendChild(ok); wrap.appendChild(no);
    form.appendChild(wrap);
    list.appendChild(form);
    inp.focus();
}
function showAddSynInput(key, btnEl) {
    const wrap = document.createElement('span');
    wrap.className = 'dict-add-wrap';
    const inp = document.createElement('input');
    inp.className = 'dict-add-input';
    inp.placeholder = '输入同义词';
    const ok = document.createElement('button');
    ok.className = 'dict-mini-ok'; ok.textContent = '✓';
    const no = document.createElement('button');
    no.className = 'dict-mini-no'; no.textContent = '✕';
    const commit = function () {
        const v = inp.value.trim();
        if (!v) { renderDictList(); return; }
        if (!Array.isArray(state.dictData[key])) state.dictData[key] = [];
        if (state.dictData[key].indexOf(v) === -1) state.dictData[key].push(v);
        else showToast('该同义词已存在');
        renderDictList();
    };
    ok.onclick = commit;
    no.onclick = function () { renderDictList(); };
    inp.onkeydown = function (e) { if (e.key === 'Enter') commit(); else if (e.key === 'Escape') renderDictList(); };
    wrap.appendChild(inp); wrap.appendChild(ok); wrap.appendChild(no);
    if (btnEl && btnEl.replaceWith) btnEl.replaceWith(wrap);
    else if (btnEl && btnEl.parentNode) btnEl.parentNode.replaceChild(wrap, btnEl);
    inp.focus();
}
function removeSynonym(key, i) {
    const arr = state.dictData[key];
    if (Array.isArray(arr)) arr.splice(i, 1);
    renderDictList();
}
function editDictGroup(oldKey, titleEl) {
    const wrap = document.createElement('span');
    wrap.className = 'dict-add-wrap';
    const inp = document.createElement('input');
    inp.className = 'dict-add-input';
    inp.value = oldKey;
    const ok = document.createElement('button');
    ok.className = 'dict-mini-ok'; ok.textContent = '✓';
    const no = document.createElement('button');
    no.className = 'dict-mini-no'; no.textContent = '✕';
    const commit = function () {
        const v = inp.value.trim();
        if (!v || v === oldKey) { renderDictList(); return; }
        if ((state.dictData || {})[v] !== undefined) { showToast('该标准词已存在'); inp.focus(); return; }
        const arr = state.dictData[oldKey];
        delete state.dictData[oldKey];
        state.dictData[v] = arr;
        renderDictList();
    };
    ok.onclick = commit;
    no.onclick = function () { renderDictList(); };
    inp.onkeydown = function (e) { if (e.key === 'Enter') commit(); else if (e.key === 'Escape') renderDictList(); };
    wrap.appendChild(inp); wrap.appendChild(ok); wrap.appendChild(no);
    if (titleEl && titleEl.replaceWith) titleEl.replaceWith(wrap);
    else if (titleEl && titleEl.parentNode) titleEl.parentNode.replaceChild(wrap, titleEl);
    inp.focus();
    inp.select();
}
function removeDictGroup(key) {
    if (!confirm('确认删除标准词「' + key + '」及其所有同义词？')) return;
    delete state.dictData[key];
    renderDictList();
}
async function saveDict() {
    const res = await apiCall('save_user_dict', [state.dictData || {}]);
    if (res && res.success) {
        showToast('💾 同义词词典已保存');
    } else if (res) {
        showToast('❌ 保存失败: ' + (res.error || '未知'));
    }
}
async function exportDict() {
    const res = await apiCall('export_user_dict', []);
    let content;
    if (res && res.success && typeof res.content === 'string') {
        content = res.content;
    } else if (res && res.success) {
        content = JSON.stringify(state.dictData || {}, null, 2);
    } else {
        if (res) showToast('❌ 导出失败: ' + (res.error || '未知'));
        return;
    }
    try {
        const blob = new Blob([content], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = (res && res.filename) || '同义词词典.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        showToast('📤 已导出词典');
    } catch (e) {
        showToast('❌ 导出失败: ' + e.message);
    }
}
function importDict() {
    const inp = document.getElementById('dict-import-input');
    if (!inp) return;
    inp.value = '';
    inp.onchange = function () {
        const file = inp.files && inp.files[0];
        inp.onchange = null;
        if (!file) return;
        const reader = new FileReader();
        reader.onload = async function () {
            const text = reader.result;
            try {
                const res = await apiCall('import_user_dict', [text]);
                if (res && res.success) {
                    await refreshDictFromServer();
                    showToast('✅ 已导入，点【重载】生效');
                } else if (res) {
                    showToast('❌ 导入失败: ' + (res.error || '格式不合法'));
                }
            } catch (e) {
                showToast('❌ 导入失败: ' + e.message);
            }
        };
        reader.onerror = function () { showToast('❌ 读取文件失败'); };
        reader.readAsText(file);
    };
    inp.click();
}
async function reloadDict() {
    const res = await apiCall('reload_user_dict', []);
    if (res && res.success) {
        const d = (res.dict !== undefined) ? res.dict : res;
        state.dictData = (d && typeof d === 'object' && !Array.isArray(d)) ? d : {};
        renderDictList();
        showToast('🔄 已重载词典');
    } else if (res) {
        showToast('❌ 重载失败: ' + (res.error || '未知'));
    } else {
        renderDictList();
    }
}
function closeDictModal() {
    const o = document.getElementById('dict-overlay');
    if (o) o.classList.remove('show');
}

console.log('%c⚡ 国企大表哥 guoqi bigbro V1.3.3', 'font-size:20px;font-weight:900;color:#6C5CE7');
