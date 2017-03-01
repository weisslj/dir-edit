# -*- coding: utf-8 -*-

"""Test module for dir_edit.py."""

from __future__ import print_function
import sys
import os
import re
import errno
import unittest
import tempfile
import shutil
from io import StringIO
import subprocess

import dir_edit

def listdir_recursive(top):
    """Yield leaf nodes of 'top' directory recursively."""
    for root, dirs, files in os.walk(top):
        not_dirs = files + [name for name in dirs if os.path.islink(os.path.join(root, name))]
        for name in not_dirs:
            yield os.path.relpath(os.path.join(root, name), top).replace(os.sep, '/')
        if root != top and not dirs and not files:
            yield os.path.relpath(root, top).replace(os.sep, '/') + '/'

def path_content(path):
    """Return file content or '<dir>' for directories."""
    if os.path.islink(path):
        return '-> ' + os.readlink(path)
    elif os.path.isdir(path):
        return '<dir>'
    else:
        with open(path) as stream:
            return stream.read()

def mkdir_p(path):
    """Like os.makedirs(), but ignores existing directories."""
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise

def fake_sys_exit(arg=0):
    """Raise exception instead of exiting, for testing."""
    raise Exception('sys.exit(%r)' % (arg,))

def dir_edit_external(*args):
    """Call dir_edit.py as external process."""
    here = os.path.abspath(os.path.dirname(__file__))
    prog = os.path.join(here, 'dir_edit.py')
    shell = False
    if os.name == 'nt':
        shell = True
    return subprocess.check_output([prog] + list(args), stderr=subprocess.STDOUT, shell=shell,
                                   universal_newlines=True)

