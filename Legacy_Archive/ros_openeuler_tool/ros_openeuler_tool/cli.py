import click
from ros_openeuler_tool.clone_repos import clone_repositories
from ros_openeuler_tool.process_packages import process_ros_packages
from ros_openeuler_tool.batch_process import batch_process_packages
from ros_openeuler_tool.sync_gitee import sync_to_gitee
from ros_openeuler_tool.make_public import make_repos_public
from ros_openeuler_tool.map_yum_rosdep import map_yum_to_rosdep_yaml
from ros_openeuler_tool.update_yum_mapping import update_yum_and_mapping
from ros_openeuler_tool.analyze_dependencies import analyze_dependencies
from ros_openeuler_tool.list_missing import list_missing_packages
from ros_openeuler_tool.extract_unresolved_dependencies import main_extract_unresolved_dependencies


@click.group()
def cli():
    """ROS OpenEuler 移植与管理工具"""
    pass


@cli.command()
def clone_repos():
    """克隆所有 ROS Jazzy 仓库"""
    clone_repositories()


@cli.command()
def process_packages():
    """生成 RPM 规范文件并打包源码"""
    process_ros_packages()


@cli.command()
def batch_process():
    """批量处理 ROS 包，记录缺失依赖和跳过的包"""
    batch_process_packages()


@cli.command()
def sync_gitee():
    """将源码同步到 Gitee 仓库"""
    sync_to_gitee()


@cli.command()
def make_public():
    """将 Gitee 仓库设为公开"""
    make_repos_public()


@cli.command()
def map_yum_to_rosdep():
    """将 YUM 仓库映射到 rosdep 的 YAML 文件中"""
    map_yum_to_rosdep_yaml()


@cli.command()
def analyze_dependencies():
    """分析依赖关系并生成构建顺序"""
    analyze_dependencies()


@cli.command()
def list_missing():
    """列出缺失的包和依赖"""
    list_missing_packages()


@cli.command()
@click.option('--base-yaml-url', required=True, help='base.yaml 的远程 URL')
@click.option('--python-yaml-url', required=True, help='python.yaml 的远程 URL')
@click.option('--output-base-yaml', default='updated_base.yaml', help='更新后的 base.yaml 文件名')
@click.option('--output-python-yaml', default='updated_python.yaml', help='更新后的 python.yaml 文件名')
@click.option('--threads', default=10, help='并发线程数（默认：10）')
def update_rosdep_yaml(base_yaml_url, python_yaml_url, output_base_yaml, output_python_yaml, threads):
    """更新 base.yaml 和 python.yaml，自动添加 openeuler 条目（DNF / PIP 方式）"""
    main_update_rosdep_yaml(base_yaml_url, python_yaml_url, output_base_yaml, output_python_yaml, threads)


@cli.command()
@click.argument('input_file', type=click.Path(exists=True))
@click.option('--mapping-file', default='unresolved_dependencies_mapping.txt', help='映射文件的输出路径')
@click.option('--list-file', default='unresolved_dependencies_list.txt', help='清单文件的输出路径')
def extract_unresolved_dependencies(input_file, mapping_file, list_file):
    """
    提取未闭环依赖的 ROS Jazzy 包，并生成映射和清单文件。

    INPUT_FILE: 输入的 Excel 文件路径。
    """
    main_extract_unresolved_dependencies(input_file, mapping_file, list_file)


if __name__ == '__main__':
    cli()