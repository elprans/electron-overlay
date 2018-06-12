#!/usr/bin/env python3
#
# This script is used to get and patch the chromium source code
# appropriate for the given electron ebuild version.


import argparse
import collections
import os
import os.path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.parse
import urllib.request


CHROMIUM_URL = \
    'https://commondatastorage.googleapis.com/chromium-browser-official/'

LIBCC_REPO = 'https://github.com/electron/libchromiumcontent.git'

CACHEHOME = os.environ.get(
    'XDG_CACHE_HOME', os.path.expandvars('$HOME/.cache'))

CACHEDIR = os.path.join(CACHEHOME, 'get-chromium-source-for-electron')


def main():
    args = parse_args()
    ebuild = args.ebuild

    info = parse_electron_ebuild(ebuild)
    update_repo(LIBCC_REPO)
    libcc_patches = [
        f for f in list_files_in_repo(LIBCC_REPO, info.libcc_version,
                                      'patches')
        if f.endswith('.patch') and 'third_party/icu' not in f
    ]

    if not os.path.exists(os.path.join(args.target, '.git')):
        git('init', cwd=args.target)

    stuff = git('status', '--porcelain', cwd=args.target)
    if stuff:
        die('there are uncommitted or untracked files in {}'.format(
            args.target))

    git('checkout', '--orphan', info.chromium_version, cwd=args.target)
    git('rm', '-rf', '--ignore-unmatch', '.', cwd=args.target)
    git('clean', '-fdx', cwd=args.target)

    download_and_unpack_chromium_source(info.chromium_version, args.target)

    git('add', '--force', '.', cwd=args.target)
    git('commit', '-m', 'Import chromium-{}'.format(info.chromium_version),
        cwd=args.target)

    if not args.apply_patches:
        return 0

    patches = [
        (patch.partition('/')[2],
         get_file_in_repo(LIBCC_REPO, info.libcc_version, patch))
        for patch in libcc_patches
    ]

    apply_patches(patches, args.target)
    git('add', '--force', '.', cwd=args.target)
    git('commit', '-m', 'libchromiumcontent patches', cwd=args.target)

    unbundle_libs(info, args.target)
    git('add', '--force', '.', cwd=args.target)
    git('commit', '-m', 'unbundled libraries', cwd=args.target)

    return 0


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply-patches', action='store_true', default=False,
                        help='Apply Electron and Gentoo patches.')
    parser.add_argument('ebuild', help='Path to electron ebuild.')
    parser.add_argument('target', help='Path to target directory.')
    return parser.parse_args()


def die(msg, *, exitcode=1):
    print(msg, file=sys.stderr)
    sys.exit(exitcode)


_ver_re = re.compile(r'CHROMIUM_VERSION="([^"]+)"')
_libcc_re = re.compile(r'LIBCHROMIUMCONTENT_COMMIT="([^"]+)"')
_patch_re = re.compile(r'CHROMIUM_PATCHES="([^"]+)"', re.M)
_bundled_re = re.compile(r'keeplibs=\(([^)]+)\)', re.M)
_gn_syslibs_re = re.compile(r'gn_system_libraries=\(([^)]+)\)', re.M)


ElectronInfo = collections.namedtuple(
    'ElectronInfo', [
        'chromium_version',
        'libcc_version',
        'bundled_libraries',
        'gn_system_libraries',
    ]
)


def parse_electron_ebuild(ebuild_fn):
    with open(ebuild_fn, 'r') as f:
        ebuild = f.read()

    ver = _ver_re.search(ebuild)
    if not ver:
        die('could not find Chromium version in {}'.format(ebuild_fn))
    ver = ver.group(1)

    libcc_ver = _libcc_re.search(ebuild)
    if not libcc_ver:
        die('could not find libchromiumcontent version in {}'.format(
            ebuild_fn))
    libcc_ver = libcc_ver.group(1)

    bundled = _bundled_re.search(ebuild)
    if not bundled:
        die('could not find keeplibs in {}'.format(
            ebuild_fn))
    bundled_libs = list(filter(
        lambda f: f and not f.startswith('#'),
        (l.strip(' \n\t') for l in bundled.group(1).split('\n'))
    ))

    gn_syslibs = _gn_syslibs_re.search(ebuild)
    if not gn_syslibs:
        die('could not find gn_system_libraries in {}'.format(
            ebuild_fn))
    gn_syslibs = list(filter(
        None, (l.strip(' \n\t') for l in gn_syslibs.group(1).split('\n'))))

    gn_syslibs.append('ffmpeg')

    return ElectronInfo(
        chromium_version=ver,
        libcc_version=libcc_ver,
        bundled_libraries=bundled_libs,
        gn_system_libraries=gn_syslibs,
    )


