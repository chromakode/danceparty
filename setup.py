#!/usr/bin/env python
from setuptools import setup, find_packages

setup(name='danceparty',
    description='An animated gif dance club.',
    version='0.1',
    author='Max Goodman',
    author_email='c@chromakode.com',
    keywords='dance gifs',
    license='BSD',
    classifiers=[
        "Programming Language :: Python",
        "Topic :: Internet :: WWW/HTTP",
    ],
    packages=find_packages(),
    install_requires=[
        'Flask',
    ],
    include_package_data=True,
    zip_safe=False,
)
