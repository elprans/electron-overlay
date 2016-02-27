# Copyright 1999-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

EAPI=5

PYTHON_COMPAT=( python2_7 )
inherit git-r3 flag-o-matic python-any-r1 eutils

DESCRIPTION="A hackable text editor for the 21st Century"
HOMEPAGE="https://atom.io"
#SRC_URI="https://github.com/atom/atom/archive/v${MY_PV}.tar.gz -> atom-${PV}.tar.gz"
EGIT_REPO_URI="https://github.com/atom/atom.git"
RESTRICT="mirror"
LICENSE="MIT"
SLOT="0"
KEYWORDS="~amd64"
IUSE=""

DEPEND="
	${PYTHON_DEPS}
	|| ( net-libs/nodejs[npm] net-libs/iojs[npm] )
	>=dev-util/electron-0.36.7:=
	>=dev-util/apm-1.7.0
"
RDEPEND="${DEPEND}"

pkg_setup() {
	python-any-r1_pkg_setup

	npm config set python $PYTHON
}

get_install_suffix() {
	local c=(${SLOT//\// })
	local slot=${c[0]}
	local suffix

	if [[ "${slot}" == "0" ]]; then
		suffix=""
	else
		suffix="-${slot}"
	fi

	echo -n "${suffix}"
}

get_install_dir() {
	echo -n "/usr/$(get_libdir)/atom$(get_install_suffix)"
}

src_prepare() {
	local install_dir="$(get_install_dir)"

	epatch "${FILESDIR}/${PN}-python.patch"
	epatch "${FILESDIR}/${PN}-unbundle-electron-and-apm.patch"

	sed -i  -e "/exception-reporting/d" \
		-e "/metrics/d" package.json

	sed -e "s/<%= description %>/$pkgdesc/" \
		-e "s|<%= installDir %>/share/<%= appFileName %>/atom|/usr/bin/atom|"\
		-e "s|<%= iconPath %>|atom|"\
		-e "s|<%= appName %>|Atom|" \
		resources/linux/atom.desktop.in > resources/linux/Atom.desktop

	sed -i -e "s|{{ATOM_PATH}}|/usr/$(get_libdir)/electron/electron|g" \
		./atom.sh \
		|| die

	sed -i -e "s|{{ATOM_RESOURCE_PATH}}|${install_dir}/app.asar|g" \
		./atom.sh \
		|| die

	# Make bootstrap process more verbose
	sed -i -e 's@node script/bootstrap@node script/bootstrap --no-quiet@g' \
		./script/build \
		|| die "Fail fixing verbosity of script/build"
}

src_compile() {
	local builddir="${WORKDIR}/build"

	mkdir -p "${builddir}" || die
	NPM_CONFIG_NODEDIR="/usr/include/electron/node" \
	NPM_CONFIG_LOGLEVEL="warn" \
		./script/build --verbose --build-dir "${builddir}" \
			|| die "Failed to compile"
	echo "python = $PYTHON" >> "${builddir}/Atom/resources/app/apm/.apmrc"
}

src_install() {
	local install_dir="$(get_install_dir)"
	local builddir="${WORKDIR}/build"
	local suffix="$(get_install_suffix)"

	insinto "${install_dir}"
	doins -r "${builddir}"/Atom/resources/*
	exeinto "${install_dir}"
	newexe "${builddir}/Atom/resources/app/atom.sh" atom
	rm -rf "${ED}/${install_dir}/app" || die
	rm -f "${ED}/${install_dir}/LICENSE.md" || die
	insinto /usr/share/applications
	newins resources/linux/Atom.desktop "atom${suffix}.desktop"
	insinto /usr/share/pixmaps
	newins resources/app-icons/stable/png/128.png "atom${suffix}.png"
	insinto /usr/share/licenses/"${PN}${suffix}"
	doins LICENSE.md
	dosym "${install_dir}/atom" "/usr/bin/atom${suffix}"
}
