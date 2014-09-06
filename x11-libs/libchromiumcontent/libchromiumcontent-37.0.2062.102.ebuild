# Copyright 1999-2014 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: $

EAPI="5"
PYTHON_COMPAT=( python{2_6,2_7} )

CHROMIUM_LANGS="am ar bg bn ca cs da de el en_GB es es_LA et fa fi fil fr gu he
	hi hr hu id it ja kn ko lt lv ml mr ms nb nl pl pt_BR pt_PT ro ru sk sl sr
	sv sw ta te th tr uk vi zh_CN zh_TW"

inherit chromium eutils flag-o-matic git-2 multilib multiprocessing pax-utils \
	portability python-any-r1 toolchain-funcs versionator virtualx

DESCRIPTION="Open-source version of Google Chrome web browser"
HOMEPAGE="http://chromium.org/"
SRC_URI="https://commondatastorage.googleapis.com/chromium-browser-official/chromium-${PV}-lite.tar.xz"
LCC_EGIT_REPO_URI="https://github.com/brightray/libchromiumcontent.git"
LCC_EGIT_COMMIT="ef6f735cf946570a89bd6269121e1cd0911da4ab"
LCC_EGIT_SOURCEDIR="${WORKDIR}/${P}"
LCC_S="${LCC_EGIT_SOURCEDIR}"
S="${WORKDIR}/chromium-${PV}"

LICENSE="BSD"
SLOT="0"
KEYWORDS="amd64 ~arm ~x86"
IUSE="bindist cups custom-cflags gnome gnome-keyring kerberos neon pic pulseaudio selinux +tcmalloc"

# Native Client binaries are compiled with different set of flags, bug #452066.
QA_FLAGS_IGNORED=".*\.nexe"

# Native Client binaries may be stripped by the build system, which uses the
# right tools for it, bug #469144 .
QA_PRESTRIPPED=".*\.nexe"

RDEPEND=">=app-accessibility/speech-dispatcher-0.8:=
	app-arch/bzip2:=
	app-arch/snappy:=
	cups? (
		dev-libs/libgcrypt:0=
		>=net-print/cups-1.3.11:=
	)
	>=dev-libs/elfutils-0.149
	dev-libs/expat:=
	dev-libs/glib:=
	dev-libs/icu:=
	>=dev-libs/jsoncpp-0.5.0-r1:=
	>=dev-libs/libevent-1.4.13:=
	dev-libs/libxml2:=[icu]
	dev-libs/libxslt:=
	dev-libs/nspr:=
	>=dev-libs/nss-3.14.3:=
	dev-libs/re2:=
	gnome? ( >=gnome-base/gconf-2.24.0:= )
	gnome-keyring? ( >=gnome-base/libgnome-keyring-3.12:= )
	>=media-libs/alsa-lib-1.0.19:=
	media-libs/flac:=
	media-libs/fontconfig:=
	media-libs/freetype:=
	>=media-video/ffmpeg-2.2.7:=
	media-libs/harfbuzz:=[icu(+)]
	media-libs/libexif:=
	>=media-libs/libjpeg-turbo-1.2.0-r1:=
	media-libs/libpng:0=
	>=media-libs/libwebp-0.4.0:=
	media-libs/speex:=
	pulseaudio? ( media-sound/pulseaudio:= )
	sys-apps/dbus:=
	sys-apps/pciutils:=
	>=sys-libs/libcap-2.22:=
	sys-libs/zlib:=[minizip]
	virtual/udev
	x11-libs/cairo:=
	x11-libs/gdk-pixbuf:=
	x11-libs/gtk+:2=
	x11-libs/libdrm
	x11-libs/libX11:=
	x11-libs/libXcomposite:=
	x11-libs/libXcursor:=
	x11-libs/libXdamage:=
	x11-libs/libXext:=
	x11-libs/libXfixes:=
	>=x11-libs/libXi-1.6.0:=
	x11-libs/libXinerama:=
	x11-libs/libXrandr:=
	x11-libs/libXrender:=
	x11-libs/libXScrnSaver:=
	x11-libs/libXtst:=
	x11-libs/pango:=
	kerberos? ( virtual/krb5 )
	selinux? ( sec-policy/selinux-chromium )"
DEPEND="${RDEPEND}
	!arm? (
		dev-lang/yasm
	)
	dev-lang/perl
	dev-perl/JSON
	>=dev-util/gperf-3.0.3
	dev-util/ninja
	sys-apps/hwids[usb(+)]
	>=sys-devel/bison-2.4.3
	sys-devel/flex
	virtual/pkgconfig"

