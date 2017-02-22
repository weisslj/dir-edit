#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>.
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law.

import sys
import os
import re
import tempfile
import locale
import subprocess
from optparse import OptionParser

class Error(Exception):
    pass

##############################################################################
# Logging functions
#
def warn(msg, *args, **kwargs):
    '''Output a warning message to stderr.'''
    msg = u'%s: %s' % (prog_name, msg % args)
    if type(msg) == unicode:
        pref_enc = locale.getpreferredencoding()
        msg = msg.encode(pref_enc)
    print >> sys.stderr, msg

def error(msg, *args, **kwargs):
    '''Output an error message to stderr and exit.'''
    warn(msg, *args, **kwargs)
    raise Error(msg % args)

def shellquote(s):
    '''Return a quoted version of s suitable for a sh-like shell.'''
    return "'" + s.replace("'", "'\\''") + "'"

def fslog(msg, *args, **kwargs):
    '''Output a shell command to stdout, quoting it's arguments.'''
    if not verbose:
        return
    msg = msg % tuple(shellquote(x) for x in args)
    print msg
#
##############################################################################

class Path(str):
    '''Represent a path.

    This class can be used like a string path (os.path.*). As an extension,
    comparisions (or lookups) are refering to the real pathname, e.g.:

    Path('a/b/..//c') == Path('a/c')

    Public members:
    self.real -- the os.path.realname of the path
    self.head -- the dirname of the path
    self.tail -- the basename of the path
    '''
    def __init__(self, s):
        self.rebuild(s)
    def rebuild(self, s):
        head, tail = os.path.split(s)
        if not tail:
            head, tail = os.path.split(head)
        self.str = s
        self.real = os.path.join(os.path.realpath(head), tail)
        self.head = head
        self.tail = tail
    def __eq__(self, other):
        if type(other) == str:
            return self.str == other
        return self.real == other.real
    def __ne__(self, other):
        if type(other) == str:
            return self.str != other
        return self.real != other.real
    def __lt__(self, other):
        if type(other) == str:
            return self.str <  other
        return self.real <  other.real
    def __le__(self, other):
        if type(other) == str:
            return self.str <= other
        return self.real <= other.real
    def __gt__(self, other):
        if type(other) == str:
            return self.str >  other
        return self.real >  other.real
    def __ge__(self, other):
        if type(other) == str:
            return self.str >= other
        return self.real >= other.real
    def __cmp__(self, other):
        if type(other) == str:
            return self.str.__cmd__(other)
        return self.real.__cmd__(other.real)
    def __hash__(self):
        return self.real.__hash__()


##############################################################################
# Wrapper functions for manipulation the file system
#
def dir_make_all(path):
    fslog('mkdir -p %s', path)
    if simulate:
        return
    os.makedirs(path)

def file_remove(path):
    fslog('unlink %s', path)
    if simulate:
        return
    os.remove(path)

def dir_remove(path):
    fslog('rmdir %s', path)
    if simulate:
        return
    os.rmdir(path)

def remove_recursive(top):
    fslog('rm -rf %s', top)
    if simulate:
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
    if os.path.isdir(path):
        lst = os.listdir(path)
        if recursive:
            for l in lst:
                remove_recursive(os.path.join(path,l))
            lst = []
        if lst:
            warn('not removing directory %s: not empty (try -R)', path)
        else:
            dir_remove(path)
    else:
        file_remove(path)

def path_rename(src, dst):
    if os.path.exists(dst):
        warn('path %s already exists, skip', dst)
        return
    fslog('mv %s %s', src, dst)
    if simulate:
        return
    os.rename(src, dst)

def path_least_common_ancestor(p1, p2):
    '''Return least common ancestor of Path objects p1 and p2.
    e.g.
    path_least_common_ancestor(Path('a/b/c'), Path('a/b/d')) == '/.../a/b'
    '''
    r1, r2 = p1.real, p2.real
    while r1 != r2:
        if len(r1) > len(r2):
            r1, r2 = r2, r1
        r2 = os.path.dirname(r2)
    return r1

