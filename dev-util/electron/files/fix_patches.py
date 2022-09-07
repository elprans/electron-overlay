#!/usr/bin/env python

from __future__ import print_function

import argparse
import glob
import json
import os
import os.path
import sys

import unidiff


PY2 = sys.version_info[0] == 2
if not PY2:
    unicode = str


def parse_args():
    parser = argparse.ArgumentParser(description="List Electron patches")
    parser.add_argument(
        "config",
        nargs="+",
        type=argparse.FileType("r"),
        help="patches' config(s) the JSON format",
    )
    return parser.parse_args()


def die(msg):
    print("ERROR: {}".format(msg), file=sys.stderr)
    sys.exit(1)


def note(msg):
    print("    >>> {}".format(msg), file=sys.stderr)


def main():
    configs = parse_args().config
    for config_json in configs:
        note(f"Cleaning up Electron patches declared in {config_json.name}...")
        for patch_dir, repo in json.load(config_json).items():
            index = os.path.join(patch_dir, ".patches")
            if not os.path.isfile(index):
                die("patch index does not exist in {}".format(patch_dir))

            with open(index) as f:
                patches = [line.strip() for line in f.readlines()]
            patches_set = set(patches)

            for fn in os.listdir(patch_dir):
                fpath = os.path.join(patch_dir, fn)
                if (
                    os.path.isfile(fpath)
                    and (
                        fpath.endswith(".patch")
                        or fpath.endswith(".diff")
                    )
                    and fn not in patches_set
                ):
                    note("Removing redundant {}".format(fn))
                    os.unlink(fpath)

            for i, patch_name in enumerate(patches):
                patch_path = os.path.join(patch_dir, patch_name)
                if not os.path.isfile(patch_path):
                    die("patch does not exist: {}".format(patch_path))

                new_patch_name = "{i:04}-{patch_name}".format(
                    i=i,
                    patch_name=patch_name,
                )
                new_patch_path = os.path.join(patch_dir, new_patch_name)
                os.rename(patch_path, new_patch_path)

                patch = unidiff.PatchSet.from_filename(
                    new_patch_path,
                    encoding="utf-8",
                )
                patched_files = []
                removals = False
                for file in patch:
                    if not file.source_file.endswith("/dev/null"):
                        source_file = os.path.join(
                            repo,
                            "/".join(file.source_file.split("/")[1:]),
                        )
                    else:
                        continue

                    if not os.path.exists(source_file):
                        note(
                            "Patch source file {} "
                            "does not exist, skipping.".format(source_file)
                        )
                        removals = True
                    else:
                        patched_files.append(file)

                if removals:
                    if patched_files:
                        with open(new_patch_path, "w") as f:
                            f.write(
                                "".join(str(pf) for pf in patched_files),
                            )
                    else:
                        note("Removing redundant {}".format(new_patch_path))
                        os.unlink(new_patch_path)

            if not os.path.exists(repo) or (
                not glob.glob(os.path.join(patch_dir, "*.patch"))
                and not glob.glob(os.path.join(patch_dir, "*.diff"))
            ):
                continue

            print("{}:{}".format(patch_dir, repo))


if __name__ == "__main__":
    main()
