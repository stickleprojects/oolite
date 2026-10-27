/* uitest-fakeinput: keys and the mouse through KWin's org_kde_kwin_fake_input, needed because XTEST events never reach clients on
   headless kwin (issues #5, #30). KWin must be started with KWIN_WAYLAND_NO_PERMISSION_CHECKS=1.
   Commands come from the arguments, or with none, one per line on stdin, each answered "ok" once KWin has it (or "error ...").
   KWin releases whatever a client still holds when it disconnects, so a held key or button needs the stdin form, kept running.
     move X Y          pointer to output coordinates (X, Y)
     down BTN | up BTN press / release a button (evdev code, 0x110 = BTN_LEFT)
     click [BTN]       down, 50 ms, up (default BTN_LEFT)
     press K | release K   press / release a key (evdev code)
     key K             press, 30 ms, release
     sleep MS                                                                                                         */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <wayland-client.h>
#include "fake-input-client-protocol.h"

static struct wl_display *d;
static struct org_kde_kwin_fake_input *fi;
static uint32_t fiver;

static void reg(void *data, struct wl_registry *r, uint32_t name, const char *iface, uint32_t ver) {
    if (!strcmp(iface, "org_kde_kwin_fake_input"))
        fi = wl_registry_bind(r, name, &org_kde_kwin_fake_input_interface, fiver = ver < 4 ? ver : 4);
}
static void rem(void *data, struct wl_registry *r, uint32_t n) {}
static const struct wl_registry_listener rl = { reg, rem };

static void button(uint32_t b, int down) {
    org_kde_kwin_fake_input_button(fi, b, down ? WL_POINTER_BUTTON_STATE_PRESSED : WL_POINTER_BUTTON_STATE_RELEASED);
}
static void keyev(uint32_t k, int down) {
    org_kde_kwin_fake_input_keyboard_key(fi, k, down ? WL_KEYBOARD_KEY_STATE_PRESSED : WL_KEYBOARD_KEY_STATE_RELEASED);
}

/* Runs the commands in tok[0..n); returns NULL or what was wrong. */
static const char *run(char **tok, int n) {
    for (int i = 0; i < n; i++) {
        const char *c = tok[i], *a = i + 1 < n ? tok[i + 1] : NULL;
        if (!strcmp(c, "move") && i + 2 < n) {
            if (fiver < 2) return "fake_input has no absolute motion (needs v2)";
            org_kde_kwin_fake_input_pointer_motion_absolute(fi, wl_fixed_from_double(atof(a)), wl_fixed_from_double(atof(tok[i + 2])));
            i += 2;
        } else if (!strcmp(c, "click")) {
            uint32_t b = a && strtoul(a, NULL, 0) ? (i++, strtoul(a, NULL, 0)) : 0x110;
            button(b, 1); wl_display_roundtrip(d); usleep(50000); button(b, 0);
        } else if ((!strcmp(c, "down") || !strcmp(c, "up")) && a) {
            button(strtoul(a, NULL, 0), c[0] == 'd'); i++;
        } else if ((!strcmp(c, "press") || !strcmp(c, "release") || !strcmp(c, "key")) && a) {
            if (fiver < 4) return "fake_input has no keyboard (needs v4)";
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
    wl_display_roundtrip(d);
    if (!fi) { fprintf(stderr, "no org_kde_kwin_fake_input global\n"); return 3; }
    org_kde_kwin_fake_input_authenticate(fi, "uitest", "input injection for tests");
    if (argc > 1) {
        const char *err = run(argv + 1, argc - 1);
        if (err) { fprintf(stderr, "%s\n", err); return 2; }
        return 0;
    }
    char line[512], *tok[64];
    while (fgets(line, sizeof line, stdin)) {
        int n = 0;
        for (char *t = strtok(line, " \t\r\n"); t && n < 64; t = strtok(NULL, " \t\r\n")) tok[n++] = t;
        const char *err = n ? run(tok, n) : NULL;
        if (err) printf("error %s\n", err); else printf("ok\n");
        fflush(stdout);
    }
    return 0;
}
