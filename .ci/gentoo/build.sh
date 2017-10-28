#!/bin/bash

set -ex

emerge-webrsync
eselect profile set default/linux/amd64/13.0/desktop
cat "/overlay/.ci/gentoo/make.conf" >> /etc/portage/make.conf

ACCEPT_KEYWORDS="~amd64" emerge -v ccache cpuid2cpuflags

mkdir -p /etc/portage/package.use/
echo "*/* $(cpuid2cpuflags)" >> /etc/portage/package.use/00cpuflags

USE="${GENTOO_USE}" emerge -DNuv @world
USE="${GENTOO_USE}" emerge -vo ${GENTOO_PACKAGE}
USE="${GENTOO_USE}" emerge -v --jobs=1 ${GENTOO_PACKAGE}
