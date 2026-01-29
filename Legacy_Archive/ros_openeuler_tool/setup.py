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
            'rot=ros_openeuler_tool.cli:cli'
        ]
    },
)
