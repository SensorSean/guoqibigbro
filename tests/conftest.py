"""pytest 公共夹具：把工程根目录加入 sys.path，保证 `import core.*` 可用。

项目此前没有 tests 目录，本文件为新增测试套件提供最小导入环境，
不修改任何被测代码。
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
