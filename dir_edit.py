#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law.

"""Rename or remove files in a directory using an editor (e.g. vi)."""

import sys
import os
import re
import tempfile
import locale
import subprocess
from optparse import OptionParser

PROG_NAME = 'dir_edit'
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
    msg = '%s: %s' % (PROG_NAME, msg % args)
    print >> sys.stderr, msg

def error(msg, *args, **kwargs):
    """Output an error message to stderr and exit."""
    warn(msg, *args, **kwargs)
    raise Error(msg % args)

def shellquote(string):
    """Return a quoted version of string suitable for a sh-like shell."""
    return "'" + string.replace("'", "'\\''") + "'"

def fslog(msg, *args, **_kwargs):
    """Output a shell command to stdout, quoting it's arguments."""
    if not VERBOSE:
        return
    msg = msg % tuple(shellquote(x) for x in args)
    print msg
#
##############################################################################

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
        super(Path, self).__init__(string)
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
        if isinstance(other, str):
            return self.string == other
        return self.real == other.real
    def __ne__(self, other):
        if isinstance(other, str):
            return self.string != other
        return self.real != other.real
    def __lt__(self, other):
        if isinstance(other, str):
            return self.string < other
        return self.real < other.real
    def __le__(self, other):
        if isinstance(other, str):
            return self.string <= other
        return self.real <= other.real
    def __gt__(self, other):
        if isinstance(other, str):
            return self.string > other
        return self.real > other.real
    def __ge__(self, other):
        if isinstance(other, str):
            return self.string >= other
        return self.real >= other.real
    def __cmp__(self, other):
        if isinstance(other, str):
            return self.string.__cmp__(other)
        return self.real.__cmp__(other.real)
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


