# dir-edit

Rename or remove files in a directory using an editor (e.g. vi)

## Motivation

If you want to rename files in a directory, things get really cumbersome
if...

- the name modifications are not easily automatable (e.g. spelling mistakes)
- file names contain spaces / special characters (when using a shell)
- you have to rename a lot of files (when using a GUI)
- you would need to use temporary files (e.g. `mv a tmp ; mv b a ; mv tmp b`)
- ...

This script creates a temporary file, where every line is a filename in the
directory. Then an user-defined editor is started, enabling the user to
edit the names. After saving, the script checks the file for consistency
and detects rename loops or paths and finally performs the changes.


## Usage

    Usage: dir_edit [OPTION]... [DIR] [FILES]...
    
    Modify contents of DIR using an editor. Creates a temporary file, where every
    line is a filename in the directory DIR. Then an user-defined editor is
    started, enabling the user to edit the names. After saving, the script checks
    the file for consistency and detects rename loops or paths and finally
    performs the changes. If DIR is omitted, the current one is used.
    
    Options:
      --version             show program's version number and exit
      -h, --help            show this help message and exit
      -a, --all             include entries starting with . (besides . and ..)
      -d, --dry-run         don't do any file system modifications
      -e CMD, --editor=CMD  use CMD to edit dirfile (default: $EDITOR or vi)
      -i FILE, --input=FILE
                            FILE containing paths to be edited (FILES, -a, -m, -n
                            and -r ignored)
      -m, --mangle-newlines
                            replace newlines in files through blanks
      -n, --numeric-sort    sort entries according to string numerical value
      -R, --remove-recursive
                            remove non-empty directories recursively
      -r, --recursive       list DIR recursively
      -S, --safe            do not create or remove directories while renaming
      -v, --verbose         output filesystem modifications to stdout


## Examples

You don't trust this script (it could accidentally delete all your files):

    # don't actually perform any modifications
    dir_edit -vd ./music > LOG
    # check proposed changes
    view LOG
    # perform changes
    sh LOG

Rename all pictures with maximum directory depth 2:

    # create file list
    find pics -maxdepth 2 -type f -iregex ".*\.\(jpg\|png\)" > file_list
    dir_edit -i file_list

Rename all ogg files in current directory using gedit:

    dir_edit -e gedit . *.ogg