def apply_patches(patches, target):
    for patch_name, patch_text in patches:
        dirname = os.path.dirname(patch_name)
        if dirname:
            cwd = os.path.join(target, dirname)
        else:
            cwd = target
        p = subprocess.run(['patch', '-p1'], cwd=cwd, encoding='utf8',
                           input=patch_text)
        if p.returncode != 0:
            die(f'Could not apply {patch_name}')


def repodir(repo_url):
    u = urllib.parse.urlparse(repo_url)
    base = os.path.basename(u.path)
    name, _ = os.path.splitext(base)
    return name


def git(*cmdline, **kwargs):
    cmd = ['git'] + list(cmdline)

    default_kwargs = {
        'stderr': sys.stderr,
        'stdout': subprocess.PIPE,
        'encoding': 'utf8',
    }

    default_kwargs.update(kwargs)

    p = subprocess.run(cmd, **default_kwargs)

    if p.returncode != 0:
        die('{} failed with exit code {}'.format(' '.join(cmd), p.returncode))

    return p.stdout


def list_files_in_repo(repo, treeish, path):
    repo_dir = os.path.join(CACHEDIR, repodir(repo))
    files = git('ls-tree', '-r', '--name-only', '--full-name',
                treeish, '--', path, cwd=repo_dir).split('\n')
    return [f.strip() for f in files if f.strip()]


def get_file_in_repo(repo, commitish, path):
    repo_dir = os.path.join(CACHEDIR, repodir(repo))
    return git('show', '{}:{}'.format(commitish, path), cwd=repo_dir)


def update_repo(repo_url):
    repo_dir = os.path.join(CACHEDIR, repodir(repo_url))
    repo_gitdir = os.path.join(repo_dir, '.git')

    if os.path.exists(repo_gitdir):
        git('fetch', cwd=repo_dir)
    else:
        if os.path.exists(repo_dir):
            # Repo dir exists for some reason, remove it.
            shutil.rmtree(repo_dir)

        git('clone', repo_url, repo_dir)


def download_and_unpack_chromium_source(version, target_dir):
    target_dir = target_dir.rstrip('/')
    archive_name = 'chromium-{}.tar.xz'.format(version)
    distfile = '/usr/portage/distfiles/{}'.format(archive_name)
    if os.path.exists(distfile):
        archive = distfile
    else:
        archive = download_chromium_source(version)

    print('Extracting {} to {}...'.format(archive_name, target_dir),
          end='', flush=True)
    tf = tarfile.open(archive)
    members = tf.getmembers()
    print('', end='\r')
    for i, member in enumerate(members):
        print('Extracting {} to {}: {}%'.format(archive_name, target_dir,
                                                round(i / len(members) * 100)),
              end='\r')

        try:
            i = member.name.index('/')
        except ValueError:
            continue

        proper_name = member.name[(i + 1):]

        proper_path = os.path.join(target_dir, proper_name)
        if proper_name:
            if os.path.isfile(proper_path):
                os.unlink(proper_path)
            elif os.path.isdir(proper_path):
                shutil.rmtree(proper_path)
        tf.extract(member, target_dir)
        if proper_name:
            member_path = os.path.join(target_dir, member.name)
            os.rename(member_path, proper_path)

    print()


def download_chromium_source(version):
    archive_name = 'chromium-{}.tar.xz'.format(version)
    url = '{}/{}'.format(CHROMIUM_URL, archive_name)
    archive = os.path.join(CACHEDIR, archive_name)

    print('Downloading {}...'.format(archive_name), end='')

    def progress(block_count, block_size, total_size):
        if total_size > 0:
            pc = round(block_count * block_size / total_size * 100)
            print('Downloading {}: {}%'.format(archive_name, pc), end='\r')

    urllib.request.urlretrieve(url, filename=archive, reporthook=progress)
    print()

    return archive


def unbundle_libs(info, target):
    p = subprocess.run(
        (['build/linux/unbundle/remove_bundled_libraries.py'] +
         info.bundled_libraries + ['--do-remove']),
        cwd=target
    )
    if p.returncode != 0:
        die('could not unbundle libraries')

    p = subprocess.run(
        (['build/linux/unbundle/replace_gn_files.py'] +
         ['--system-libraries'] + info.gn_system_libraries),
        cwd=target
    )
    if p.returncode != 0:
        die('could not unbundle libraries')


if __name__ == '__main__':
    sys.exit(main())
