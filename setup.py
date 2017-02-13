#!/usr/bin/env python
# -*- coding: utf-8 -*-

from distutils.core import setup

setup(name='dir-edit',
      version='1.1',
      description='Rename or remove files in a directory using an editor (e.g. vi)',
      author=u'Johannes Weißl',
      author_email='jargon@molb.org',
      url='http://github.com/weisslj/dir-edit',
      license='GNU GPL v3',
      classifiers=[
          'License :: OSI Approved :: GNU General Public License (GPL)',
          'Programming Language :: Python :: 2.5',
          'Topic :: Utilities',
      ],
      scripts=['dir_edit'])
