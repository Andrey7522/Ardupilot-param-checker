#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Самопроверка параметров ArduPilot (Plane / Copter / QuadPlane).
Генерирует:
  <name>_REPORT.txt   — отчёт с причинами
  <name>_CHECKED.txt  — копию параметров с маркерами !!! / ! / i
  <name>_CHECKED.html — (опционально) цветная версия для браузера
"""
import sys, os, argparse, math
from collections import OrderedDict

SEV_ORDER = {"CRIT": 3, "WARN": 2, "INFO": 1}
SEV_LABEL = {"CRIT": "КРИТИЧНО", "WARN": "ВНИМАНИЕ", "INFO": "ИНФО"}
MARK      = {"CRIT": "!!! ", "WARN": "!   ", "INFO": "i   ", None: "    "}


def load_params(path):
    params = OrderedDict()
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#") or "," not in s:
                continue
            name, _, val = s.partition(",")
            name, val = name.strip(), val.strip()
            try:
                if any(c in val for c in ".eE"):
                    v = float(val)
                    if v.is_integer():
                        v = int(v)
                else:
                    v = int(val)
            except ValueError:
                v = val
            params[name] = v
    return params


def detect_vehicle(p):
    if p.get("Q_ENABLE") == 1:
        return "QuadPlane"
    if "TECS_CLMB_MAX" in p or "PTCH_RATE_P" in p or "NAVL1_PERIOD" in p:
        return "Plane"
    if "FRAME_CLASS" in p or "MOT_THST_HOVER" in p:
        return "Copter"
    return "Unknown"


def check_all(p, vehicle):
    issues = []
    def add(sev, param, value, msg):
        issues.append({"sev": sev, "param": param, "value": value, "msg": msg})
    def n(name, default=None):
        v = p.get(name, default)
        return v if isinstance(v, (int, float)) else default

    # ---- ARMING ----
    v = n("ARMING_CHECK")
    if v is None:
        add("WARN", "ARMING_CHECK", None, "Параметр отсутствует (по умолчанию 1=ALL)")
    elif v == 0:
        add("CRIT", "ARMING_CHECK", 0, "Все arming checks отключены — дрон армится без проверок")
    elif not (v & 1):
        crit = [(1, "Baro"), (2, "Compass"), (3, "GPS lock"), (4, "INS"),
                (6, "RC channels"), (7, "Board voltage"), (8, "Battery")]
        missing = [name for bit, name in crit if not (v & (1 << bit))]
        if missing:
            add("CRIT", "ARMING_CHECK", v, "Отключены критичные arming checks: " + ", ".join(missing))
        else:
            add("WARN", "ARMING_CHECK", v, "Нестандартная маска (не ALL) — проверьте намеренность")

    if n("ARMING_REQUIRE", 1) == 0:
        add("CRIT", "ARMING_REQUIRE", 0, "Arming не требуется — моторы могут крутиться сразу")

    # ---- FAILSAFE ----
    if vehicle in ("Plane", "QuadPlane"):
        if n("THR_FAILSAFE", 0) == 0:
            add("CRIT", "THR_FAILSAFE", 0, "Failsafe по потере RC (throttle) отключён")
        thr_min = n("THR_MIN", 0)
        thr_fs  = n("THR_FS_VALUE", 0)
        if thr_fs <= thr_min:
            add("WARN", "THR_FS_VALUE", thr_fs, f"Порог ({thr_fs}) <= THR_MIN ({thr_min}) — не сработает")
        if n("FS_GCS_ENABL", 0) == 0:
            add("WARN", "FS_GCS_ENABL", 0, "Failsafe по потере GCS отключён")
        if n("FS_LONG_ACTN", 1) == 0:
            add("CRIT", "FS_LONG_ACTN", 0, "Действие при длительном failsafe = None")
        if n("FS_SHORT_ACTN", 0) == 2:
            add("WARN", "FS_SHORT_ACTN", 2, "Короткий failsafe отключён")
    else:
        if n("FS_THR_ENABLE", 0) == 0:
            add("WARN", "FS_THR_ENABLE", 0, "Failsafe по RC throttle отключён")
        if n("FS_GCS_ENABLE", 0) == 0:
            add("WARN", "FS_GCS_ENABLE", 0, "Failsafe по GCS отключён")

    # ---- BATTERY ----
    if n("BATT_MONITOR", 0) == 0:
        add("WARN", "BATT_MONITOR", 0, "Мониторинг батареи отключён")
    else:
        arm, low, crt = n("BATT_ARM_VOLT", 0), n("BATT_LOW_VOLT", 0), n("BATT_CRT_VOLT", 0)
        if arm and low and crt and not (crt < low < arm):
            add("WARN", "BATT_LOW_VOLT", low,
                f"Нарушена иерархия: CRT({crt}) < LOW({low}) < ARM({arm})")
        if n("BATT_FS_LOW_ACT", 0) == 0:
            add("WARN", "BATT_FS_LOW_ACT", 0, "Действие при низком напряжении = None")
        if n("BATT_FS_CRT_ACT", 0) == 0:
            add("WARN", "BATT_FS_CRT_ACT", 0, "Действие при критическом напряжении = None")
        if n("BATT_CAPACITY", 0) == 0:
            add("WARN", "BATT_CAPACITY", 0, "Ёмкость батареи не задана")

    # ---- EKF / INS ----
    ekf_type = n("AHRS_EKF_TYPE", 3)
    if ekf_type == 0:
        add("CRIT", "AHRS_EKF_TYPE", 0, "EKF отключён — нет оценки ориентации")
    if ekf_type == 3 and n("EK3_ENABLE", 1) == 0:
        add("CRIT", "EK3_ENABLE", 0, "EKF3 выбран, но отключён")
    if n("EK3_IMU_MASK", 1) == 0:
        add("CRIT", "EK3_IMU_MASK", 0, "Ни один IMU не назначен для EKF3")
    if n("EK3_GPS_CHECK", 1) == 0:
        add("WARN", "EK3_GPS_CHECK", 0, "EKF не проверяет GPS — можно взлететь с плохим GPS")
    if n("EK3_SRC1_POSXY", 0) == 0:
        add("WARN", "EK3_SRC1_POSXY", 0, "Нет источника горизонтальной позиции")
    if n("EK3_SRC1_YAW", 0) == 0:
        add("WARN", "EK3_SRC1_YAW", 0, "Нет источника курса (YAW)")
    if n("INS_GYR_CAL", 1) == 0:
        add("CRIT", "INS_GYR_CAL", 0, "Гироскоп не калиброван")
    if "INS_ACC_ID" in p and p.get("INS_ACC_ID", 0) == 0:
        add("CRIT", "INS_ACC_ID", 0, "Акселерометр не калиброван")

    # ---- Harmonic notch ----
    if n("INS_HNTCH_ENABLE", 0) == 1:
        if n("INS_HNTCH_MODE", 0) == 0:
            add("WARN", "INS_HNTCH_MODE", 0,
                "Harmonic notch включён (ENABLE=1), но MODE=0 (Disabled) — фильтр не работает")
        if n("INS_HNTCH_FREQ", 0) <= 0:
            add("WARN", "INS_HNTCH_FREQ", 0, "FREQ не задана при включённом notch")
        if n("INS_HNTCH_HMNCS", 0) == 0:
            add("WARN", "INS_HNTCH_HMNCS", 0, "Не выбрано ни одной гармоники")

    # ---- COMPASS ----
    uses = [n("COMPASS_USE", 0), n("COMPASS_USE2", 0), n("COMPASS_USE3", 0)]
    if sum(1 for u in uses if u) == 0:
        add("CRIT", "COMPASS_USE", 0, "Все компасы отключены (USE=0, USE2=0, USE3=0)")
    elif n("COMPASS_USE", 0) == 0:
        add("WARN", "COMPASS_USE", 0, "Основной компас отключён")

    offs_max = n("COMPASS_OFFS_MAX", 1800)
    for i, sfx in [(1, ""), (2, "2"), (3, "3")]:
        x = n(f"COMPASS_OFS{sfx}_X")
        if x is None:
            continue
        mag = math.sqrt(x*x + (n(f"COMPASS_OFS{sfx}_Y", 0) or 0)**2 + (n(f"COMPASS_OFS{sfx}_Z", 0) or 0)**2)
        if mag > offs_max:
            add("WARN", f"COMPASS_OFS{sfx}_X", round(mag, 1),
                f"Смещение компаса {i} ({round(mag)}) > OFF S_MAX ({offs_max}) — перекалибровать/переставить")

    # ---- GPS ----
    if n("GPS_TYPE", 0) == 0:
        add("CRIT", "GPS_TYPE", 0, "GPS отключён")
    if n("AHRS_GPS_USE", 1) == 0:
        add("INFO", "AHRS_GPS_USE", 0, "GPS не используется в AHRS (допустимо для Plane)")

    # ---- FENCE ----
    if n("FENCE_ENABLE", 0) == 0:
        add("WARN", "FENCE_ENABLE", 0, "Геозона (fence) отключена")
    else:
        if n("FENCE_ACTION", 1) == 0:
            add("WARN", "FENCE_ACTION", 0, "FENCE_ACTION=Report only — дрон не вернётся/не сядет")
        if n("FENCE_TYPE", 0) == 0:
            add("WARN", "FENCE_TYPE", 0, "FENCE_TYPE=0 при включённой геозоне")
        if n("FENCE_ALT_MAX", 0) <= n("FENCE_ALT_MIN", 0):
            add("CRIT", "FENCE_ALT_MAX", n("FENCE_ALT_MAX"),
                f"ALT_MAX <= ALT_MIN ({n('FENCE_ALT_MIN')})")

    # ---- RC ----
    rcmap = {k: n(f"RCMAP_{k}") for k in ("ROLL", "PITCH", "THROTTLE", "YAW")}
    vals = [v for v in rcmap.values() if v is not None]
    if len(vals) != 4:
        add("WARN", "RCMAP_ROLL", rcmap.get("ROLL"), "Не все RCMAP_* заданы")
    elif len(set(vals)) != 4:
        add("CRIT", "RCMAP_ROLL", rcmap["ROLL"], f"Дублирование каналов RCMAP_*: {rcmap}")

    for stick in ("ROLL", "PITCH", "YAW"):
        ch = rcmap.get(stick)
        if not isinstance(ch, int) or ch == 0:
            continue
        mn, mx, tr = n(f"RC{ch}_MIN"), n(f"RC{ch}_MAX"), n(f"RC{ch}_TRIM")
        if None in (mn, mx, tr) or mx <= mn:
            continue
        rel = (tr - mn) / (mx - mn)
        if not (0.35 <= rel <= 0.65):
            add("WARN", f"RC{ch}_TRIM", tr, f"TRIM канала {stick} не по центру (rel={rel:.2f})")

    ch = rcmap.get("THROTTLE")
    if isinstance(ch, int) and ch:
        mn, mx, tr = n(f"RC{ch}_MIN"), n(f"RC{ch}_MAX"), n(f"RC{ch}_TRIM")
        if None not in (mn, mx, tr) and mx > mn:
            rel = (tr - mn) / (mx - mn)
            if rel > 0.3:
                add("WARN", f"RC{ch}_TRIM", tr, f"TRIM дросселя не в нижней части (rel={rel:.2f})")

    if n("RC_PROTOCOLS", 0) == 1:
        add("INFO", "RC_PROTOCOLS", 1, "Включён только PPM. Если приёмник SBUS/CRSF/DSM — RC работать не будет")
    if n("FLTMODE_CH", 0) == 0:
        add("WARN", "FLTMODE_CH", 0, "Канал переключения режимов не задан")

    # ---- SERVO / MOTORS ----
    motor_funcs = {33: 1, 34: 2, 35: 3, 36: 4, 37: 5, 38: 6, 39: 7, 40: 8}
    seen = {}
    for i in range(1, 17):
        f = n(f"SERVO{i}_FUNCTION")
        if f in motor_funcs:
            if f in seen:
                add("CRIT", f"SERVO{i}_FUNCTION", f,
                    f"Моторная функция {f} уже назначена на SERVO{seen[f]}")
            else:
                seen[f] = i
        mn, mx = n(f"SERVO{i}_MIN"), n(f"SERVO{i}_MAX")
        if mn is not None and mx is not None and mn >= mx:
            add("CRIT", f"SERVO{i}_MIN", mn, f"MIN({mn}) >= MAX({mx}) на SERVO{i}")

    if n("Q_ENABLE", 0) == 1 and len(seen) < 4:
        add("CRIT", "SERVO1_FUNCTION", len(seen),
            f"Назначено моторов: {len(seen)}, нужно 4+ для квадрокоптера")

    # ---- Q_* (QuadPlane) ----
    if n("Q_ENABLE", 0) == 1:
        if n("Q_FRAME_CLASS", 0) == 0:
            add("CRIT", "Q_FRAME_CLASS", 0, "Класс рамы не задан")
        pwm_min, pwm_max = n("Q_M_PWM_MIN", 1000), n("Q_M_PWM_MAX", 2000)
        if pwm_min >= pwm_max:
            add("CRIT", "Q_M_PWM_MIN", pwm_min, f"Q_M_PWM_MIN({pwm_min}) >= MAX({pwm_max})")
        spin_min, spin_max = n("Q_M_SPIN_MIN", 0), n("Q_M_SPIN_MAX", 1)
        if spin_min >= spin_max:
            add("CRIT", "Q_M_SPIN_MIN", spin_min, f"SPIN_MIN({spin_min}) >= SPIN_MAX({spin_max})")
        if n("Q_M_SPIN_ARM", 0) > spin_min:
            add("WARN", "Q_M_SPIN_ARM", n("Q_M_SPIN_ARM"), f"SPIN_ARM > SPIN_MIN({spin_min})")
        hov = n("Q_M_THST_HOVER", 0.5)
        if not (0.1 <= hov <= 0.8):
            add("WARN", "Q_M_THST_HOVER", hov, "THST_HOVER вне 0.1..0.8")
        vmin, vmax = n("Q_M_BAT_VOLT_MIN", 0), n("Q_M_BAT_VOLT_MAX", 0)
        if vmax > 0 and vmin >= vmax:
            add("CRIT", "Q_M_BAT_VOLT_MIN", vmin, f"VOLT_MIN({vmin}) >= VOLT_MAX({vmax})")
        if n("Q_ASSIST_SPEED", 0) == 0:
            add("WARN", "Q_ASSIST_SPEED", 0, "Q_ASSIST отключён (0)")

    # ---- PLANE ----
    if vehicle in ("Plane", "QuadPlane"):
        thr_min, thr_max = n("THR_MIN", 0), n("THR_MAX", 100)
        if thr_min >= thr_max:
            add("CRIT", "THR_MIN", thr_min, f"THR_MIN({thr_min}) >= THR_MAX({thr_max})")
        tt = n("TRIM_THROTTLE", 50)
        if not (thr_min <= tt <= thr_max):
            add("WARN", "TRIM_THROTTLE", tt, "TRIM_THROTTLE вне THR_MIN..THR_MAX")
        pmin, pmax = n("TECS_PITCH_MIN", 0), n("TECS_PITCH_MAX", 0)
        if pmin >= pmax:
            add("CRIT", "TECS_PITCH_MIN", pmin, f"TECS_PITCH_MIN({pmin}) >= MAX({pmax})")
        lmin, lmax = n("PTCH_LIM_MIN_DEG", -90), n("PTCH_LIM_MAX_DEG", 90)
        if lmin >= lmax:
            add("CRIT", "PTCH_LIM_MIN_DEG", lmin, f"PTCH_LIM_MIN({lmin}) >= MAX({lmax})")
        if n("ARSPD_USE", 0) == 0:
            add("WARN", "ARSPD_USE", 0, "Airspeed не используется")
        elif n("ARSPD_TYPE", 0) == 0:
            add("CRIT", "ARSPD_TYPE", 0, "ARSPD_USE=1, но датчик airspeed не задан")
        if n("STALL_PREVENTION", 1) == 0:
            add("WARN", "STALL_PREVENTION", 0, "Защита от сваливания отключена")

    # ---- LOG / BOARD ----
    if n("LOG_BITMASK", 0) == 0:
        add("WARN", "LOG_BITMASK", 0, "Логирование отключено")
    if n("FFT_ENABLE", 0) == 0 and n("INS_LOG_BAT_MASK", 0) == 0:
        add("INFO", "INS_LOG_BAT_MASK", 0, "Нет batch-логирования IMU и FFT — не будет данных по вибрациям")
    if n("BRD_SAFETY_DEFLT", 1) == 0:
        add("INFO", "BRD_SAFETY_DEFLT", 0, "Safety switch по умолчанию отключён")

    return issues


def build_param_severity(issues):
    byparam = {}
    for it in issues:
        p = it["param"]
        if not p:
            continue
        if p not in byparam:
            byparam[p] = it["sev"]
        elif SEV_ORDER[it["sev"]] > SEV_ORDER[byparam[p]]:
            byparam[p] = it["sev"]
    return byparam


def write_report(path, issues, vehicle, src, nparams):
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write("=" * 78 + "\n")
        f.write(f"  ПРОВЕРКА ПАРАМЕТРОВ — {vehicle}\n")
        f.write(f"  Файл: {src}\n")
        f.write(f"  Параметров загружено: {nparams}\n")
        f.write("=" * 78 + "\n")
        if not issues:
            f.write("\n  [OK] Проблем не найдено.\n")
            return
        counts = {}
        for it in issues:
            counts[it["sev"]] = counts.get(it["sev"], 0) + 1
        f.write("\n  Сводка: " + ", ".join(
            f"{SEV_LABEL[s]}={counts[s]}" for s in ("CRIT", "WARN", "INFO") if s in counts) + "\n\n")
        for sev in ("CRIT", "WARN", "INFO"):
            grp = [i for i in issues if i["sev"] == sev]
            if not grp:
                continue
            f.write("\n" + "-" * 78 + "\n")
            f.write(f"  {SEV_LABEL[sev]} ({len(grp)})\n")
            f.write("-" * 78 + "\n")
            for it in grp:
                val = "-" if it["value"] is None else str(it["value"])
                f.write(f"{MARK[sev]} {it['param']} = {val}\n")
                f.write(f"      {it['msg']}\n\n")


def write_marked(src_path, out_path, issues, vehicle):
    with open(src_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        lines = f.readlines()
    byparam = build_param_severity(issues)
    with open(out_path, "w", encoding="utf-8-sig") as f:
        f.write("=" * 78 + "\n")
        f.write(f"  МАРКИРОВАННЫЕ ПАРАМЕТРЫ — {vehicle}\n")
        f.write("=" * 78 + "\n")
        f.write("  !!!  = КРИТИЧНО (дрон не должен взлетать)\n")
        f.write("  !    = ВНИМАНИЕ  (полёт с риском)\n")
        f.write("  i    = ИНФО      (стоит проверить)\n")
        f.write("  (пусто) = проблем не обнаружено\n")
        f.write("=" * 78 + "\n\n")
        for line in lines:
            raw = line.rstrip("\n")
            stripped = raw.strip()
            name = stripped.split(",")[0].strip() if "," in stripped else ""
            sev = byparam.get(name)
            f.write(MARK[sev] + raw + "\n")


def write_html(src_path, out_path, issues, vehicle, src):
    with open(src_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        lines = f.readlines()
    byparam = build_param_severity(issues)
    colors = {"CRIT": "#ffd0d0", "WARN": "#fff4cc", "INFO": "#d8ecff"}
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("<!DOCTYPE html><html><head><meta charset='utf-8'>\n")
        f.write(f"<title>{src}</title>\n<style>")
        f.write("body{font-family:Consolas,monospace;background:#1e1e1e;color:#ccc;padding:20px;font-size:14px}")
        f.write(".crit{background:#ffd0d0;color:#000}").write(".warn{background:#fff4cc;color:#000}")
        f.write(".info{background:#d8ecff;color:#000}")
        f.write(".ln{display:inline-block;width:3.5em;text-align:right;color:#666;margin-right:1em}")
        f.write("</style></head><body>\n")
        f.write(f"<h2>{vehicle} — {src}</h2>\n<pre>\n")
        for i, line in enumerate(lines, 1):
            raw = line.rstrip("\n").replace("<", "&lt;")
            stripped = line.strip()
            name = stripped.split(",")[0].strip() if "," in stripped else ""
            sev = byparam.get(name)
            cls = f" class='{sev.lower()}'" if sev else ""
            f.write(f"<span class='ln'>{i}</span><span{cls}>{raw}</span>\n")
        f.write("</pre></body></html>\n")


def main():
    ap = argparse.ArgumentParser(description="Самопроверка параметров ArduPilot")
    ap.add_argument("param", help="файл параметров (.param / .txt)")
    ap.add_argument("-r", "--report", help="отчёт (по умолчанию <name>_REPORT.txt)")
    ap.add_argument("-m", "--marked", help="маркеры (по умолчанию <name>_CHECKED.txt)")
    ap.add_argument("--html", action="store_true", help="доп. цветной HTML-отчёт")
    args = ap.parse_args()

    if not os.path.isfile(args.param):
        print(f"Файл не найден: {args.param}")
        sys.exit(3)

    cur = load_params(args.param)
    vehicle = detect_vehicle(cur)
    issues = check_all(cur, vehicle)

    base, ext = os.path.splitext(args.param)
    report_path = args.report or f"{base}_REPORT.txt"
    marked_path = args.marked or f"{base}_CHECKED{ext or '.txt'}"

    write_report(report_path, issues, vehicle, args.param, len(cur))
    write_marked(args.param, marked_path, issues, vehicle)
    if args.html:
        write_html(args.param, f"{base}_CHECKED.html", issues, vehicle, args.param)

    counts = {}
    for it in issues:
        counts[it["sev"]] = counts.get(it["sev"], 0) + 1
    print(f"\nПроверка: {args.param}")
    print(f"Тип: {vehicle}, параметров: {len(cur)}\n")
    for it in issues:
        val = "-" if it["value"] is None else str(it["value"])
        print(f"  [{it['sev']}] {it['param']} = {val}")
        print(f"         {it['msg']}")
    if counts:
        print("\n  Итого: " + ", ".join(
            f"{SEV_LABEL[s]}={counts[s]}" for s in ("CRIT", "WARN", "INFO") if s in counts))
    print(f"\n  Отчёт:   {report_path}")
    print(f"  Маркеры: {marked_path}" + (f"\n  HTML:    {base}_CHECKED.html" if args.html else ""))

    sys.exit(2 if "CRIT" in counts else 1 if "WARN" in counts else 0)


if __name__ == "__main__":
    main()