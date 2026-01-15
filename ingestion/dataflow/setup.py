"""
Setup file for Dataflow pipeline dependencies.

This file is used by Dataflow to install custom modules on workers.
"""

import setuptools

setuptools.setup(
    name='subway-pipeline',
    version='1.0.0',
    description='NYC Subway GTFS-RT ingestion pipeline',
    packages=setuptools.find_packages(),
    install_requires=[
        'apache-beam[gcp]>=2.50.0',
    ],
)
