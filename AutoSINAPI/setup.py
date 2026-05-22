from setuptools import setup, find_packages

setup(
    name="autosinapi",
    # A versão agora é gerenciada pelo setuptools_scm
    packages=find_packages(where="."),
    package_dir={"": "."},
    install_requires=[
        'numpy',
        'openpyxl',
        'pandas',
        'requests',
        'setuptools',
        'sqlalchemy',
        'psycopg2-binary',  # Driver para PostgreSQL
        'tqdm',
        'typing',
        'pytest>=7.0.0',
        'pytest-mock>=3.10.0',
        'pytest-cov>=4.0.0',
    ],
    python_requires='>=3.8',  # Atualizado para versão mais moderna
    author="Lucas Antonio M. Pereira",
    author_email="contato@mundoaec.com",
    description="Toolkit para automação do SINAPI",
    long_description=open('README.md', encoding='utf-8').read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)