# For nvidia-drivers blocker, see bug #413637 .
RDEPEND+="
	x11-misc/xdg-utils
	virtual/ttf-fonts
	tcmalloc? ( !<x11-drivers/nvidia-drivers-331.20 )"

# Python dependencies. The DEPEND part needs to be kept in sync
# with python_check_deps.
DEPEND+=" $(python_gen_any_dep '
	dev-python/simplejson[${PYTHON_USEDEP}]
')"
python_check_deps() {
	has_version "dev-python/simplejson[${PYTHON_USEDEP}]"
}

if ! has chromium_pkg_die ${EBUILD_DEATH_HOOKS}; then
	EBUILD_DEATH_HOOKS+=" chromium_pkg_die";
fi

pkg_setup() {
	if [[ "${SLOT}" == "0" ]]; then
		CHROMIUM_SUFFIX=""
	else
		CHROMIUM_SUFFIX="-${SLOT}"
	fi
	CHROMIUM_HOME="/usr/$(get_libdir)/libchromiumcontent${CHROMIUM_SUFFIX}"
	CHROMIUM_INCLUDE="/usr/include/libchromiumcontent${CHROMIUM_SUFFIX}"

	# Make sure the build system will use the right python, bug #344367.
	python-any-r1_pkg_setup

	chromium_suid_sandbox_check_kernel_config

	if use bindist; then
		elog "bindist enabled: H.264 video support will be disabled."
	else
		elog "bindist disabled: Resulting binaries may not be legal to re-distribute."
	fi
}

src_unpack() {
	EGIT_REPO_URI=${LCC_EGIT_REPO_URI} \
	EGIT_COMMIT=${LCC_EGIT_COMMIT} \
	EGIT_SOURCEDIR=${LCC_EGIT_SOURCEDIR} \
		git-2_src_unpack
}

