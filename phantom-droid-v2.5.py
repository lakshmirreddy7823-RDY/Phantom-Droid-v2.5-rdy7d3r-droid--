#!/usr/bin/env python3
#install requement # Kali / Debian
# sudo apt install adb scrcpy libimobiledevice-utils usbmuxd
# pip3 install pymobiledevice3 frida-tools "qrcode[pil]"

import os
import sys
import time
import json
import shlex
import shutil
import signal
import subprocess
import threading
from datetime import datetime

# ============================ CONFIG ============================
CONFIG = {
    "adb_port": 5555,
    "output_dir": os.path.join(os.getcwd(), "phantom_output"),
    "auto_wifi_transfer": True,   # USB -> WiFi auto transfer
    "screen_share_fps": 24,
    "scrcpy_args": [],
    "frida_default": "frida-server",
}
SESSIONS = {}          # active screen-share sessions {serial: popen}
IOS_SESSIONS = {}      # {udid: {"syslog": popen}}
BANNER_SMALL = False

# ============================ UTILS ============================
BANNER = r"""
██████╗ ██╗  ██╗ █████╗ ███╗   ██╗████████╗ ██████╗ ███╗   ███╗██████╗ ██████╗  ██████╗ ██╗██████╗
██╔══██╗██║  ██║██╔══██╗████╗  ██║╚══██╔══╝██╔═══██╗████╗ ████║██╔══██╗██╔══██╗██╔═══██╗██║██╔══██╗
██████╔╝███████║███████║██╔██╗ ██║   ██║   ██║   ██║██╔████╔██║██║  ██║██████╔╝██║   ██║██║██║  ██║
██╔═══╝ ██╔══██║██╔══██║██║╚██╗██║   ██║   ██║   ██║██║╚██╔╝██║██║  ██║██╔══██╗██║   ██║██║██║  ██║
██║     ██║  ██║██║  ██║██║ ╚████║   ██║   ╚██████╔╝██║ ╚═╝ ██║██████╔╝██║  ██║╚██████╔╝██║██████╔╝
╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═══╝   ╚═╝    ╚═════╝ ╚═╝     ╚═╝╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚═╝╚═════╝
 Phantom-Droid v2.5                          Created by @Rdy7d3r
 Android (ADB) + iOS (usbmuxd)
"""

def c(code, s): return f"\033[{code}m{s}\033[0m" if sys.stdout.isatty() else str(s)
def green(s): return c("92", s)
def red(s):   return c("91", s)
def yellow(s):return c("93", s)
def cyan(s):  return c("96", s)
def bold(s):  return c("1", s)

