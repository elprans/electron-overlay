#!/usr/bin/env python3
#
# This script is used to automate the creation of app-editors/atom
# ebuilds using a template file and upstream dependency tree
# introspection.


import argparse
import collections
import concurrent.futures
import json
import operator
import os
import os.path
import pickle
import re
import shutil
import string
import subprocess
import sys
import textwrap
import traceback
import urllib.error
import urllib.parse
import urllib.request


ATOM_REPO_URL = 'https://github.com/atom/atom.git'
ATOM_REGISTRY = 'https://atom.io/api/packages/'
NPM_REGISTRY = 'https://registry.npmjs.org/'
VSCODE_REPO_URL = 'https://github.com/Microsoft/vscode.git'

CACHEHOME = os.environ.get(
    'XDG_CACHE_HOME', os.path.expandvars('$HOME/.cache'))

CACHEDIR = os.path.join(CACHEHOME, 'atom-ebuild-gen')


urlopener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)


class Template(string.Template):
    delimiter = '@@'


def main():
    args = parse_args()

    if args.test_version_parser:
        p = parse_version_range(args.test_version_parser)
        import pprint
        pprint.pprint(p)
        return 0

    if args.test_package_metadata:
        package, _, version = args.test_package_metadata.partition(' ')
        metadata = get_package_metadata(package, version)
        import pprint
        pprint.pprint(metadata)
        return 0

    if args.target == 'atom':
        args.repo_url = ATOM_REPO_URL
    elif args.target == 'vscode':
        args.repo_url = VSCODE_REPO_URL
    else:
        die('unsupported target: {}'.format(args.target))

    os.makedirs(CACHEDIR, exist_ok=True)

    update_repo(args.repo_url)
    target_tags = get_tags(repodir(args.repo_url))
    target_stable_versions = list(filter(
        lambda v: not v[0].pre, target_tags.items()))
    target_beta_versions = list(filter(
        lambda v: v[0].pre and v[0].pre[0].startswith('beta'),
        target_tags.items()))

    if not args.target_version:
        target_version = 'stable'
    else:
        target_version = args.target_version

    if target_version == 'stable':
        requested_v, sha = target_stable_versions[0]
    elif target_version == 'beta':
        requested_v, sha = target_beta_versions[0]
    else:
        requested_v = parse_version(target_version)

        if requested_v is None:
            die('Invalid --target-version: {!r}'.format(target_version))

        if requested_v not in target_tags:
            die('Unknown --target-version: {!r}'.format(target_version))

        sha = target_tags[requested_v]

    print('Using {} version {} ({}).'.format(
        args.target, format_version(requested_v), sha))

    deps = get_target_deps(args, sha)

    template = args.template
    if not template:
        template = os.path.join(os.path.dirname(__file__),
                                '{}.template.ebuild'.format(args.target))

    output = generate_ebuild(args.target, target_version, deps, template)

    if args.output:
        output_fn = args.output
    else:
        outdir = args.output_directory
        if not outdir:
            outdir = os.getcwd()

        target_v = format_version(requested_v, as_gentoo_atom=True)
        fn = '{target}-{v}.ebuild'.format(target=args.target, v=target_v)
        output_fn = os.path.join(outdir, fn)

    if output_fn == '-':
        print(output, end='')
    else:
        with open(output_fn, 'wt') as f:
            print(output, end='', file=f)

    return 0


def get_target_deps(args, sha):
    try:
        cache_fn = os.path.join(CACHEDIR, 'depcache-{}'.format(sha))
        with open(cache_fn, 'rb') as f:
            deps = pickle.load(f)
    except Exception as e:
        print('Could not load dependency cache: {}'.format(
            traceback.format_exception_only(type(e), e)
        ))
        print('Introspecting dependencies...')
        deps = None

    if deps is None:
        if args.target == 'atom':
            deps = find_atom_deps(args, sha)
        elif args.target == 'vscode':
            deps = find_vscode_deps(args, sha)
        else:
            die('unsupported target: {}'.format(args.target))

    try:
        cache_fn = os.path.join(CACHEDIR, 'depcache-{}'.format(sha))
        with open(cache_fn, 'wb') as f:
            pickle.dump(deps, file=f)
    except Exception as e:
        print('Could not store dependency cache: {}'.format(
            traceback.format_exception_only(type(e), e)
        ))

    return deps


