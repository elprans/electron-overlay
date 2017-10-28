#!/bin/bash

set -ex

docker run \
    -v "${TRAVIS_BUILD_DIR}":/overlay \
    -v "${HOME}/.ccache":/var/tmp/ccache \
    -e GENTOO_USE="${GENTOO_USE}" \
    -e GENTOO_PACKAGE="${GENTOO_PACKAGE}" \
    gentoo/stage3-amd64 /overlay/.ci/gentoo/build.sh