def path_renames(src, dst):
    '''Rename src to dst, possibly creating needed or removing unneeded
    directories. Also handles the case when moving a file to a subdirectory
    with the same name, e.g.:
    mv x x/new_x
    '''
    if os.path.exists(dst):
        warn('path %s already exists, skip', dst)
        return
    if src.real == os.path.dirname(dst.real):
        tmp_src = os.path.join(tmpdir, 's_' + src.tail)
        path_rename(src, tmp_src)
        dir_make_all(dst.head)
        path_rename(tmp_src, dst)
        return
    if dst.head and not os.path.exists(dst.head):
        dir_make_all(dst.head)
    path_rename(src, dst)
    lca = path_least_common_ancestor(src, dst)
    if src.head and src.tail:
        dir, old = os.path.split(src.real)
        while dir != lca:
            if os.listdir(dir) == [old]:
                dir_remove(dir)
            dir, old = os.path.split(dir)
#
##############################################################################


# Wrapper functions for reversely renaming a list of files using reduce()
def rev_redux_rename(a, b):
    path_rename(b, a)
    return b
def rev_redux_renames(a, b):
    path_renames(b, a)
    return b

numkey_regex = re.compile('(\s*[+-]?[0-9]+\.?[0-9]*\s*)(.*)')
def numkey(s):
    m = numkey_regex.match(s)
    if m:
        return float(m.group(1)), locale.strxfrm(m.group(2))
    return (0.0, locale.strxfrm(s))

def path_split_all(path):
    '''Return a list of path elements, e.g. 'a/b/..//c' -> ['a', 'c'].'''
    return os.path.normpath(path).split(os.sep)

def textkey_path(path):
    return tuple(locale.strxfrm(s) for s in path_split_all(path))

def numkey_path(path):
    return tuple(numkey(s) for s in path_split_all(path))

def check_input_path(p):
    '''Return true if p is a valid input path, false otherwise.'''
    if not p or not os.path.exists(p):
        return False
    return True

def sanitize_file_list(lst):
    '''Remove all invalid path elements from lst.'''
    lst[:] = [f for f in lst if check_input_path(f)]

def read_input_file(filename):
    '''Read a file containing a single path per line, return list of paths.
    Can throw exception IOError.
    '''
    f = open(filename, 'r')
    file_list = [l.rstrip('\n') for l in f]
    f.close()
    return file_list

def read_dir(path, all_entries=False):
    '''Return a list of paths in directory at path. If all_entries is not
    true, exclude all entries starting with a dot (.).
    '''
    if not os.path.exists(path):
        return []
    lst = os.listdir(path)
    if not all_entries:
        lst[:] = [f for f in lst if not f.startswith('.')]
    return lst

def read_dir_recursive(path, all_entries=False):
    '''Return a list of paths in directory at path (recursively). If
    all_entries is not true, exclude all entries starting with a dot (.).
    '''
    lst = []
    for root, dirs, files in os.walk(path):
        for d in dirs:
            d_full = os.path.join(root, d)
            if os.listdir(d_full) != []:
                continue
            if all_entries or not d.startswith('.'):
                lst.append(os.path.normpath(d_full))
        for f in files:
            if all_entries or not f.startswith('.'):
                lst.append(os.path.normpath(os.path.join(root, f)))
    return lst

def decompose_mapping(graph):
    '''Decompose a mapping ('bijective' bipartite graph) into
    paths and cycles and returns them.

    Attention: Afterwards, graph will be empty!
    '''
    paths = {}
    cycles = {}
    while graph:
        a, b = graph.popitem()
        path = [a, b]
        while b in graph:
            b = graph.pop(b)
            path.append(b)
        if a == path[-1]:
            cycles[a] = path
        else:
            paths[a] = path
    return paths, cycles