def dir_edit(dirname, filenames, options):
    """Main functionality."""

    global TMPDIR

    try:
        os.chdir(dirname)
    except OSError as exc:
        error('%s: %s', dirname, exc.strerror)

    if options.input:
        try:
            file_list = read_input_file(options.input)
        except IOError as exc:
            error('error reading input file: %s', exc.strerror)
        sanitize_file_list(file_list)
    elif filenames:
        file_list = filenames
        sanitize_file_list(file_list)
    else:
        if not options.recursive:
            file_list = read_dir(os.curdir, options.all)
        else:
            file_list = read_dir_recursive(os.curdir, options.all)
        key = textkey_path if not options.numeric_sort else numkey_path
        file_list.sort(key=key)

    if not file_list:
        error('no valid path given for renaming')

    if not options.mangle_newlines:
        for filename in file_list:
            if '\n' in filename or '\r' in filename:
                error('file names with newlines are not supported, try -m!')

    TMPDIR = tempfile.mkdtemp(prefix='dir_edit-')
    if options.output:
        try:
            new_file_list = read_input_file(options.output)
        except IOError as exc:
            error('error reading output file: %s', exc.strerror)
    else:
        tmpfile = os.path.join(TMPDIR, 'file_list.txt')
        nl_r = re.compile(r'[\n\r]+')
        with open(tmpfile, 'w') as stream:
            stream.write(''.join([nl_r.sub(' ', e) + '\n' for e in file_list]))

        if os.name == 'nt':
            # Windows opens default editor if text file is opened directly:
            command = [tmpfile]
            if options.editor:
                command = options.editor + ' ' + subprocess.list2cmdline(command)
        else:
            command = options.editor + ' ' + shellquote(tmpfile)
        retval = subprocess.call(command, shell=True)

        if retval != 0:
            error('editor command failed: %s', command)

        with open(tmpfile, 'r') as stream:
            new_file_list = [line.rstrip('\n') for line in stream]

    if len(file_list) != len(new_file_list):
        error('new file list has different length than old')

    # generate mapping and inverse mapping from file lists
    mapping = {}
    inv_mapping = {}
    to_remove = []
    for srcfile, dstfile in zip(file_list, new_file_list):
        srcpath = Path(srcfile)
        dstpath = Path(dstfile)
        if srcpath in mapping:
            error('error, two identical entries have different destination:\n'
                  '%s', '\n'.join(['%s -> %s' % (x, y) for x, y in
                                   [(inv_mapping[mapping[srcpath]], mapping[srcpath]),
                                    (srcpath, dstpath)]]))
        # empty lines indicate removal
        if not dstfile:
            to_remove.append(srcpath)
            continue
        if dstpath in inv_mapping:
            error('error, two or more files have the same destination:\n'
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
        for srcpath, dstpath in mapping.iteritems():
            if srcpath.real == os.path.dirname(dstpath.real):
                need_tmpdir = True
                break

        paths, cycles = decompose_mapping(mapping)

        if not need_tmpdir and cycles:
            need_tmpdir = True

        if need_tmpdir:
            fslog('mkdir %s', TMPDIR)

        for srcpath in to_remove:
            path_remove(srcpath, options.remove_recursive)

        rename_func = rev_redux_rename if options.safe else rev_redux_renames

        for path in paths.values():
            reduce(rename_func, reversed(path))

        for cycle in cycles.values():
            tmppath = Path(os.path.join(TMPDIR, 'c_' + cycle[0].tail))
            path_rename(cycle[0], tmppath)
            cycle[0] = tmppath
            reduce(rename_func, reversed(cycle))

        if need_tmpdir:
            fslog('rmdir %s', TMPDIR)

    if not options.output:
        os.remove(tmpfile)
    os.rmdir(TMPDIR)

def main_throws(args=None):
    """Main function, throws exception on error."""

    global PROG_NAME
    global SIMULATE
    global VERBOSE

    locale.setlocale(locale.LC_ALL, '')

    usage = 'Usage: %prog [OPTION]... [DIR] [FILES]...'
    version = '%prog 1.1\nCopyright (C) 2010 Johannes Weißl\n'\
        'License GPLv3+: GNU GPL version 3 or later '\
        '<http://gnu.org/licenses/gpl.html>.\n'\
        'This is free software: you are free to change and redistribute it.\n'\
        'There is NO WARRANTY, to the extent permitted by law.'
    desc = '''\
Modify contents of DIR using an editor. Creates a temporary file, where
every line is a filename in the directory DIR. Then an user-defined
editor is started, enabling the user to edit the
names. After saving, the script checks the file for consistency and
detects rename loops or paths and finally performs the changes. If DIR
is omitted, the current one is used.'''

    default_editor = 'vi'
    if os.name == 'nt':
        # Windows opens default editor if text file is opened directly:
        default_editor = ''
    editor = os.getenv('EDITOR', default_editor)

    parser = OptionParser(usage=usage, version=version, description=desc)

    parser.add_option('-a', '--all', action='store_true', default=False,
                      help='include entries starting with . (besides . and ..)')
    parser.add_option('-d', '--dry-run', action='store_true',
                      default=False, help='don\'t do any file system modifications')
    parser.add_option('-e', '--editor', metavar='CMD',
                      help='use CMD to edit dirfile (default: $EDITOR or vi)')
    parser.add_option('-i', '--input', metavar='FILE',
                      help='FILE containing paths to be edited (FILES, -a, -m, -n and -r ignored)')
    parser.add_option('-o', '--output', metavar='FILE',
                      help='FILE containing paths after being edited (-e is ignored)')
    parser.add_option('-m', '--mangle-newlines', action='store_true',
                      default=False, help='replace newlines in files through blanks')
    parser.add_option('-n', '--numeric-sort', action='store_true',
                      default=False, help='sort entries according to string numerical value')
    parser.add_option('-R', '--remove-recursive', action='store_true',
                      default=False, help='remove non-empty directories recursively')
    parser.add_option('-r', '--recursive', action='store_true', default=False,
                      help='list DIR recursively')
    parser.add_option('-S', '--safe', action='store_true',
                      default=False, help='do not create or remove directories while renaming')
    parser.add_option('-v', '--verbose', action='store_true', default=False,
                      help='output filesystem modifications to stdout')

    (options, args) = parser.parse_args(args)
    PROG_NAME = parser.get_prog_name()

    VERBOSE = options.verbose
    SIMULATE = options.dry_run
    if options.editor is None:
        options.editor = editor

    dirname = args[0] if args else os.curdir
    filenames = args[1:]

    dir_edit(dirname, filenames, options)

def main(args=None):
    """Main function, exits program on error."""

    try:
        main_throws(args)
    except Error:
        sys.exit(1)

if __name__ == '__main__':
    main()
