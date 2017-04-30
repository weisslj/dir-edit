#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010-2017 Johannes Weißl
# License GPLv3+:
# GNU GPL version 3 or later <http://gnu.org/licenses/gpl.html>
# This is free software: you are free to change and redistribute it.
# There is NO WARRANTY, to the extent permitted by law.

"""Rename or remove files in a directory using an editor."""

from __future__ import print_function
import sys
import os
import re
import tempfile
import locale
import subprocess
import argparse
import shutil
import shlex
import pipes
import random
import itertools
import logging

if sys.version_info < (3, 2):
    os.fsencode = lambda filename: filename
if sys.version_info < (3, 3):
    shlex.quote = pipes.quote

class Error(Exception):
    """Abort program, used in test suite."""
    pass

def pairwise(iterable):
    """s -> (s0, s1), (s1, s2), (s2, s3), ..."""
    it1, it2 = itertools.tee(iterable)
    next(it2, None)
    return zip(it1, it2)

def warning(msg, *args, **kwargs):
    """Output a warning message to stderr."""
    if sys.version_info < (3, 0):
        msg = msg.decode(errors='replace')
    logging.warning(msg, *args, **kwargs)

def cd_ops(path):
    """Return operations for changing current directory, only needed for verbose mode."""
    return [((None, 'cd'), (path,))]

def rmdir_ops(path):
    """Return operations for removing empty directory."""
    return [((os.rmdir, 'rmdir'), (path,))]

MAKEDIRS = os.makedirs
if sys.version_info < (3, 4):
    def makedirs_compat(name, exist_ok=False, **kwargs):
        """Compatibility function with Python 3.4 os.makedirs()."""
        try:
            os.makedirs(name, **kwargs)
        except OSError:
            # This is broken in Python 3.2 and 3.3, cf. https://bugs.python.org/issue13498
            if not exist_ok or not os.path.isdir(name):
                raise
    MAKEDIRS = makedirs_compat

def makedirs_exist_ok(path):
    """Like os.makedirs(), but ignores existing directories."""
    MAKEDIRS(path, exist_ok=True)

def makedirs_ops(path):
    """Return operations for creating directory and all intermediate-level directories."""
    return [((makedirs_exist_ok, 'mkdir -p'), (path,))]

def mkdir_ops(path):
    """Return operations for creating directory."""
    return [((os.mkdir, 'mkdir'), (path,))]

def remove_ops(path):
    """Return operations for removing a file."""
    return [((os.remove, 'rm'), (path,))]

def rmtree_ops(path):
    """Return operations for recursively removing a directory."""
    return [((shutil.rmtree, 'rm -r'), (path,))]

def path_remove_ops(path, recursive=False):
    """Return operations for removing path, optionally recursive."""
    if os.path.islink(path) or not os.path.isdir(path):
        ops = remove_ops(path)
    elif os.listdir(path):
        if recursive:
            ops = rmtree_ops(path)
        else:
            warning('not removing directory %s: not empty (try -R)', path)
            ops = []
    else:
        ops = rmdir_ops(path)
    return ops

def rename(src, dst):
    """Rename src path to dst, do not overwrite existing file."""
    # This is of course not race-condition free:
    if os.path.lexists(dst):
        warning('path %s already exists, skip', dst)
        return
    os.rename(src, dst)

def rename_ops(src, dst):
    """Return operations for renaming src path to dst."""
    return [((rename, 'mv -n'), (src, dst))]

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

def check_file_list(file_list):
    """Check that entries of file list exist, throw Error otherwise."""
    try:
        for path in file_list:
            os.lstat(path)
    except OSError as exc:
        raise Error('{}: {}'.format(path, exc.strerror))

def read_file_list(filename):
    """Read a file containing a single path per line, return list of paths.
    Can throw exception IOError.
    """
    with open(filename, 'r') as stream:
        return [line.rstrip('\r\n') for line in stream]

def remove_hidden(names, all_entries=False):
    """Remove entries starting with a dot (.) from list of basenames."""
    if not all_entries:
        names[:] = [name for name in names if not name.startswith('.')]

