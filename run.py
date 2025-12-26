#!/usr/bin/env python
"""
运行脚本

用于运行主程序，自动设置Python路径
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入并运行主程序
from src.cli.main import main

if __name__ == '__main__':
    main()