def log(tag, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{yellow(f'[{ts}]')} {green(f'[{tag}]')} {msg}")
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    with open(os.path.join(CONFIG["output_dir"], "phantom.log"), "a") as f:
        f.write(f"[{ts}] [{tag}] {msg}\n")

def run(cmd, timeout=60, capture=True):
    """Run a shell command, return (rc, stdout+stderr)."""
    try:
        r = subprocess.run(cmd, shell=isinstance(cmd, str), timeout=timeout,
                           capture_output=capture, text=True)
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode, out.strip()
    except FileNotFoundError:
        return 127, f"command not found: {cmd if isinstance(cmd,str) else cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "timeout"
    except Exception as e:
        return 1, str(e)

def ensure_dir():
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    return CONFIG["output_dir"]

def ts(): return datetime.now().strftime("%Y%m%d_%H%M%S")

def pick(devices, kind="serial"):
    """Let user pick a device if multiple."""
    if not devices:
        print(red("No devices found.")); return None
    if len(devices) == 1:
        return devices[0]
    print(cyan("Available devices:"))
    for i, d in enumerate(devices, 1):
        print(f"  {i}. {d}")
    try:
        n = int(input("Select device #: "))
        return devices[n-1] if 1 <= n <= len(devices) else None
    except (ValueError, IndexError):
        return None

def have(tool):
    return shutil.which(tool) is not None

# ========================= ANDROID / ADB =========================
def adb(*args, serial=None, timeout=60):
    cmd = ["adb"]
    if serial: cmd += ["-s", serial]
    cmd += list(args)
    return run(cmd, timeout)

def android_devices():
    rc, out = adb("devices")
    devs = []
    if rc == 0:
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devs.append(parts[0])
    return devs

# --- Android features ---
def a_list_devices():
    print(cyan(bold("[ANDROID] Devices:")))
    rc, out = adb("devices", "-l")
    print(out if rc == 0 else red("adb not available"))
    for d in android_devices():
        rc, model = adb("shell", "getprop", "ro.product.model", serial=d)
        rc2, ver = adb("shell", "getprop", "ro.build.version.release", serial=d)
        print(f"  {green(d)}  model={model}  android={ver}")

def a_connect_wifi():
    ip = input("Device IP:port (e.g. 192.168.1.11:5555): ").strip()
    rc, out = adb("connect", ip)
    print(green(out) if rc == 0 else red(out))

def a_disconnect():
    rc, out = adb("devices")
    for line in out.splitlines()[1:]:
        s = line.split()[0] if line.split() else ""
        if ":5555" in s:
            _, o2 = adb("disconnect", s)
            log("ADB", f"disconnected {s}")
    print(green("Done."))

def a_device_info():
    d = pick(android_devices())
    if not d: return
    props = ["ro.product.model","ro.product.brand","ro.build.version.release",
             "ro.build.version.sdk","ro.serialno","ro.product.cpu.abi",
             "persist.sys.timezone","wifi.interface"]
    for p in props:
        _, v = adb("shell", "getprop", p, serial=d)
        print(f"  {cyan(p)}: {v}")

def a_restart_adb():
    adb("kill-server"); time.sleep(1); adb("start-server")
    print(green("ADB server restarted."))

def a_check_connection():
    devs = android_devices()
    print(green(f"{len(devs)} device(s) online: {devs}") if devs else red("None online."))

def a_shell():
    d = pick(android_devices())
    if not d: return
    print(yellow("Interactive ADB shell. 'exit' to quit."))
    while True:
        cmd = input(f"adb:{d}$ ").strip()
        if cmd in ("exit", "quit"): break
        if cmd: print(run(f"adb -s {d} shell {cmd}", timeout=120)[1])

def a_logs():
    d = pick(android_devices())
    if not d: return
    f = os.path.join(ensure_dir(), f"logcat_{d}_{ts()}.log")
    rc, _ = adb("logcat", "-d", serial=d)
    with open(f, "w") as fh: fh.write(_)
    print(green(f"Saved {len(_)} bytes -> {f}"))
    tail = input("Show last 50 lines? [y/N]: ").lower()
    if tail == "y":
        _, out = adb("shell", "logcat", "-d", "-t", "50", serial=d)
        print(out)

def a_reboot():
    d = pick(android_devices())
    if d:
        adb("reboot", serial=d); print(green(f"Rebooting {d}..."))

# App management
def a_install():
    d = pick(android_devices())
    if not d: return
    apk = input("Path to APK: ").strip().strip('"')
    rc, out = adb("install", "-r", apk, serial=d)
    print(green(out) if rc == 0 else red(out))

def a_uninstall():
    d = pick(android_devices())
    if not d: return
    pkg = input("Package name: ").strip()
    rc, out = adb("uninstall", pkg, serial=d)
    print(green(out) if rc == 0 else red(out))

def a_list_packages():
    d = pick(android_devices())
    if not d: return
    _, out = adb("shell", "pm", "list", "packages", "-3", serial=d)
    pkgs = sorted(l.replace("package:", "") for l in out.splitlines() if l)
    term = input("Filter (blank = all): ").strip().lower()
    for p in pkgs:
        if term in p: print("  " + p)
    print(green(f"Total: {len(pkgs)} third-party packages"))

def a_package_info():
    d = pick(android_devices())
    if not d: return
    pkg = input("Package name: ").strip()
    _, out = adb("shell", "dumpsys", "package", pkg, serial=d)
    print(out[:4000])

def a_clear_data():
    d = pick(android_devices())
    if not d: return
    pkg = input("Package name: ").strip()
    rc, out = adb("shell", "pm", "clear", pkg, serial=d)
    print(green(out) if rc == 0 else red(out))

def a_force_stop():
    d = pick(android_devices())
    if not d: return
    pkg = input("Package name: ").strip()
    adb("shell", "am", "force-stop", pkg, serial=d); print(green("Stopped."))

def a_start_app():
    d = pick(android_devices())
    if not d: return
    comp = input("Component (pkg/.Activity or monkey pkg): ").strip()
    rc, out = adb("shell", "monkey", "-p", comp, "-c",
                  "android.intent.category.LAUNCHER", "1", serial=d) \
              if "." not in comp.split("/")[0] else \
              adb("shell", "am", "start", "-n", comp, serial=d)
    print(green("Launched.") if rc == 0 else red(out))

def a_backup_app():
    d = pick(android_devices())
    if not d: return
    pkg = input("Package name: ").strip()
    apks, _, _ = f"pm path {pkg}", None, None
    _, out = adb("shell", "pm", "path", pkg, serial=d)
    paths = [l.replace("package:", "").strip() for l in out.splitlines() if l]
    if not paths: print(red("Package not found.")); return
    outdir = os.path.join(ensure_dir(), "apks"); os.makedirs(outdir, exist_ok=True)
    for p in paths:
        dest = os.path.join(outdir, f"{pkg}_{ts()}_{os.path.basename(p)}")
        rc, _o = adb("pull", p, dest, serial=d)
        print(green(f"Pulled -> {dest}") if rc == 0 else red(_o))

def a_batch_install():
    d = pick(android_devices())
    if not d: return
    folder = input("Folder with APKs: ").strip().strip('"')
    if not os.path.isdir(folder): print(red("Not a folder.")); return
    for f in os.listdir(folder):
        if f.endswith(".apk"):
            rc, out = adb("install", "-r", os.path.join(folder, f), serial=d)
            print(green(f"[OK] {f}") if rc == 0 else red(f"[FAIL] {f}: {out}"))

# File ops
def a_screenshot(d=None):
    d = d or pick(android_devices())
    if not d: return
    remote = "/sdcard/_phantom_shot.png"
    adb("shell", "screencap", "-p", remote, serial=d)
    local = os.path.join(ensure_dir(), f"shot_{d}_{ts()}.png")
    rc, out = adb("pull", remote, local, serial=d)
    adb("shell", "rm", remote, serial=d)
    print(green(f"Saved -> {local}") if rc == 0 else red(out))

def a_multi_screenshot():
    n = int(input("How many shots: ") or "3")
    delay = float(input("Delay seconds: ") or "1")
    d = pick(android_devices())
    if not d: return
    for i in range(n):
        a_screenshot(d); time.sleep(delay)

def a_record_screen():
    d = pick(android_devices())
    if not d: return
    secs = int(input("Seconds to record: ") or "10")
    remote = "/sdcard/_phantom_rec.mp4"
    print(yellow(f"Recording {secs}s..."))
    t = threading.Thread(target=adb, args=("shell", "screenrecord",
        "--time-limit", str(secs), remote), kwargs={"serial": d, "timeout": secs+30})
    t.start(); t.join()
    local = os.path.join(ensure_dir(), f"rec_{d}_{ts()}.mp4")
    rc, out = adb("pull", remote, local, serial=d)
    adb("shell", "rm", remote, serial=d)
    print(green(f"Saved -> {local}") if rc == 0 else red(out))

def a_upload():
    d = pick(android_devices())
    if not d: return
    src = input("Local file: ").strip().strip('"')
    dest = input("Remote path [/sdcard/]: ").strip() or "/sdcard/"
    rc, out = adb("push", src, dest, serial=d)
    print(green(out) if rc == 0 else red(out))

def a_download():
    d = pick(android_devices())
    if not d: return
    src = input("Remote path: ").strip()
    rc, out = adb("pull", src, ensure_dir(), serial=d)
    print(green(out) if rc == 0 else red(out))

def a_list_files():
    d = pick(android_devices())
    if not d: return
    path = input("Remote path [/sdcard/]: ").strip() or "/sdcard/"
    _, out = adb("shell", "ls", "-la", path, serial=d)
    print(out)

def a_mkdir():
    d = pick(android_devices())
    if not d: return
    path = input("Remote folder path: ").strip()
    rc, _ = adb("shell", "mkdir", "-p", path, serial=d)
    print(green("Created.") if rc == 0 else red("Failed."))

def a_delete():
    d = pick(android_devices())
    if not d: return
    path = input("Remote path to delete: ").strip()
    if input(red(f"Delete {path}? [y/N]: ")).lower() != "y": return
    rc, _ = adb("shell", "rm", "-rf", path, serial=d)
    print(green("Deleted.") if rc == 0 else red("Failed."))

def a_backup_folder():
    d = pick(android_devices())
    if not d: return
    src = input("Remote folder: ").strip()
    rc, out = adb("pull", src, ensure_dir(), serial=d)
    print(green(out) if rc == 0 else red(out))

# System monitoring
def _dump(d, svc):
    _, out = adb("shell", "dumpsys", svc, serial=d)
    return out

def a_battery():
    d = pick(android_devices());  print(_dump(d, "battery")[:2000] if d else "")

def a_memory():
    d = pick(android_devices());  print(_dump(d, "meminfo")[:3000] if d else "")

def a_cpu():
    d = pick(android_devices())
    if d:
        _, out = adb("shell", "top", "-n", "1", "-b", serial=d)
        print(out[:3000])

def a_storage():
    d = pick(android_devices())
    if d:
        _, out = adb("shell", "df", "-h", serial=d); print(out)

def a_processes():
    d = pick(android_devices())
    if d:
        _, out = adb("shell", "ps", "-A", serial=d); print(out)

def a_network():
    d = pick(android_devices())
    if d:
        for cmd in (["ip", "addr"], ["ip", "route"]):
            _, out = adb("shell", *cmd, serial=d); print(cyan(" ".join(cmd))); print(out)

def a_sysprops():
    d = pick(android_devices())
    if d:
        _, out = adb("shell", "getprop", serial=d); print(out[:6000])

def a_apps_size():
    d = pick(android_devices())
    if not d: return
    _, out = adb("shell", "pm", "list", "packages", "-3", serial=d)
    for l in out.splitlines():
        p = l.replace("package:", "").strip()
        _, du = adb("shell", "du", "-h", p, serial=d)  # fallback simple
    _, out2 = adb("shell", "dumpsys", "diskstats", serial=d)
    print(out2[:3000])

def a_monitor_perf():
    d = pick(android_devices())
    if not d: return
    print(yellow("Live performance (Ctrl+C to stop)"))
    try:
        while True:
            _, cpu = adb("shell", "top", "-n", "1", "-b", serial=d)
            print("\033[2J\033[H" + cpu[:2000]); time.sleep(2)
    except KeyboardInterrupt: print()

# Screen sharing (scrcpy)
def a_start_share(d=None, custom=False):
    d = d or pick(android_devices())
    if not d: return
    if not have("scrcpy"):
        print(red("scrcpy not installed. apt install scrcpy")); return
    args = ["scrcpy", "-s", d]
    if custom:
        extra = input("Extra scrcpy args (e.g. --max-size 1024 --bit-rate 2M): ").split()
        args += extra
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    SESSIONS[d] = p
    log("SCRCPY", f"session started {d} (pid {p.pid})")

def a_stop_share():
    d = pick(list(SESSIONS.keys()) or [])
    if d and d in SESSIONS:
        SESSIONS[d].terminate(); del SESSIONS[d]; print(green("Stopped."))

def a_stop_all():
    for s, p in list(SESSIONS.items()):
        p.terminate(); del SESSIONS[s]
    print(green("All sessions stopped."))

def a_active_sessions():
    for s, p in list(SESSIONS.items()):
        alive = p.poll() is None
        print(f"  {s}: {'RUNNING' if alive else 'DEAD'} (pid {p.pid})")
    if not SESSIONS: print("  none")

def a_multi_share():
    for d in android_devices():
        a_start_share(d)

def a_check_scrcpy():
    rc, out = run("scrcpy --version")
    print(green(out.splitlines()[0]) if rc == 0 else red("scrcpy missing"))

def a_sync_folder():
    d = pick(android_devices())
    if not d: return
    src = input("Local folder: ").strip().strip('"')
    dest = input("Remote folder [/sdcard/]: ").strip() or "/sdcard/"
    rc, out = adb("push", src + "/.", dest, serial=d, timeout=600)
    print(green("Synced.") if rc == 0 else red(out))

# WiFi management
def _detect_new_usb(known):
    devs = set(android_devices())
    return [d for d in devs - known if ":5555" not in d]

def _usb_to_wifi(serial):
    rc, ip = run(f"adb -s {serial} shell ip -4 addr show wlan0")
    ipaddr = next((l.split()[1].split("/")[0] for l in ip.splitlines()
                   if "inet " in l), None)
    if not ipaddr:
        log("USB-WiFi", f"no wlan0 IP on {serial}, skipping"); return False
    log("USB-WiFi", f"New USB device detected: {serial}")
    log("USB-WiFi", f"Enabling TCP/IP mode for {serial} on port {CONFIG['adb_port']}...")
    _, out = adb("tcpip", str(CONFIG["adb_port"]), serial=serial)
    log("USB-WiFi", out or "TCP/IP mode enabled")
    target = f"{ipaddr}:{CONFIG['adb_port']}"
    log("USB-WiFi", f"Connecting {serial} via WiFi to {target}...")
    rc, out = adb("connect", target)
    if rc == 0 and "connected" in out.lower():
        log("USB-WiFi", f"Device {serial} successfully transferred to WiFi")
        return True
    log("USB-WiFi", f"connect failed: {out}")
    return False

def a_wifi_transfer():
    d = pick(android_devices())
    if d: _usb_to_wifi(d)

def a_transfer_all():
    for d in _detect_new_usb(set()):
        _usb_to_wifi(d)

def a_quick_setup():
    print(yellow("Watching for USB devices — plug devices now (Ctrl+C to stop)"))
    known = set(android_devices())
    try:
        while True:
            for d in _detect_new_usb(known):
                if CONFIG["auto_wifi_transfer"]:
                    _usb_to_wifi(d)
            known = set(android_devices())
            time.sleep(2)
    except KeyboardInterrupt:
        print(green("\nWatcher stopped."))

def a_wifi_status():
    rc, out = adb("devices")
    print(out)

def a_disconnect_wifi():
    a_disconnect()

def a_toggle_auto():
    CONFIG["auto_wifi_transfer"] = not CONFIG["auto_wifi_transfer"]
    print(green(f"Auto-transfer = {CONFIG['auto_wifi_transfer']}"))

def a_monitor_logcat():
    d = pick(android_devices())
    if not d: return
    filt = input("Tag filter (blank=all): ").strip()
    cmd = f"adb -s {d} logcat"
    if filt: cmd += f" -s {filt}"
    p = subprocess.run(cmd, shell=True)
    print()

def a_service_status():
    for t in ("adb", "scrcpy", "frida"):
        print(f"  {t}: {green('OK') if have(t) else red('MISSING')}")
    rc, _ = run("pymobiledevice3 --help")
    print(f"  pymobiledevice3: {green('OK') if rc == 0 else red('MISSING')}")
    rc, _ = run("idevice_id -l")
    print(f"  libimobiledevice: {green('OK') if rc == 0 else red('MISSING')}")

def a_settings():
    print(f"  output_dir: {CONFIG['output_dir']}")
    print(f"  adb_port: {CONFIG['adb_port']}")
    print(f"  auto_wifi_transfer: {CONFIG['auto_wifi_transfer']}")
    new = input("Change adb_port? (blank=keep): ").strip()
    if new.isdigit(): CONFIG["adb_port"] = int(new)
    od = input("Change output_dir? (blank=keep): ").strip()
    if od: CONFIG["output_dir"] = od; ensure_dir()

def a_qr_payload():
    data = input("Payload text/URL for QR: ").strip()
    try:
        import qrcode
        img = qrcode.make(data)
        f = os.path.join(ensure_dir(), f"qr_{ts()}.png")
        img.save(f); print(green(f"QR saved -> {f}"))
        qrcodeterminal = None
    except ImportError:
        print(red("pip install qrcode[pil]"))

def a_qr_exploit():
    print(yellow("QR payload: push a shortcut/URL to the device via QR scanner"))
    url = input("URL/command endpoint: ").strip()
    payload = f"intent://scan#Intent;scheme={shlex.quote(url)};end"
    a_qr_payload.__wrapped__ if False else None
    try:
        import qrcode
        f = os.path.join(ensure_dir(), f"qr_exploit_{ts()}.png")
        qrcode.make(payload).save(f)
        print(green(f"QR exploit payload saved -> {f}\nPayload: {payload}"))
    except ImportError:
        print(red("pip install qrcode[pil]"), "\nPayload:", payload)

# ========================= iOS MANAGEMENT =========================
def idev(*args, timeout=60):
    return run(["idevice" + args[0]] + list(args[1:]), timeout) \
        if have("idevice" + args[0]) else run(["idevice" + args[0]] + list(args[1:]), timeout)

def _pm3(*args, timeout=120):
    return run(["pymobiledevice3"] + list(args), timeout)

def ios_devices():
    rc, out = run(["idevice_id", "-l"])
    if rc == 0 and out:
        return [l.strip() for l in out.splitlines() if l.strip()]
    rc, out = _pm3("usbmux", "list")
    if rc == 0:
        try:
            return [d["UniqueDeviceID"] for d in json.loads(out)]
        except Exception:
            pass
    return []

def ios_pick():
    return pick(ios_devices(), kind="udid")

def i_list_devices():
    print(cyan(bold("[iOS] Devices:")))
    devs = ios_devices()
    if not devs:
        print(red("No iOS devices. Check usbmuxd / idevice_id / pymobiledevice3."))
        return
    for u in devs:
        rc, name = run(["ideviceinfo", "-u", u, "-k", "DeviceName"])
        rc2, ver = run(["ideviceinfo", "-u", u, "-k", "ProductVersion"])
        rc3, model = run(["ideviceinfo", "-u", u, "-k", "ProductType"])
        print(f"  {green(u)}  name={name}  ios={ver}  model={model}")

def i_device_info():
    u = ios_pick()
    if not u: return
    rc, out = run(["ideviceinfo", "-u", u])
    print(out if rc == 0 else red("ideviceinfo failed"))
    if rc != 0:
        rc, out = _pm3("activer", "-u", u)  # placeholder
        rc, out = _pm3("usbmux", "forward")

def i_pair():
    u = ios_pick()
    if not u: return
    rc, out = run(["idevicepair", "-u", u, "pair"])
    print(green("Paired.") if rc == 0 else red(out))

def i_apps_list():
    u = ios_pick()
    if not u: return
    rc, out = _pm3("apps", "list", "--user", "-u", u)
    if rc == 0:
        try:
            for a in json.loads(out):
                print(f"  {a.get('CFBundleIdentifier','?'):45s} {a.get('CFBundleDisplayName','')}")
        except Exception: print(out)
    else:
        print(red("pymobiledevice3 apps list failed (install: pip install pymobiledevice3)"))

def i_app_install():
    u = ios_pick()
    if not u: return
    ipa = input("Path to .ipa: ").strip().strip('"')
    rc, out = _pm3("apps", "install", ipa, "-u", u, timeout=600)
    print(green("Installed.") if rc == 0 else red(out))

def i_app_uninstall():
    u = ios_pick()
    if not u: return
    bid = input("Bundle ID: ").strip()
    rc, out = _pm3("apps", "uninstall", bid, "-u", u)
    print(green("Uninstalled.") if rc == 0 else red(out))

def i_syslog():
    u = ios_pick()
    if not u: return
    print(yellow("Live syslog (Ctrl+C to stop). Saved to file."))
    f = os.path.join(ensure_dir(), f"ios_syslog_{u}_{ts()}.log")
    rc, out = run(["idevicesyslog", "-u", u], timeout=86400)
    if rc == 0:
        with open(f, "w") as fh: fh.write(out)
        print(green(f"Saved -> {f}")); print(out[:5000])
    else:
        print(yellow("idevicesyslog unavailable; trying pymobiledevice3 live..."))
        subprocess.run(["pymobiledevice3", "syslog", "live", "-u", u])

def i_screenshot():
    u = ios_pick()
    if not u: return
    f = os.path.join(ensure_dir(), f"ios_shot_{u}_{ts()}.png")
    rc, out = _pm3("developer", "dvt", "screenshot", f, "-u", u, timeout=60)
    print(green(f"Saved -> {f}") if rc == 0 else
          red("Failed. Requires Developer Mode enabled + pymobiledevice3 developer services.\n" + out))

def i_reboot():
    u = ios_pick()
    if not u: return
    rc, out = run(["idevicediagnostics", "-u", u, "restart"])
    print(green("Rebooting.") if rc == 0 else red(out or "idevicediagnostics failed"))

def i_crash_list():
    u = ios_pick()
    if not u: return
    rc, out = _pm3("crash", "ls", "-u", u)
    print(out if rc == 0 else red("crash service failed"))

def i_frida():
    u = ios_pick()
    if not u: return
    if not have("frida-ps"):
        print(red("pip install frida-tools")); return
    target = input("Process name to attach (blank=list USB procs): ").strip()
    if target:
        subprocess.run(["frida", "-U", "-f", target])
    else:
        subprocess.run(["frida-ps", "-U"])

def i_backup():
    u = ios_pick()
    if not u: return
    dest = os.path.join(ensure_dir(), f"ios_backup_{ts()}")
    print(yellow("Starting full backup (can take a long time)..."))
    subprocess.run(["idevicebackup2", "backup", dest, "-u", u])

def i_auto_detect():
    print(yellow("Watching for iOS USB attach events (Ctrl+C to stop)"))
    known = set(ios_devices())
    try:
        while True:
            cur = set(ios_devices())
            for u in cur - known:
                log("iOS-USB", f"New iOS device attached: {u}")
                rc, out = run(["idevicepair", "-u", u, "validate"])
                log("iOS-USB", "pairing valid" if rc == 0 else "needs pairing (run: idevicepair pair)")
            known = cur
            time.sleep(2)
    except KeyboardInterrupt:
        print(green("\nWatcher stopped."))

# ========================= MENUS =========================
ANDROID_MENU = """
 ANDROID (ADB)              |  APP MGMT               |  FILES / SCREEN
----------------------------|-------------------------|-----------------------
  1. List devices           | 10. Install APK         | 19. Screenshot
  2. Connect WiFi           | 11. Uninstall app       | 20. Multi screenshot
  3. Disconnect device      | 12. List packages       | 21. Record screen
  4. Device info            | 13. Package info        | 22. Upload file
  5. Restart ADB            | 14. Clear app data      | 23. Download file
  6. Check connection       | 15. Force stop app      | 24. List files
  7. Execute shell          | 16. Start app           | 25. Create folder
  8. Get device logs        | 17. Backup app (pull)   | 26. Delete file/folder
  9. Reboot device          | 18. Batch install       | 27. Backup folder
 SYSTEM                     |  SCREEN SHARING         |  WIFI
----------------------------|-------------------------|-----------------------
 28. Battery info           | 37. Start sharing       | 46. Manual WiFi transfer
 29. Memory info            | 38. Custom sharing      | 47. Transfer all USB->WiFi
 30. CPU info               | 39. Stop sharing        | 48. Quick setup watcher
 31. Storage info           | 40. Stop all sharing    | 49. WiFi status
 32. Running processes      | 41. Active sessions     | 50. Disconnect WiFi
 33. Network info           | 42. Multi-device share  | 51. Toggle auto-transfer
 34. System properties      | 43. Check scrcpy        | 52. Monitor logcat
 35. Apps with size         | 44. Record screen       | 53. Service status
 36. Monitor performance    | 45. Sync folder         | 54. Settings
 55. Generate QR payload    | 56. Generate QR exploit |
"""

IOS_MENU = """
 iOS (usbmuxd) MENU
-------------------------------------------
 101. List iOS devices
 102. Device info
 103. Pair device
 104. List apps
 105. Install .ipa
 106. Uninstall app
 107. Live syslog (capture)
 108. Screenshot (Developer Mode req.)
 109. Reboot
 110. List crash logs
 111. Frida attach / process list
 112. Full backup
 113. iOS USB attach watcher
"""

def banner():
    print(cyan(BANNER))

def main():
    ensure_dir()
    signal.signal(signal.SIGINT, signal.default_int_handler)
    banner()
    print(yellow(" Tip: type 'a' for Android menu, 'i' for iOS menu, 'both' to see all,"
                 " '99' to exit.\n"))
    while True:
        mode = input(bold("Mode [a/i/both/99] > ")).strip().lower()
        if mode == "99":
            a_stop_all(); print(green("Bye.")); break
        if mode == "a":
            print(ANDROID_MENU)
            choice = input("Choice: ").strip()
            fn = ANDROID_ACTIONS.get(choice)
            (fn() if fn else print(red("Unknown option.")))
        elif mode == "i":
            print(IOS_MENU)
            choice = input("Choice: ").strip()
            fn = IOS_ACTIONS.get(choice)
            (fn() if fn else print(red("Unknown option.")))
        elif mode == "both":
            print(ANDROID_MENU); print(IOS_MENU)
            choice = input("Choice: ").strip()
            fn = ANDROID_ACTIONS.get(choice) or IOS_ACTIONS.get(choice)
            (fn() if fn else print(red("Unknown option.")))
        else:
            print(red("Enter a, i, both, or 99."))

ANDROID_ACTIONS = {
    "1": a_list_devices, "2": a_connect_wifi, "3": a_disconnect,
    "4": a_device_info, "5": a_restart_adb, "6": a_check_connection,
    "7": a_shell, "8": a_logs, "9": a_reboot,
    "10": a_install, "11": a_uninstall, "12": a_list_packages,
    "13": a_package_info, "14": a_clear_data, "15": a_force_stop,
    "16": a_start_app, "17": a_backup_app, "18": a_batch_install,
    "19": a_screenshot, "20": a_multi_screenshot, "21": a_record_screen,
    "22": a_upload, "23": a_download, "24": a_list_files, "25": a_mkdir,
    "26": a_delete, "27": a_backup_folder,
    "28": a_battery, "29": a_memory, "30": a_cpu, "31": a_storage,
    "32": a_processes, "33": a_network, "34": a_sysprops, "35": a_apps_size,
    "36": a_monitor_perf,
    "37": a_start_share, "38": lambda: a_start_share(custom=True),
    "39": a_stop_share, "40": a_stop_all, "41": a_active_sessions,
    "42": a_multi_share, "43": a_check_scrcpy, "44": a_record_screen,
    "45": a_sync_folder,
    "46": a_wifi_transfer, "47": a_transfer_all, "48": a_quick_setup,
    "49": a_wifi_status, "50": a_disconnect_wifi, "51": a_toggle_auto,
    "52": a_monitor_logcat, "53": a_service_status, "54": a_settings,
    "55": a_qr_payload, "56": a_qr_exploit,
}

IOS_ACTIONS = {
    "101": i_list_devices, "102": i_device_info, "103": i_pair,
    "104": i_apps_list, "105": i_app_install, "106": i_app_uninstall,
    "107": i_syslog, "108": i_screenshot, "109": i_reboot,
    "110": i_crash_list, "111": i_frida, "112": i_backup,
    "113": i_auto_detect,
}

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        a_stop_all()
        print(yellow("\nInterrupted — sessions cleaned up."))