def read_dir_flat(path, all_entries=False):
    """Return a list of paths in directory at path. If all_entries is not
    true, exclude all entries starting with a dot (.).
    """
    names = os.listdir(path)
    remove_hidden(names, all_entries)
    return names

def read_dir_recursive(path, all_entries=False):
    """Return a list of paths in directory at path (recursively). If
    all_entries is not true, exclude all entries starting with a dot (.).
    """
    paths = []
    for root, dirs, files in os.walk(path):
        not_dirs = files + [name for name in dirs if os.path.islink(os.path.join(root, name))]
        remove_hidden(not_dirs, all_entries)
        for name in not_dirs:
            paths.append(os.path.normpath(os.path.join(root, name)))
        if root != path and not dirs and not files:
            paths.append(os.path.normpath(root))
        remove_hidden(dirs, all_entries)
    return paths

def read_dir(path, args):
    """Return a list of paths in directory at path, possibly recursively."""
    if args.recursive:
        paths = read_dir_recursive(path, args.all)
    else:
        paths = read_dir_flat(path, args.all)
    return paths

def normcase(path):
    """Normalize path case for cycle detection."""
    if sys.platform == 'darwin':
        # On Mac OS X 'mv -n' is case-insensitive:
        return path.lower()
    return os.path.normcase(path)

def decompose_mapping(mapping):
    """Decompose a mapping ('bijective' bipartite graph) into paths and cycles."""
    mapping = mapping.copy()
    paths = {}
    cycles = {}
    srcs = set(mapping.keys()) - set(mapping.values())  # set() for Python 2
    while mapping:
        try:
            src = srcs.pop()
            dst = mapping.pop(src)
        except KeyError:
            src, dst = mapping.popitem()
        path = [src, dst]
        while dst in mapping:
            dst = mapping.pop(dst)
            path.append(dst)
        # Use normcase to allow case-renaming on Windows:
        if normcase(src) == normcase(path[-1]):
            cycles[src] = path
        else:
            paths[src] = path
    return paths.values(), cycles.values()

def make_relpath(path):
    """Return relative path to current directory, raise error if it leads outside."""
    try:
        relpath = os.path.relpath(path)
        if relpath.startswith(os.pardir + os.sep):
            raise Error('error, path {} leads outside given directory'.format(path))
        return relpath
    except ValueError as exc:  # only on Windows, e.g. if drive letters differ
        raise Error('{}: {}'.format(path, exc))

def generate_mapping(input_file_list, output_file_list):
    """Generate renames and removals from file lists."""
    renames = {}
    removals = []
    src_seen = {}
    dst_seen = {}
    for srcfile, dstfile in zip(input_file_list, output_file_list):
        src = make_relpath(srcfile)
        if src in src_seen:
            raise Error('error, duplicate input entries {} and {}'.format(srcfile, src_seen[src]))
        src_seen[src] = srcfile
        # empty lines indicate removal
        if not dstfile:
            removals.append(src)
            continue
        dst = make_relpath(dstfile)
        if dst in dst_seen:
            raise Error('error, duplicate target entries {} and {}'.format(dstfile, dst_seen[dst]))
        dst_seen[dst] = dstfile
        # no self loops (need no renaming!)
        if src != dst:
            renames[src] = dst
    return renames, removals

def get_file_list_from_user(file_list, args):
    """Return user-edited file_list or raise error."""
    tmpdir = tempfile.mkdtemp(prefix='dir_edit-')
    tmpfile = os.path.join(tmpdir, 'file_list.txt')
    nl_re = re.compile(r'[\n\r]+')
    nl_buf = os.linesep.encode()
    with open(tmpfile, 'wb') as stream:
        stream.write(b''.join([os.fsencode(nl_re.sub(' ', e)) + nl_buf for e in file_list]))
    if os.name == 'nt':
        # Windows opens default editor if text file is opened directly:
        command = [tmpfile]
        if args.editor:
            command = args.editor + ' ' + subprocess.list2cmdline(command)
    else:
        command = args.editor + ' ' + shlex.quote(tmpfile)
    try:
        subprocess.check_call(command, shell=True)
        with open(tmpfile, 'r') as stream:
            return [line.rstrip('\r\n') for line in stream]
    except subprocess.CalledProcessError:
        raise Error('editor command failed: {}'.format(command))
    finally:
        os.remove(tmpfile)
        os.rmdir(tmpdir)

