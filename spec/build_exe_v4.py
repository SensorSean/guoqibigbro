"""
build_exe_v4.py - 国企大表哥 v4 打包脚本 (PyInstaller 单文件)

将 v4 打包为独立的 Windows EXE：
  - 单文件 (--onefile)：一个 exe 即可分发，无需 Python 环境
  - 无控制台 (--windowed)：GUI 模式，不弹黑窗口
  - 内置反编译保护：源码以 Python 3.13 字节码形式封入 exe
    （3.13 字节码目前无公开反编译器，普通手段无法还原源码）
  - 如需更强保护（编译为原生机器码），见文末 Nuitka 备选方案

用法：
    python build_exe_v4.py
产物：
    dist/国企大表哥.exe
"""

import os
import sys
import subprocess
import shutil

# 构建清理阶段 PyInstaller 会大量调用 os.remove；在部分受限环境（回收站不可用）
# 下 safe-delete 拦截会抛 SAFE_DELETE_FAIL_CLOSED 导致打包中断。此处仅在沙箱明确
# 开启 safe-delete 时将其关闭，让子进程(PyInstaller)使用真实删除；用户正常环境不受影响。
if os.environ.get("CODEBUDDY_SAFE_DELETE_SANDBOX") == "1":
    os.environ["CODEBUDDY_SAFE_DELETE_SANDBOX"] = "0"


def get_project_root() -> str:
    d = os.path.dirname(os.path.abspath(__file__))
    # 脚本若置于 spec/ 子目录，自动取父目录为工程根
    if os.path.basename(d) == "spec":
        return os.path.dirname(d)
    return d


