/* uitest-wlrinput: keys and the mouse on wlroots compositors (sway) through the standard virtual-keyboard (zwp_virtual_keyboard_v1)
   and virtual-pointer (zwlr_virtual_pointer_v1) protocols: native Wayland has no X server for XTEST (issue #44). The same commands
   and replies as uitest-fakeinput (docker/fakeinput.c), so fakeinput.py drives both.
   Commands come from the arguments, or with none, one per line on stdin, each answered "ok" once the compositor has it (or "error ...").
   A virtual device's held keys are released when the client disconnects, so a held key or button needs the stdin form, kept running.
     move X Y          pointer to output coordinates (X, Y) of the first output
     down BTN | up BTN press / release a button (evdev code, 0x110 = BTN_LEFT)
     click [BTN]       down, 50 ms, up (default BTN_LEFT)
     press K | release K   press / release a key (evdev code)
     key K             press, 30 ms, release
     sleep MS                                                                                                         */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/mman.h>
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include "virtual-keyboard-unstable-v1-client-protocol.h"
#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"

static struct wl_display *d;
static struct wl_seat *seat;
static struct wl_output *output;
static struct zwp_virtual_keyboard_manager_v1 *kbm;
static struct zwlr_virtual_pointer_manager_v1 *ptm;
static struct zwp_virtual_keyboard_v1 *kb;
static struct zwlr_virtual_pointer_v1 *pt;
static int32_t out_w, out_h;

static void mode(void *data, struct wl_output *o, uint32_t flags, int32_t w, int32_t h, int32_t refresh) {
    if (flags & WL_OUTPUT_MODE_CURRENT) { out_w = w; out_h = h; }
}
static void geom(void *data, struct wl_output *o, int32_t x, int32_t y, int32_t pw, int32_t ph, int32_t sp, const char *mk,
                 const char *md, int32_t tr) {}
static void odone(void *data, struct wl_output *o) {}
static void oscale(void *data, struct wl_output *o, int32_t f) {}
static void oname(void *data, struct wl_output *o, const char *n) {}
static void odesc(void *data, struct wl_output *o, const char *n) {}
static const struct wl_output_listener ol = { geom, mode, odone, oscale, oname, odesc };