def get_output_file_list(input_file_list, args):
    """Return output file list or raise error."""
    if args.output:
        try:
            return read_file_list(args.output)
        except IOError as exc:
            raise Error('error reading output file: {}'.format(exc.strerror))
    else:
        return get_file_list_from_user(input_file_list, args)

def get_input_file_list(args, orig_cwd):
    """Return input file list or raise error."""
    if args.input:
        try:
            file_list = read_file_list(args.input)
        except IOError as exc:
            raise Error('error reading input file: {}'.format(exc.strerror))
        check_file_list(file_list)
    elif args.files:
        file_list = []
        for path in args.files:
            file_list.append(path if os.path.isabs(path) else os.path.join(orig_cwd, path))
        check_file_list(file_list)
    else:
        file_list = read_dir(os.curdir, args)
        key = textkey_path if not args.numeric_sort else numkey_path
        file_list.sort(key=key)
    if not file_list:
        raise Error('no valid path given for renaming')
    if not args.mangle_newlines:
        for filename in file_list:
            if '\n' in filename or '\r' in filename:
                raise Error('file names with newlines are not supported, try -m!')
    return file_list

def get_file_lists(args, orig_cwd):
    """Return input and output file list or raise error."""
    input_file_list = get_input_file_list(args, orig_cwd)
    output_file_list = get_output_file_list(input_file_list, args)
    if len(input_file_list) != len(output_file_list):
        raise Error('new file list has different length than old')
    return input_file_list, output_file_list

def tmpname():
    """Return temporary file name."""
    characters = 'abcdefghijklmnopqrstuvwxyz0123456789_'
    return 'tmp_' + ''.join(random.choice(characters) for _ in range(20))

def dirnames(path):
    """Yield all os.path.dirname()s."""
    head, _tail = os.path.split(path)
    while head:
        yield head
        head, _tail = os.path.split(head)

def create_tmpdir(ops, tmpdir):
    """Append operations for creating temporary directory to ops, return path."""
    if not tmpdir:
        tmpdir = tmpname()
        ops += mkdir_ops(tmpdir)
    return tmpdir

def remove_tmpdir(tmpdir):
    """Return operations for removing temporary directory."""
    return rmdir_ops(tmpdir) if tmpdir else []

def generate_operations(paths, cycles, removals, args):
    """Generate file system operations."""
    ops = cd_ops(os.path.realpath(os.curdir))
    src_dirs = set()
    dst_dirs = set()
    tmpdir = ''
    for path in paths:
        for dst, src in pairwise(reversed(path)):
            if not dst.startswith(src + os.sep):
                src_dirs |= set(dirnames(src))
                dst_dirs |= set(dirnames(dst))
    for filename in removals:
        ops += path_remove_ops(filename, args.remove_recursive)
    for filename in sorted(dst_dirs - src_dirs, key=len):
        ops += makedirs_ops(filename)
    for path in paths:
        for dst, src in pairwise(reversed(path)):
            if dst.startswith(src + os.sep):
                tmpdir = create_tmpdir(ops, tmpdir)
                tmp = os.path.join(tmpdir, os.path.basename(src))
                ops += rename_ops(src, tmp)
                ops += makedirs_ops(os.path.dirname(dst))
                ops += rename_ops(tmp, dst)
            else:
                ops += rename_ops(src, dst)
    for filename in sorted(src_dirs - dst_dirs, key=len, reverse=True):
        ops += rmdir_ops(filename)
    for cycle in cycles:
        tmpdir = create_tmpdir(ops, tmpdir)
        tmp = os.path.join(tmpdir, os.path.basename(cycle[0]))
        ops += rename_ops(cycle[0], tmp)
        cycle[0] = tmp
        for dst, src in pairwise(reversed(cycle)):
            ops += rename_ops(src, dst)
    ops += remove_tmpdir(tmpdir)
    return ops

