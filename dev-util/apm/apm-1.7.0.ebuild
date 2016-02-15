# Copyright 1999-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

EAPI=5

PYTHON_COMPAT=( python2_7 )
inherit flag-o-matic python-any-r1 eutils

DESCRIPTION="Atom Package Manager"
HOMEPAGE="https://atom.io"
SRC_URI="https://github.com/atom/apm/archive/v${PV}.tar.gz -> ${P}.tar.gz"
RESTRICT="mirror"
LICENSE="MIT"
SLOT="0"
KEYWORDS="~amd64"
IUSE=""

DEPEND="
	${PYTHON_DEPS}
	>=dev-util/electron-0.36.7:=
	>=net-libs/nodejs-5.1.0[npm]
"
RDEPEND="${DEPEND}"

pkg_setup() {
	python-any-r1_pkg_setup
	npm config set python $PYTHON
}

get_install_dir() {
	echo -n "/usr/$(get_libdir)/electron/node_modules/apm"
}

src_prepare() {
	sed -i -e "/download-node/d" package.json || die
	sed -i -e "/npm/d" package.json || die
	local env="export NPM_CONFIG_NODEDIR=/usr/include/electron/node/"
	sed -i -e \
		"s|\"\$binDir/\$nodeBin\" --harmony_collections|${env}\nexec node|g" \
			bin/apm || die
}

src_compile() {
	npm install coffeelint || die
	NPM_CONFIG_NODEDIR=/usr/include/electron/node \
		npm install || die
	node_modules/.bin/grunt || die
}

src_install() {
	local install_dir="$(get_install_dir)"
	insinto "${install_dir}"
	doins package.json
	doins deprecated-packages.json
	doins -r templates
	doins -r lib
	cp -a node_modules "${ED}/${install_dir}"
	dodir "${install_dir}/bin"
	exeinto "${install_dir}/bin"
	doexe bin/apm
}
