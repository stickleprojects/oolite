/* uitest-fakekey: press an evdev key through KWin's org_kde_kwin_fake_input, hold it until SIGTERM/SIGINT, then release it.
   Needed because XTEST keys never reach clients on headless kwin (see issue #5). KWin must be started with
   KWIN_WAYLAND_NO_PERMISSION_CHECKS=1. Usage: uitest-fakekey EVDEV_CODE */
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "fake-input-client-protocol.h"

static struct org_kde_kwin_fake_input *fi;
static volatile sig_atomic_t stop;

static void reg(void *d, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
    if (!strcmp(iface, "org_kde_kwin_fake_input"))
        fi = wl_registry_bind(r, name, &org_kde_kwin_fake_input_interface, ver < 4 ? ver : 4);
}
static void rem(void *d, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = { reg, rem };
static void on_signal(int s) { stop = 1; }

int main(int argc, char **argv) {
    if (argc != 2) { fprintf(stderr, "usage: uitest-fakekey EVDEV_CODE\n"); return 2; }
    struct wl_display *d = wl_display_connect(NULL);
    if (!d) { fprintf(stderr, "no wayland display\n"); return 2; }
    struct wl_registry *r = wl_display_get_registry(d);
    wl_registry_add_listener(r, &rl, NULL);
    wl_display_roundtrip(d);
    if (!fi) { fprintf(stderr, "no org_kde_kwin_fake_input global\n"); return 3; }
    signal(SIGTERM, on_signal); signal(SIGINT, on_signal);
    int code = atoi(argv[1]);
    org_kde_kwin_fake_input_authenticate(fi, "uitest", "key injection for tests");
    org_kde_kwin_fake_input_keyboard_key(fi, code, WL_KEYBOARD_KEY_STATE_PRESSED);
    wl_display_roundtrip(d);
    printf("down\n"); fflush(stdout);
    while (!stop) usleep(20000);
    org_kde_kwin_fake_input_keyboard_key(fi, code, WL_KEYBOARD_KEY_STATE_RELEASED);
    wl_display_roundtrip(d);
    return 0;
}
