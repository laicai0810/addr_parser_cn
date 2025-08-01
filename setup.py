from setuptools import setup, find_packages

# 读取README.md作为长描述
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name='addr_parser_cn',
    version='1.1.0',
    author='ysx',
    author_email='ysx_explorer@163.com',
    description='一个功能强大的中文地址解析与地理编码Python包',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/yourusername/addr_parser_cn',
    packages=find_packages(),
    package_data={
        'addr_parser_cn': ['data/.gitkeep'],  # 确保data目录被创建
    },
    include_package_data=True,
    install_requires=[
        'pandas>=1.0.0',
        'requests>=2.20.0',
        'tqdm>=4.50.0',
        'numpy>=1.18.0',
    ],
    extras_require={
        'dev': [
            'pytest>=6.0',
            'pytest-cov>=2.0',
            'black>=21.0',
            'flake8>=3.8',
            'sphinx>=3.0',
        ],
    },
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Text Processing :: Linguistic',
        'Topic :: Scientific/Engineering :: GIS',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Operating System :: OS Independent',
        'Natural Language :: Chinese (Simplified)',
    ],
    python_requires='>=3.7',
    keywords='chinese address parser geocoding china administrative-divisions 中文地址 地址解析 地理编码 行政区划',
    project_urls={
        'Bug Reports': 'https://github.com/yourusername/addr_parser_cn/issues',
        'Source': 'https://github.com/yourusername/addr_parser_cn',
        'Documentation': 'https://github.com/yourusername/addr_parser_cn#readme',
    },
)
