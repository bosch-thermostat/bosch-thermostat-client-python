#!/usr/bin/env python
# -*- coding:utf-8 -*-
from setuptools import setup, find_packages

with open("bosch_thermostat_client/version.py") as f:
    exec(f.read())


with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="bosch-thermostat-client",
    version=__version__,  # type: ignore # noqa: F821,
    description="Python API for talking to Bosch™ Heating gateway using HTTP or XMPP",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Pawel Szafer",
    author_email="pszafer@gmail.com",
    url="https://github.com/bosch-thermostat/bosch-thermostat-client-python",
    download_url="https://github.com/bosch-thermostat/bosch-thermostat-client-python/archive/{}.zip".format(
        __version__
    ),
    packages=find_packages(exclude=["tests*"]),
    install_requires=[
        "aioxmpp>=0.13.3",
        "aiohttp",
        "click>=8",
        "colorlog",
        "pyaes>=1.6.1",
    ],
    include_package_data=True,
    license="Apache License 2.0",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: End Users/Desktop",
        "Environment :: Console",
        "Topic :: Other/Nonlisted Topic",
        "Topic :: Utilities",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
    ],
    entry_points={
        "console_scripts": [
            "bosch_cli=bosch_thermostat_client.bosch_cli:cli",
            "bosch_examples=bosch_thermostat_client.bosch_examples:cli",
        ]
    },
)
