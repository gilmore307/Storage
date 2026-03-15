import json
import os
import socket
import subprocess
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

import psutil
import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
PROCESS_FLAGS = CREATE_NO_WINDOW | DETACHED_PROCESS


def load_profile(profile_path: str) -> dict:
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_profile_path"] = str(Path(profile_path).resolve())
    return data


class NodeTrayApp:
    def __init__(self, profile: dict):
        self.profile = profile
        self.profile_dir = Path(profile["_profile_path"]).resolve().parent
        self.base_dir = Path(getattr(__import__("sys"), "_MEIPASS", self.profile_dir)).resolve()

        self.node_cfg = profile["openclaw"]
        self.vpn_cfg = profile["vpn"]
        self.app_cfg = profile.get("app", {})

        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.tray_icon = None
        self.monitor_thread = None

        self.node_desired = self.app_cfg.get("auto_start_node", True)
        self.vpn_desired = self.app_cfg.get("auto_start_vpn", False)
        self.node_status = False
        self.vpn_status = False

        self.log_path = self.resolve_path(self.app_cfg["log_path"])
        self.icon_path = self.resolve_path(self.app_cfg["icon_path"])
        self.check_interval = self.app_cfg.get("check_interval", 10)
        self.startup_wait = self.app_cfg.get("startup_wait", 2)
        self.socket_timeout = self.app_cfg.get("socket_timeout", 1.5)
        self.generated_vpn_config_path = self.resolve_path(self.vpn_cfg.get("generated_config_path", "generated/vpn.generated.json"))

        self.env = os.environ.copy()
        self.env["OPENCLAW_GATEWAY_TOKEN"] = self.node_cfg["gateway_token"]
        self.env["OPENCLAW_ALLOW_INSECURE_PRIVATE_WS"] = "1"

    def resolve_path(self, path_value: str) -> str:
        p = Path(path_value)
        if p.is_absolute():
            return str(p)
        return str((self.profile_dir / p).resolve())

    def ensure_log_dir(self):
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)

    def write_log(self, msg: str):
        self.ensure_log_dir()
        with open(self.log_path, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] [tray] {msg}\n")

    def write_exception(self, prefix: str, exc: Exception):
        self.write_log(f"{prefix}: {exc}")
        for line in traceback.format_exc().strip().splitlines():
            self.write_log(f"{prefix} traceback: {line}")

    def _safe_name(self, proc) -> str:
        try:
            return (proc.info.get("name") or "").lower()
        except Exception:
            return ""

    def _safe_cmdline(self, proc) -> str:
        try:
            cmdline = proc.info.get("cmdline") or []
            return " ".join(cmdline).strip()
        except Exception:
            return ""

    def _iter_processes(self, attrs=None):
        attrs = attrs or ["pid", "name", "cmdline"]
        for proc in psutil.process_iter(attrs):
            try:
                yield proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

    def _contains_flag_with_value(self, cmdline: str, flag: str, value: str) -> bool:
        return f"{flag} {value}".lower() in cmdline.lower()

    def is_node_process(self, proc) -> bool:
        name = self._safe_name(proc)
        cmdline = self._safe_cmdline(proc).lower()
        return (
            name == Path(self.resolve_path(self.node_cfg["nodejs_path"])).name.lower()
            and self.resolve_path(self.node_cfg["openclaw_path"]).lower() in cmdline
            and self._contains_flag_with_value(cmdline, "--display-name", self.node_cfg["display_name"].lower())
            and self._contains_flag_with_value(cmdline, "--port", str(self.node_cfg["node_port"]))
        )

    def is_ssh_process(self, proc) -> bool:
        tunnel = self.node_cfg.get("ssh_tunnel")
        if not tunnel or not tunnel.get("enabled"):
            return False
        name = self._safe_name(proc)
        cmdline = self._safe_cmdline(proc).lower()
        expected_forward = f"{self.node_cfg['gateway_tunnel_local_port']}:127.0.0.1:{self.node_cfg['remote_port']}".lower()
        expected_host = f"{tunnel['ssh_user']}@{tunnel['ssh_host']}".lower()
        return name == "ssh.exe" and expected_forward in cmdline and expected_host in cmdline

    def is_vpn_process(self, proc) -> bool:
        name = self._safe_name(proc)
        cmdline = self._safe_cmdline(proc).lower()
        exe_name = Path(self.resolve_path(self.vpn_cfg["singbox_exe"])).name.lower()
        config_path = self.generated_vpn_config_path.lower()
        return name == exe_name and config_path in cmdline and " run " in f" {cmdline} "

    def extract_proxy_keywords(self) -> list[str]:
        keyword_file = self.vpn_cfg.get("keyword_file_path")
        if not keyword_file:
            return self.vpn_cfg.get("default_keywords", [])

        path = self.resolve_path(keyword_file)
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        in_section = False
        keywords = []
        for raw in lines:
            line = raw.strip()
            if line.startswith("## "):
                if line == "## Current proxy keywords":
                    in_section = True
                    continue
                if in_section:
                    break
            if not in_section:
                continue
            if line.startswith("- `") and line.endswith("`"):
                keywords.append(line[3:-1])
            elif line.startswith("- "):
                keywords.append(line[2:].strip())

        if not keywords:
            keywords = self.vpn_cfg.get("default_keywords", [])
        return [k for k in keywords if k]

    def generate_vpn_runtime_config(self) -> str:
        template_path = self.resolve_path(self.vpn_cfg.get("config_template_path", self.vpn_cfg.get("config_path")))
        with open(template_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        keywords = self.extract_proxy_keywords()
        for rule in config.get("route", {}).get("rules", []):
            if "domain_keyword" in rule:
                rule["domain_keyword"] = keywords

        cert_path_value = self.vpn_cfg.get("cert_path")
        if cert_path_value:
            resolved_cert_path = self.resolve_path(cert_path_value)
            for outbound in config.get("outbounds", []):
                tls_cfg = outbound.get("tls")
                if isinstance(tls_cfg, dict) and tls_cfg.get("certificate_path"):
                    tls_cfg["certificate_path"] = resolved_cert_path

        out_path = Path(getattr(self, "generated_vpn_config_path", self.resolve_path(self.vpn_cfg.get("generated_config_path", "generated/vpn.generated.json"))))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        self.write_log(f"Generated VPN runtime config at {out_path} with keywords: {', '.join(keywords)}")
        return str(out_path)

    def find_processes(self, predicate):
        results = []
        for proc in self._iter_processes(["pid", "name", "cmdline"]):
            try:
                if predicate(proc):
                    results.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        return results

    def kill_processes(self, procs, label: str):
        if not procs:
            self.write_log(f"No {label} processes found.")
            return
        for proc in procs:
            try:
                proc.kill()
                self.write_log(f"Killed {label} PID={proc.pid}")
            except Exception as e:
                self.write_log(f"Failed to kill {label} PID={getattr(proc, 'pid', '?')}: {e}")

    def is_local_port_open(self, host: str, port: int, timeout: float) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except Exception:
            return False

    def is_gateway_reachable(self, host: str, port: int, timeout: float) -> bool:
        return self.is_local_port_open(host, port, timeout)

    def choose_gateway_url(self) -> str:
        direct = self.node_cfg["direct_gateway_url"]
        if self.node_cfg.get("prefer_direct", True):
            host = self.node_cfg["direct_gateway_host"]
            port = int(self.node_cfg["direct_gateway_port"])
            if self.is_gateway_reachable(host, port, self.socket_timeout):
                self.write_log("Direct gateway reachable. Using direct path.")
                return direct
        tunnel = self.node_cfg.get("ssh_tunnel")
        if tunnel and tunnel.get("enabled"):
            self.write_log("Falling back to SSH tunnel path.")
            return self.node_cfg["tunnel_gateway_url"]
        self.write_log("Using direct gateway path without SSH tunnel fallback.")
        return direct

    def build_node_env(self, gateway_url: str):
        env = self.env.copy()
        env["OPENCLAW_GATEWAY_URL"] = gateway_url
        return env

    def start_ssh_tunnel(self):
        tunnel = self.node_cfg.get("ssh_tunnel")
        if not tunnel or not tunnel.get("enabled"):
            return
        self.kill_processes(self.find_processes(self.is_ssh_process), "ssh")
        self.write_log("Starting SSH tunnel...")
        subprocess.Popen(
            [
                tunnel.get("ssh_exe", "ssh"),
                "-N",
                "-o", "ExitOnForwardFailure=yes",
                "-o", "ServerAliveInterval=30",
                "-o", "ServerAliveCountMax=3",
                "-L", f"{self.node_cfg['gateway_tunnel_local_port']}:127.0.0.1:{self.node_cfg['remote_port']}",
                f"{tunnel['ssh_user']}@{tunnel['ssh_host']}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=PROCESS_FLAGS,
        )
        time.sleep(self.startup_wait)

    def start_node(self):
        gateway_url = self.choose_gateway_url()
        if gateway_url == self.node_cfg.get("tunnel_gateway_url"):
            self.start_ssh_tunnel()
        self.kill_processes(self.find_processes(self.is_node_process), "node")
        self.write_log(f"Starting OpenClaw node using gateway: {gateway_url}")
        subprocess.Popen(
            [
                self.resolve_path(self.node_cfg["nodejs_path"]),
                self.resolve_path(self.node_cfg["openclaw_path"]),
                "node",
                "run",
                "--host", self.node_cfg.get("bind_host", "127.0.0.1"),
                "--port", str(self.node_cfg["gateway_tunnel_local_port"]),
                "--display-name", self.node_cfg["display_name"],
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=PROCESS_FLAGS,
            env=self.build_node_env(gateway_url),
        )
        time.sleep(self.startup_wait)
        self.node_status = self.check_node_status()
        self.refresh_ui()

    def stop_node(self):
        self.write_log("Stopping OpenClaw node and SSH tunnel...")
        self.kill_processes(self.find_processes(self.is_node_process), "node")
        self.kill_processes(self.find_processes(self.is_ssh_process), "ssh")
        self.node_status = False
        self.refresh_ui()

    def start_vpn(self):
        self.kill_processes(self.find_processes(self.is_vpn_process), "vpn")
        runtime_config = self.generate_vpn_runtime_config()
        self.write_log(f"Starting sing-box VPN with config: {runtime_config}")
        subprocess.Popen(
            [
                self.resolve_path(self.vpn_cfg["singbox_exe"]),
                "run",
                "-c",
                runtime_config,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            creationflags=PROCESS_FLAGS,
        )
        time.sleep(self.startup_wait)
        self.vpn_status = self.check_vpn_status()
        self.refresh_ui()

    def stop_vpn(self):
        self.write_log("Stopping sing-box VPN...")
        self.kill_processes(self.find_processes(self.is_vpn_process), "vpn")
        self.vpn_status = False
        self.refresh_ui()

    def check_node_status(self) -> bool:
        node_ok = len(self.find_processes(self.is_node_process)) > 0
        if not node_ok:
            return False
        gateway_url = self.choose_gateway_url()
        if gateway_url == self.node_cfg.get("tunnel_gateway_url"):
            return len(self.find_processes(self.is_ssh_process)) > 0 and self.is_local_port_open("127.0.0.1", int(self.node_cfg["gateway_tunnel_local_port"]), self.socket_timeout)
        return True

    def check_vpn_status(self) -> bool:
        return len(self.find_processes(self.is_vpn_process)) > 0

    def load_base_icon(self) -> Image.Image:
        img = Image.open(self.icon_path).convert("RGBA")
        return img.resize((64, 64))

    def make_status_icon(self) -> Image.Image:
        base = self.load_base_icon().copy()
        draw = ImageDraw.Draw(base)
        colors = [
            (0, 180, 0, 255) if self.node_status else (180, 0, 0, 255),
            (0, 180, 255, 255) if self.vpn_status else (100, 100, 100, 255),
        ]
        positions = [(50, 16), (50, 48)]
        radius = 8
        for (cx, cy), color in zip(positions, colors):
            draw.ellipse((cx - radius - 2, cy - radius - 2, cx + radius + 2, cy + radius + 2), fill=(255, 255, 255, 255))
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color)
        return base

    def refresh_ui(self):
        if self.tray_icon is None:
            return
        try:
            self.tray_icon.icon = self.make_status_icon()
            self.tray_icon.title = f"{self.profile['profile_name']} | node={'ON' if self.node_status else 'OFF'} | vpn={'ON' if self.vpn_status else 'OFF'}"
            self.tray_icon.update_menu()
        except Exception as e:
            self.write_log(f"refresh_ui error: {e}")

    def status_label(self, _):
        return f"Node: {'ON' if self.node_status else 'OFF'} | VPN: {'ON' if self.vpn_status else 'OFF'}"

    def noop(self, icon=None, menu_item=None):
        return

    def start_node_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.node_desired = True
            self.start_node()
            if icon:
                icon.notify("OpenClaw node started", self.profile['profile_name'])

    def stop_node_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.node_desired = False
            self.stop_node()
            if icon:
                icon.notify("OpenClaw node stopped", self.profile['profile_name'])

    def start_vpn_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.vpn_desired = True
            self.start_vpn()
            if icon:
                icon.notify("VPN started", self.profile['profile_name'])

    def stop_vpn_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.vpn_desired = False
            self.stop_vpn()
            if icon:
                icon.notify("VPN stopped", self.profile['profile_name'])

    def restart_all(self, icon=None, menu_item=None):
        try:
            with self.state_lock:
                self.stop_vpn()
                self.stop_node()
                if self.node_desired:
                    self.start_node()
                if self.vpn_desired:
                    self.start_vpn()
                if icon:
                    icon.notify("Restarted configured services", self.profile['profile_name'])
        except Exception as e:
            self.write_exception("restart_all error", e)
            if icon:
                icon.notify(f"Restart failed: {e}", self.profile['profile_name'])

    def on_exit(self, icon=None, menu_item=None):
        self.write_log("Exit requested.")
        self.stop_event.set()
        with self.state_lock:
            self.stop_vpn()
            self.stop_node()
        if icon:
            icon.stop()

    def monitor_loop(self):
        self.write_log("Monitor thread started.")
        while not self.stop_event.is_set():
            try:
                with self.state_lock:
                    self.node_status = self.check_node_status()
                    self.vpn_status = self.check_vpn_status()
                    self.refresh_ui()
            except Exception as e:
                self.write_exception("monitor_loop error", e)
            self.stop_event.wait(self.check_interval)
        self.write_log("Monitor thread exited.")

    def run(self):
        self.write_log("Tray app started.")
        if self.node_desired:
            self.start_node()
        if self.vpn_desired:
            self.start_vpn()
        self.node_status = self.check_node_status()
        self.vpn_status = self.check_vpn_status()

        self.tray_icon = pystray.Icon(
            self.profile["profile_name"],
            self.make_status_icon(),
            self.profile["profile_name"],
            menu=pystray.Menu(
                item(self.status_label, self.noop),
                pystray.Menu.SEPARATOR,
                item("Start Node", self.start_node_menu),
                item("Stop Node", self.stop_node_menu),
                item("Start VPN", self.start_vpn_menu),
                item("Stop VPN", self.stop_vpn_menu),
                item("Restart All", self.restart_all),
                item("Exit", self.on_exit),
            ),
        )
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.tray_icon.run()


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="Path to profile json")
    args = parser.parse_args()

    profile_path = args.profile
    if not profile_path:
        exe_path = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve()
        candidate = exe_path.with_suffix('.profile.json')
        if candidate.exists():
            profile_path = str(candidate)
        else:
            script_candidate = Path(__file__).resolve().with_name(exe_path.stem + '.profile.json')
            if script_candidate.exists():
                profile_path = str(script_candidate)

    if not profile_path:
        raise SystemExit('Profile not found. Pass --profile or place <exe-name>.profile.json beside the executable.')

    profile = load_profile(profile_path)
    app = NodeTrayApp(profile)
    app.run()


if __name__ == "__main__":
    main()