def find_atom_deps(args, sha):
    package_json = get_repo_package_json(repodir(args.repo_url), sha=sha)
    electron_version = package_json['electronVersion']

    binary_deps = {}

    npm_deps = package_json['dependencies']
    find_binary_deps(npm_deps, binary_deps, parents=['atom'])

    apm_package_json = get_repo_package_json(repodir(args.repo_url), sha=sha,
                                             path='apm/package.json')

    apm_deps = apm_package_json['dependencies']
    find_binary_deps(apm_deps, binary_deps, parents=['atom'])

    atomio_deps = package_json['packageDependencies']
    find_binary_deps(atomio_deps, binary_deps, parents=['atom'],
                     registries=(ATOM_REGISTRY, NPM_REGISTRY))

    return (
        electron_version,
        list(sorted(binary_deps.values(), key=lambda d: d.package)),
    )


def find_vscode_deps(args, sha):
    package_json = get_repo_package_json(repodir(args.repo_url), sha=sha)
    yarnrc = get_repo_file(repodir(args.repo_url), path='.yarnrc', sha=sha)
    for line in yarnrc.split('\n'):
        k, v, *_ = re.split('\s+', line)
        if k == 'target':
            electron_version = v.strip('"')
            break
    else:
        die('could not determine Electron version from vscode/.yarnrc')

    binary_deps = {}

    npm_deps = package_json['dependencies']
    find_binary_deps(npm_deps, binary_deps, parents=['atom'])

    return (
        electron_version,
        list(sorted(binary_deps.values(), key=lambda d: d.package)),
    )


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-version', default='stable',
                        help='Target version to create the ebuild for.  '
                             'Use "stable" for the latest stable version, '
                             'and "beta" for the latest beta version. '
                             'Defaults to "stable".')
    parser.add_argument('-O', '--output-directory',
                        help='The directory where the ebuild will be '
                             'created.  Defaults to current directory.')
    parser.add_argument('-o', '--output',
                        help='Output file name.  '
                             'Defaults to "<target>-<version>.ebuild" in the '
                             'directory specified by --output-directory.  '
                             'Pass "-" to output to stdout.')
    parser.add_argument('-t', '--template',
                        help='Path to the template file.  '
                             'The default is "atom.ebuild.template" in the '
                             'directory of the script.')

    parser.add_argument('-V', '--test-version-parser')
    parser.add_argument('-M', '--test-package-metadata')
    parser.add_argument('target', choices=['atom', 'vscode'],
                        help='The target to generate an ebuild for.')

    return parser.parse_args()


def generate_ebuild(target, target_version, deps, template_fn):
    with open(template_fn, 'rt') as f:
        template = Template(f.read())

    pkgs = []
    vers = []
    urls = []

    electron_version, packages = deps

    electron_v = parse_version(electron_version)
    electron_slot = '{}.{}'.format(electron_v.major, electron_v.minor)

    for pkg in packages:
        name = pkg.package.strip('@').replace('/', '--')
        varname = name.upper().replace('-', '_')

        urls.append(
            '{} -> {}dep-{}-${{{}_V}}.tar.gz'.format(
                pkg.archive, target, name, varname))
        pkgs.append(name)
        vers.append('{}_V={}'.format(varname, pkg.version))

    return template.substitute({
        'SLOT': 'beta' if target_version == 'beta' else '0',
        'KEYWORDS': '~amd64',
        'ELECTRON_V': electron_version,
        'ELECTRON_S': electron_slot,
        'SRC_URI': textwrap.indent('\n'.join(urls), '\t'),
        'BINMODS': textwrap.indent('\n'.join(pkgs), '\t'),
        'BINMOD_VERSIONS': '\n'.join(vers)
    })


def die(msg, *, exitcode=1):
    print(msg, file=sys.stderr)
    sys.exit(exitcode)


_ver_re = re.compile(r'''
    ^
        v?
        (?P<major>\d+)
        (?:
            \. (?P<minor>\d+)
            (?:
                \. (?P<patch>\d+)
            )?
        )?
        (?:
            -
            (?P<pre>
                [0-9A-Za-z-]+
                (?:
                    \.
                    [0-9A-Za-z-]+
                )*
            )
        )?
        (?:
            \+
            (?P<meta>
                [0-9A-Za-z-]+
                (?:
                    \.
                    [0-9A-Za-z-]+
                )*
            )
        )?
    $
''', re.X)


Version = collections.namedtuple(
    'Version', ['major', 'minor', 'patch', 'pre']
)


VersionShape = collections.namedtuple(
    'VersionShape', ['major', 'minor', 'patch', 'pre']
)


Dependency = collections.namedtuple(
    'Dependency', ['package', 'version', 'repository', 'archive']
)


