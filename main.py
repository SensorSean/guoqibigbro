import webview
import os
import sys
import json
import datetime
import tempfile
import traceback
import threading
import pandas as pd

try:
    from core.excel_reader import ExcelReader
    from core.matcher import FieldMatcher, _get_dict_path
    from core.filler import TableFiller
except ImportError as e:
    print(f"[FATAL] 导入模块失败: {e}")
    sys.exit(1)


__version__ = "V1.3.3"
APP_NAME = "国企大表哥"
APP_TAGLINE = "guoqibigbro · 填表表哥"
AUTHOR = "LuoLei"


class UsageLog:
    """开发人员使用日志：后台静默记录匹配/执行过程详情，不暴露给前端。
    日志文件：exe 同目录下的 国企大表哥_usage.log，每行一条 JSON，便于 grep/cat。
    """
    LOG_FILE = "国企大表哥_usage.log"

    @staticmethod
    def _log_path():
        base = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base, UsageLog.LOG_FILE)

    @staticmethod
    def _write(entry):
        try:
            path = UsageLog._log_path()
            with open(path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception:
            pass  # 日志写入失败不阻断主流程

    @staticmethod
    def log_matches(matches):
        """auto_match 完成后调用：记录每一对目标→源映射的明细。"""
        ts = datetime.datetime.now().isoformat(timespec='seconds')
        for m in (matches or []):
            if not isinstance(m, dict):
                continue
            src = m.get("src_field") or ""
            tgt = m.get("tgt_field") or ""
            if not tgt:
                continue
            conf = m.get("confidence", 0)
            if m.get("auto"):
                decision = "auto"
            elif m.get("suggested"):
                decision = "suggested"
            elif m.get("matched"):
                decision = "manual"
            else:
                decision = "unmatched"
            UsageLog._write({
                "ts": ts,
                "event": "match",
                "target": tgt,
                "source": src,
                "score": round(conf, 1) if isinstance(conf, (int, float)) else 0,
                "decision": decision,
            })

    @staticmethod
    def log_exec_start(matches):
        """execute_fill 启动时调用：再次记录当前生效的映射明细（可能与 auto_match 后有变化）。"""
        ts = datetime.datetime.now().isoformat(timespec='seconds')
        for m in (matches or []):
            if not isinstance(m, dict):
                continue
            src = m.get("src_field") or ""
            tgt = m.get("tgt_field") or ""
            if not tgt:
                continue
            conf = m.get("confidence", 0)
            if m.get("auto"):
                decision = "auto"
            elif m.get("suggested"):
                decision = "suggested"
            elif m.get("matched"):
                decision = "manual"
            else:
                decision = "unmatched"
            UsageLog._write({
                "ts": ts,
                "event": "exec_match",
                "target": tgt,
                "source": src,
                "score": round(conf, 1) if isinstance(conf, (int, float)) else 0,
                "decision": decision,
            })

    @staticmethod
    def log_exec_summary(matches, duration_sec):
        """执行完成后调用：汇总统计。"""
        ts = datetime.datetime.now().isoformat(timespec='seconds')
        auto = sum(1 for m in (matches or []) if isinstance(m, dict) and m.get("auto"))
        suggested = sum(1 for m in (matches or []) if isinstance(m, dict) and m.get("suggested") and not m.get("auto"))
        manual = sum(1 for m in (matches or []) if isinstance(m, dict) and m.get("matched") and not m.get("auto") and not m.get("suggested"))
        unmatched = sum(1 for m in (matches or []) if isinstance(m, dict) and not m.get("matched") and not m.get("suggested"))
        total = len(matches or [])
        UsageLog._write({
            "ts": ts,
            "event": "exec_done",
            "total": total,
            "auto": auto,
            "suggested": suggested,
            "manual": manual,
            "unmatched": unmatched,
            "duration_sec": round(duration_sec, 1) if isinstance(duration_sec, (int, float)) else 0,
        })


class Api:
    """JS API 桥接层，暴露给前端 app.js 调用。
    方法签名保持与 guoqi-bigbro 完全一致：
      select_files / select_target / load_sources / load_target /
      auto_match / execute_fill
    V1.2 新增：行级映射契约（get_rowkey_candidates / compute_row_alignment）、
    执行超时真支撑（后台线程 + abort_fill + 进度心跳）、样例值、路径校验。
    """

    def __init__(self):
        self.reader = ExcelReader()
        self.matcher = FieldMatcher()
        # V1.3.2：启动时加载 exe 同目录的用户同义词词典（叠加进写死词典）。
        # 失败仅 log，不阻断启动；损坏/缺失都回退纯写死内置词典。
        try:
            ok, msg = self.matcher.load_user_dict()
            if not ok:
                print(f"[WARN] 启动加载用户同义词词典失败（已用内置词典）: {msg}")
        except Exception as e:
            print(f"[WARN] 启动加载用户同义词词典异常（已用内置词典）: {e}")
        self.filler = TableFiller()
        self.state = {}
        # 执行看门狗：后台填充线程 + 停止事件
        self._stop_event = threading.Event()
        self._exec_thread = None
        # 执行状态（前端轮询，避免依赖 evaluate_js 的线程安全性）
        self._exec = {
            "running": False, "pct": 0, "msg": "", "done": False,
            "aborted": False, "error": None, "result": None,
            "last_progress_ts": 0,
        }

    def get_app_info(self):
        """返回应用元信息（版本/作者等），供前端「关于」页调用。"""
        return {
            "version": __version__,
            "app_name": APP_NAME,
            "tagline": APP_TAGLINE,
            "author": AUTHOR,
        }

    def select_files(self):
        try:
            win = webview.windows[0]
            result = win.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=True,
                file_types=("Excel Files (*.xlsx;*.xls;*.csv)",)
            )
            return result if result else []
        except Exception as e:
            print(f"[ERROR] select_files: {e}")
            traceback.print_exc()
            return []

    def select_target(self):
        try:
            win = webview.windows[0]
            result = win.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=("Excel Files (*.xlsx;*.xls)",)
            )
            return result[0] if result else None
        except Exception as e:
            print(f"[ERROR] select_target: {e}")
            traceback.print_exc()
            return None

    def load_sources(self, file_paths, manual_zones=None):
        try:
            print(f"[INFO] load_sources: 收到 {len(file_paths)} 个文件")
            res = self.reader.load_files(file_paths, manual_zones=manual_zones)
            self.state['src_dfs'] = res.get("dfs", [])
            fields = self.reader.get_all_fields(self.state['src_dfs'])
            header_info = res.get("header_info", {})
            print(f"[INFO] load_sources: 识别到 {len(fields)} 个数据源字段")
            for f in fields[:3]:
                print(f"[DEBUG] 字段示例: {f}")
            return {"success": True, "fields": fields, "header_info": header_info}
        except Exception as e:
            print(f"[ERROR] load_sources: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def load_target(self, file_path, manual_zone=None):
        try:
            print(f"[INFO] load_target: {file_path}")
            res = self.reader.load_target(file_path, manual_zone=manual_zone)
            self.state['tgt_df'] = res.get("df")
            self.state['tgt_path'] = file_path
            self.state['tgt_header_row'] = getattr(self.reader, 'tgt_header_row', 0)
            fields = self.reader.get_target_fields(self.state['tgt_df'])
            print(f"[INFO] load_target: 识别到 {len(fields)} 个目标字段")
            return {"success": True, "fields": fields, "header_info": res.get("header_info", {})}
        except Exception as e:
            print(f"[ERROR] load_target: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def auto_match(self, src_fields, tgt_fields):
        try:
            print(f"[INFO] auto_match: 数据源{len(src_fields)}个，目标{len(tgt_fields)}个")
            matches = self.matcher.auto_match(src_fields, tgt_fields)
            matched_count = sum(1 for m in matches if m.get("matched"))
            print(f"[INFO] auto_match: 匹配完成，成功{matched_count}/{len(matches)}")
            # 使用日志：记录每一对映射明细
            try:
                UsageLog.log_matches(matches)
            except Exception:
                pass
            # 直接返回 dict，由 pywebview 的 json.dumps 做【单次】序列化（避免双重编码导致前端 Promise 挂起）。
            return {"success": True, "matches": matches}
        except Exception as e:
            print(f"[ERROR] auto_match: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def get_candidates(self, tgt_field: str):
        """为指定目标字段计算与所有源字段的相似度，按相似度逆序返回。"""
        try:
            src_dfs = self.state.get('src_dfs', [])
            if not src_dfs:
                return {"success": False, "error": "未加载数据源"}

            all_fields = self.reader.get_all_fields(src_dfs)

            scored = []
            for src in all_fields:
                score = self.matcher.score_field(
                    src.get("name", ""), tgt_field
                )
                src_copy = dict(src)
                src_copy["similarity"] = round(score, 1)
                scored.append(src_copy)

            scored.sort(key=lambda x: -x["similarity"])
            return {"success": True, "candidates": scored}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # V1.3.2 用户同义词词典桥接 API（前端 同义词词典面板 调用）
    # ------------------------------------------------------------------

    def get_user_dict(self):
        """返回当前内存中的用户同义词词典（标准词→同义词数组）。"""
        try:
            return {"success": True, "data": self.matcher._user_dict or {}}
        except Exception as e:
            print(f"[ERROR] get_user_dict: {e}")
            return {"success": False, "error": str(e)}

    def save_user_dict(self, data):
        """写入用户同义词词典（exe 同目录 同义词词典.json）并重载。

        接收前端传来的 {标准词: [同义词]} 字典；写临时文件再 rename 防半写；
        随后调用 matcher.load_user_dict() 重载。返回 {success, error?}。
        """
        try:
            if not isinstance(data, dict):
                return {"success": False, "error": "数据格式错误（应为字典）"}
            # 校验并归一化为标准结构
            payload = {}
            for std, syns in data.items():
                if not isinstance(std, str) or not std.strip():
                    continue
                if not isinstance(syns, list):
                    return {"success": False, "error": f"标准词「{std}」的同义词须为数组"}
                arr = [s for s in syns if isinstance(s, str) and s.strip()]
                if arr:
                    payload[std.strip()] = arr
            wrapped = {
                "version": 1,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "synonyms": payload,
            }
            content = json.dumps(wrapped, ensure_ascii=False, indent=2)
            path = _get_dict_path()
            self._write_dict_file(path, content)
            ok, msg = self.matcher.load_user_dict()
            if not ok:
                return {"success": False, "error": msg}
            print(f"[INFO] save_user_dict: 已保存 {len(payload)} 组到 {path}")
            return {"success": True}
        except Exception as e:
            print(f"[ERROR] save_user_dict: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def reload_user_dict(self):
        """重新加载 exe 同目录的用户同义词词典（供「🔄 重载」按钮）。"""
        try:
            ok, msg = self.matcher.load_user_dict()
            if not ok:
                return {"success": False, "error": msg}
            return {"success": True}
        except Exception as e:
            print(f"[ERROR] reload_user_dict: {e}")
            return {"success": False, "error": str(e)}

    def export_user_dict(self):
        """导出当前内存用户同义词词典为 JSON 字符串（前端负责弹保存对话框）。"""
        try:
            user_dict = self.matcher._user_dict or {}
            wrapped = {
                "version": 1,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "synonyms": user_dict,
            }
            content = json.dumps(wrapped, ensure_ascii=False, indent=2)
            return {"success": True, "content": content}
        except Exception as e:
            print(f"[ERROR] export_user_dict: {e}")
            return {"success": False, "error": str(e)}

    def import_user_dict(self, content):
        """导入用户同义词词典（接收 JSON 字符串），校验/写文件/重载。

        损坏 JSON → 返回失败（前端 Toast），不写文件、不崩。
        """
        try:
            if not isinstance(content, str):
                return {"success": False, "error": "导入内容须为 JSON 字符串"}
            try:
                raw = json.loads(content)
            except (json.JSONDecodeError, ValueError) as e:
                return {"success": False, "error": f"JSON 解析失败: {e}"}
            if not isinstance(raw, dict) or "synonyms" not in raw \
                    or not isinstance(raw["synonyms"], dict):
                return {"success": False, "error": "结构非法：顶层须含 synonyms 字典"}
            # 归一化（容错 version/updated_at 缺省），同时校验每个同义词数组
            payload = {}
            for std, syns in raw["synonyms"].items():
                if not isinstance(std, str) or not std.strip():
                    continue
                if not isinstance(syns, list):
                    return {"success": False, "error": f"标准词「{std}」的同义词须为数组"}
                arr = [s for s in syns if isinstance(s, str) and s.strip()]
                if arr:
                    payload[std.strip()] = arr
            wrapped = {
                "version": 1,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "synonyms": payload,
            }
            out = json.dumps(wrapped, ensure_ascii=False, indent=2)
            path = _get_dict_path()
            self._write_dict_file(path, out)
            ok, msg = self.matcher.load_user_dict()
            if not ok:
                return {"success": False, "error": msg}
            print(f"[INFO] import_user_dict: 已导入 {len(payload)} 组到 {path}")
            return {"success": True}
        except Exception as e:
            print(f"[ERROR] import_user_dict: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    @staticmethod
    def _write_dict_file(path, content):
        """原子写入词典文件：先写临时文件再 os.replace 重命名，防半写损坏。"""
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass
            raise

    def save_output_dialog(self, default_name="匹配结果.xlsx"):
        """弹出保存对话框让用户选择保存位置。返回完整路径（强制 .xlsx 后缀）。"""
        try:
            win = webview.windows[0]
            result = win.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=("Excel Files (*.xlsx)",)
            )
            if not result:
                return None
            if isinstance(result, str):
                path = result.strip()
                return path if path.lower().endswith('.xlsx') else path + '.xlsx'
            if isinstance(result, (tuple, list)):
                if len(result) == 0:
                    return None
                if len(result) == 2:
                    d, f = result
                    path = os.path.join(str(d), str(f))
                    return path if path.lower().endswith('.xlsx') else path + '.xlsx'
                path = str(result[0]).strip()
                return path if path.lower().endswith('.xlsx') else path + '.xlsx'
            return str(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[ERROR] save_output_dialog: {e}")
            return None

    def path_exists(self, path):
        """校验输出路径是否已存在（供前端执行前覆盖确认）。"""
        try:
            return {"success": True, "exists": bool(path) and os.path.exists(path)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_all_samples(self):
        """返回所有数据源字段的首个非空样例值，供映射卡内联展示（替代预览）。"""
        try:
            src_dfs = self.state.get('src_dfs', [])
            samples = {}
            for info in src_dfs:
                df = info['df']
                for col in df.columns:
                    key = str(col)
                    if key in samples:
                        continue
                    vals = []
                    for v in df[col]:
                        if pd.notna(v) and str(v).strip():
                            vals.append(str(v).strip())
                            if len(vals) >= 3:
                                break
                    if vals:
                        samples[key] = " / ".join(vals[:3])
            return {"success": True, "samples": samples}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _derive_row_keys(matches, tgt_df=None):
        """从字段映射中派生出行键（目标字段 + 其映射到的源字段）。

        优先挑选目标字段名含「项目/工程/立项/标段/合同/协议/编号/名称」
        且已匹配到源字段的映射；找不到则取任意已匹配项兜底。

        【V1.2.8 修复】在原「按关键字优先级」基础上增加「目标列实际有值」约束：
        某些模板首列是「立项名称」(402 行全有值) 而「项目编号」列虽同名却全空。
        旧逻辑按关键字顺序会先命中「项目编号」→ filler 以空列作行键 →
        判定模板无数据行 → 误入空模板自动收集分支，把 340 条源记录填进
        新追加的行、用户原有的 402 行一个值都没填 → “匹配了但填不进去”。
        现改为：在命中关键字的候选里，优先选「目标模板中非空单元格最多」的那列，
        从而保证选中的是真正承载行身份的、有数据的列。
        """
        # 关键字优先级：名字类(立项/名称) > 项目/工程/标段/合同/协议 > 编号。
        # 行身份应以「立项名称/项目名称」这类跨源通用的“名字”为准，而非“项目编号”
        # 这类仅部分数据源存在的“编码”——本例中目标首尾两列(立项名称、项目编号)
        # 都满 402 行，若按旧顺序(项目先于立项)会误选“项目编号”，而源2/源3根本
        # 没有“项目编号”列，按编码对齐会导致这两源整列漏填。名字类置顶可确保选中
        # 所有源都共有的“立项名称”作行键。
        rowkey_kws = ["立项", "名称", "项目", "工程", "标段", "合同", "协议", "编号"]
        usable = [
            m for m in matches
            if isinstance(m, dict) and m.get("matched") and m.get("src_field")
        ]
        if not usable:
            return None, None

        def _pop(tgt_field):
            """目标列在模板中的有效单元格数（用于挑选真正有数据的行键列）。

            【V1.3.0 修复】必须与 filler._extract_keys / _auto_detect_key_column
            的口径一致：用 pd.notna 判定有效性。否则全 NaT 的日期列会被
            str(NaT)="NaT" 误判为非空，导致：行键派生误选该列 → execute 内
            valid_tgt_keys=0 → 误入「空模板自动收集」分支 → 源记录被追加到
            131 个空模板行之下（用户看到的 134 起、前段空白）。
            """
            if tgt_df is None or not hasattr(tgt_df, "columns"):
                return 0
            if tgt_field not in tgt_df.columns:
                return 0
            col = tgt_df[tgt_field]
            try:
                return int(col.apply(
                    lambda v: bool(pd.notna(v)) and str(v).strip() != ""
                ).sum())
            except Exception:
                return 0

        def _kw_rank(tgt_field):
            s = str(tgt_field)
            for i, kw in enumerate(rowkey_kws):
                if kw in s:
                    return i
            return len(rowkey_kws)

        # 候选 = 命中任一行键关键字的已匹配字段；若都没有则退回全部已匹配字段
        cands = [
            m for m in usable
            if _kw_rank(m.get("tgt_field", "")) < len(rowkey_kws)
        ]
        pool = cands if cands else usable

        # 「兜底的兜底」：matches 列表若缺失关键条目（如 pywebview 序列化丢字段），
        # 直接从目标 DataFrame 列名中按关键字+非空数搜索行键列，避免退回 None → auto-collect
        if not pool and tgt_df is not None and hasattr(tgt_df, "columns"):
            best_col, best_pop = None, 0
            for col in tgt_df.columns:
                for kw in rowkey_kws:
                    if kw in str(col):
                        n = _pop(col)
                        if n > best_pop:
                            best_col, best_pop = col, n
                        break
            if best_col:
                return best_col, best_col  # 同名直用作 src/tgt 行键
        # 排序：非空数最多 > 关键字优先级最高 > 原匹配顺序最前
        pool_sorted = sorted(
            pool,
            key=lambda m: (
                -_pop(m.get("tgt_field")),
                _kw_rank(m.get("tgt_field", "")),
                usable.index(m),
            ),
        )
        m = pool_sorted[0]
        return m.get("src_field"), m.get("tgt_field")

    def get_rowkey_candidates(self, src_fields, tgt_fields):
        """返回可作为「行标识键」的候选列名（源 / 目标分别列出）。"""
        def names(fields):
            out = []
            if isinstance(fields, list):
                for f in fields:
                    if isinstance(f, dict) and f.get('name'):
                        out.append(f['name'])
                    elif isinstance(f, str):
                        out.append(f)
            return out

        def dedupe(lst):
            seen = set()
            r = []
            for x in lst:
                if x not in seen:
                    seen.add(x)
                    r.append(x)
            return r

        return {
            "success": True,
            "src": dedupe(names(src_fields)),
            "tgt": dedupe(names(tgt_fields)),
        }

    def compute_row_alignment(self, src_key, tgt_key):
        """按行标识键计算源/目标行级配对，供「项目/合同行映射」列表展示与纠偏。"""
        try:
            src_dfs = self.state.get('src_dfs', [])
            tgt_df = self.state.get('tgt_df')
            if not src_dfs or tgt_df is None:
                return {"success": False, "error": "未加载数据源/目标"}

            alignment = self.filler.compute_alignment(
                src_dfs, tgt_df, src_key, tgt_key,
                template_path=self.state.get('tgt_path', ''),
                header_row=self.state.get('tgt_header_row', 0),
            )

            # 收集所有源行键值（供「改配」弹窗候选）
            src_keys = []
            for info in src_dfs:
                df = info['df']
                col = self.filler._find_matching_column(df, src_key) if src_key else None
                if col and col in df.columns:
                    for v in df[col]:
                        s = str(v).strip() if pd.notna(v) else ''
                        if s and s not in src_keys:
                            src_keys.append(s)

            return {"success": True, "alignment": alignment, "src_keys": src_keys}
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def execute_fill(
        self,
        matches,
        output_path=None,
        timeout_sec=600,
        row_key_src=None,
        row_key_tgt=None,
        row_overrides=None,
        prompt_save=False,
    ):
        """执行填表（V1.2：后台线程 + 超时中止 + 行级覆盖）。

        立即返回 {"success": True, "started": True}，真正的填充在后台线程进行，
        进度通过 window.__onProgress 心跳、完成通过 window.__onFillDone 回调。
        """
        try:
            src_dfs = self.state.get('src_dfs', [])
            tgt_df = self.state.get('tgt_df')
            if tgt_df is None:
                return {"success": False, "error": "请先加载目标模板"}
            if not src_dfs:
                return {"success": False, "error": "请先加载至少一个数据源后再执行自动填表"}

            # 默认输出路径：模板同目录 / 模板名_已填充_时间戳
            if not output_path:
                tgt_path = self.state.get('tgt_path', '')
                if tgt_path:
                    base, ext = os.path.splitext(tgt_path)
                    ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                    output_path = f"{base}_已填充_{ts}{ext}"
                else:
                    output_path = os.path.join(
                        tempfile.gettempdir(),
                        f"国企大表哥_结果_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    )

            # 后端自动派生行键（不受前端 state.rowKeys 影响，避免前端误选编码列）
            auto_src, auto_tgt = self._derive_row_keys(
                matches, self.state.get('tgt_df')
            )
            if auto_src and auto_tgt:
                # 派生成功 → 直接覆盖前端传值（避免前端误选编码列）
                row_key_src, row_key_tgt = auto_src, auto_tgt
                # 【V1.3.0 加固】与 filler._extract_keys 口径再次校验派生结果：
                # 若派生出的目标行键列在模板中实际 0 有效值（如全 NaT 的日期列），
                # 则放弃派生值、交还 filler 的 NA-aware 自动检测，避免 execute 内
                # valid_tgt_keys=0 → 误入「空模板自动收集」把数据追加到 134+ 行。
                _tgt_df = self.state.get('tgt_df')
                if _tgt_df is not None and auto_tgt in _tgt_df.columns:
                    _valid = int(sum(
                        1 for v in _tgt_df[auto_tgt]
                        if bool(pd.notna(v)) and str(v).strip() != ""
                    ))
                    if _valid == 0:
                        print(f"[WARN] execute_fill: 派生行键'{auto_tgt}'在目标列 0 有效值，"
                              f"放弃派生、改用自动检测 key 列")
                        row_key_src, row_key_tgt = None, None
                # 写日志确认（方便排查）
                logf = os.path.join(os.environ.get('LOCALAPPDATA', os.environ.get('TEMP', '.')), 'Temp', '国企大表哥_startup.log')
                with open(logf, 'a', encoding='utf-8') as _lf:
                    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    _lf.write(f"[{ts}] [row_key] derived: src={row_key_src} tgt={row_key_tgt}\n")
            elif not (row_key_src and row_key_tgt):
                # 派生失败且前端也未传 → 无行键，filler 会走 auto_detect
                print("[WARN] execute_fill: 无法确定行键，filler 将自动检测")
                print(f"[INFO] execute_fill: 派生行键 源={row_key_src} 目标={row_key_tgt}")

            # 归一化行覆盖：{tgt_key: src_key} 或 {tgt_key: None(解绑)}
            norm_overrides = {}
            if row_overrides:
                for k, v in row_overrides.items():
                    norm_overrides[str(k)] = (None if v is None else str(v))

            # 启动后台填充线程（主线程立即返回，前端看门狗接管计时）
            self._stop_event.clear()
            self._exec_thread = threading.Thread(
                target=self._exec_worker,
                args=(src_dfs, tgt_df, list(matches), output_path,
                      norm_overrides, timeout_sec,
                      row_key_src, row_key_tgt),
                daemon=True,
            )
            self._exec_thread.start()
            # 使用日志：记录当前生效的映射明细
            try:
                UsageLog.log_exec_start(matches)
            except Exception:
                pass
            print(f"[INFO] execute_fill: 后台线程已启动，输出={output_path} 超时={timeout_sec}s")
            return {"success": True, "started": True, "output_path": output_path}
        except Exception as e:
            print(f"[ERROR] execute_fill: {e}")
            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def _exec_worker(self, src_dfs, tgt_df, matches, output_path, row_overrides,
                     timeout_sec, row_key_src=None, row_key_tgt=None):
        """后台填充线程：更新 self._exec 状态（前端轮询），保存前可中止。"""
        import time
        logf = os.path.join(os.environ.get('LOCALAPPDATA', os.environ.get('TEMP', '.')), 'Temp', '国企大表哥_startup.log')
        os.makedirs(os.path.dirname(logf), exist_ok=True)
        with open(logf, 'a', encoding='utf-8') as _lf:
            ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            _lf.write(f"[{ts}] [exec_worker BEGIN] output={output_path}\n")
        self._exec["running"] = True
        self._exec["done"] = False
        self._exec["aborted"] = False
        self._exec["error"] = None
        self._exec["result"] = None
        self._exec["pct"] = 0
        self._exec["msg"] = "开始填充..."
        self._exec["last_progress_ts"] = time.time()
        _start_ts = time.time()

        def _progress(pct, msg):
            self._exec["pct"] = pct
            self._exec["msg"] = msg
            self._exec["last_progress_ts"] = time.time()

        try:
            _progress(0, "开始填充...")
            result = self.filler.execute(
                src_dfs, tgt_df, matches, output_path,
                key_column=row_key_tgt,
                src_key_column=row_key_src,
                template_path=self.state.get('tgt_path', ''),
                header_row=self.state.get('tgt_header_row', 0),
                stop_event=self._stop_event,
                row_overrides=row_overrides,
                progress_cb=_progress,
            )
            # 保存前若已被中止 → 不写文件
            if self._stop_event.is_set():
                self._exec["aborted"] = True
                self._exec["error"] = "执行已取消/超时，未写入文件"
                self._exec["done"] = True
                self._exec["running"] = False
                return
            if result.get("error"):
                self._exec["error"] = result["error"]
                self._exec["done"] = True
                self._exec["running"] = False
                with open(logf, 'a', encoding='utf-8') as _lf:
                    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    _lf.write(f"[{ts}] [exec_worker ERROR] filler result error: {result['error']}\n")
                return
            self._exec["result"] = result
            self._exec["pct"] = 100
            self._exec["msg"] = "完成"
            self._exec["done"] = True
            self._exec["running"] = False
            # 使用日志：记录执行汇总
            try:
                UsageLog.log_exec_summary(matches, time.time() - _start_ts)
            except Exception:
                pass
        except TimeoutError:
            self._exec["aborted"] = True
            self._exec["error"] = "执行超时，已中止填充（未写入文件）"
            self._exec["done"] = True
            self._exec["running"] = False
            with open(logf, 'a', encoding='utf-8') as _lf:
                ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                _lf.write(f"[{ts}] [exec_worker ERROR] TimeoutError\n")
        except Exception as e:
            traceback.print_exc()
            self._exec["error"] = str(e)
            self._exec["done"] = True
            self._exec["running"] = False
            with open(logf, 'a', encoding='utf-8') as _lf:
                ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                _lf.write(f"[{ts}] [exec_worker ERROR] {e}\n")

    def get_exec_status(self):
        """前端轮询：返回当前后台执行状态。"""
        return {
            "success": True,
            "running": self._exec["running"],
            "pct": self._exec["pct"],
            "msg": self._exec["msg"],
            "done": self._exec["done"],
            "aborted": self._exec["aborted"],
            "error": self._exec["error"],
            "result": self._exec["result"],
            "last_progress_ts": self._exec["last_progress_ts"],
        }

    def abort_fill(self):
        """置位停止事件，让后台填充线程在保存前中断（超时/取消共用）。"""
        self._stop_event.set()
        print("[INFO] abort_fill: 已请求中止后台填充")
        return {"success": True, "aborted": True}

    def open_output_folder(self, path=None):
        """打开结果文件所在文件夹（Windows）。"""
        try:
            if not path:
                path = self.state.get('last_output_path')
            if not path or not os.path.exists(path):
                return {"success": False, "error": "文件不存在或尚未生成"}
            folder = os.path.dirname(os.path.abspath(path))
            os.startfile(folder)
            return {"success": True, "folder": folder}
        except Exception as e:
            print(f"[ERROR] open_output_folder: {e}")
            return {"success": False, "error": str(e)}

    def open_output(self, path):
        """用系统关联程序打开已生成的填表结果文件（Windows）。"""
        import os
        try:
            os.startfile(path)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}


def get_window_size():
    """根据屏幕分辨率计算合适的窗口尺寸（不超过 85% 屏幕，最大 1200x800）。"""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        screensize = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        sw, sh = screensize
        target_w = min(1200, int(sw * 0.85))
        target_h = min(800, int(sh * 0.85))
        target_w = max(800, target_w)
        target_h = max(600, target_h)
        return target_w, target_h
    except Exception:
        return 1100, 750


def _native_msgbox(title, msg):
    """原生 Windows MessageBox — 零依赖，100% 可靠弹出。"""
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, title, 0x40 | 0x0)
    except Exception:
        pass


def _check_webview2():
    """检测系统是否已安装 Microsoft Edge WebView2 Runtime。"""
    import glob

    search_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\EdgeWebView\Application"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\EdgeWebView\Application"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\EdgeWebView\Application"),
    ]
    for base in search_paths:
        if not base or not os.path.isdir(base):
            continue
        try:
            if glob.glob(os.path.join(base, "*", "msedgewebview2.exe")):
                return True
        except Exception:
            continue

    reg_keys = [
        ("HKLM", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-968EE10D5E78}"),
        ("HKLM", r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-968EE10D5E78}"),
        ("HKCU", r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-968EE10D5E78}"),
    ]
    try:
        import winreg
        for hive_name, key_path in reg_keys:
            try:
                hive = winreg.HKEY_LOCAL_MACHINE if hive_name == "HKLM" else winreg.HKEY_CURRENT_USER
                key = winreg.OpenKey(hive, key_path)
                key.Close()
                return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def _show_webview2_dialog():
    _native_msgbox(
        "国企大表哥 — 需要 WebView2 运行时",
        "本软件需要 Microsoft Edge WebView2 Runtime 才能运行。\n\n"
        "安装步骤：\n"
        "1. 关闭所有 Edge 浏览器窗口\n"
        "2. 打开以下网址下载「Evergreen Bootstrapper」\n"
        "   https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/\n"
        "3. 安装完成后重新运行本软件\n\n"
        "提示：主流 Windows 10 / 11 通常已自带 WebView2，无需额外安装；Windows 7 / 8 需单独安装。\n"
        "如安装时提示「已运行相同 Edge 版本」,\n"
        "请在任务管理器结束所有 msedge 进程后重试。"
    )


def start_app():
    _log_path = os.path.join(tempfile.gettempdir(), "国企大表哥_startup.log")
    _log_fh = open(_log_path, "w", encoding="utf-8")
    def _log(msg):
        t = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        _log_fh.write(f"[{t}] {msg}\n")
        _log_fh.flush()
    _log("start_app BEGIN")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    _log(f"base_dir={base_dir}")
    html_path = os.path.join(base_dir, "ui", "index.html")
    _log(f"html_path exists={os.path.exists(html_path)}")

    runtime_dir = os.path.join(base_dir, "webview2_runtime")
    _log(f"runtime_dir={runtime_dir}, exists={os.path.isdir(runtime_dir)}")
    if os.path.isdir(runtime_dir):
        os.environ["WEBVIEW2_BROWSER_EXECUTABLE_FOLDER"] = runtime_dir
        _log(f"WEBVIEW2_BROWSER_EXECUTABLE_FOLDER set")
        print(f"[INFO] 使用自带 WebView2 运行时: {runtime_dir}")
    else:
        wv2_ok = _check_webview2()
        _log(f"WebView2 DLL check: {wv2_ok}")
        if not wv2_ok:
            _log("SHOWING DIALOG + EXIT")
            _show_webview2_dialog()
            sys.exit(1)

    if not os.path.exists(html_path):
        print(f"[FATAL] 找不到 UI 文件: {html_path}")
        sys.exit(1)

    print("[INFO] 国企大表哥 启动中...")
    print(f"[INFO] UI 路径: {html_path}")

    api = Api()
    w, h = get_window_size()
    print(f"[INFO] 窗口尺寸: {w}x{h}")

    try:
        _log("calling webview.create_window...")
        webview.create_window(
            title="国企大表哥",
            url=html_path,
            js_api=api,
            width=w,
            height=h,
            min_size=(800, 600),
            resizable=True,
        )
    except Exception as e:
        _log(f"create_window FAILED: {e}")
        print(f"[FATAL] 创建窗口失败: {e}")
        traceback.print_exc()
        sys.exit(1)

    _log("create_window OK, calling webview.start...")
    try:
        webview.start(debug=False)
        _log("webview.start returned normally")
    except Exception as e:
        _log(f"webview.start FAILED: {e}")
        traceback.print_exc()
        err_lower = str(e).lower()
        if any(k in err_lower for k in ("webview2", "edge", "runtime", "msedgewebview")):
            _show_webview2_dialog()
        sys.exit(1)


if __name__ == "__main__":
    start_app()