_unnest_patches() {
	local _s="${1%/}/" relpath out

	for f in $(find "${_s}" -mindepth 2 -name *.patch -printf \"%P\"\\n); do
		relpath="$(dirname ${f})"
		out="${_s}/${relpath////_}_$(basename ${f})"
		sed -r -e "s|^([-+]{3}) (.*)$|\1 ${relpath}/\2 ${f}|g" > "${out}"
	done
}

src_prepare() {
	# if ! use arm; then
	#	mkdir -p out/Release/gen/sdk/toolchain || die
	#	# Do not preserve SELinux context, bug #460892 .
	#	cp -a --no-preserve=context /usr/$(get_libdir)/nacl-toolchain-newlib \
	#		out/Release/gen/sdk/toolchain/linux_x86_newlib || die
	#	touch out/Release/gen/sdk/toolchain/linux_x86_newlib/stamp.untar || die
	# fi

	# libcc patches
	cd "${LCC_S}"
	epatch "${FILESDIR}/libchromiumcontent-gentoo-build-fixes.patch"

	# chromium patches
	cd "${S}"
	epatch "${FILESDIR}/chromium-angle-r1.patch"

	_unnest_patches "${LCC_S}/patches"

	EPATCH_SOURCE="${LCC_S}/patches" \
	EPATCH_SUFFIX="patch" \
	EPATCH_FORCE="yes" \
	EPATCH_EXCLUDE="third_party_icu*" \
	EPATCH_MULTI_MSG="Applying libchromiumcontent patches..." \
		epatch

	# build scripts
	mkdir -p "${S}/chromiumcontent"
	cp -a "${LCC_S}/chromiumcontent" "${S}/" || die
	cp -a "${LCC_S}/tools/linux/" "${S}/tools/" || die

	epatch_user

	# Remove most bundled libraries. Some are still needed.
	build/linux/unbundle/remove_bundled_libraries.py \
		'base/third_party/dmg_fp' \
		'base/third_party/dynamic_annotations' \
		'base/third_party/icu' \
		'base/third_party/nspr' \
		'base/third_party/superfasthash' \
		'base/third_party/symbolize' \
		'base/third_party/valgrind' \
		'base/third_party/xdg_mime' \
		'base/third_party/xdg_user_dirs' \
		'breakpad/src/third_party/curl' \
		'chrome/third_party/mozilla_security_manager' \
		'courgette/third_party' \
		'crypto/third_party/nss' \
		'net/third_party/mozilla_security_manager' \
		'net/third_party/nss' \
		'third_party/WebKit' \
		'third_party/angle' \
		'third_party/brotli' \
		'third_party/cacheinvalidation' \
		'third_party/cld' \
		'third_party/cros_system_api' \
		'third_party/dom_distiller_js' \
		'third_party/ffmpeg' \
		'third_party/fips181' \
		'third_party/flot' \
		'third_party/hunspell' \
		'third_party/iccjpeg' \
		'third_party/icu/icu.isolate' \
		'third_party/jinja2' \
		'third_party/jstemplate' \
		'third_party/khronos' \
		'third_party/leveldatabase' \
		'third_party/libaddressinput' \
		'third_party/libjingle' \
		'third_party/libphonenumber' \
		'third_party/libsrtp' \
		'third_party/libusb' \
		'third_party/libvpx' \
		'third_party/libwebm' \
		'third_party/libxml/chromium' \
		'third_party/libXNVCtrl' \
		'third_party/libyuv' \
		'third_party/lss' \
		'third_party/lzma_sdk' \
		'third_party/markupsafe' \
		'third_party/mesa' \
		'third_party/modp_b64' \
		'third_party/mt19937ar' \
		'third_party/npapi' \
		'third_party/opus' \
		'third_party/ots' \
		'third_party/pdfium' \
		'third_party/polymer' \
		'third_party/ply' \
		'third_party/protobuf' \
		'third_party/pywebsocket' \
		'third_party/qcms' \
		'third_party/readability' \
		'third_party/sfntly' \
		'third_party/skia' \
		'third_party/smhasher' \
		'third_party/sqlite' \
		'third_party/tcmalloc' \
		'third_party/tlslite' \
		'third_party/trace-viewer' \
		'third_party/undoview' \
		'third_party/usrsctp' \
		'third_party/webdriver' \
		'third_party/webrtc' \
		'third_party/widevine' \
		'third_party/x86inc' \
		'third_party/zlib/google' \
		'url/third_party/mozilla' \
		'v8/src/third_party/valgrind' \
		--do-remove || die
}

src_configure() {
	local myconf=""

	# Never tell the build system to "enable" SSE2, it has a few unexpected
	# additions, bug #336871.
	myconf+=" -Ddisable_sse2=1"

	# Disable nacl, we can't build without pnacl (http://crbug.com/269560).
	myconf+=" -Ddisable_nacl=1"

	# Disable glibc Native Client toolchain, we don't need it (bug #417019).
	# myconf+=" -Ddisable_glibc=1"

	# TODO: also build with pnacl
	# myconf+=" -Ddisable_pnacl=1"

	# It would be awkward for us to tar the toolchain and get it untarred again
	# during the build.
	# myconf+=" -Ddisable_newlib_untar=1"

	# Make it possible to remove third_party/adobe.
	echo > "${T}/flapper_version.h" || die
	myconf+=" -Dflapper_version_h_file=${T}/flapper_version.h"

	# Use system-provided libraries.
	# TODO: use_system_hunspell (upstream changes needed).
	# TODO: use_system_libsrtp (bug #459932).
	# TODO: use_system_libvpx (http://crbug.com/347823).
	# TODO: use_system_libusb (http://crbug.com/266149).
	# TODO: use_system_opus (https://code.google.com/p/webrtc/issues/detail?id=3077).
	# TODO: use_system_protobuf (bug #503084).
	# TODO: use_system_ssl (http://crbug.com/58087).
	# TODO: use_system_sqlite (http://crbug.com/22208).
	myconf+="
		-Duse_system_bzip2=1
		-Duse_system_flac=1
		-Duse_system_ffmpeg=1
		-Duse_system_harfbuzz=1
		-Duse_system_icu=1
		-Duse_system_jsoncpp=1
		-Duse_system_libevent=1
		-Duse_system_libjpeg=1
		-Duse_system_libpng=1
		-Duse_system_libwebp=1
		-Duse_system_libxml=1
		-Duse_system_libxslt=1
		-Duse_system_minizip=1
		-Duse_system_nspr=1
		-Duse_system_openssl=1
		-Duse_system_re2=1
		-Duse_system_snappy=1
		-Duse_system_speex=1
		-Duse_system_xdg_utils=1
		-Duse_system_zlib=1"

	# Needed for system icu - we don't need additional data files.
	myconf+=" -Dicu_use_data_file_flag=0"

	# TODO: patch gyp so that this arm conditional is not needed.
	if ! use arm; then
		myconf+="
			-Duse_system_yasm=1"
	fi

	# Optional dependencies.
	# TODO: linux_link_kerberos, bug #381289.
	myconf+="
		$(gyp_use cups)
		$(gyp_use gnome use_gconf)
		$(gyp_use gnome-keyring use_gnome_keyring)
		$(gyp_use gnome-keyring linux_link_gnome_keyring)
		$(gyp_use kerberos)
		$(gyp_use pulseaudio)
		$(gyp_use tcmalloc use_allocator tcmalloc none)"

	# Use explicit library dependencies instead of dlopen.
	# This makes breakages easier to detect by revdep-rebuild.
	myconf+="
		-Dlinux_link_gsettings=1
		-Dlinux_link_libpci=1
		-Dlinux_link_libspeechd=1
		-Dlibspeechd_h_prefix=speech-dispatcher/"

	# TODO: use the file at run time instead of effectively compiling it in.
	myconf+="
		-Dusb_ids_path=/usr/share/misc/usb.ids"

	# Save space by removing DLOG and DCHECK messages (about 6% reduction).
	myconf+="
		-Dlogging_like_official_build=1"

	# Never use bundled gold binary. Disable gold linker flags for now.
	myconf+="
		-Dlinux_use_bundled_binutils=0
		-Dlinux_use_bundled_gold=0
		-Dlinux_use_gold_flags=0"

	# Always support proprietary codecs.
	myconf+=" -Dproprietary_codecs=1"

	# Set python version and libdir so that python_arch.sh can find libpython.
	# Bug 492864.
	myconf+="
		-Dpython_ver=${EPYTHON#python}
		-Dsystem_libdir=$(get_libdir)"

	# system-ffmpeg
	# ffmpeg_branding="Chromium"
	# if ! use bindist; then
	# 	# Enable H.264 support in bundled ffmpeg.
	# 	ffmpeg_branding="Chrome"
	# fi
	# myconf+=" -Dffmpeg_branding=${ffmpeg_branding}"

	# Set up Google API keys, see http://www.chromium.org/developers/how-tos/api-keys .
	# Note: these are for Gentoo use ONLY. For your own distribution,
	# please get your own set of keys. Feel free to contact chromium@gentoo.org
	# for more info.
	myconf+=" -Dgoogle_api_key=AIzaSyDEAOvatFo0eTgsV_ZlEzx0ObmepsMzfAc
		-Dgoogle_default_client_id=329227923882.apps.googleusercontent.com
		-Dgoogle_default_client_secret=vgKG0NNv7GoDpbtoFNLxCUXu"

	local myarch="$(tc-arch)"
	if [[ $myarch = amd64 ]] ; then
		target_arch=x64
		# ffmpeg_target_arch=x64
	elif [[ $myarch = x86 ]] ; then
		target_arch=ia32
		# ffmpeg_target_arch=ia32
	elif [[ $myarch = arm ]] ; then
		target_arch=arm
		# ffmpeg_target_arch=$(usex neon arm-neon arm)
		# TODO: re-enable NaCl (NativeClient).
		local CTARGET=${CTARGET:-${CHOST}}
		if [[ $(tc-is-softfloat) == "no" ]]; then

			myconf+=" -Darm_float_abi=hard"
		fi
		filter-flags "-mfpu=*"
		use neon || myconf+=" -Darm_fpu=${ARM_FPU:-vfpv3-d16}"

		if [[ ${CTARGET} == armv[78]* ]]; then
			myconf+=" -Darmv7=1"
		else
			myconf+=" -Darmv7=0"
		fi
		myconf+=" -Dsysroot=
			$(gyp_use neon arm_neon)
			-Ddisable_nacl=1"
	else
		die "Failed to determine target arch, got '$myarch'."
	fi

	myconf+=" -Dtarget_arch=${target_arch}"

	# Make sure that -Werror doesn't get added to CFLAGS by the build system.
	# Depending on GCC version the warnings are different and we don't want
	# the build to fail because of that.
	myconf+=" -Dwerror="

	# Disable fatal linker warnings, bug 506268.
	myconf+=" -Ddisable_fatal_linker_warnings=1"

	# Avoid CFLAGS problems, bug #352457, bug #390147.
	if ! use custom-cflags; then
		replace-flags "-Os" "-O2"
		strip-flags

		# Prevent linker from running out of address space, bug #471810 .
		if use x86; then
			filter-flags "-g*"
		fi
	fi

	# Make sure the build system will use the right tools, bug #340795.
	tc-export AR CC CXX RANLIB

	# Tools for building programs to be executed on the build system, bug #410883.
	export AR_host=$(tc-getBUILD_AR)
	export CC_host=$(tc-getBUILD_CC)
	export CXX_host=$(tc-getBUILD_CXX)
	export LD_host=${CXX_host}

	# Bug 491582.
	export TMPDIR="${WORKDIR}/temp"
	mkdir -m 755 "${TMPDIR}" || die

	# local build_ffmpeg_args=""
	# if use pic && [[ "${ffmpeg_target_arch}" == "ia32" ]]; then
	# 	build_ffmpeg_args+=" --disable-asm"
	# fi

	# Re-configure bundled ffmpeg. See bug #491378 for example reasons.
	# einfo "Configuring bundled ffmpeg..."
	# pushd third_party/ffmpeg > /dev/null || die
	# chromium/scripts/build_ffmpeg.py linux ${ffmpeg_target_arch} \
	# 	--branding ${ffmpeg_branding} -- ${build_ffmpeg_args} || die
	# chromium/scripts/copy_config.sh || die
	# chromium/scripts/generate_gyp.py || die
	# popd > /dev/null || die

	third_party/libaddressinput/chromium/tools/update-strings.py || die

	einfo "Configuring Chromium..."
	build/linux/unbundle/replace_gyp_files.py ${myconf} || die
	myconf+=" -Ichromiumcontent/chromiumcontent.gypi"
	myconf+=" chromiumcontent/chromiumcontent.gyp"
	egyp_chromium ${myconf} || die
}

eninja() {
	if [[ -z ${NINJAOPTS+set} ]]; then
		local jobs=$(makeopts_jobs)
		local loadavg=$(makeopts_loadavg)

		if [[ ${MAKEOPTS} == *-j* && ${jobs} != 999 ]]; then
			NINJAOPTS+=" -j ${jobs}"
		fi
		if [[ ${MAKEOPTS} == *-l* && ${loadavg} != 999 ]]; then
			NINJAOPTS+=" -l ${loadavg}"
		fi
	fi
	set -- ninja -v ${NINJAOPTS} "$@"
	echo "$@"
	"$@"
}

src_compile() {
	local ninja_targets="chromiumcontent_all"

	# Build mksnapshot and pax-mark it.
	# eninja -C out/Release mksnapshot || die
	# pax-mark m out/Release/mksnapshot

	# Even though ninja autodetects number of CPUs, we respect
	# user's options, for debugging with -j 1 or any other reason.
	eninja -C out/Release ${ninja_targets} || die
}


src_install() {
	local _INCLUDE_DIRS="
	    base
	    build
	    cc
	    chrome/browser/ui/libgtk2ui
	    components/os_crypt
	    content/public
	    ipc
	    gin
	    gpu
	    mojo
	    net
	    printing
	    sandbox
	    skia
	    testing
	    third_party/WebKit/Source/Platform/chromium/public
	    third_party/WebKit/Source/WebKit/chromium/public
	    third_party/WebKit/public
	    third_party/icu/source
	    third_party/skia
	    third_party/wtl/include
	    ui
	    url
	    v8/include
	    webkit
	"

	local _GENERATED_INCLUDE_DIRS="
		ui
	"

	local _EXTRA_INSTALL="
		content/common/content_export.h
		content/app/startup_helper_win.cc
	"

	dolib.so out/Release/libchromiumcontent.so
	dolib.a out/Release/libchromiumviews.a
	dolib.a out/Release/libtest_support_chromiumcontent.a

	insinto "${CHROMIUM_HOME}"

	newexe out/Release/chrome_sandbox chrome-sandbox || die
	fperms 4755 "${CHROMIUM_HOME}/chrome-sandbox"

	doexe out/Release/chromedriver || die

	insinto "${CHROMIUM_INCLUDE}"

	for hdir in ${_INCLUDE_DIRS}; do
		doins $(find ${hdir} -name '*.h' -printf \"%P\"\\n)
	done

	cd out/Release/gen
	for hdir in ${_GENERATED_INCLUDE_DIRS}; do
		doins $(find ${hdir} -name '*.h' -printf \"%P\"\\n)
	done
	cd "${S}"

	for f in ${_EXTRA_INSTALL}; do
		doins "${f}"
	done
}