def format_version(v, as_gentoo_atom=False):
    version = '{}.{}.{}'.format(v.major, v.minor, v.patch)
    if v.pre:
        if as_gentoo_atom:
            version += '_'
        else:
            version += '-'

        version += '.'.join(v.pre)

    return version


def parse_version(s):
    m = _ver_re.match(s)
    if not m:
        return None
    else:
        pre = m.group('pre')
        if pre:
            pre = tuple(pre.split('.'))
        else:
            pre = ()

        # Note that we intentionally ignore meta fields,
        # as they are useless for our purposes here.

        return Version(
            major=int(m.group('major')),
            minor=int(m.group('minor') or 0),
            patch=int(m.group('patch') or 0),
            pre=pre,
        )


# See https://docs.npmjs.com/misc/semver

_nr_re_text = r'''(?:
    0 |
    (?:[1-9][0-9]*)
)'''

_xr_re_text = r'''(?:
    ( x | X | \* | {nr} )
)'''.format(nr=_nr_re_text)

_parts_re_text = r'''(?:
    [0-9A-Za-z-]+
    (?:
        \.
        [0-9A-Za-z-]+
    )*
)'''

_qualifier_re_text = r'''(?:
    ( - {parts} )? ( \+ {parts} )?
)'''.format(parts=_parts_re_text)

_partial_re_text = r'''(?:
    {xr} ( \. {xr} ( \. {xr} {qualifier}? )? )?
)'''.format(xr=_xr_re_text, qualifier=_qualifier_re_text)

_partial_re = re.compile(r'''
    (?P<major>{xr})
    (
        \.
        (?P<minor>{xr})
        (
            \.
            (?P<patch>{xr})
            ( - (?P<pre>{parts}) )? ( \+ (?P<meta>{parts}) )?
        )?
    )?
'''.format(xr=_xr_re_text, parts=_parts_re_text), re.X)

_ops_re_text = r'''(?:
    >= | <= | > | < | =
)'''

_simple_re_text = r'''(?:
    (?P<op> {ops} | \~ | \^ )? \s*
    (?P<ver> {partial} )
)'''.format(ops=_ops_re_text, partial=_partial_re_text)

_hyphen_re = re.compile(r'''(?:
    (?P<lower> {partial} ) \s+ - \s+ (?P<upper> {partial} )
)'''.format(partial=_partial_re_text), re.X)

_simple_re = re.compile(r'''
    \s* {simple}
'''.format(simple=_simple_re_text), re.X)


def _normalize_ver(s):
    m = _partial_re.match(s)

    kw = {}
    shape_kw = {}

    for part in ('major', 'minor', 'patch'):
        v = m.group(part)
        xrange = not v or v in 'xX*'
        shape_kw[part] = '*' if xrange else True
        if xrange:
            v = 0
        else:
            v = int(v)
        kw[part] = v

    if m.group('pre'):
        kw['pre'] = tuple(m.group('pre').split('.'))
        shape_kw['pre'] = True
    else:
        kw['pre'] = ()
        shape_kw['pre'] = False

    return Version(**kw), VersionShape(**shape_kw)


operators = {
    '>': operator.gt,
    '<': operator.lt,
    '>=': operator.ge,
    '<=': operator.le,
    '=': operator.eq
}


def _operator_for_op(op):
    if not op:
        op = '='

    if op not in operators:
        die('unrecognized version spec operator: {}'.format(op))
    else:
        return operators[op]


