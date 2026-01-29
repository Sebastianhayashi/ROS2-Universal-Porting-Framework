# ros_openeuler_tool/__init__.py

# 导入核心功能模块
from .clone_repos import clone_repositories
from .process_packages import process_ros_packages
from .batch_process import batch_process_packages
from .sync_gitee import sync_to_gitee
from .make_public import make_repos_public
from .map_yum_rosdep import map_yum_to_rosdep_yaml
from .update_yum_mapping import update_yum_and_mapping
from .analyze_dependencies import analyze_dependencies
from .list_missing import list_missing_packages
from .extract_unresolved_dependencies import main_extract_unresolved_dependencies  

# 定义工具版本
__version__ = "1.0.0"

# 声明所有可导出的功能（可选，方便 IDE 提示）
__all__ = [
    "clone_repositories",
    "process_ros_packages",
    "batch_process_packages",
    "sync_to_gitee",
    "make_repos_public",
    "map_yum_to_rosdep_yaml",
    "update_yum_and_mapping",
    "analyze_dependencies",
    "list_missing_packages",
    "main_extract_unresolved_dependencies"
]