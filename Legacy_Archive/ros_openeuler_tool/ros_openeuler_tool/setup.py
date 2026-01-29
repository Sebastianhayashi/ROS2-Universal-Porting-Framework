from setuptools import setup, find_packages

setup(
    name='ros_openeuler_tool',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'click',
        'requests',
        'beautifulsoup4',
        'PyYAML',
        'networkx'
    ],
    entry_points={
        'console_scripts': [
            'ros_openeuler_tool=ros_openeuler_tool.cli:cli',  # 原始命令
            'rtool=ros_openeuler_tool.cli:cli',               # 新增简短命令
            'rot=ros_openeuler_tool.cli:cli'                  # 另一个简短命令
        ],
    },
    author='Your Name',
    description='ROS Jazzy 移植与管理工具',
    url='https://github.com/yourusername/ros_openeuler_tool',
)
