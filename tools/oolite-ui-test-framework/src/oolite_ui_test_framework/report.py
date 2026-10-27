"""Statistical verdicts for uitest. Pure python3 stdlib, no AI. Usage: report.py RAW OUT.md [options]; report.py --selftest
Values that are NA / not tested (anything other than 0 or 1) are NOT MEASURED: they are left out of every count and statistic and
shown as NA in the tables. They are never failures. SKIP lines in the raw file ("not available: ...") are listed in their own table."""
import sys, argparse, json, re

from . import geometry
from math import comb

ALPHA = 0.05
CRIT = ("frame", "focus", "splash_centred", "centred", "renders")

def fisher(fa, na, fb, nb):
    """One-sided exact Fisher p. Returns (p_more, p_fewer): P(build has >= fb failures | totals), P(<= fb)."""
    tot = fa + fb; N = na + nb
    den = comb(N, tot) if tot else 1
    pm = sum(comb(nb, k) * comb(na, tot - k) for k in range(fb, min(nb, tot) + 1)) / den
    pf = sum(comb(nb, k) * comb(na, tot - k) for k in range(max(0, tot - na), fb + 1)) / den
    return pm, pf

def can_reach(na, nb):
    """Smallest possible one-sided p for these sample sizes (all control runs fail, no build run fails)."""
    return 1 / comb(na + nb, nb)

def status(r, c):
    """1 pass, 0 fail, None not measured (NA / not tested). An exited run fails every criterion."""
    if r.get("exited") == "1": return 0
    v = r.get(c, "NA")
    if c == "centred" and r.get("dx", "NA") == "NA" and "source" not in r: return None
    if c == "t_centred" and r.get("t_dx", "NA") == "NA" and r.get("t_ok") != "0": return None
    return int(v) if v in ("0", "1") else None

def fails(rs):
    """{criterion: (failures, measured runs)}"""
    out = {}
    for c in CRIT:
        st = [status(r, c) for r in rs]
        out[c] = (sum(1 for x in st if x == 0), sum(1 for x in st if x is not None))
    return out

def run_passes(r):
    """True if every measured criterion passed in this run, False if any failed, None if nothing was measured."""
    st = [status(r, c) for c in CRIT]
    if 0 in st: return False
    return True if 1 in st else None


def clean_runs(rs):
    """(runs where every test passed, measured runs): the '9/10' score"""
    v = [run_passes(r) for r in rs]
    return sum(1 for x in v if x), sum(1 for x in v if x is not None)


def compare(ctl, bld, minruns):
    """ctl, bld: lists of result dicts. Returns (verdict, detail, pvals)."""
    if not ctl or not bld: return "NO DATA", "", {}
    fa, fb = fails(ctl), fails(bld)
    use = [c for c in CRIT if fa[c][1] and fb[c][1]]          # measured on both sides
    if not use: return "NOT MEASURED", "no criterion measured on both sides", {}
    pv = {c: fisher(fa[c][0], fa[c][1], fb[c][0], fb[c][1]) for c in use}
    shown = [c for c in use if fa[c][0] or fb[c][0]]
    det = " ".join("%s %d/%d v %d/%d p=%.3g" % (c, fb[c][0], fb[c][1], fa[c][0], fa[c][1], min(pv[c])) for c in shown) or "no failures on either side (%d v %d runs)" % (len(bld), len(ctl))
    ok = [c for c in use if min(fa[c][1], fb[c][1]) >= minruns and can_reach(fa[c][1], fb[c][1]) < ALPHA]
    if not ok: return "INCONCLUSIVE", det, pv
    if any(pv[c][0] < ALPHA for c in ok): return "REGRESSED", det, pv
    if any(pv[c][1] < ALPHA for c in ok): return "FIXED", det, pv
    return "UNCHANGED", det, pv

def equiv(ctl, bld, minruns):
    v, det, pv = compare(ctl, bld, minruns)
    if v in ("NO DATA", "INCONCLUSIVE", "NOT MEASURED"): return v, det
    if v == "UNCHANGED": return "SAME", det
    return "DIFFERS(p=%.3g)" % min(min(pv[c]) for c in pv), det

