# -*- coding: utf-8 -*-

"""A setuptools based setup module."""

from __future__ import unicode_literals
from setuptools import setup

setup(
    name='dir-edit',
    version='1.1',
    description='Rename or remove files in a directory using an editor (e.g. vi)',
    author='Johannes Weißl',
    author_email='jargon@molb.org',
    url='http://github.com/weisslj/dir-edit',
    license='GNU GPL v3',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Utilities',
    ],
    py_modules=[
        'dir_edit',
    ],
    entry_points={
        'console_scripts': [
            'dir_edit=dir_edit:main',
        ],
    },
    test_suite='test_dir_edit',
)
