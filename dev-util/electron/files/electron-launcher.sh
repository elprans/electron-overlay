#!/usr/bin/env sh

set -euo pipefail

for f in /etc/electron/*; do
    [[ -f ${f} ]] && source "${f}"
done

for f in ${XDG_CONFIG_HOME:-$HOME/.config/electron}*; do
    [[ -f ${f} ]] && source "${f}"
done

# Let the wrapped binary know that it has been run through the wrapper
export CHROME_WRAPPER=$(readlink -f "$0")

PROGDIR=${CHROME_WRAPPER%/*}

case ":$PATH:" in
  *:$PROGDIR:*)
    # $PATH already contains $PROGDIR
    ;;
  *)
    # Append $PROGDIR to $PATH
    export PATH="$PATH:$PROGDIR"
    ;;
esac

exec "@INSTALL_PATH@/electron" "${flags[@]}" "$@"

# Select session type and platform
if @@OZONE_AUTO_SESSION@@; then
	platform=
	if [[ ${XDG_SESSION_TYPE} == x11 ]]; then
		platform=x11
	elif [[ ${XDG_SESSION_TYPE} == wayland ]]; then
		platform=wayland
	else
		if [[ -n ${WAYLAND_DISPLAY} ]]; then
			platform=wayland
		else
			platform=x11
		fi
	fi
	if ${DISABLE_OZONE_PLATFORM:-false}; then
		platform=x11
	fi
	ELECTRON_FLAGS="--ozone-platform=${platform} ${ELECTRON_FLAGS}"
fi

exec -a "@INSTALL_PATH@/electron" ${ELECTRON_FLAGS} "$@"