def flaky(rs):
    f = fails(rs)
    return any(0 < f[c][0] < f[c][1] for c in CRIT)

REG = {}   # raw wm id -> {family, session, where} from environments.toml (set by set_registry); else ids are parsed by name

def set_registry(envs):
    REG.clear()
    for n, e in envs.items(): REG[n] = {"family": e.family, "session": e.session, "where": e.where, "probes": list(e.probes)}

def load(raw, tol=geometry.DEFAULT_TOL):
    cells, order = {}, []
    global SKIPS
    SKIPS = []; VERS.clear(); HOSTENV.clear()
    META["purpose"] = None; META["builds"] = []; WARNINGS.clear()
    for line in open(raw):
        if line.startswith("WARN "):
            d = dict(kv.split("=", 1) for kv in line.split(" text=")[0].split()[1:] if "=" in kv)
            WARNINGS.append((d.get("wm", "-"), d.get("build", "-"), d.get("run", "?"), line.split(" text=", 1)[-1].strip())); continue
        if line.startswith("HARD "):
            d = dict(kv.split("=", 1) for kv in line.split(" reason=")[0].split()[1:] if "=" in kv)
            SKIPS.append((d.get("wm", "-"), d.get("screen", "-"), d.get("build", "-"), "hard failure: " + line.split(" reason=", 1)[-1].strip()))
            continue
        if line.startswith("PURPOSE ") or line.startswith("BUILD "):
            try:
                v = json.loads(line.split(" ", 1)[1])
                if line.startswith("PURPOSE"): META["purpose"] = v
                else: META["builds"].append(v)
            except ValueError: pass
            continue
        if line.startswith("WMVER") or line.startswith("HOSTENV"):
            d = dict(kv.split("=", 1) for kv in line.split()[1:] if "=" in kv)
            d = {k: v.replace("_", " ") for k, v in d.items()}
            if line.startswith("WMVER"): VERS[d.get("wm", "")] = d.get("version", "")
            else: HOSTENV.update(d)
            continue
        if line.startswith("SKIP"):
            head, _, why = line.partition("reason=")
            d = dict(kv.split("=", 1) for kv in head.split()[1:] if "=" in kv)
            SKIPS.append((d.get("wm", "-"), d.get("screen", "-"), d.get("build", "-"), why.strip()))
        if line.startswith("RESULT"):
            d = geometry.apply(dict(kv.split("=", 1) for kv in line.split()[1:]), tol)   # re-judge centring from recorded geometry
            if "t_frame" in d:
                global CRIT
                CRIT = ("frame", "focus", "splash_centred", "centred", "renders", "t_frame", "t_focus", "t_centred")
            k = (d["wm"], d["screen"], d["build"])
            if k not in cells: order.append(k)
            cells.setdefault(k, []).append(d)
    return cells, order

def uniq(seq):
    return list(dict.fromkeys(seq))

VERS = {}; HOSTENV = {}
SESS_ORDER = {"X11": 0, "XWayland": 1, "Wayland native": 2}

def parse_wm(wm):
    """raw wm id -> (family, session, is_host). Registry first; else by name. Ids: marco | kwin-xwayland | sway-native | host-x11-marco | host-kde-xwayland | host-kde-native."""
    if wm in REG: return REG[wm]["family"], REG[wm]["session"], REG[wm]["where"] == "host"
    host = wm.startswith("host-")
    if host: wm = wm[5:]
    if wm.endswith("-xwayland"): fam, ses = wm[:-9], "XWayland"
    elif wm.endswith("-native"): fam, ses = wm[:-7], "Wayland native"
    elif host and wm.startswith("x11-"): fam, ses = wm[4:], "X11"
    else: fam, ses = wm, "X11"
    return fam, ses, host

FALLBACK = {}   # id -> version, from --versions FILE (lines "id=version") for raw data that has no WMVER lines

def vkey(v):
    if not v: return (1,)           # unknown versions sort last within a family
    return (0,) + tuple(int(x) if x.isdigit() else 0 for x in re.findall(r"\d+", v or "")) or (0,)

