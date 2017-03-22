# -*- coding: utf-8 -*-

"""A setuptools based setup module."""

from __future__ import unicode_literals
from os import path
from setuptools import setup

# Get the long description from the README file
HERE = path.abspath(path.dirname(__file__))
with open(path.join(HERE, 'README.rst'), encoding='utf-8') as stream:
    LONG_DESCRIPTION = stream.read()

setup(
    name='dir-edit',
    version='1.1',
    description='Rename or remove files in a directory using an editor (e.g. vi)',
    long_description=LONG_DESCRIPTION,
    author='Johannes Weißl',
    author_email='jargon@molb.org',
    url='http://github.com/weisslj/dir-edit',
    license='GPLv3+',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)',
        'Development Status :: 5 - Production/Stable',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Operating System :: POSIX',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Utilities',
    ],
    keywords='renamer tool editor',
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
