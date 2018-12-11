from setuptools import setup

setup(
    name="django-pythia",
    version="0.2.4",
    description="Pythia scans your django project for potentially tainted flows of data",
    author="Linos Giannopoulos",
    author_email="linosgian00@gmail.com",
    license="MIT",
    packages=["pythia"],
    install_requires=[
        'Django<=1.11.18,>=1.8.0',
    ],
    entry_points={'console_scripts': [
        'pythia = pythia:main',
    ]}
)