def wm_info(wm):
    """(sort key, display name 'family version (session)', 'WM / compositor' family+version, session label)"""
    fam, ses, host = parse_wm(wm)
    ver = VERS.get(wm) or FALLBACK.get(wm, "")
    if host and HOSTENV:
        fam = HOSTENV.get("wm", fam) if ses != "X11" or fam in ("", "x11", "host") else fam
        ver = HOSTENV.get("version", "") if fam == HOSTENV.get("wm", fam) else ver
    ver = "" if ver == "unknown" else ver
    base = ("%s %s" % (fam, ver or "?")).strip()
    return (host, fam.lower(), vkey(ver), SESS_ORDER[ses], wm), "%s (%s)" % (base, ses), base, ses

def where(wm):
    return "host" if (REG[wm]["where"] == "host" if wm in REG else wm.startswith("host-")) else "docker"

def sort_wms(wms):
    return sorted(wms, key=lambda w: wm_info(w)[0])

def host_section(cells, minruns_h):
    """One row per live-desktop session x SDL driver x check, even when nothing was run."""
    he = HOSTENV
    if not he: return []
    st = he.get("session", "unknown"); desk = he.get("desktop", "unknown"); wmn = he.get("wm", "unknown"); ver = he.get("version", "")
    det = "%s / %s %s / %s session" % (desk, wmn, "" if ver == "unknown" else ver, st)
    plan = [("X11", "x11")] if st == "x11" else [("XWayland", "x11"), ("Wayland native", "wayland")]
    hskips = [s for s in SKIPS if s[0].startswith("host")]
    L = ["", "## Live desktop (--host): everything it would test", "",
         "Detected: **%s**. SDL driver is forced per row. Counts are failures/measured runs per build." % det.strip(), "",
         "| where | session | SDL driver | check | status | detail |", "|---|---|---|---|---|---|"]
    for ses, sdl in plan:
        byb = {}
        for (wm, sc, b), rs in cells.items():
            fam, s_, host = parse_wm(wm)
            if host and s_ == ses: byb.setdefault(b, []).extend(rs)
        rs = [r for v in byb.values() for r in v]
        for chk in ("frame", "focus", "centred", "toggle"):
            if not rs:
                status, why = "not tested", (hskips[0][3] if hskips else "host run not completed")
            elif chk == "toggle":
                tr = {b: [r for r in v if "t_ok" in r] for b, v in byb.items()}
                if not any(tr.values()): status, why = "not tested", "toggle (F12) not requested: add --toggle"
                else: status, why = "measured", ", ".join("%s %d/%d ok" % (b, sum(1 for r in v if r["t_ok"] != "0"), len(v)) for b, v in tr.items() if v)
            else:
                meas = {b: [x for x in (status_of(r, chk) for r in v) if x is not None] for b, v in byb.items()}
                if not any(meas.values()):
                    status, why = "NA", "cannot be measured from outside" + ("; question skipped / --no-prompt" if ses == "Wayland native" else "")
                else:
                    ans = [a.split(":")[1] for r in rs for a in r.get("asked", "").split(",") if a.startswith(chk + ":") and ":" in a]
                    why = ", ".join("%s %d/%d" % (b, sum(1 for x in m if x == 0), len(m)) for b, m in meas.items() if m) + " failed"
                    if ans:
                        status = "asked: " + ("yes" if all(x == "y" for x in ans) else "no" if all(x == "n" for x in ans) else "mixed")
                        why = "user answered y in %d of %d runs, n in %d (%s)" % (ans.count("y"), len(ans), ans.count("n"), why)
                    else:
                        status = "measured"
                        if any(r.get("source") == "compositor" for r in rs): why += "; compositor probe"
                        if any(r.get("xcheck") == "kwin" for r in rs): why += "; cross-checked with KWin D-Bus"
            L.append("| host | %s | %s | %s | %s | %s |" % (ses, sdl, chk, status, why))
    return L

def status_of(r, c):
    return status(r, c)

def cells_by_host(cells, ses):
    out = []
    for (wm, sc, b), rs in cells.items():
        fam, s, host = parse_wm(wm)
        if host and s == ses: out.append(rs)
    return out