class DirEditTestCase(unittest.TestCase):
    # pylint: disable=too-many-instance-attributes,too-many-public-methods
    """Main dir_edit.py test class."""

    @classmethod
    def setUpClass(cls):
        """Add renamed member functions for Python 2.7."""
        if sys.version_info < (3, 2):
            cls.assertRegex = cls.assertRegexpMatches
            cls.assertRaisesRegex = cls.assertRaisesRegexp

    def setUp(self):
        """Create temporary directories, declare attributes."""
        self.curdir = os.getcwd()
        self.tmpdir = tempfile.mkdtemp()
        self.tmpdir2 = tempfile.mkdtemp()
        self.original_stdout = []
        self.original_stderr = []
        self.stdout_buffer = []
        self.stderr_buffer = []
        self.output = None
        self.error = None

    def tearDown(self):
        """Remove temporary directories."""
        os.chdir(self.curdir)
        shutil.rmtree(self.tmpdir2)
        shutil.rmtree(self.tmpdir)

    def put_files(self, *filenames):
        """Put files into the temporary directory."""
        for filename in filenames:
            path = os.path.join(self.tmpdir, filename)
            mkdir_p(os.path.dirname(path))
            with open(path, 'w') as stream:
                stream.write(filename)

    def put_dirs(self, *dirnames):
        """Put directories into the temporary directory."""
        for dirname in dirnames:
            path = os.path.join(self.tmpdir, dirname)
            mkdir_p(path)

    def tmpfile(self, *filenames):
        """Create a temporary file with list of filenames, return path."""
        with tempfile.NamedTemporaryFile(mode='w', dir=self.tmpdir2, delete=False) as tmpfile:
            tmpfile.write('\n'.join(filenames) + '\n')
        return tmpfile.name

    def list_tmpdir(self):
        """Return sorted list of leaf nodes of self.tmpdir recursively."""
        return sorted(listdir_recursive(self.tmpdir))

    def path_content(self, path):
        """Return file content or '<dir>' for directories of path relative to self.tmpdir."""
        return path_content(os.path.join(self.tmpdir, path))

    def list_tmpdir_content(self):
        """Like list_tmpdir(), but return list of (path, content) tuples."""
        return [(path, self.path_content(path)) for path in self.list_tmpdir()]

    def setup_stdout(self):
        """Replace stdout and stderr with StringIO() for later inspection."""
        self.original_stdout.append(sys.stdout)
        self.original_stderr.append(sys.stderr)
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        self.stdout_buffer.append(sys.stdout)
        self.stderr_buffer.append(sys.stderr)

    def restore_stdout(self):
        """Restore stdout and stderr and store buffer values for inspection."""
        self.output = self.stdout_buffer.pop().getvalue()
        self.error = self.stderr_buffer.pop().getvalue()
        sys.stdout = self.original_stdout.pop()
        sys.stderr = self.original_stderr.pop()
        sys.stdout.write(self.output)
        sys.stderr.write(self.error)

    def dir_edit(self, *args):
        """Convenience function to call dir_edit.py, restores current directory."""
        curdir = os.getcwd()
        self.call_dir_edit(list(args))
        os.chdir(curdir)

    def call_dir_edit(self, args):
        # Is a method to be overridden in child:
        # pylint: disable=no-self-use
        """Call dir_edit.py main function."""
        dir_edit.main_throws(args)

    def test_mkdir_p(self):
        """Test internal function for coverage."""
        self.put_files('a/b')
        self.put_dirs('c/d')
        regexp = '(File exists|Cannot create a file when that file already exists)'
        with self.assertRaisesRegex(OSError, regexp):
            self.put_dirs('a/b')
        self.assertEqual([('a/b', 'a/b'), ('c/d/', '<dir>')], self.list_tmpdir_content())

    def test_empty(self):
        """Raise error if called on empty directory."""
        with self.assertRaisesRegex(dir_edit.Error, 'no valid path given for renaming'):
            self.dir_edit(self.tmpdir)

    def test_main(self):
        """Test main function for coverage."""
        original_sys_exit = sys.exit
        sys.exit = fake_sys_exit
        with self.assertRaisesRegex(Exception, r'^sys.exit\(0\)$'):
            dir_edit.main(['--help'])
        sys.exit = original_sys_exit

    def test_main_error(self):
        """Test main function error for coverage."""
        original_sys_exit = sys.exit
        sys.exit = fake_sys_exit
        with self.assertRaisesRegex(Exception, r'^sys.exit\(1\)$'):
            dir_edit.main([os.path.join(self.tmpdir, 'nonexist')])
        sys.exit = original_sys_exit

    def test_help(self):
        """Check that '-h' and '--help' options work."""
        help_output1 = dir_edit_external('-h')
        help_output2 = dir_edit_external('--help')
        self.assertRegex(help_output1, '^usage: dir_edit')
        self.assertEqual(help_output1, help_output2)

    def test_version(self):
        """Check that the '--version' option works."""
        here = os.path.abspath(os.path.dirname(__file__))
        setup_prog = os.path.join(here, 'setup.py')
        version = subprocess.check_output(['python', setup_prog, '--version'],
                                          universal_newlines=True)
        version_output = dir_edit_external('--version')
        self.assertRegex(version_output, '^dir_edit.py ' + re.escape(version))

    def test_editor(self):
        """Check that '-e' and '--editor' options work."""
        self.put_files('a1', 'a2')
        pysed = (
            'python -c "'
            'from sys import argv as a;'
            's = open(a[3]).read();'
            'open(a[3], \'w\').write(s.replace(a[1], a[2]))'
            '"'
        )
        self.dir_edit(self.tmpdir, '-e', pysed + ' a b')
        self.assertEqual(['b1', 'b2'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--editor', pysed + ' b c')
        self.assertEqual(['c1', 'c2'], self.list_tmpdir())
        with self.assertRaisesRegex(dir_edit.Error, 'editor command failed'):
            self.dir_edit(self.tmpdir, '-e' 'python -c "exit(1)"')

    def test_nonexisting(self):
        """Raise error if directory does not exist."""
        regexp = 'nonexist: (No such file or directory|The system cannot find the file specified)'
        with self.assertRaisesRegex(dir_edit.Error, regexp):
            self.dir_edit(os.path.join(self.tmpdir, 'nonexist'))

    def test_nodirectory(self):
        """Raise error if path is no directory."""
        self.put_files('nodirectory')
        regexp = 'nodirectory: (Not a directory|The directory name is invalid)'
        with self.assertRaisesRegex(dir_edit.Error, regexp):
            self.dir_edit(os.path.join(self.tmpdir, 'nodirectory'))

    def test_output(self):
        """Check that '-o' and '--output' options work."""
        self.put_files('a1', 'a2')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('b1', 'b2'))
        self.assertEqual(['b1', 'b2'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--output', self.tmpfile('c1', 'c2'))
        self.assertEqual(['c1', 'c2'], self.list_tmpdir())
        with self.assertRaisesRegex(dir_edit.Error, 'error reading output file'):
            self.dir_edit(self.tmpdir, '-o', os.path.join(self.tmpdir2, 'nonexist'))

    def test_input(self):
        """Check that '-i' and '--input' options work."""
        self.put_files('a1', 'a2')
        self.dir_edit(self.tmpdir, '-i', self.tmpfile('a2', 'nonexist'), '-o', self.tmpfile('b2'))
        self.assertEqual(['a1', 'b2'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--input', self.tmpfile('b2'), '-o', self.tmpfile('c2'))
        self.assertEqual(['a1', 'c2'], self.list_tmpdir())
        with self.assertRaisesRegex(dir_edit.Error, 'identical entries'):
            self.dir_edit(self.tmpdir, '-i', self.tmpfile('c2', 'c2'),
                          '-o', self.tmpfile('d2', 'd2'))
        with self.assertRaisesRegex(dir_edit.Error, 'error reading input file'):
            self.dir_edit(self.tmpdir, '-i', os.path.join(self.tmpdir2, 'nonexist'))
        self.assertEqual(['a1', 'c2'], self.list_tmpdir())

    def test_files(self):
        """Check that filename arguments work."""
        self.put_files('a1', 'a2')
        self.dir_edit(self.tmpdir, 'a2', 'nonexist', '-o', self.tmpfile('b2'))
        self.assertEqual(['a1', 'b2'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, 'b2', '-o', self.tmpfile('c2'))
        self.assertEqual(['a1', 'c2'], self.list_tmpdir())

    @unittest.skipIf(os.name == 'nt', 'newlines in files not supported on Windows')
    def test_newlines(self):
        """Check that '-m' and '--mangle-newlines' options work."""
        self.put_files('a\r\n1', 'a\n\n2')
        with self.assertRaisesRegex(dir_edit.Error, 'file names with newlines are not supported'):
            self.dir_edit(self.tmpdir)
        self.dir_edit(self.tmpdir, '-m', '-e', 'python -c "exit(0)"')
        self.assertEqual(['a 1', 'a 2'], self.list_tmpdir())
        self.put_files('a\r3')
        self.dir_edit(self.tmpdir, '--mangle-newlines', '-e', 'python -c "exit(0)"')
        self.assertEqual(['a 1', 'a 2', 'a 3'], self.list_tmpdir())

    def test_same_length(self):
        """Abort if input and output have different length."""
        self.put_files('a1', 'a2')
        with self.assertRaisesRegex(dir_edit.Error, 'has different length'):
            self.dir_edit(self.tmpdir, '-o', self.tmpfile('b2'))
        self.assertEqual(['a1', 'a2'], self.list_tmpdir())

    def test_same_destination(self):
        """Abort if rename destination is the same for two or more files."""
        self.put_files('a1', 'a2')
        with self.assertRaisesRegex(dir_edit.Error, 'same destination'):
            self.dir_edit(self.tmpdir, '-o', self.tmpfile('b', 'b'))
        self.assertEqual(['a1', 'a2'], self.list_tmpdir())

    def test_swap(self):
        """Swapping filenames, smallest cycle."""
        self.put_files('a', 'b')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('b', 'a'))
        self.assertEqual([('a', 'b'), ('b', 'a')], self.list_tmpdir_content())

    def test_cycle(self):
        """Larger cycles."""
        self.put_files('a', 'b', 'c', 'd')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('b', 'c', 'd', 'a'))
        self.assertEqual([('a', 'd'), ('b', 'a'), ('c', 'b'), ('d', 'c')],
                         self.list_tmpdir_content())
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('d', 'a', 'b', 'c'))
        self.assertEqual([('a', 'a'), ('b', 'b'), ('c', 'c'), ('d', 'd')],
                         self.list_tmpdir_content())

    def test_path(self):
        """Test rename paths, order is important."""
        self.put_files('a', 'b', 'c', 'd')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('b', 'c', 'd', 'e'))
        self.assertEqual([('b', 'a'), ('c', 'b'), ('d', 'c'), ('e', 'd')],
                         self.list_tmpdir_content())
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('a', 'b', 'c', 'd'))
        self.assertEqual([('a', 'a'), ('b', 'b'), ('c', 'c'), ('d', 'd')],
                         self.list_tmpdir_content())

    def test_remove(self):
        """Test file removal through empty lines."""
        self.put_files('a', 'b')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('', 'a'))
        self.assertEqual([('a', 'b')], self.list_tmpdir_content())

    def test_all(self):
        """Check that '-a' and '--all' options work."""
        self.put_files('.a', 'b')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('.b'))
        self.assertEqual(['.a', '.b'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '-a', '-o', self.tmpfile('.a', ''))
        self.assertEqual(['.a'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--all', '-o', self.tmpfile('.c'))
        self.assertEqual(['.c'], self.list_tmpdir())

    def test_all_not_top(self):
        """Check that missing '-a' option does not exclude top directory."""
        self.put_files('.x/a')
        self.dir_edit(os.path.join(self.tmpdir, '.x'), '-o', self.tmpfile('b'))
        self.assertEqual(['.x/b'], self.list_tmpdir())
        self.dir_edit(os.path.join(self.tmpdir, '.x'), '-r', '-o', self.tmpfile('c'))
        self.assertEqual(['.x/c'], self.list_tmpdir())

    def test_only_leaf_dirs(self):
        """Check that only empty directories are listed in recursive mode."""
        self.put_dirs('a/b/c', 'd/e/f/.g')
        self.put_files('h/i/j', 'k/l/m/.n')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('a/b/c', 'h/i/j'))

    def test_all_recursive(self):
        """Check that '-a' option works in recursive mode."""
        self.put_files('.x/a', 'y/.b', 'z')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('z'))
        self.assertEqual(['.x/a', 'y/.b', 'z'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '-r', '-a', '-o', self.tmpfile('.x/a', 'y/.b', 'z'))
        self.assertEqual(['.x/a', 'y/.b', 'z'], self.list_tmpdir())

    def test_dry_run(self):
        """Check that '-d' and '--dry-run' options work."""
        self.put_files('a')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('b'))
        self.assertEqual(['b'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '-d', '-o', self.tmpfile('c'))
        self.assertEqual(['b'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--dry-run', '-o', self.tmpfile('d'))
        self.assertEqual(['b'], self.list_tmpdir())

    def test_filenames(self):
        """Test that filenames with special characters work."""
        self.put_files('-', "'")
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('', ''))
        self.assertEqual([], self.list_tmpdir())

    @unittest.skipIf(os.name == 'nt', 'filenames not supported on Windows')
    def test_filenames_posix(self):
        """Test that filenames with special characters work."""
        self.put_files('"')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile(''))
        self.assertEqual([], self.list_tmpdir())

    def test_recursive(self):
        """Test that recursive mode ('-r' and '--recursive') works."""
        self.put_files('x/a')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('x/b'))
        self.assertEqual(['x/b'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--recursive', '-o', self.tmpfile('x/c'))
        self.assertEqual(['x/c'], self.list_tmpdir())

    def test_recursive_cleanup(self):
        """Check that recursive mode cleans up an empty directory."""
        self.put_files('x/a')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('y'))
        self.assertEqual(['y'], self.list_tmpdir())

    def test_recursive_cleanup_stop(self):
        """Check that recursive cleanup stops after first failure."""
        self.put_files('x/y/a', 'x/y/b')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('a', 'x/y/c'))
        self.assertEqual([('a', 'x/y/a'), ('x/y/c', 'x/y/b')], self.list_tmpdir_content())

    def test_recursive_cleanup_multiple(self):
        """Check that recursive mode cleans up empty directories."""
        self.put_files('x/a/b/c/d')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('y'))
        self.assertEqual(['y'], self.list_tmpdir())

    def test_recursive_mkdir(self):
        """Check that recursive mode can create directories."""
        self.put_files('x/a')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('x/b/c/d'))
        self.assertEqual(['x/b/c/d'], self.list_tmpdir())

    # TODO: Fix bug!
    # def test_recursive_fail2(self):
    #     """Test that recursive mode works."""
    #     self.put_files('x/a')
    #     self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('z/c'))
    #     self.assertEqual(['x/', 'z/c'], self.list_tmpdir())
    #     self.dir_edit(self.tmpdir, '--recursive', '-o', self.tmpfile('y', 'x/y/b'))
    #     self.assertEqual(['x/y/b', 'y/', 'z/'], self.list_tmpdir())

    def test_recursive_remove(self):
        """Test that recursive remove works."""
        self.put_files('a/b', 'x/y/z1', 'x/y/z2')
        self.put_dirs('z/z/z')
        self.setup_stdout()
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('', 'x', ''))
        self.restore_stdout()
        self.assertRegex(self.error, 'not removing directory a: not empty')
        self.assertEqual(['a/b', 'x/y/z1', 'x/y/z2', 'z/z/z/'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '-R', '-o', self.tmpfile('', 'x', ''))
        self.assertEqual(['x/y/z1', 'x/y/z2'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '--remove-recursive', '-o', self.tmpfile(''))
        self.assertEqual([], self.list_tmpdir())

    def test_own_subdirectory(self):
        """Move a file to a subdirectory with the same name."""
        self.put_files('x')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('x/new_x'))
        self.assertEqual(['x/new_x'], self.list_tmpdir())

    def test_own_subdirectory_multiple(self):
        """Move a file to a subdirectory with the same name."""
        self.put_files('a/b')
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('a/b/c/d'))
        self.assertEqual(['a/b/c/d'], self.list_tmpdir())

    def test_safe(self):
        """Check that '-S' and '--safe' options work."""
        self.put_files('a')
        # TODO: Better error message!
        regexp = '(No such file or directory|The system cannot find the path specified)'
        with self.assertRaisesRegex(OSError, regexp):
            self.dir_edit(self.tmpdir, '-S', '-o', self.tmpfile('x/y'))
        self.assertEqual(['a'], self.list_tmpdir())

    def test_numeric_sort(self):
        """Check that '-n' and '--numeric-sort' options work."""
        self.put_files('1', '5', '10', '20')
        self.dir_edit(self.tmpdir, '-n', '-o', self.tmpfile('-1x', '!', ' 0.1 a', '  4'))
        self.dir_edit(self.tmpdir, '-n', '-o', self.tmpfile('a', 'b', 'c', 'd'))
        self.assertEqual([('a', '1'), ('b', '5'), ('c', '10'), ('d', '20')],
                         self.list_tmpdir_content())

    def test_dest_exists_recursive(self):
        """Check that existing destination error is handled."""
        self.put_files('a/x', 'b/y')
        self.setup_stdout()
        self.dir_edit(self.tmpdir, 'a', '-r', '-o', self.tmpfile('b/y'))
        self.restore_stdout()
        self.assertEqual([('a/x', 'a/x'), ('b/y', 'b/y')], self.list_tmpdir_content())
        self.assertRegex(self.error, 'path b/y already exists, skip')

    def test_dest_exists_safe(self):
        """Check that existing destination error is handled in safe mode."""
        self.put_files('a', 'b')
        self.setup_stdout()
        self.dir_edit(self.tmpdir, '-S', '-i', self.tmpfile('a'), '-o', self.tmpfile('b'))
        self.restore_stdout()
        self.assertEqual([('a', 'a'), ('b', 'b')], self.list_tmpdir_content())
        self.assertRegex(self.error, 'path b already exists, skip')

    def test_reldir(self):
        """Check that a relative directory works."""
        shutil.rmtree(self.tmpdir)
        self.tmpdir = tempfile.mkdtemp(dir=os.curdir)
        self.put_files('a')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('b'))
        self.assertEqual(['b'], self.list_tmpdir())
        self.dir_edit(self.tmpdir, '-r', '-o', self.tmpfile('c'))
        self.assertEqual(['c'], self.list_tmpdir())

    def test_realpath(self):
        """Check that paths are correctly compared."""
        self.put_files('a')
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('x/..//a'))
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('a/'))
        self.dir_edit(self.tmpdir, '-i', self.tmpfile('./a'), '-o', self.tmpfile('a'))
        self.assertEqual([('a', 'a')], self.list_tmpdir_content())
        # for coverage:
        self.assertFalse(dir_edit.Path('a') == [])
        self.assertTrue(dir_edit.Path('a') == 'a')
        self.assertTrue(dir_edit.Path('a') < dir_edit.Path('b'))
        self.assertTrue(dir_edit.Path('a') < 'b')
        self.assertRaises(TypeError, lambda: dir_edit.Path('a') < [])

    @unittest.skipIf(os.name == 'nt', 'symlinks not supported on Windows')
    def test_realpath_symlinks(self):
        """Check that symlinks are correctly resolved (but not for last element)."""
        self.put_files('i', 'x/a')
        os.symlink('i', os.path.join(self.tmpdir, 'j'))
        os.symlink('q', os.path.join(self.tmpdir, 'k'))
        os.symlink('a', os.path.join(self.tmpdir, 'x/b'))
        os.symlink('r', os.path.join(self.tmpdir, 'x/c'))
        os.symlink('x', os.path.join(self.tmpdir, 'y'))
        self.dir_edit(self.tmpdir, '-o', self.tmpfile('i', 'j', 'k', 'x', 'y'))
        self.dir_edit(self.tmpdir, '-r', '-o',
                      self.tmpfile('i', 'j', 'k', 'x/a', 'x/b', 'x/c', 'y'))
        self.assertEqual([('i', 'i'), ('j', '-> i'), ('k', '-> q'),
                          ('x/a', 'x/a'), ('x/b', '-> a'), ('x/c', '-> r'),
                          ('y', '-> x')],
                         self.list_tmpdir_content())
        self.dir_edit(self.tmpdir, '-r', '-o',
                      self.tmpfile('j', 'i', 'k', 'x/b', 'x/a', 'x/c', 'y'))
        self.assertEqual([('i', '-> i'), ('j', 'i'), ('k', '-> q'),
                          ('x/a', '-> a'), ('x/b', 'x/a'), ('x/c', '-> r'),
                          ('y', '-> x')],
                         self.list_tmpdir_content())

    def test_multibyte_error(self):
        """Check that multibyte error message works."""
        regexp = '(No such file or directory|The system cannot find the file specified)'
        with self.assertRaisesRegexp(dir_edit.Error, regexp):
            self.dir_edit(os.path.join(self.tmpdir, '\xc3\xa4'))
        with self.assertRaisesRegex(dir_edit.Error, regexp):
            self.dir_edit(os.path.join(self.tmpdir, '\xe4'))

@unittest.skipIf(os.name == 'nt', 'not yet supported on Windows')
class DirEditDryRunVerboseTestCase(DirEditTestCase):
    """Test dir_edit.py -d -v."""
    def call_dir_edit(self, args):
        self.setup_stdout()
        try:
            dir_edit.main_throws(['--dry-run', '--verbose'] + args)
        finally:
            self.restore_stdout()
        for command in self.output.split('\n'):
            subprocess.check_output(command, shell=True, universal_newlines=True)
    def test_dry_run(self):
        """Not necessary here."""
        pass
    def test_remove(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_recursive(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_path(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_swap(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_cycle(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_safe(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_own_subdirectory_multiple(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_numeric_sort(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_filenames(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    def test_newlines(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass
    @unittest.skipIf(os.name == 'nt', 'symlinks not supported on Windows')
    def test_realpath_symlinks(self):
        """Exclude test case for now."""
        # TODO: Fix bug!
        pass

if __name__ == '__main__':
    unittest.main(buffer=True, catchbreak=True)
