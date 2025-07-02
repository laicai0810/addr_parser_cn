from setuptools import setup, find_packages

# 读取README.md作为长描述
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='addr_parser_cn',
    version='1.0.0',
    author='ysx',
    author_email='ysx_explorer@163.com',
    description='一个功能强大的中文地址解析与地理编码API包',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/laicai0810/addr_parser_cn', # 请替换为您的项目URL
    packages=find_packages(),
    # 核心：确保data/目录被包含在包中，但初始为空
    # 数据库文件将在首次使用时自动生成
    package_data={
        'addr_parser_cn': ['data/*'],
    },
    include_package_data=True,
    install_requires=[
        'pandas',
        'requests',
        'tqdm',
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.7',
)