META = {"purpose": None, "builds": []}
WARNINGS = []
LAST = {}   # counts from the last report() call, for exit codes
OUT_ORDER = ["REGRESSED", "SUSPECT", "STILL BROKEN", "FIXED", "NEEDS MORE RUNS", "WORKS", "NOT MEASURABLE"]
MAIN_CRITS = ("frame", "focus", "splash_centred", "centred", "renders")
TEST_NAMES = {"frame": "has_frame", "focus": "gets_focus", "splash_centred": "splash_centred", "centred": "game_window_centred", "renders": "game_renders", "toggle": "f12_toggle"}
TOGGLE_CRITS = ("t_frame", "t_focus", "t_centred")


def crit_outcome(fa, na, fb, nb, minruns):
    """One criterion, control (fa failures of na measured runs) v candidate (fb of nb). Returns (outcome, detail).
    WORKS / FIXED / STILL BROKEN / REGRESSED / SUSPECT / NEEDS MORE RUNS / NOT MEASURABLE."""
    if na == 0 or nb == 0: return "NOT MEASURABLE", "cannot be observed here"
    pm, pf = fisher(fa, na, fb, nb)
    powered = min(na, nb) >= minruns and can_reach(na, nb) < ALPHA
    if fa == 0 and fb == 0:
        if min(na, nb) >= minruns: return "WORKS", "passed in all %d and %d runs" % (na, nb)
        return "NEEDS MORE RUNS", "tested %d runs, all passed, below %d needed" % (min(na, nb), minruns)
    if fa > 0 and fb > 0:
        if powered and pm < ALPHA: return "REGRESSED", "fails more often (%d/%d v %d/%d, p=%.3g)" % (fb, nb, fa, na, pm)
        if powered and pf < ALPHA: return "FIXED", "fails less often (%d/%d v %d/%d, p=%.3g), still not perfect" % (fb, nb, fa, na, pf)
        return "STILL BROKEN", "fails in both (%d/%d v %d/%d)" % (fb, nb, fa, na)
    if fa == 0:
        if powered and pm < ALPHA: return "REGRESSED", "fails %d/%d, control 0/%d (p=%.3g)" % (fb, nb, na, pm)
        return "SUSPECT", "fails %d/%d, control 0/%d: rerun with more runs" % (fb, nb, na)
    if powered and pf < ALPHA: return "FIXED", "control fails %d/%d, candidate 0/%d (p=%.3g)" % (fa, na, nb, pf)
    return "NEEDS MORE RUNS", "control fails %d/%d, candidate 0/%d, but too few runs for significance" % (fa, na, nb)


def combine(items):
    """[(criterion, outcome, detail)] -> (cell outcome, detail naming the criteria). Worst outcome wins; NOT MEASURABLE only if all are."""
    real = [i for i in items if i[1] != "NOT MEASURABLE"]
    if not real: return "NOT MEASURABLE", "; ".join("%s: %s" % (c, d) for c, o, d in items) if items else ""
    top = min((i[1] for i in real), key=OUT_ORDER.index)
    det = "; ".join("%s %s" % (c.replace("t_", "toggle "), d) if o == top else "" for c, o, d in real if o == top)
    return top, det


def cell_outcomes(ctl, bld, minruns, has_x=True):
    """-> {'frame':(outcome, detail), 'focus':.., 'centred':.., 'toggle':.., 'cell': (outcome, detail)}"""
    fa, fb = fails(ctl), fails(bld); res = {}; allitems = []
    def go(crits):
        out = []
        for c in crits:
            if c not in fa: out.append((c, "NOT MEASURABLE", "cannot be observed here")); continue
            o, d = crit_outcome(fa[c][0], fa[c][1], fb[c][0], fb[c][1], minruns); out.append((c, o, d))
        return out
    for c in MAIN_CRITS:
        res[c] = combine(go([c])); allitems += go([c])
    tog = [c for c in TOGGLE_CRITS if c in fa and fa[c][1] and fb.get(c, (0, 0))[1]]
    if tog:
        t = go(tog); res["toggle"] = combine(t); allitems += t
    else:
        res["toggle"] = ("NOT TESTED", "toggle not run in this data (no --toggle)" if has_x else "no X11 probe for F12 in this environment")
    res["cell"] = combine(allitems)
    return res


def cell_name(wm, sc, multi):
    return wm_info(wm)[1] + (" " + sc if multi and sc not in ("-", "host") and not wm.startswith("host") else "")


