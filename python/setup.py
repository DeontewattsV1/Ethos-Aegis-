"""Compatibility shim for setuptools.

The sole source of Python distribution metadata (name, version, dependencies,
supported Python versions, console scripts and package discovery) is
`python/pyproject.toml`. Do not duplicate or override it here.
"""

from setuptools import setup

setup()
