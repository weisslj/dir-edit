#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law.

"""Rename or remove files in a directory using an editor (e.g. vi)."""

from __future__ import print_function
import sys
import os
import re
import tempfile
import locale
import subprocess
import argparse
from functools import total_ordering
from functools import reduce

if sys.version_info < (3, 2):
    os.fsencode = lambda filename: filename

SIMULATE = False
VERBOSE = False
TMPDIR = None

class Error(Exception):
    """Aborts program, used in test suite."""
    pass

##############################################################################
# Logging functions
#
def warn(msg, *args, **_kwargs):
    """Output a warning message to stderr."""
    prog_name = os.path.basename(sys.argv[0])
    msg = '%s: %s' % (prog_name, msg % args)
    if sys.version_info < (3, 0):
        msg = msg.decode(errors='replace')
    print(msg, file=sys.stderr)

def shellquote(string):
    """Return a quoted version of string suitable for a sh-like shell."""
    return "'" + string.replace("'", "'\\''") + "'"

def fslog(msg, *args, **_kwargs):
    """Output a shell command to stdout, quoting it's arguments."""
    if not VERBOSE:
        return
    msg = msg % tuple(shellquote(x) for x in args)
    if sys.version_info < (3, 0):
        msg = msg.decode(errors='replace')
    print(msg)
#
##############################################################################

@total_ordering
class Path(str):
    """Represent a path.

    This class can be used like a string path (os.path.*). As an extension,
    comparisions (or lookups) are refering to the real pathname, e.g.:

    Path('a/b/..//c') == Path('a/c')

    Public members:
    self.real -- the os.path.realname of the path
    self.head -- the dirname of the path
    self.tail -- the basename of the path
    """
    def __init__(self, string):
        self.rebuild(string)
    def rebuild(self, string):
        """Reinitialize object from string."""
        head, tail = os.path.split(string)
        if not tail:
            head, tail = os.path.split(head)
        self.string = string
        self.real = os.path.join(os.path.realpath(head), tail)
        self.head = head
        self.tail = tail
    def __eq__(self, other):
        if isinstance(other, Path):
            return self.real == other.real
        elif isinstance(other, str):
            return self == Path(other)
        else:
            return NotImplemented
    def __lt__(self, other):
        if isinstance(other, Path):
            return self.real < other.real
        elif isinstance(other, str):
            return self < Path(other)
        else:
            raise TypeError('unorderable types')
    def __hash__(self):
        return self.real.__hash__()


##############################################################################
# Wrapper functions for manipulation the file system
#
def dir_make_all(path):
    """Wrapper function for os.makedirs()."""
    fslog('mkdir -p %s', path)
    if SIMULATE:
        return
    os.makedirs(path)

def file_remove(path):
    """Wrapper function for os.remove()."""
    fslog('unlink %s', path)
    if SIMULATE:
        return
    os.remove(path)

def dir_remove(path):
    """Wrapper function for os.rmdir()."""
    fslog('rmdir %s', path)
    if SIMULATE:
        return
    os.rmdir(path)