def report(raw, outp, control, cand, minruns, tol, equiv_label, name, header="", host_minruns=None, brief=False):
    cells, order = load(raw, int(float(tol)) if str(tol).replace(".", "").isdigit() else geometry.DEFAULT_TOL)
    ran = uniq(k[0] for k in order); scs = uniq(k[1] for k in order); builds = uniq(k[2] for k in order)
    builds = uniq(builds + [s_[2] for s_ in SKIPS if s_[2] not in builds])
    extra = [s_[0] for s_ in SKIPS if s_[0] not in ran]
    extra += [n for n, v in REG.items() if v["where"] != "host" and n not in ran and n not in extra]
    wms = sort_wms(uniq(ran + extra))
    cand = [c for c in cand.split(",") if c] or [b for b in builds if b not in (control, equiv_label)]
    mr = lambda wm: (host_minruns or minruns) if wm.startswith("host-") or REG.get(wm, {}).get("where") == "host" else minruns
    multi = len({k[1] for k in order if not k[0].startswith("host-")}) > 1
    def has_x(wm):
        e = REG.get(wm)
        if e is not None and "probes" in e: return any(p.split(":")[0] == "x11" for p in e["probes"])
        return not wm.endswith("-native")
    reason = {}
    for w_, sc_, b_, why in SKIPS: reason.setdefault(w_, why)
    # outcomes[(wm, screen, build)] = cell_outcomes or ("NOT TESTED", reason)
    outs = {}; tested = []
    for wm in wms:
        wsc = [sc for sc in scs if (wm, sc, control) in cells] or ["-"]
        for sc in wsc:
            ctl = cells.get((wm, sc, control), [])
            for b in builds:
                if b == control: continue
                bld = cells.get((wm, sc, b), [])
                if ctl and bld: outs[(wm, sc, b)] = cell_outcomes(ctl, bld, mr(wm), has_x(wm)); tested.append((wm, sc, b))
                else:
                    why = reason.get(wm) or ("control `%s` has no runs here" % control if bld else "not requested")
                    nt = ("NOT TESTED", why); outs[(wm, sc, b)] = {k: nt for k in MAIN_CRITS + ("toggle", "cell")}
    bad = [k for k in tested if k[2] in cand and outs[k]["cell"][0] == "REGRESSED"]
    tc = [k for k in tested if k[2] in cand]
    anyc = lambda word: sum(1 for k in tc if any(outs[k][c][0] == word for c in MAIN_CRITS + ("toggle",)))
    LAST.clear(); LAST.update(tested=len(tc), regressed=len(bad), suspect=anyc("SUSPECT"), still_broken=anyc("STILL BROKEN"),
                              measured=sum(1 for k in tc if outs[k]["cell"][0] not in ("NOT MEASURABLE", "NOT TESTED")))
    single = len(builds) == 1
    if single:
        rs_all = [r for k, v in cells.items() if k[2] == control for r in v]
        LAST.update(measured=sum(1 for r in rs_all if run_passes(r) is not None), regressed=sum(1 for r in rs_all if run_passes(r) is False))
    L = ["# Window-manager matrix: %s" % name, ""]
    if META["purpose"] is not None or META["builds"]:
        L += ["## Purpose", "", META["purpose"] or "Purpose: not given", ""]
        if META["builds"]:
            L += ["### Builds", "", "| label | AppImage | sha256 (short) | note |", "|---|---|---|---|"]
            L += ["| %s%s | %s | %s | %s |" % (b["label"], " (control)" if b["label"] == control else "", b["file"], b["sha256"], b.get("note") or "") for b in META["builds"]]
            L.append("")
    # ---- headline
    HL = []
    for b in builds:
        if b == control or b not in cand: continue
        mine = [(k, v["cell"]) for k, v in outs.items() if k[2] == b]
        by = {}
        for k, (o, d) in mine: by.setdefault(o, []).append((k, d))
        verdict_ = "NOT TESTED" if set(by) <= {"NOT TESTED"} else "FAIL" if "REGRESSED" in by else "NEEDS MORE RUNS" if ("SUSPECT" in by or "NEEDS MORE RUNS" in by) else "PASS"
        counts = ", ".join("%d %s" % (len(by[o]), o) for o in OUT_ORDER + ["NOT TESTED"] if o in by)
        HL.append("- **%s**: **%s** (%s)" % (b, verdict_, counts))
        for o in ("FIXED", "REGRESSED", "SUSPECT", "STILL BROKEN", "NOT TESTED"):
            if o in by:
                HL.append("  - %s: %s" % (o, "; ".join(cell_name(k[0], k[1], multi) + (" (%s)" % d if d and o != "NOT TESTED" else "") for k, d in by[o]) if o != "NOT TESTED"
                         else "%d environments (%s)" % (len(by[o]), "; ".join(sorted({d.split(":")[0][:60] for k, d in by[o]})))))
    bro = []
    for wm in wms:
        for sc in scs:
            ctl = cells.get((wm, sc, control))
            if not ctl: continue
            f = fails(ctl); bad_c = [c for c in MAIN_CRITS if f[c][0]]
            if bad_c: bro.append("%s %s" % (cell_name(wm, sc, multi), "+".join(bad_c)))
    HL.append("- %s%s fails on: %s" % (control, "" if single else " (control)", "; ".join(bro) or "nothing measured"))
    test_failures = {}
    for b in builds:
        test_failures[b] = sum(fails(rs)[c][0] for (wm, sc, build), rs in cells.items() if build == b for c in CRIT)
    HL.append("- Failed measured criteria: " + ", ".join("%s %d" % (b, test_failures[b]) for b in builds))
    if not single: HL.append("- Control failures are baseline results, not candidate failures; pytest's failed count includes tests from both builds.")
    tot = {b: [sum(clean_runs(v)[i] for kk, v in cells.items() if kk[2] == b) for i in (0, 1)] for b in builds}
    HL.append("- Runs with every measured criterion passing: " + ", ".join("%s %d/%d" % (b, *tot[b]) for b in builds))
    L += ["## Headline", ""] + HL + [""]
    if WARNINGS:
        L += ["## Warnings", ""] + ["- %s %s run %s: %s (the game was relaunched before the next test)" % (w[0], w[1], w[2], w[3]) for w in WARNINGS] + [""]
    # ---- coverage table(s)
    for b in builds:
        if b == control or b not in cand: continue
        L += ["## Coverage: `%s` v control `%s`" % (b, control), "",
              "| WM / compositor | where | session | screen | runs/build (%s) | %s | note |" % ("/".join(builds), " | ".join(TEST_NAMES[c] for c in MAIN_CRITS + ("toggle",))), "|---|---|---|---|---|" + "---|" * 7]
        for wm in wms:
            _, disp, base, sess = wm_info(wm)
            for k in [k for k in outs if k[0] == wm and k[2] == b] or []:
                o = outs[k]; runs = "/".join(str(len(cells.get((wm, k[1], x), []))) for x in builds)
                note = o["cell"][1] if o["cell"][0] in ("NOT TESTED", "SUSPECT", "STILL BROKEN") else ""
                if o["cell"][0] != "NOT TESTED":
                    nt = "; ".join("%s: %s" % (c, o[c][1]) for c in MAIN_CRITS + ("toggle",) if o[c][0] == "NOT TESTED")
                    note = "; ".join(x for x in (note, nt) if x)
                L.append("| %s | %s | %s | %s | %s | %s | %s |" % (disp, where(wm), sess, k[1], runs, " | ".join(o[c][0] for c in MAIN_CRITS + ("toggle",)), note[:140]))
        L.append("")
    if header: L += ["## Environment", "", "```", header.rstrip(), "```", ""]
    L += ["Generated by uitest + verdict (python3 stdlib, deterministic). Centring tolerance %s px, MINRUNS %d (live desktop: %d). Rows: WM / compositor family A-Z, then version, then session; live desktop last." % (tol, minruns, host_minruns or minruns), ""]
    L += ["## Runs with every measured criterion passing", "", "A run scores 1 only if all its measured criteria passed; unmeasured or skipped tests do not count as failures. Shown as passing runs / measured runs.", "",
          "| WM / compositor | screen | " + " | ".join(builds) + " |", "|---|---|" + "---|" * len(builds)]
    for k in sorted({(k[0], k[1]) for k in cells}):
        L.append("| %s | %s | %s |" % (k[0], k[1], " | ".join("%d/%d" % clean_runs(cells[(k[0], k[1], b)]) if (k[0], k[1], b) in cells else "-" for b in builds)))
    L.append("")
    L += ["## Outcomes (control `%s` v candidate, per cell)" % control,
          "- **WORKS** tested, both pass every criterion. **FIXED** control fails, candidate passes (significant). **STILL BROKEN** both fail the same criterion. **REGRESSED** control passes, candidate fails (significant).",
          "- **SUSPECT** candidate fails where control passes, too few runs to be sure. **NEEDS MORE RUNS** nothing failed but fewer than MINRUNS runs (or too few to be significant). **NOT MEASURABLE** this criterion cannot be observed here (NA). **NOT TESTED** the environment was not run (reason given).",
          "- NA / not tested is never a failure. One-sided exact Fisher test, alpha %s. Exit code 1 only if a candidate (%s) is REGRESSED." % (ALPHA, ", ".join(cand)), ""]
    L += ["## Failure counts per cell (failures / measured runs)", "", "These are failures attributed to the named build. Control-build failures describe the baseline and do not count as candidate failures or regressions.", "", "| WM / compositor | where | session | screen | build | frame | focus | splash | centred | renders | exited | median dx/dy | flaky |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    import statistics as stt
    for wm in wms:
        _, disp, base, sess = wm_info(wm)
        for sc in scs:
            for b in builds:
                rs = cells.get((wm, sc, b))
                if not rs: continue
                f = fails(rs)
                cnt = lambda c: "%d/%d" % f[c] if f[c][1] else "NA"
                num = lambda k: [int(r[k]) for r in rs if r.get(k, "NA") != "NA"]
                med = lambda v: str(int(stt.median(v))) if v else "NA"
                L.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %d | %s/%s | %s |" % (disp, where(wm), sess, sc, b, cnt("frame"), cnt("focus"), cnt("splash_centred"), cnt("centred"), cnt("renders"),
                         sum(1 for r in rs if r["exited"] == "1"), med(num("dx")), med(num("dy")), "FLAKY" if (b == control and flaky(rs)) else ""))
    L += ["", "## Results per cell and criterion", "", "| WM / compositor | where | session | screen | build | outcome | detail |", "|---|---|---|---|---|---|---|"]
    vs = []
    for k in sorted(outs, key=lambda k: (wms.index(k[0]), k[1], k[2])):
        wm, sc, b = k; o, d = outs[k]["cell"]; _, disp, base, sess = wm_info(wm)
        if o == "NOT TESTED" and wm not in ran and False: continue
        if equiv_label and b == equiv_label and o in ("FIXED", "REGRESSED", "SUSPECT"): o = "DIFFERS"
        L.append("| %s | %s | %s | %s | %s | %s | %s |" % (disp, where(wm), sess, sc, b, o, d)); vs.append("%s | %s | %s | %s | %s = %s" % (disp, where(wm), sess, sc, b, o))
    L += host_section(cells, host_minruns)
    L += ["", "## Machine-readable outcomes", "", "```"] + vs + ["```", "", "Candidates REGRESSED: %d" % len(bad)]
    open(outp, "w").write("\n".join(L) + "\n")
    print("\n".join(HL))
    if single:
        n, bad_runs = LAST["measured"], LAST["regressed"]
        print("Result: %d passed" % (n - bad_runs) + (", %d failed" % bad_runs if bad_runs else ""))   # pytest style: counts, no "X of Y"
    else: print("FINAL: %d candidate cell(s) REGRESSED" % len(bad))
    return 1 if bad else 0