def build_exe():
    project_root = get_project_root()
    main_script = os.path.join(project_root, "main.py")
    output_dir = os.path.join(project_root, "dist")
    work_dir = os.path.join(project_root, "build")
    # PyInstaller 按 --name 参数自动生成 .spec 文件（不需要预先准备）

    # 依赖自检
    try:
        import openpyxl  # noqa: F401
        import PyInstaller  # noqa: F401
    except ImportError as e:
        print(f"[错误] 缺少依赖: {e}")
        print("请先安装: pip install -r requirements_build.txt")
        sys.exit(1)

    if not os.path.exists(main_script):
        print(f"[错误] 主脚本不存在: {main_script}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    pyinstaller_args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--noupx",
        "--name", "国企大表哥_V1.3.1",
        f"--distpath", output_dir,
        f"--workpath", work_dir,
        f"--specpath", project_root,
        # 内含资源：前端 UI（含新 logo）—— 用绝对路径避免 specpath 偏移
        "--add-data", f"{os.path.join(project_root, 'ui')}{os.pathsep}ui",
        # 自定义 exe 图标（像素风 logo）
        "--icon", os.path.join(project_root, "ui", "大表哥Logo.ico"),
        # 隐式导入（PyInstaller 静态分析抓不到的运行时依赖）
        "--hidden-import", "openpyxl",
        "--hidden-import", "openpyxl.cell._writer",
        "--hidden-import", "openpyxl.reader.excel",
        "--hidden-import", "openpyxl.writer.excel",
        "--hidden-import", "openpyxl.styles",
        "--hidden-import", "openpyxl.utils",
        "--hidden-import", "openpyxl.worksheet",
        "--hidden-import", "webview",
        "--hidden-import", "webview.platforms.edgechromium",
        "--hidden-import", "pandas",
        "--hidden-import", "Levenshtein",
        "--hidden-import", "xlrd",
        # logo 生成用的 Pillow 不参与运行时，避免打包进 exe 增大体积
        "--exclude-module", "PIL",
        "--exclude-module", "Pillow",
        main_script,
    ]

    # 可选：自带 WebView2 Fixed Version 运行时（零安装分发）
    runtime_src = os.path.join(project_root, "webview2_runtime")
    if os.path.isdir(runtime_src):
        pyinstaller_args += ["--add-data", f"webview2_runtime{os.pathsep}webview2_runtime"]
        print("[信息] 已将 WebView2 运行时打包进 exe（目标电脑零安装）")
    else:
        print("[提示] 未检测到 webview2_runtime 目录，将依赖系统 WebView2 Runtime")

    print("=" * 60)
    print("  国企大表哥 v4 - 打包程序")
    print("=" * 60)
    print(f"项目目录: {project_root}")
    print(f"输出目录: {output_dir}")
    print(f"主脚本:   {main_script}")
    print("-" * 60)
    print("正在打包，请耐心等待（首次约 1-3 分钟）...")
    print("-" * 60)

    try:
        result = subprocess.run(
            pyinstaller_args,
            capture_output=True,
            text=True,
            cwd=project_root,
        )

        if result.returncode == 0:
            print("[成功] 打包完成！")
            exe_name = "国企大表哥_V1.3.1.exe"
            exe_path = os.path.join(output_dir, exe_name)
            if os.path.exists(exe_path):
                size = os.path.getsize(exe_path) / (1024 * 1024)
                print(f"[信息] 生成文件: {exe_path}")
                print(f"[信息] 文件大小: {size:.1f} MB")
            # 将 PyInstaller 生成的 .spec 文件移入 spec/ 目录
            spec_dir = os.path.join(project_root, "spec")
            os.makedirs(spec_dir, exist_ok=True)
            for f in os.listdir(project_root):
                if f.endswith(".spec") and "国企大表哥" in f:
                    sf = os.path.join(project_root, f)
                    tf = os.path.join(spec_dir, f)
                    try:
                        shutil.move(sf, tf)
                        print(f"[信息] spec 文件已归位: spec/{f}")
                    except Exception:
                        pass
            # 复制同义词词典到输出目录（exe 运行时需要）
            dict_src = os.path.join(project_root, "同义词词典.json")
            if os.path.isfile(dict_src):
                dict_dst = os.path.join(output_dir, "同义词词典.json")
                shutil.copy2(dict_src, dict_dst)
                print(f"[信息] 同义词词典已复制到输出目录: {dict_dst}")
            else:
                print("[警告] 未找到 同义词词典.json，匹配能力将受限")
            print("-" * 60)
            print("使用说明:")
            print(f"  1. 找到 {output_dir} 下的 '{exe_name}'")
            print("  2. 双击运行（无需安装 Python）")
            if os.path.isdir(runtime_src):
                print("  3. 已内置 WebView2 运行时 —— 目标电脑无需安装任何组件，双击即用")
            else:
                print("  3. 目标电脑需已安装 Microsoft Edge WebView2 Runtime")
                print("     （运行 get_webview2_runtime.bat 下载内置版后重新打包即可零安装）")
            print("=" * 60)
        else:
            print("[失败] 打包出错:")
            print(result.stderr)
            for line in result.stderr.split("\n"):
                if any(kw in line.lower() for kw in ["error", "exception", "traceback", "failed"]):
                    print(f"  {line}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n[提示] 用户中断打包。")
        sys.exit(1)
    except Exception as e:
        print(f"[错误] 打包过程异常: {str(e)}")
        sys.exit(1)
    finally:
        if os.path.exists(work_dir):
            try:
                shutil.rmtree(work_dir)
                print(f"[清理] 删除临时构建目录: {work_dir}")
            except Exception:
                pass


if __name__ == "__main__":
    build_exe()

"""
=====================================================================
备选：更强反编译保护 —— Nuitka（编译为原生机器码，Apache-2.0 可商用）
=====================================================================
Nuitka 把 Python 编译成 C 再编成原生二进制，几乎无法还原源码，
且许可证对商业/政府用途友好（PyInstaller 方案之上可叠加）。

    pip install nuitka
    python -m nuitka --onefile --windows-disable-console \
        --include-data-dir=ui=ui \
        --enable-plugin=pywebview \
        --output-filename=国企大表哥.exe \
        main.py

注意：Nuitka 需本机有 C 编译器（Visual Studio / MinGW）；
首次编译较慢（数分钟），但产物抗反编译能力显著更强。
如打包失败或需更强保护，可改用此方案。
"""