def remove_recursive(top):
    """Recursive path removal."""
    fslog('rm -rf %s', top)
    if SIMULATE:
        return
    for root, dirs, files in os.walk(top, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    if os.path.isdir(top):
        os.rmdir(top)
    else:
        os.remove(top)

def path_remove(path, recursive=False):
    """Path removal, optionally recursive."""
    if os.path.isdir(path):
        subpaths = os.listdir(path)
        if recursive:
            for subpath in subpaths:
                remove_recursive(os.path.join(path, subpath))
            subpaths = []
        if subpaths:
            warn('not removing directory %s: not empty (try -R)', path)
        else:
            dir_remove(path)
    else:
        file_remove(path)

def path_rename(src, dst):
    """Rename src path to dst."""
    if os.path.exists(dst):
        warn('path %s already exists, skip', dst)
        return
    fslog('mv %s %s', src, dst)
    if SIMULATE:
        return
    os.rename(src, dst)

def path_least_common_ancestor(path1, path2):
    """Return least common ancestor of Path objects path1 and path2.
    e.g.
    path_least_common_ancestor(Path('a/b/c'), Path('a/b/d')) == '/.../a/b'
    """
    real1, real2 = path1.real, path2.real
    while real1 != real2:
        if len(real1) > len(real2):
            real1, real2 = real2, real1
        real2 = os.path.dirname(real2)
    return real1

def path_renames(src, dst):
    """Rename src to dst, possibly creating needed or removing unneeded
    directories. Also handles the case when moving a file to a subdirectory
    with the same name, e.g.:
    mv x x/new_x
    """
    if os.path.exists(dst):
        warn('path %s already exists, skip', dst)
        return
    if os.path.commonprefix([src.real, os.path.dirname(dst.real)]) == src.real:
        tmp_src = os.path.join(TMPDIR, 's_' + src.tail)
        path_rename(src, tmp_src)
        dir_make_all(dst.head)
        path_rename(tmp_src, dst)
        return
    if dst.head and not os.path.exists(dst.head):
        dir_make_all(dst.head)
    path_rename(src, dst)
    # FIXME: Restructure!
    lca = path_least_common_ancestor(src, dst)
    if src.head and src.tail and not os.path.isabs(src):
        head, tail = os.path.split(src.real)
        while head != lca:
            content = [tail] if SIMULATE else []
            if os.listdir(head) == content:
                dir_remove(head)
            else:
                break
            head, tail = os.path.split(head)
#
##############################################################################


# Wrapper functions for reversely renaming a list of files using reduce()
def rev_redux_rename(dst, src):
    """Rename src path to dst, without creating intermediate directories."""
    path_rename(src, dst)
    return src
def rev_redux_renames(dst, src):
    """Rename src path to dst, creating intermediate directories if needed."""
    path_renames(src, dst)
    return src

NUMKEY_REGEX = re.compile(r'(\s*[+-]?[0-9]+\.?[0-9]*\s*)(.*)')
def numkey(string):
    """Return a sort key that works for filenames like '23 - foo'."""
    match = NUMKEY_REGEX.match(string)
    if match:
        return float(match.group(1)), locale.strxfrm(match.group(2))
    return (0.0, locale.strxfrm(string))

def path_split_all(path):
    """Return a list of path elements, e.g. 'a/b/..//c' -> ['a', 'c']."""
    return os.path.normpath(path).split(os.sep)

def textkey_path(path):
    """Return a sort key for paths, respecting user locale setting."""
    return tuple(locale.strxfrm(s) for s in path_split_all(path))

def numkey_path(path):
    """Return a sort key that works for paths like '2/23 - foo'."""
    return tuple(numkey(s) for s in path_split_all(path))

def check_input_path(path):
    """Return true if path is a valid input path, false otherwise."""
    if not path or not os.path.exists(path):
        return False
    return True

def sanitize_file_list(lst):
    """Remove all invalid path elements from lst."""
    lst[:] = [f for f in lst if check_input_path(f)]

def read_input_file(filename):
    """Read a file containing a single path per line, return list of paths.
    Can throw exception IOError.
    """
    with open(filename, 'r') as stream:
        file_list = [line.rstrip('\n') for line in stream]
    return file_list

def read_dir(path, all_entries=False):
    """Return a list of paths in directory at path. If all_entries is not
    true, exclude all entries starting with a dot (.).
    """
    filenames = os.listdir(path)
    if not all_entries:
        return [filename for filename in filenames if not filename.startswith('.')]
    return filenames

def read_dir_recursive(path, all_entries=False):
    """Return a list of paths in directory at path (recursively). If
    all_entries is not true, exclude all entries starting with a dot (.).
    """
    paths = []
    for root, dirs, files in os.walk(path):
        for name in files:
            if all_entries or not name.startswith('.'):
                paths.append(os.path.normpath(os.path.join(root, name)))
        if root != path and not dirs and not files:
            paths.append(os.path.normpath(root))
        if not all_entries:
            dirs[:] = [name for name in dirs if not name.startswith('.')]
    return paths

def decompose_mapping(graph):
    """Decompose a mapping ('bijective' bipartite graph) into
    paths and cycles and returns them.

    Attention: Afterwards, graph will be empty!
    """
    paths = {}
    cycles = {}
    while graph:
        src, dst = graph.popitem()
        path = [src, dst]
        while dst in graph:
            dst = graph.pop(dst)
            path.append(dst)
        if src == path[-1]:
            cycles[src] = path
        else:
            paths[src] = path
    return paths, cycles


def dir_edit(args):
    """Main functionality."""

    global TMPDIR

    try:
        os.chdir(args.dir)
    except OSError as exc:
        raise Error('%s: %s' % (args.dir, exc.strerror))

    if args.input:
        try:
            file_list = read_input_file(args.input)
        except IOError as exc:
            raise Error('error reading input file: %s' % (exc.strerror,))
        sanitize_file_list(file_list)
    elif args.files:
        file_list = args.files
        sanitize_file_list(file_list)
    else:
        if not args.recursive:
            file_list = read_dir(os.curdir, args.all)
        else:
            file_list = read_dir_recursive(os.curdir, args.all)
        key = textkey_path if not args.numeric_sort else numkey_path
        file_list.sort(key=key)

    if not file_list:
        raise Error('no valid path given for renaming')

    if not args.mangle_newlines:
        for filename in file_list:
            if '\n' in filename or '\r' in filename:
                raise Error('file names with newlines are not supported, try -m!')

    TMPDIR = tempfile.mkdtemp(prefix='dir_edit-')
    if args.output:
        try:
            new_file_list = read_input_file(args.output)
        except IOError as exc:
            raise Error('error reading output file: %s' % (exc.strerror,))
    else:
        tmpfile = os.path.join(TMPDIR, 'file_list.txt')
        nl_r = re.compile(r'[\n\r]+')
        with open(tmpfile, 'wb') as stream:
            stream.write(b''.join([os.fsencode(nl_r.sub(' ', e)) + b'\n' for e in file_list]))

        if os.name == 'nt':
            # Windows opens default editor if text file is opened directly:
            command = [tmpfile]
            if args.editor:
                command = args.editor + ' ' + subprocess.list2cmdline(command)
        else:
            command = args.editor + ' ' + shellquote(tmpfile)
        retval = subprocess.call(command, shell=True)

        if retval != 0:
            raise Error('editor command failed: %s' % (command,))

        with open(tmpfile, 'r') as stream:
            new_file_list = [line.rstrip('\n') for line in stream]

    if len(file_list) != len(new_file_list):
        raise Error('new file list has different length than old')

    # generate mapping and inverse mapping from file lists
    mapping = {}
    inv_mapping = {}
    to_remove = []
    for srcfile, dstfile in zip(file_list, new_file_list):
        srcpath = Path(srcfile)
        dstpath = Path(dstfile)
        if srcpath in mapping:
            raise Error('error, two identical entries have different destination:\n'
                        '%s', '\n'.join(['%s -> %s' % (x, y) for x, y in
                                         [(inv_mapping[mapping[srcpath]], mapping[srcpath]),
                                          (srcpath, dstpath)]]))
        # empty lines indicate removal
        if not dstfile:
            to_remove.append(srcpath)
            continue
        if dstpath in inv_mapping:
            raise Error('error, two or more files have the same destination:\n'
                        '%s', '\n'.join(['%s -> %s' % (x, y) for x, y in
                                         [(inv_mapping[dstpath], mapping[inv_mapping[dstpath]]),
                                          (srcpath, dstpath)]]))
        # no self loops (need no renaming!)
        if srcpath == dstpath:
            continue
        mapping[srcpath] = dstpath
        inv_mapping[dstpath] = srcpath

    if mapping or to_remove:

        # log directory change
        fslog('cd %s', os.path.realpath(os.curdir))

        need_tmpdir = False
        for srcpath, dstpath in mapping.items():
            if srcpath.real == os.path.dirname(dstpath.real):
                need_tmpdir = True
                break

        paths, cycles = decompose_mapping(mapping)

        if not need_tmpdir and cycles:
            need_tmpdir = True

        if need_tmpdir:
            fslog('mkdir %s', TMPDIR)

        for srcpath in to_remove:
            path_remove(srcpath, args.remove_recursive)

        rename_func = rev_redux_rename if args.safe else rev_redux_renames

        for path in paths.values():
            reduce(rename_func, reversed(path))

        for cycle in cycles.values():
            tmppath = Path(os.path.join(TMPDIR, 'c_' + cycle[0].tail))
            path_rename(cycle[0], tmppath)
            cycle[0] = tmppath
            reduce(rename_func, reversed(cycle))

        if need_tmpdir:
            fslog('rmdir %s', TMPDIR)

    if not args.output:
        os.remove(tmpfile)
    os.rmdir(TMPDIR)

def main_throws(args=None):
    """Main function, throws exception on error."""

    global SIMULATE
    global VERBOSE

    locale.setlocale(locale.LC_ALL, '')

    usage = '%(prog)s [OPTION]... [DIR] [FILES]...'
    desc = '''\
Modify contents of DIR using an editor. Creates a temporary file, where every
line is a filename in the directory DIR. Then an editor is started, enabling
the user to rename or delete (blank line) entries. After saving, the script
performs a consistency check, detects rename loops / paths and finally executes
the changes.'''

    default_editor = 'vi'
    if os.name == 'nt':
        # Windows opens default editor if text file is opened directly:
        default_editor = ''
    default_editor = os.getenv('EDITOR', default_editor)

    parser = argparse.ArgumentParser(usage=usage, description=desc)

    parser.add_argument('dir', metavar='DIR', nargs='?', default=os.curdir,
                        help='directory to edit (default: current directory)')
    parser.add_argument('files', metavar='FILES', nargs='*',
                        help='limit to these filenames (relative to DIR)')
    parser.add_argument('--version', action='version', version='%(prog)s 1.1')
    parser.add_argument('-a', '--all', action='store_true', default=False,
                        help='include entries starting with . (besides . and ..)')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        default=False, help='don\'t do any file system modifications')
    parser.add_argument('-e', '--editor', metavar='CMD', default=default_editor,
                        help='use CMD to edit dirfile (default: $EDITOR or vi)')
    parser.add_argument('-i', '--input', metavar='FILE',
                        help=('FILE containing paths to be edited '
                              '(FILES, -a, -m, -n, and -r ignored)'))
    parser.add_argument('-o', '--output', metavar='FILE',
                        help='FILE containing paths after being edited (-e is ignored)')
    parser.add_argument('-m', '--mangle-newlines', action='store_true',
                        default=False, help='replace newlines in files through blanks')
    parser.add_argument('-n', '--numeric-sort', action='store_true',
                        default=False, help='sort entries according to string numerical value')
    parser.add_argument('-R', '--remove-recursive', action='store_true',
                        default=False, help='remove non-empty directories recursively')
    parser.add_argument('-r', '--recursive', action='store_true', default=False,
                        help='list DIR recursively')
    parser.add_argument('-S', '--safe', action='store_true',
                        default=False, help='do not create or remove directories while renaming')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='output filesystem modifications to stdout')

    args = parser.parse_args(args)

    VERBOSE = args.verbose
    SIMULATE = args.dry_run

    dir_edit(args)

def main(args=None):
    """Main function, exits program on error."""
    try:
        main_throws(args)
    except Error as exc:
        warn(str(exc))
        sys.exit(1)

if __name__ == '__main__':
    main()