def parse_version_range(s):
    alternatives = []

    for alternative in s.split('||'):
        alternative = alternative.strip()
        if not alternative:
            alternative = '*'

        specs = set()

        m = _hyphen_re.match(alternative)
        if m:
            lower = _normalize_ver(m.group('lower'))[0]
            upper = _normalize_ver(m.group('upper'))[0]
            specs.update([
                (operator.ge, lower),
                (operator.le, upper)
            ])
            continue

        mm = _simple_re.finditer(alternative)

        for m in mm:
            op = m.group('op')
            ver, vershape = _normalize_ver(m.group('ver'))

            if op == '^':
                lower = ver

                if ver.major == 0:
                    if ver.minor == 0:
                        # ^0.0.x := >=0.0.x <0.0.(x+1)
                        upper = Version(
                            ver.major, ver.minor, ver.patch + 1, ())
                    else:
                        # ^0.x.y := >=0.x.y <0.(x+1).0
                        upper = Version(ver.major, ver.minor + 1, 0, ())
                else:
                    # ^x.y.z := >=x.y.z <(x+1).0.0
                    upper = Version(ver.major + 1, 0, 0, ())

                specs.update([
                    (operator.ge, lower),
                    (operator.lt, upper)
                ])

            elif op == '~':
                lower = ver

                if vershape.minor:
                    # ~x.y := >=x.y <x.(y+1)
                    upper = Version(ver.major, ver.minor + 1, 0, ())
                else:
                    # ~x := >=x <(x+1)
                    upper = Version(ver.major + 1, 0, 0, ())

                specs.update([
                    (operator.ge, lower),
                    (operator.lt, upper)
                ])

            elif not op and vershape.major == '*':
                specs.add(
                    (operator.ge, Version(0, 0, 0, ()))
                )

            elif not op and vershape.minor == '*':
                specs.update([
                    (operator.ge, ver),
                    (operator.lt, Version(ver.major + 1, 0, 0, ()))
                ])

            elif not op and vershape.patch == '*':
                specs.update([
                    (operator.ge, ver),
                    (operator.lt, Version(ver.major, ver.minor + 1, 0, ()))
                ])

            else:
                specs.add((_operator_for_op(op), ver))

        if not specs:
            raise ValueError('cannot parse version range: {}'.format(s))

        alternatives.append(specs)

    return alternatives


def match_spec(ranges, v):
    return all(op(v, v2) for op, v2 in ranges)


def match_version(spec, versions):
    for v in sorted(versions, reverse=True):
        if any(match_spec(alternative, v) for alternative in spec):
            return v
    else:
        return None


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
        'universal_newlines': True,
    }

    default_kwargs.update(kwargs)

    print(' '.join(cmd))
    p = subprocess.Popen(cmd, **default_kwargs)
    result = p.wait()

    if result != 0:
        die('{} failed with exit code {}'.format(' '.join(cmd), result))

    return p.stdout.read()


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


def get_tags(reponame):
    repo_dir = os.path.join(CACHEDIR, reponame)
    tags = []
    fmt = '--format=%(objectname):%(refname:strip=2)'
    for tag in git('tag', fmt, cwd=repo_dir).split('\n'):
        if not tag.strip():
            continue

        sha, _, name = tag.partition(':')

        if not re.match(r'v?\d+(\.\d.)*', name):
            continue

        if name[0] == 'v':
            name = name[1:]

        tags.append((parse_version(name), sha))

    return collections.OrderedDict(
        sorted(tags, key=lambda v: v[0], reverse=True))


def get_repo_file(reponame, path, sha='HEAD'):
    repo_dir = os.path.join(CACHEDIR, reponame)
    return git('show', '{}:{}'.format(sha, path), cwd=repo_dir)


def get_repo_package_json(reponame, sha='HEAD', path='package.json'):
    package_json = get_repo_file(reponame, path=path, sha=sha)

    try:
        package_json = json.loads(package_json)
    except Exception as e:
        die('could not read {}/{}: {}'.format(
            reponame, path, traceback.format_exception_only(type(e), e)
        ))

    return package_json


def get_repo_metadata(repo_url, refspec):
    update_repo(repo_url)
    name = repodir(repo_url)

    if isinstance(refspec, str):
        # We were given a commit-ish
        version = refspec
    else:
        # We were given a semver
        tags = get_tags(name)
        tag = match_version(refspec, tags)

        if not tag:
            raise RuntimeError('refspec {} not found in {}'.format(
                refspec, repo_url
            ))

        version = tags[tag]

    return get_repo_package_json(name, sha=version)


def get_dependencies_from_repo(reponame, sha='HEAD'):
    package_json = get_repo_package_json(reponame, sha=sha)
    return package_json.get('dependencies', [])


def _get_npm_metadata(package, version, registry):
    url = registry + urllib.parse.quote_plus(package, safe='@')

    try:
        response = urlopener.open(url)
    except urllib.error.HTTPError as e:
        raise LookupError(
            'could not fetch npm metadata for {}: {}'.format(
                package, traceback.format_exception_only(type(e), e)))

    metadata_json = response.read().decode('utf-8')
    metadata = json.loads(metadata_json)

    versions = metadata.get('versions')
    if not versions:
        raise LookupError(
            '{} is missing versions in its metadata'.format(package))

    parsed_versions = {
        parse_version(v): v for v in versions
    }

    ver_spec = parse_version_range(version)

    pkg_ver = match_version(ver_spec, parsed_versions)
    if pkg_ver is None:
        raise LookupError(
            'could not find package {!r} version '
            '{}, available: {}'.format(
                package, version, ', '.join(versions)))

    ver_str = parsed_versions[pkg_ver]
    ver_metadata = versions[ver_str]

    return ver_metadata


