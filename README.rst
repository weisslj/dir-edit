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