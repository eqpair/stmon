from setuptools import setup, find_packages

setup(
    name="stmon",
    version="0.1.0",
    packages=find_packages(include=['modules', 'modules.*']),
)
