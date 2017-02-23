# -*- coding: utf-8 -*-

"""A setuptools based setup module."""

from setuptools import setup

setup(
    name='dir-edit',
    version='1.1',
    description='Rename or remove files in a directory using an editor (e.g. vi)',
    author=u'Johannes Weißl',
    author_email='jargon@molb.org',
    url='http://github.com/weisslj/dir-edit',
    license='GNU GPL v3',
    classifiers=[
        'License :: OSI Approved :: GNU General Public License (GPL)',
        'Programming Language :: Python :: 2.7',
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
    test_suite='dir_edit_test',
)