def main(args=None):
    '''Main function.'''

    global prog_name
    global simulate
    global verbose
    global tmpdir

    locale.setlocale(locale.LC_ALL, '')

    usage = 'Usage: %prog [OPTION]... [DIR] [FILES]...'
    version = '%prog 1.0\nCopyright (C) 2010 Johannes Weißl\n'\
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

    if os.name == 'nt':
        default_editor = 'notepad'
    else:
        default_editor = 'vi'
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
    prog_name = parser.get_prog_name()

    verbose = options.verbose
    simulate = options.dry_run
    if options.editor:
        editor = options.editor

    dir = args[0] if args else os.curdir
    files = args[1:]

    if not os.path.exists(dir):
        error('error, directory `%s\' doesn\'t exist', dir)

    if not os.path.isdir(dir):
        error('error, `%s\' is no directory', dir)

    os.chdir(dir)
    if options.input:
        try:
            file_list = read_input_file(options.input)
        except IOError, (errno, strerror):
            error('error reading input file: %s', strerror)
        sanitize_file_list(file_list)
    elif files:
        file_list = files
        sanitize_file_list(file_list)
    else:
        if not options.recursive:
            file_list = read_dir(dir, options.all)
        else:
            file_list = read_dir_recursive(dir, options.all)
        key = textkey_path if not options.numeric_sort else numkey_path
        file_list.sort(key=key)

    if not file_list:
        error('no valid path given for renaming')

    if not options.mangle_newlines:
        for f in file_list:
            if '\n' in f or '\r' in f:
                error('file names with newlines are not supported, try -m!')

    tmpdir = tempfile.mkdtemp(prefix='dir_edit-')

    if options.output:
        try:
            new_file_list = read_input_file(options.output)
        except IOError, (errno, strerror):
            error('error reading output file: %s', strerror)
    else:
        tmpfile = os.path.join(tmpdir, 'file_list')
        nl_r = re.compile(r'[\n\r]+')
        f = open(tmpfile, 'w')
        f.write(''.join([nl_r.sub(' ', e) + '\n' for e in file_list]))
        f.close()

        command = editor + ' ' + shellquote(tmpfile)
        retval = subprocess.call(command, shell=True)

        if retval != 0:
            error('editor command failed: %s', command)

        f = open(tmpfile, 'r')
        new_file_list = [l.rstrip('\n') for l in f]
        f.close()

    if len(file_list) != len(new_file_list):
        error('new file list has different length than old')

    # generate mapping and inverse mapping from file lists
    mapping = {}
    inv_mapping = {}
    to_remove = []
    for a, b in zip(file_list, new_file_list):
        p1 = Path(a)
        p2 = Path(b)
        if p1 in mapping:
            error('error, two identical entries have different destination:\n'
                  '%s', '\n'.join(['%s -> %s' % (x,y) for x,y in
                  [(inv_mapping[mapping[p1]],mapping[p1]), (p1,p2)]]))
        # empty lines indicate removal
        if not b:
            to_remove.append(p1)
            continue
        if p2 in inv_mapping:
            error('error, two or more files have the same destination:\n'
                  '%s', '\n'.join(['%s -> %s' % (x,y) for x,y in
                  [(inv_mapping[p2],mapping[inv_mapping[p2]]), (p1,p2)]]))
        # no self loops (need no renaming!)
        if p1 == p2:
            continue
        mapping[p1] = p2
        inv_mapping[p2] = p1

    if mapping or to_remove:

        # log directory change
        fslog('chdir %s', os.path.realpath(dir))

        need_tmpdir = False
        for x in mapping:
            if x.real == os.path.dirname(mapping[x].real):
                need_tmpdir = True
                break

        paths, cycles = decompose_mapping(mapping)

        if not need_tmpdir and cycles:
            need_tmpdir = True

        if need_tmpdir:
            fslog('mkdir %s', tmpdir)

        for x in to_remove:
            path_remove(x, options.remove_recursive)

        rename_func = rev_redux_rename if options.safe else rev_redux_renames

        for p in paths.values():
            reduce(rename_func, reversed(p))

        for c in cycles.values():
            t = Path(os.path.join(tmpdir, 'c_' + c[0].tail))
            path_rename(c[0], t)
            c[0] = t
            reduce(rename_func, reversed(c))

        if need_tmpdir:
            fslog('rmdir %s', tmpdir)

    if not options.output:
        os.remove(tmpfile)
    os.rmdir(tmpdir)

if __name__ == '__main__':
    try:
        main()
    except Error:
        sys.exit(1)
