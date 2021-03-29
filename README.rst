dir-edit
========

Rename or remove files in a directory using an editor.

Motivation
----------

If you want to rename files in a directory, things get really cumbersome if:

- the name modifications are not easily automatable (e.g. spelling mistakes)
- file names contain spaces / special characters (when using a shell)
- you have to rename a lot of files (when using a GUI)
- you would need to use temporary files (e.g. ``mv a tmp ; mv b a ; mv tmp b``)
- etc.

This script launches a used-defined text editor with a temporary file, where
every line is a filename in the directory. This enables the user to rename
(edit a line) or delete (blank line) entries. After saving and exiting the
editor, the script checks the file for consistency, detects rename loops and
finally performs the changes.

News
----

=====  ==========  ==================================================================
3.0.0  2021-03-29  Require Python 3.6 (no new features, just usage of "try ... from")
2.1.0  2017-05-01  Support renaming of intermediate dirs in recursive mode,
                   drop ``--safe`` mode, small bugfixes
2.0.0  2017-03-22  Bugfixes, Python 3 support, ``-o`` and ``-L`` option,
                   extensive test suite
1.1    2010-11-21  Bugfixes
1.0    2010-05-06  First working version
=====  ==========  ==================================================================

Examples
--------

Rename non-hidden files in the current directory::

  dir_edit

Rename mp3 files in the music directory using gedit::

  dir_edit -e gedit ~/Music ~/Music/*.mp3

Review changes before executing them::

  dir_edit -vd -L log.txt
  view log.txt
  sh -e log.txt

Rename pictures with maximum directory depth 2::

  find pics -maxdepth 2 -type f -iregex ".*\.\(jpg\|png\)" > file_list
  dir_edit -i file_list

Usage
-----

::

  dir_edit [OPTION]... [DIR] [FILES]...

    DIR        directory to edit (default: current directory)
    FILES      limit to these filenames (default: all non-hidden in directory)

  Some options:

    -e CMD, --editor=CMD       use CMD to edit dirfile (default: $EDITOR or vi)
    -d, --dry-run              don't perform any file system modifications
    -v, --verbose              output filesystem modifications to stdout
    -L FILE, --logfile FILE    path to logfile for verbose mode (default: stdout)
    -i FILE, --input FILE      FILE containing paths to be edited

Copyright
=========

| Copyright (C) 2010-2021 Johannes Weißl
| License GPLv3+:
| GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
| This is free software: you are free to change and redistribute it.
| There is NO WARRANTY, to the extent permitted by law.