def execute_operations(ops, args):
    """Execute file system operations."""
    for (fun, cmd), fargs in ops:
        if args.verbose:
            sep = ' -- ' if any(farg.startswith('-') for farg in fargs) else ' '
            msg = cmd + sep + ' '.join(shlex.quote(farg) for farg in fargs)
            if sys.version_info < (3, 0):
                msg = msg.decode(errors='replace')
            print(msg, file=args.logfile)
        if not args.dry_run and fun is not None:
            try:
                fun(*fargs)
            except OSError as exc:
                fun_call = fun.__name__ + '(' + ', '.join((repr(farg) for farg in fargs)) + ')'
                raise Error(fun_call + ': ' + exc.strerror)

def dir_edit(args):
    """Main functionality."""
    orig_cwd = os.getcwd()
    try:
        os.chdir(args.dir)
    except OSError as exc:
        raise Error('{}: {}'.format(args.dir, exc.strerror))
    input_file_list, output_file_list = get_file_lists(args, orig_cwd)
    renames, removals = generate_mapping(input_file_list, output_file_list)
    paths, cycles = decompose_mapping(renames)
    ops = generate_operations(paths, cycles, removals, args)
    execute_operations(ops, args)

def main_throws(args=None):
    """Main function, throws exception on error."""
    # For locale-specific sorting of filenames:
    locale.setlocale(locale.LC_ALL, '')
    #
    usage = '%(prog)s [OPTION]... [DIR] [FILES]...'
    desc = '''\
Modify contents of DIR using an editor. Creates a temporary file, where every
line is a filename in the directory DIR. Then an editor is started, enabling
the user to rename or delete (blank line) entries. After saving, the script
performs a consistency check, detects rename loops and finally executes the
changes.'''
    #
    default_editor = 'vi'
    if os.name == 'nt':
        # Windows opens default editor if text file is opened directly:
        default_editor = ''
    default_editor = os.getenv('EDITOR', default_editor)
    #
    parser = argparse.ArgumentParser(usage=usage, description=desc)
    parser.add_argument('dir', metavar='DIR', nargs='?', default=os.curdir,
                        help='directory to edit (default: current directory)')
    parser.add_argument('files', metavar='FILES', nargs='*',
                        help='limit to these filenames (default: all non-hidden in directory)')
    parser.add_argument('--version', action='version', version='%(prog)s 2.1.0')
    parser.add_argument('-a', '--all', action='store_true', default=False,
                        help='include entries starting with . (besides . and ..)')
    parser.add_argument('-d', '--dry-run', action='store_true',
                        default=False, help='don\'t perform any file system modifications')
    parser.add_argument('-e', '--editor', metavar='CMD', default=default_editor,
                        help='use CMD to edit dirfile (default: $EDITOR or vi)')
    parser.add_argument('-i', '--input', metavar='FILE',
                        help=('FILE containing paths to be edited '
                              '(FILES, -a, -m, -n, and -r ignored)'))
    parser.add_argument('-o', '--output', metavar='FILE',
                        help='FILE containing paths after being edited (-e is ignored)')
    parser.add_argument('-m', '--mangle-newlines', action='store_true',
                        default=False, help='replace newlines in files through spaces')
    parser.add_argument('-n', '--numeric-sort', action='store_true',
                        default=False, help='sort entries according to string numerical value')
    parser.add_argument('-R', '--remove-recursive', action='store_true',
                        default=False, help='remove non-empty directories recursively')
    parser.add_argument('-r', '--recursive', action='store_true', default=False,
                        help='list DIR recursively')
    parser.add_argument('-L', '--logfile', metavar='FILE',
                        type=argparse.FileType('w'), default=sys.stdout,
                        help='path to logfile for verbose mode (default: stdout)')
    parser.add_argument('-v', '--verbose', action='store_true', default=False,
                        help='output filesystem modifications to logfile')
    args = parser.parse_args(args)
    # Use style='{' after Python 2 support is dropped:
    logging.basicConfig(format='%(module)s: %(message)s')
    dir_edit(args)

def main(args=None):
    """Main function, exits program on error."""
    try:
        main_throws(args)
    except Error as exc:
        logging.critical('%s', str(exc))
        sys.exit(1)

if __name__ == '__main__':
    sys.exit(main())
