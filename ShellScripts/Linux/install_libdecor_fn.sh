#!/bin/bash

# Installs the libdecor that the AppImage will bundle. This is the one place that decides which libdecor that is.
#
# SDL3 needs libdecor to draw the game window's title bar on GNOME Wayland (#75, upstream #793). quick-sharun
# bundles libdecor from the system library folder, so the build machine must have the libdecor we want to ship.
#
# - OOLITE_DISPOSABLE_BUILD_MACHINE=true: libdecor-mini (libdecor-rs), which REPLACES the system libdecor. It draws
#   its own title bar and needs only glibc, so the AppImage works without the player's libdecor plugins and never
#   loads GTK. The CI workflows set this flag, only in the container jobs that build AppImages; the containers are
#   deleted after each job. All published AppImages are built there. Never set it on a machine you keep.
# - Otherwise (e.g. a developer's machine): the distribution's libdecor, so no system library is replaced. Its
#   title bar on GNOME Wayland then depends on the player's libdecor plugins.
#
# Why a flag of our own rather than CI=true: CI=true says "running under a CI system", not "this machine is thrown
# away afterwards". Every CI system sets it, including self-hosted runners, which are real machines, and some
# developers export CI=true in their shells to make tools non-interactive. Replacing a system library has to be
# asked for explicitly, by the one workflow step that knows its machine is disposable.
#
# libdecor-mini is only published under a rolling "continuous" release, so its sha256 is checked: when the package
# changes, the build stops until the new package has been tested and the hash updated here.
install_libdecor() {
    local script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)
    source "$script_dir/os_detection.sh"
    source "$script_dir/install_package_fn.sh"

    if [[ "${OOLITE_DISPOSABLE_BUILD_MACHINE:-}" != "true" ]]; then
        echo "ℹ️ OOLITE_DISPOSABLE_BUILD_MACHINE is not 'true': installing the distribution's libdecor; no system library"
        echo "   is replaced. AppImages built here bundle it, so their title bar on GNOME Wayland depends on the player's"
        echo "   libdecor plugins. Published AppImages are built with OOLITE_DISPOSABLE_BUILD_MACHINE=true (in CI"
        echo "   containers), which replaces the system libdecor with libdecor-mini (#75)."
        install_package libdecor
        return
    fi

    local arch=$(uname -m)
    local url="https://github.com/pkgforge-dev/archlinux-pkgs-debloated/releases/download/continuous/libdecor-mini-$arch.pkg.tar.zst"
    local sha256="435e1e65f4227069f207d562ae83eb493e1cc14b9f36bcd0e90cf1a124a32e0f"
    local tmp=$(mktemp -d)
    local pkg="$tmp/libdecor-mini-$arch.pkg.tar.zst"

    echo "⚠️ OOLITE_DISPOSABLE_BUILD_MACHINE=true: REPLACING this machine's libdecor with libdecor-mini, so AppImages"
    echo "   built here draw their own title bar on GNOME Wayland (#75). Other programs on this machine will use"
    echo "   libdecor-mini too. Only set this flag on a throwaway build machine, such as a CI container."
    install_package zstd || return 1
    if ! curl -fsSL -o "$pkg" "$url"; then
        echo "❌ Error downloading libdecor-mini from $url!" >&2
        return 1
    fi
    if ! echo "$sha256  $pkg" | sha256sum -c -; then
        echo "❌ The libdecor-mini package has changed. Test the new one, then update its sha256 in ${BASH_SOURCE[0]}" >&2
        return 1
    fi

    case "$CURRENT_DISTRO" in
        arch)
            # libdecor-mini declares that it provides and conflicts with libdecor; --ask 4 removes libdecor
            if ! pacman -U --noconfirm --ask 4 "$pkg"; then
                echo "❌ pacman could not install libdecor-mini!" >&2
                return 1
            fi
            ;;
        debian|redhat)
            # no package for these distributions: put the one library where quick-sharun looks for libdecor
            local libdir="/usr/lib/$arch-linux-gnu"
            [[ "$CURRENT_DISTRO" == "redhat" ]] && libdir="/usr/lib64"
            if ! tar --zstd -xf "$pkg" -C "$tmp" usr/lib/libdecor-0.so.0; then
                echo "❌ Could not unpack libdecor-mini!" >&2
                return 1
            fi
            rm -f "$libdir"/libdecor-0.so*
            install -m 755 "$tmp/usr/lib/libdecor-0.so.0" "$libdir/libdecor-0.so.0"
            ln -sf libdecor-0.so.0 "$libdir/libdecor-0.so"
            ldconfig
            ;;
    esac
    rm -rf "$tmp"
    echo "✅ libdecor-mini installed"
}