static void reg(void *data, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
    if (!strcmp(iface, "wl_seat") && !seat) seat = wl_registry_bind(r, name, &wl_seat_interface, 1);
    else if (!strcmp(iface, "wl_output") && !output) {
        output = wl_registry_bind(r, name, &wl_output_interface, ver < 4 ? ver : 4); wl_output_add_listener(output, &ol, NULL);
    } else if (!strcmp(iface, "zwp_virtual_keyboard_manager_v1")) kbm = wl_registry_bind(r, name, &zwp_virtual_keyboard_manager_v1_interface, 1);
    else if (!strcmp(iface, "zwlr_virtual_pointer_manager_v1")) ptm = wl_registry_bind(r, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void rem(void *data, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = { reg, rem };

static uint32_t now_ms(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

/* A virtual keyboard needs a keymap before its first key: the default (evdev rules, us layout) from xkbcommon, passed in a memfd. */
static const char *keymap(void) {
    struct xkb_context *ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
    struct xkb_rule_names names = { 0 };
    struct xkb_keymap *km = ctx ? xkb_keymap_new_from_names(ctx, &names, XKB_KEYMAP_COMPILE_NO_FLAGS) : NULL;
    char *s = km ? xkb_keymap_get_as_string(km, XKB_KEYMAP_FORMAT_TEXT_V1) : NULL;
    if (!s) return "could not make an xkb keymap";
    size_t n = strlen(s) + 1; int fd = memfd_create("uitest-keymap", MFD_CLOEXEC);
    if (fd < 0 || write(fd, s, n) != (ssize_t)n) return "could not write the keymap";
    zwp_virtual_keyboard_v1_keymap(kb, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, n);
    wl_display_roundtrip(d); close(fd); free(s); xkb_keymap_unref(km); xkb_context_unref(ctx);
    return NULL;
}

static void button(uint32_t b, int down) {
    zwlr_virtual_pointer_v1_button(pt, now_ms(), b, down ? WL_POINTER_BUTTON_STATE_PRESSED : WL_POINTER_BUTTON_STATE_RELEASED);
    zwlr_virtual_pointer_v1_frame(pt);
}
static void keyev(uint32_t k, int down) {
    zwp_virtual_keyboard_v1_key(kb, now_ms(), k, down ? WL_KEYBOARD_KEY_STATE_PRESSED : WL_KEYBOARD_KEY_STATE_RELEASED);
}

/* Runs the commands in tok[0..n); returns NULL or what was wrong. */
static const char *run(char **tok, int n) {
    for (int i = 0; i < n; i++) {
        const char *c = tok[i], *a = i + 1 < n ? tok[i + 1] : NULL;
        if (!strcmp(c, "move") && i + 2 < n) {
            if (out_w <= 0 || out_h <= 0) return "no output size known";
            zwlr_virtual_pointer_v1_motion_absolute(pt, now_ms(), atoi(a), atoi(tok[i + 2]), out_w, out_h);
            zwlr_virtual_pointer_v1_frame(pt);
            i += 2;
        } else if (!strcmp(c, "click")) {
            uint32_t b = a && strtoul(a, NULL, 0) ? (i++, strtoul(a, NULL, 0)) : 0x110;
            button(b, 1); wl_display_roundtrip(d); usleep(50000); button(b, 0);
        } else if ((!strcmp(c, "down") || !strcmp(c, "up")) && a) {
            button(strtoul(a, NULL, 0), c[0] == 'd'); i++;
        } else if ((!strcmp(c, "press") || !strcmp(c, "release") || !strcmp(c, "key")) && a) {
            uint32_t k = strtoul(a, NULL, 0); i++;
            if (c[0] == 'k') { keyev(k, 1); wl_display_roundtrip(d); usleep(30000); keyev(k, 0); }
            else keyev(k, c[0] == 'p');
        } else if (!strcmp(c, "sleep") && a) {
            usleep(atoi(a) * 1000); i++;
        } else return "bad command";
        if (wl_display_roundtrip(d) < 0) return "lost the wayland connection";
    }
    return NULL;
}

int main(int argc, char **argv) {
    d = wl_display_connect(NULL);
    if (!d) { fprintf(stderr, "no wayland display\n"); return 2; }
    struct wl_registry *r = wl_display_get_registry(d);
    wl_registry_add_listener(r, &rl, NULL);
    wl_display_roundtrip(d); wl_display_roundtrip(d);   /* the second gets the output's mode */
    if (!seat || !kbm || !ptm) {
        fprintf(stderr, "missing %s\n", !seat ? "wl_seat" : !kbm ? "zwp_virtual_keyboard_manager_v1" : "zwlr_virtual_pointer_manager_v1");
        return 3;
    }
    kb = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(kbm, seat);
    pt = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(ptm, seat);
    const char *err = keymap();
    if (err) { fprintf(stderr, "%s\n", err); return 2; }
    /* The first key from a new keyboard makes it the seat's keyboard, and the focused client gets its keymap then: that key was lost
       (the keys test failed in run 1 only, the game logged no key). A Shift tap first, which no game screen acts on. */
    keyev(42, 1); wl_display_roundtrip(d); keyev(42, 0); wl_display_roundtrip(d); usleep(200000);
    if (argc > 1) {
        err = run(argv + 1, argc - 1);
        if (err) { fprintf(stderr, "%s\n", err); return 2; }
        return 0;
    }
    char line[512], *tok[64];
    while (fgets(line, sizeof line, stdin)) {
        int n = 0;
        for (char *t = strtok(line, " \t\r\n"); t && n < 64; t = strtok(NULL, " \t\r\n")) tok[n++] = t;
        err = n ? run(tok, n) : NULL;
        if (err) printf("error %s\n", err); else printf("ok\n");
        fflush(stdout);
    }
    return 0;
}