def selftest():
    mk = lambda nfail, n: [dict(frame="0" if i < nfail else "1", focus="1", centred="1", exited="0") for i in range(n)]
    ok = lambda c, m: print(("ok   " if c else "FAIL ") + m) or c
    r = []
    r.append(ok(compare(mk(5, 5), mk(0, 5), 5)[0] == "FIXED", "5/5 fail v 0/5 fail, MINRUNS 5 -> FIXED"))
    r.append(ok(compare(mk(5, 5), mk(0, 5), 10)[0] == "INCONCLUSIVE", "5 runs, MINRUNS 10 -> INCONCLUSIVE"))
    r.append(ok(compare(mk(0, 5), mk(1, 5), 5)[0] == "UNCHANGED", "1/5 v 0/5 -> UNCHANGED (not REGRESSED)"))
    r.append(ok(compare(mk(0, 10), mk(5, 10), 10)[0] == "REGRESSED", "5/10 v 0/10 -> REGRESSED"))
    r.append(ok(compare(mk(10, 10), mk(0, 10), 10)[0] == "FIXED", "10/10 v 0/10 -> FIXED"))
    r.append(ok(compare(mk(0, 2), mk(2, 2), 2)[0] == "INCONCLUSIVE", "2 v 2 can never reach significance -> INCONCLUSIVE"))
    r.append(ok(equiv(mk(0, 10), mk(5, 10), 10)[0].startswith("DIFFERS"), "equivalence check never says REGRESSED"))
    r.append(ok(flaky(mk(3, 10)) and not flaky(mk(0, 10)) and not flaky(mk(10, 10)), "FLAKY marker"))
    na = lambda n: [dict(frame="NA", focus="NA", centred="0", dx="NA", exited="0") for _ in range(n)]
    r.append(ok(fails(na(4))["frame"] == (0, 0) and fails(na(4))["centred"] == (0, 0), "NA (incl. centred with dx=NA) is not counted"))
    r.append(ok(compare(mk(0, 10), na(10), 1)[0] == "NOT MEASURED", "all-NA -> NOT MEASURED"))
    co = lambda fa, na, fb, nb, m: crit_outcome(fa, na, fb, nb, m)[0]
    r.append(ok(co(0, 10, 0, 10, 10) == "WORKS", "0/10 v 0/10 -> WORKS"))
    r.append(ok(co(0, 5, 0, 5, 10) == "NEEDS MORE RUNS", "all passed but 5 < 10 runs -> NEEDS MORE RUNS"))
    r.append(ok(co(10, 10, 0, 10, 10) == "FIXED" and co(5, 5, 0, 5, 5) == "FIXED", "control fails, candidate passes -> FIXED"))
    r.append(ok(co(5, 5, 5, 5, 5) == "STILL BROKEN", "fails in both -> STILL BROKEN"))
    r.append(ok(co(0, 10, 5, 10, 10) == "REGRESSED", "0/10 v 5/10 -> REGRESSED"))
    r.append(ok(co(0, 3, 3, 3, 5) == "SUSPECT" and co(0, 5, 1, 5, 5) == "SUSPECT", "fails where control passes, too few runs -> SUSPECT"))
    r.append(ok(co(0, 0, 0, 5, 5) == "NOT MEASURABLE", "unobservable -> NOT MEASURABLE"))
    print("SELFTEST", "PASS" if all(r) else "FAIL"); return 0 if all(r) else 1

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--selftest"]: return selftest()
    ap = argparse.ArgumentParser(prog="uitest verdict"); ap.add_argument("raw"); ap.add_argument("out")
    ap.add_argument("--control", default="base"); ap.add_argument("--candidates", default=""); ap.add_argument("--minruns", type=int, default=10)
    ap.add_argument("--tol", default="40"); ap.add_argument("--equiv", default=""); ap.add_argument("--header", default="")
    ap.add_argument("--host-minruns", type=int, default=0); ap.add_argument("--brief", action="store_true"); ap.add_argument("--versions", default="")
    ap.add_argument("--registry", default="")
    a = ap.parse_args(argv)
    if a.registry:
        from . import registry
        set_registry(registry.load(a.registry or None)[0])
    hdr = open(a.header).read() if a.header else ""
    if a.versions:
        for ln in open(a.versions):
            if "=" in ln and not ln.startswith("#"): k, v = ln.strip().split("=", 1); FALLBACK[k] = v
    return report(a.raw, a.out, a.control, a.candidates, a.minruns, a.tol, a.equiv, a.out.rsplit("/", 1)[-1][:-3], hdr, a.host_minruns or None, a.brief)


if __name__ == "__main__":
    sys.exit(main())