def get_npm_metadata(package, version, registries):
    for i, registry in enumerate(registries):
        try:
            return _get_npm_metadata(package, version, registry)
        except LookupError:
            if i == len(registries) - 1:
                raise
            else:
                continue


def get_package_metadata(package, version, registries):
    if version.startswith('git+'):
        # git version
        r = urllib.parse.urlparse(version)
        if r.fragment:
            if r.fragment.startswith('semver:'):
                semver = r.fragment[len('semver:'):]
                ref_spec = parse_version_range(semver)
            else:
                ref_spec = r.fragment
        else:
            ref_spec = 'master'

        scheme = r.scheme[len('git+'):]
        repo_url = urllib.parse.urlunparse(
            (scheme, r.netloc, r.path, r.params, r.query, None)
        )
        return get_repo_metadata(repo_url, ref_spec)
    else:
        return get_npm_metadata(package, version, registries)


def get_package_archive(repo_url, version):
    r = urllib.parse.urlparse(repo_url)

    if r.scheme not in {'git+https', 'https', 'http', 'git'}:
        die('Unsupported package repo URL: {}'.format(repo_url))

    if r.netloc != 'github.com':
        die('Unsupported package repo URL: {}'.format(repo_url))

    if r.path.endswith('.git'):
        path = r.path[:-len('.git')]
    else:
        path = r.path

    scheme = 'https'
    archive_path = '{}/archive/v{}.tar.gz'.format(path, version)

    return urllib.parse.urlunparse(
        (scheme, r.netloc, archive_path, None, None, None)
    )


def is_binary(metadata):
    # Detect if the package is binary from its npm metadata.
    if metadata.get('gypfile'):
        return True
    deps = metadata.get('dependencies', {})
    if deps.get('nan') or deps.get('node-pre-gyp'):
        return True
    devdeps = metadata.get('devDependencies', {})
    if devdeps.get('node-pre-gyp'):
        return True
    return False


def find_binary_deps(deps, result, *, memo=set(), parents,
                     registries=(NPM_REGISTRY,)):
    resolved_deps = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as e:
        work = {
            e.submit(get_package_metadata, pkg, ver_str, registries):
            (pkg, ver_str)
            for pkg, ver_str in deps.items()
            if (not ver_str.startswith('file:') and  # skip bundled packages
                not ver_str.startswith('https:'))  # and atom.io refs
        }

        for future in concurrent.futures.as_completed(work):
            package, version = work[future]
            memo.add(package)

            try:
                metadata = future.result()
            except Exception as e:
                die('could not load npm metadata for {}: {}'.format(
                    package, traceback.format_exception_only(type(e), e)
                ))

            pkg_deps = metadata.get('dependencies', {})
            str_ver = metadata.get('version')
            pkg_ver = parse_version(str_ver)
            pkg_os = metadata.get('os')
            if pkg_os and 'linux' not in pkg_os:
                continue

            dist = metadata.get('dist')
            if dist:
                archive = dist.get('tarball')
            else:
                archive = None

            repository = metadata.get('repository')
            if isinstance(repository, dict):
                repository = repository['url']

            if is_binary(metadata):
                previous = result.get(package)
                if previous is not None:
                    if previous.version != pkg_ver:
                        die('Dependency conflict: {pkg} version {ver0} '
                            'is needed by {dep0}, but verion {ver1} is '
                            'needed by {dep1}.'.format(
                                pkg=package,
                                ver0=format_version(previous.version),
                                dep0=', '.join(previous.dependents),
                                ver1=format_version(pkg_ver),
                                dep1=', '.join(parents)))
                else:
                    if repository and archive is None:
                        archive = get_package_archive(repository, str_ver)

                    result[package] = Dependency(
                        package=package, version=str_ver,
                        repository=repository, archive=archive)

            resolved_deps[package] = pkg_deps

    new_deps = {}
    new_parents = set()

    for pkg, pkg_deps in resolved_deps.items():
        for dep, spec_str in pkg_deps.items():
            if dep in memo:
                continue

            new_parents.add(pkg)
            prev_spec = new_deps.get(dep)
            if prev_spec is None:
                new_deps[dep] = spec_str

    if new_deps:
        find_binary_deps(new_deps, result, parents=new_parents,
                         registries=registries)


if __name__ == '__main__':
    sys.exit(main())
