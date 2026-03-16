import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

try:
    import psutil
    import pystray
    from PIL import Image, ImageDraw
    from pystray import MenuItem as item
except ImportError as exc:
    missing = getattr(exc, "name", None) or str(exc)
    raise SystemExit(
        "Missing dependency for tray app: "
        f"{missing}. Install them first with: pip install pystray pillow psutil"
    ) from exc

IS_WINDOWS = os.name == "nt"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DETACHED_PROCESS = getattr(subprocess, "DETACHED_PROCESS", 0)
PROCESS_FLAGS = CREATE_NO_WINDOW | DETACHED_PROCESS
SCRIPT_PATH = Path(__file__).resolve()
RUNTIME_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else SCRIPT_PATH.parent


def load_profile(profile_path: str) -> dict:
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_profile_path"] = str(Path(profile_path).resolve())
    return data


def runtime_popen_kwargs(**kwargs):
    if IS_WINDOWS:
        kwargs.setdefault("creationflags", PROCESS_FLAGS)
    return kwargs


def _quoted_args(args: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(a) for a in args])


def _windows_pythonw_executable() -> Optional[str]:
    if not IS_WINDOWS:
        return None

    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        return str(exe)

    candidate = exe.with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    return None


def is_running_as_admin() -> bool:
    if not IS_WINDOWS:
        return True

    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_in_background(raw_argv: Sequence[str]) -> bool:
    pythonw_exe = _windows_pythonw_executable()
    if not pythonw_exe:
        return False

    new_args = [str(SCRIPT_PATH), *raw_argv[1:], "--_openclaw_pythonw_relaunched"]
    subprocess.Popen(
        [pythonw_exe, *new_args],
        cwd=str(RUNTIME_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
        close_fds=True,
        **runtime_popen_kwargs(),
    )
    return True


def relaunch_as_admin(raw_argv: Sequence[str]) -> bool:
    if not IS_WINDOWS:
        return False

    try:
        import ctypes
    except Exception:
        return False

    executable = sys.executable
    params = _quoted_args([str(SCRIPT_PATH), *raw_argv[1:], "--_openclaw_elevated"])
    result = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        executable,
        params,
        str(RUNTIME_DIR),
        1,
    )
    return result > 32


def discover_profile_path(explicit_path: Optional[str] = None) -> str:
    checked: List[Path] = []

    def _accept(path_value: Optional[str]) -> Optional[str]:
        if not path_value:
            return None
        path = Path(path_value).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        checked.append(path)
        if path.exists() and path.is_file():
            return str(path)
        return None

    explicit = _accept(explicit_path)
    if explicit:
        return explicit

    env_profile = _accept(os.environ.get("OPENCLAW_PROFILE"))
    if env_profile:
        return env_profile

    runtime_name = Path(sys.executable if getattr(sys, "frozen", False) else SCRIPT_PATH).stem
    direct_candidates = [
        RUNTIME_DIR / f"{runtime_name}.profile.json",
        SCRIPT_PATH.with_suffix(".profile.json"),
        RUNTIME_DIR / "node-1-office.profile.json",
    ]

    for candidate in direct_candidates:
        checked.append(candidate)
        if candidate.exists() and candidate.is_file():
            return str(candidate.resolve())

    profile_files = sorted(RUNTIME_DIR.glob("*.profile.json"))
    if len(profile_files) == 1:
        return str(profile_files[0].resolve())

    searched = "\n  - ".join(str(p) for p in dict.fromkeys(checked))

    if profile_files:
        available = "\n  - ".join(str(p.resolve()) for p in profile_files)
        raise SystemExit(
            "Multiple profile files found. Please pass --profile explicitly.\n"
            f"Available profiles:\n  - {available}\n"
            f"Checked default locations:\n  - {searched}"
        )

    raise SystemExit(
        "Profile not found. Pass --profile, set OPENCLAW_PROFILE, or place one *.profile.json beside the script.\n"
        f"Checked default locations:\n  - {searched}"
    )


def should_relaunch_in_background(args) -> bool:
    if getattr(sys, "frozen", False):
        return False
    if not IS_WINDOWS or args.console or args.no_pythonw:
        return False
    if args._openclaw_pythonw_relaunched:
        return False
    return Path(sys.executable).name.lower() == "python.exe" and _windows_pythonw_executable() is not None


def should_relaunch_as_admin(args, profile: dict) -> bool:
    if getattr(sys, "frozen", False):
        return False
    if not IS_WINDOWS or args.no_admin or args._openclaw_elevated:
        return False
    if is_running_as_admin():
        return False

    app_cfg = profile.get("app", {})
    require_admin = app_cfg.get("require_admin")
    if require_admin is None:
        require_admin = True
    return bool(require_admin)


class NodeTrayApp:
    def __init__(self, profile: dict):
        self.stop_event = threading.Event()
        self.state_lock = threading.Lock()
        self.tray_icon = None
        self.monitor_thread = None
        self.tray_ready = threading.Event()
        self.shutting_down = False

        self.profile = {}
        self.profile_path = None
        self.profile_dir = None
        self.node_cfg = {}
        self.vpn_cfg = {}
        self.app_cfg = {}

        self.node_desired = True
        self.vpn_mode = "off"
        self.node_status = False
        self.vpn_status = False

        self.log_path = ""
        self.icon_path = ""
        self.check_interval = 10
        self.startup_wait = 2
        self.socket_timeout = 1.5
        self.generated_vpn_config_path = ""
        self.node_stdout_log_path = ""
        self.node_stderr_log_path = ""
        self.ssh_stdout_log_path = ""
        self.ssh_stderr_log_path = ""
        self.vpn_stdout_log_path = ""
        self.vpn_stderr_log_path = ""
        self.env = os.environ.copy()
        self.vpn_interface_name = "sb-tun"
        self.vpn_speed_refresh_interval = 1.0
        self.vpn_rx_rate_bps = 0.0
        self.vpn_tx_rate_bps = 0.0
        self._vpn_last_counters = None
        self._vpn_last_ts = None

        self.apply_profile(profile, preserve_runtime_choices=False)

    @staticmethod
    def normalize_vpn_mode(mode_value, auto_start_vpn_value=None) -> str:
        mode = str(mode_value or "").strip().lower()
        if mode in {"on", "auto", "off"}:
            return mode
        return "auto" if bool(auto_start_vpn_value) else "off"

    @property
    def vpn_desired(self) -> bool:
        return self.vpn_mode != "off"

    def apply_profile(self, profile: dict, preserve_runtime_choices: bool = True):
        old_node_desired = getattr(self, "node_desired", True)
        old_vpn_mode = getattr(self, "vpn_mode", "off")

        self.profile = profile
        self.profile_path = Path(profile["_profile_path"]).resolve()
        self.profile_dir = self.profile_path.parent

        self.node_cfg = profile["openclaw"]
        self.vpn_cfg = profile["vpn"]
        self.app_cfg = profile.get("app", {})

        self.log_path = self.resolve_path(self.app_cfg["log_path"])
        self.icon_path = self.resolve_path(self.app_cfg["icon_path"])
        self.check_interval = self.app_cfg.get("check_interval", 10)
        self.startup_wait = self.app_cfg.get("startup_wait", 2)
        self.socket_timeout = self.app_cfg.get("socket_timeout", 1.5)
        self.vpn_speed_refresh_interval = float(self.app_cfg.get("vpn_speed_refresh_interval", 1.0) or 1.0)

        self.generated_vpn_config_path = self.resolve_path(
            self.vpn_cfg.get("generated_config_path", "generated/vpn.generated.json")
        )
        self.node_stdout_log_path = self.resolve_path(
            self.app_cfg.get("node_stdout_log_path", "generated/node.stdout.log")
        )
        self.node_stderr_log_path = self.resolve_path(
            self.app_cfg.get("node_stderr_log_path", "generated/node.stderr.log")
        )
        self.ssh_stdout_log_path = self.resolve_path(
            self.app_cfg.get("ssh_stdout_log_path", "generated/ssh.stdout.log")
        )
        self.ssh_stderr_log_path = self.resolve_path(
            self.app_cfg.get("ssh_stderr_log_path", "generated/ssh.stderr.log")
        )
        self.vpn_stdout_log_path = self.resolve_path(
            self.app_cfg.get("vpn_stdout_log_path", "generated/vpn.stdout.log")
        )
        self.vpn_stderr_log_path = self.resolve_path(
            self.app_cfg.get("vpn_stderr_log_path", "generated/vpn.stderr.log")
        )

        self.vpn_interface_name = self.detect_vpn_interface_name()

        self.env = os.environ.copy()
        self.env["OPENCLAW_GATEWAY_TOKEN"] = str(self.node_cfg["gateway_token"]).strip()
        self.env.pop("OPENCLAW_GATEWAY_PASSWORD", None)
        self.env["OPENCLAW_ALLOW_INSECURE_PRIVATE_WS"] = "1"

        if preserve_runtime_choices:
            self.node_desired = old_node_desired
            self.vpn_mode = old_vpn_mode
        else:
            self.node_desired = bool(self.app_cfg.get("auto_start_node", True))
            self.vpn_mode = self.normalize_vpn_mode(
                self.app_cfg.get("auto_start_vpn_mode"),
                self.app_cfg.get("auto_start_vpn", True),
            )

    def reload_profile_from_disk(self, preserve_runtime_choices: bool = True):
        self.apply_profile(load_profile(str(self.profile_path)), preserve_runtime_choices=preserve_runtime_choices)

    def detect_vpn_interface_name(self) -> str:
        config_candidates = []
        template_path = self.vpn_cfg.get("config_template_path") or self.vpn_cfg.get("config_path")
        if template_path:
            config_candidates.append(self.resolve_path(template_path))
        generated_path = self.vpn_cfg.get("generated_config_path")
        if generated_path:
            config_candidates.append(self.resolve_path(generated_path))

        for path_value in config_candidates:
            try:
                path = Path(path_value)
                if not path.exists():
                    continue
                with open(path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                for inbound in config.get("inbounds", []):
                    if inbound.get("type") == "tun" and inbound.get("interface_name"):
                        return str(inbound["interface_name"]).strip()
            except Exception as exc:
                self.write_log(f"detect_vpn_interface_name skipped {path_value}: {exc}")

        return "sb-tun"

    def resolve_path(self, path_value: str) -> str:
        p = Path(path_value)
        if p.is_absolute():
            return str(p)
        return str((self.profile_dir / p).resolve())

    def ensure_log_dir(self):
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)

    def ensure_parent_dir(self, path_value: str):
        Path(path_value).parent.mkdir(parents=True, exist_ok=True)

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

    def choose_gateway_target(self, log_decision: bool = True) -> Tuple[str, str, int, bool]:
        direct_url = self.node_cfg["direct_gateway_url"]
        direct_host = self.node_cfg["direct_gateway_host"]
        direct_port = int(self.node_cfg["direct_gateway_port"])

        prefer_direct = self.node_cfg.get("prefer_direct", True)
        if prefer_direct and self.is_gateway_reachable(direct_host, direct_port, self.socket_timeout):
            if log_decision:
                self.write_log("Direct gateway reachable. Using direct path.")
            return direct_url, direct_host, direct_port, False

        tunnel = self.node_cfg.get("ssh_tunnel")
        if tunnel and tunnel.get("enabled"):
            tunnel_url = self.node_cfg["tunnel_gateway_url"]
            tunnel_host = "127.0.0.1"
            tunnel_port = int(self.node_cfg["gateway_tunnel_local_port"])
            if log_decision:
                self.write_log("Falling back to SSH tunnel path.")
            return tunnel_url, tunnel_host, tunnel_port, True

        if log_decision:
            self.write_log("Using direct gateway path without SSH tunnel fallback.")
        return direct_url, direct_host, direct_port, False

    def build_node_env(self, gateway_url: str):
        env = self.env.copy()
        env["OPENCLAW_GATEWAY_URL"] = gateway_url
        return env

    def _open_subprocess_logs(self, stdout_path: str, stderr_path: str):
        self.ensure_parent_dir(stdout_path)
        self.ensure_parent_dir(stderr_path)
        stdout_f = open(stdout_path, "a", encoding="utf-8")
        stderr_f = open(stderr_path, "a", encoding="utf-8")
        return stdout_f, stderr_f

    def is_node_process(self, proc) -> bool:
        name = self._safe_name(proc)
        cmdline = self._safe_cmdline(proc).lower()

        expected_node_exe = Path(self.resolve_path(self.node_cfg["nodejs_path"])).name.lower()
        expected_openclaw_path = self.resolve_path(self.node_cfg["openclaw_path"]).lower()
        expected_display_name = self.node_cfg["display_name"].lower()

        expected_ports = {
            str(self.node_cfg["direct_gateway_port"]).lower(),
            str(self.node_cfg["gateway_tunnel_local_port"]).lower(),
        }

        return (
            name == expected_node_exe
            and expected_openclaw_path in cmdline
            and self._contains_flag_with_value(cmdline, "--display-name", expected_display_name)
            and any(self._contains_flag_with_value(cmdline, "--port", p) for p in expected_ports)
        )

    def is_ssh_process(self, proc) -> bool:
        tunnel = self.node_cfg.get("ssh_tunnel")
        if not tunnel or not tunnel.get("enabled"):
            return False

        name = self._safe_name(proc)
        cmdline = self._safe_cmdline(proc).lower()

        expected_forward = (
            f"{self.node_cfg['gateway_tunnel_local_port']}:127.0.0.1:{self.node_cfg['remote_port']}".lower()
        )
        expected_host = f"{tunnel['ssh_user']}@{tunnel['ssh_host']}".lower()

        return name in ("ssh.exe", "ssh") and expected_forward in cmdline and expected_host in cmdline

    def is_vpn_process(self, proc) -> bool:
        name = self._safe_name(proc)
        cmdline = self._safe_cmdline(proc).lower()
        exe_name = Path(self.resolve_path(self.vpn_cfg["singbox_exe"])).name.lower()
        config_path = self.generated_vpn_config_path.lower()
        return name == exe_name and config_path in cmdline and " run " in f" {cmdline} "

    @staticmethod
    def _normalize_keyword_text(value: str) -> str:
        text = str(value or "").strip()
        text = text.strip("`")
        if text.startswith("- "):
            text = text[2:].strip()
        return text

    def keyword_file_path(self) -> str:
        return self.resolve_path(self.vpn_cfg["keyword_file_path"])

    def extract_proxy_keywords(self) -> List[str]:
        path = self.keyword_file_path()
        if not Path(path).exists():
            return []

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

            if line.startswith("- "):
                keyword = self._normalize_keyword_text(line[2:])
                if keyword:
                    keywords.append(keyword)

        seen = set()
        deduped = []
        for keyword in keywords:
            lowered = keyword.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(keyword)
        return deduped

    def write_proxy_keywords(self, keywords: List[str]):
        path = Path(self.keyword_file_path())
        path.parent.mkdir(parents=True, exist_ok=True)

        normalized = []
        seen = set()
        for keyword in keywords:
            cleaned = self._normalize_keyword_text(keyword)
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)

        bullet_lines = [f"- `{keyword}`" for keyword in normalized]
        replacement_body = "\n".join(bullet_lines)
        if replacement_body:
            replacement_body += "\n\n"
        else:
            replacement_body = "\n"

        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        pattern = re.compile(
            r"(^## Current proxy keywords\s*\n)(.*?)(?=^##\s|\Z)",
            re.MULTILINE | re.DOTALL,
        )

        if pattern.search(existing):
            updated = pattern.sub(rf"\1{replacement_body}", existing, count=1)
        else:
            prefix = existing.rstrip()
            if prefix:
                prefix += "\n\n"
            updated = prefix + "## Current proxy keywords\n" + replacement_body

        path.write_text(updated, encoding="utf-8")
        self.write_log(f"Updated proxy keyword file: {path}")

    def add_proxy_keywords(self, raw_input: str) -> List[str]:
        incoming = [
            self._normalize_keyword_text(part)
            for part in re.split(r"[,\r\n]+", raw_input or "")
        ]
        incoming = [value for value in incoming if value]
        if not incoming:
            return []

        existing = self.extract_proxy_keywords()
        existing_lower = {keyword.lower() for keyword in existing}
        added = []
        for keyword in incoming:
            if keyword.lower() in existing_lower:
                continue
            existing.append(keyword)
            existing_lower.add(keyword.lower())
            added.append(keyword)

        if added:
            self.write_proxy_keywords(existing)
        return added


    def _prompt_for_keyword_input_windows(self) -> Optional[str]:
        candidates = ["powershell.exe", "pwsh.exe"]
        powershell_exe = None
        for candidate in candidates:
            try:
                resolved = shutil.which(candidate)
            except Exception:
                resolved = None
            if resolved:
                powershell_exe = resolved
                break

        if not powershell_exe:
            raise RuntimeError("PowerShell not found")

        title = f"{self.profile['profile_name']} - Add Keyword"
        prompt = "输入要添加的 keyword。支持一次输入多个，用逗号分隔。"
        script = f"""
Add-Type -AssemblyName Microsoft.VisualBasic
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$value = [Microsoft.VisualBasic.Interaction]::InputBox({title!r}, {prompt!r}, "")
if ($null -ne $value -and $value.Length -gt 0) {{
    [Console]::Write($value)
}}
"""
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            [
                powershell_exe,
                "-NoProfile",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-EncodedCommand",
                encoded,
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=CREATE_NO_WINDOW if IS_WINDOWS else 0,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise RuntimeError(stderr or f"PowerShell exited with code {result.returncode}")

        value = result.stdout.replace("\ufeff", "")
        value = value.rstrip("\r\n")
        return value or None

    def _prompt_for_keyword_input_tk(self) -> Optional[str]:
        try:
            import tkinter as tk
        except Exception as exc:
            raise RuntimeError(f"tkinter unavailable: {exc}") from exc

        result = {"value": None}
        root = tk.Tk()
        root.title(f"{self.profile['profile_name']} - Add Keyword")
        root.resizable(False, False)
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        frame = tk.Frame(root, padx=14, pady=12)
        frame.pack(fill="both", expand=True)

        label = tk.Label(frame, text="输入要添加的 keyword。支持一次输入多个，用逗号分隔。", anchor="w", justify="left")
        label.pack(fill="x")

        entry_var = tk.StringVar()
        entry = tk.Entry(frame, textvariable=entry_var, width=52)
        entry.pack(fill="x", pady=(10, 12))

        button_bar = tk.Frame(frame)
        button_bar.pack(fill="x")

        def submit(event=None):
            value = entry_var.get().strip()
            result["value"] = value or None
            root.quit()

        def cancel(event=None):
            result["value"] = None
            root.quit()

        tk.Button(button_bar, text="OK", width=10, command=submit).pack(side="right", padx=(8, 0))
        tk.Button(button_bar, text="Cancel", width=10, command=cancel).pack(side="right")

        root.bind("<Return>", submit)
        root.bind("<Escape>", cancel)
        root.protocol("WM_DELETE_WINDOW", cancel)

        root.update_idletasks()
        try:
            root.lift()
            root.focus_force()
        except Exception:
            pass
        root.after(100, lambda: entry.focus_set())
        root.mainloop()
        root.destroy()
        return result["value"]

    def prompt_for_keyword_input(self) -> Optional[str]:
        if IS_WINDOWS:
            try:
                return self._prompt_for_keyword_input_windows()
            except Exception as exc:
                self.write_log(f"Windows keyword prompt fallback to tkinter: {exc}")
        return self._prompt_for_keyword_input_tk()

    @staticmethod
    def _format_rate(rate_bps: float) -> str:
        units = ["B/s", "KB/s", "MB/s", "GB/s"]
        value = max(0.0, float(rate_bps or 0.0))
        unit_index = 0
        while value >= 1024.0 and unit_index < len(units) - 1:
            value /= 1024.0
            unit_index += 1
        if unit_index == 0:
            return f"{int(round(value))} {units[unit_index]}"
        if value >= 100:
            return f"{value:.0f} {units[unit_index]}"
        if value >= 10:
            return f"{value:.1f} {units[unit_index]}"
        return f"{value:.2f} {units[unit_index]}"

    def vpn_speed_text(self) -> str:
        if not self.vpn_status or self.vpn_mode == "off":
            return "↓0 B/s ↑0 B/s"
        return f"↓{self._format_rate(self.vpn_rx_rate_bps)} ↑{self._format_rate(self.vpn_tx_rate_bps)}"

    def _resolve_vpn_nic_name(self) -> Optional[str]:
        target = (self.vpn_interface_name or "").strip().lower()
        if not target:
            return None
        try:
            counters = psutil.net_io_counters(pernic=True)
        except Exception:
            return None

        for nic_name in counters:
            if nic_name.lower() == target:
                return nic_name
        for nic_name in counters:
            if target in nic_name.lower():
                return nic_name
        return None

    def update_vpn_speed(self, reset: bool = False):
        if reset or self.vpn_mode == "off" or not self.vpn_status:
            self.vpn_rx_rate_bps = 0.0
            self.vpn_tx_rate_bps = 0.0
            self._vpn_last_counters = None
            self._vpn_last_ts = None
            return

        nic_name = self._resolve_vpn_nic_name()
        if not nic_name:
            self.vpn_rx_rate_bps = 0.0
            self.vpn_tx_rate_bps = 0.0
            self._vpn_last_counters = None
            self._vpn_last_ts = None
            return

        try:
            counters = psutil.net_io_counters(pernic=True).get(nic_name)
        except Exception as exc:
            self.write_log(f"update_vpn_speed error: {exc}")
            self.vpn_rx_rate_bps = 0.0
            self.vpn_tx_rate_bps = 0.0
            self._vpn_last_counters = None
            self._vpn_last_ts = None
            return

        if counters is None:
            self.vpn_rx_rate_bps = 0.0
            self.vpn_tx_rate_bps = 0.0
            self._vpn_last_counters = None
            self._vpn_last_ts = None
            return

        now = time.time()
        current = (float(counters.bytes_recv), float(counters.bytes_sent))
        if self._vpn_last_counters is not None and self._vpn_last_ts is not None:
            elapsed = max(now - self._vpn_last_ts, 1e-6)
            recv_delta = max(0.0, current[0] - self._vpn_last_counters[0])
            sent_delta = max(0.0, current[1] - self._vpn_last_counters[1])
            self.vpn_rx_rate_bps = recv_delta / elapsed
            self.vpn_tx_rate_bps = sent_delta / elapsed
        else:
            self.vpn_rx_rate_bps = 0.0
            self.vpn_tx_rate_bps = 0.0

        self._vpn_last_counters = current
        self._vpn_last_ts = now

    def build_vpn_runtime_config(self, mode: Optional[str] = None) -> dict:

        mode = self.normalize_vpn_mode(mode or self.vpn_mode, True)
        template_path = self.resolve_path(
            self.vpn_cfg.get("config_template_path", self.vpn_cfg.get("config_path"))
        )

        with open(template_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        route = config.setdefault("route", {})
        rules = route.get("rules", [])

        cert_path_value = self.vpn_cfg.get("cert_path")
        if cert_path_value:
            resolved_cert_path = self.resolve_path(cert_path_value)
            for outbound in config.get("outbounds", []):
                tls_cfg = outbound.get("tls")
                if isinstance(tls_cfg, dict) and tls_cfg.get("certificate_path"):
                    tls_cfg["certificate_path"] = resolved_cert_path

        if mode == "on":
            keep_rules = []
            for rule in rules:
                if rule.get("action") == "sniff":
                    keep_rules.append(rule)
                    continue
                if rule.get("protocol") == "dns" and rule.get("action") == "hijack-dns":
                    keep_rules.append(rule)
            route["rules"] = keep_rules
            route["final"] = "proxy"
        else:
            keywords = self.extract_proxy_keywords()
            for rule in rules:
                if "domain_keyword" in rule:
                    rule["domain_keyword"] = keywords
            route["rules"] = rules
            route["final"] = "direct"

        return config

    def generate_vpn_runtime_config(self, mode: Optional[str] = None) -> str:
        mode = self.normalize_vpn_mode(mode or self.vpn_mode, True)
        config = self.build_vpn_runtime_config(mode)
        out_path = Path(self.generated_vpn_config_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")

        keywords = self.extract_proxy_keywords() if mode == "auto" else []
        self.write_log(
            f"Generated VPN runtime config at {out_path} | mode={mode}"
            + (f" | keywords={', '.join(keywords)}" if keywords else "")
        )
        return str(out_path)

    def start_ssh_tunnel(self):
        tunnel = self.node_cfg.get("ssh_tunnel")
        if not tunnel or not tunnel.get("enabled"):
            return

        self.kill_processes(self.find_processes(self.is_ssh_process), "ssh")
        self.write_log("Starting SSH tunnel...")

        stdout_f = None
        stderr_f = None
        try:
            stdout_f, stderr_f = self._open_subprocess_logs(
                self.ssh_stdout_log_path, self.ssh_stderr_log_path
            )

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
                stdout=stdout_f,
                stderr=stderr_f,
                shell=False,
                **runtime_popen_kwargs(),
            )
        finally:
            if stdout_f:
                stdout_f.close()
            if stderr_f:
                stderr_f.close()

        deadline = time.time() + max(self.startup_wait, 8)
        while time.time() < deadline:
            if self.is_local_port_open(
                "127.0.0.1",
                int(self.node_cfg["gateway_tunnel_local_port"]),
                self.socket_timeout,
            ):
                self.write_log("SSH tunnel local port is ready.")
                return
            time.sleep(0.5)

        self.write_log("SSH tunnel local port did not become ready before timeout.")

    def start_node(self):
        gateway_url, gateway_host, gateway_port, use_tunnel = self.choose_gateway_target(log_decision=True)

        if use_tunnel:
            self.start_ssh_tunnel()

        self.kill_processes(self.find_processes(self.is_node_process), "node")
        self.write_log(
            f"Starting OpenClaw node using gateway: {gateway_url} | target={gateway_host}:{gateway_port}"
        )

        stdout_f = None
        stderr_f = None
        proc = None

        try:
            stdout_f, stderr_f = self._open_subprocess_logs(
                self.node_stdout_log_path, self.node_stderr_log_path
            )

            proc = subprocess.Popen(
                [
                    self.resolve_path(self.node_cfg["nodejs_path"]),
                    self.resolve_path(self.node_cfg["openclaw_path"]),
                    "node",
                    "run",
                    "--host", gateway_host,
                    "--port", str(gateway_port),
                    "--display-name", self.node_cfg["display_name"],
                ],
                stdin=subprocess.DEVNULL,
                stdout=stdout_f,
                stderr=stderr_f,
                shell=False,
                env=self.build_node_env(gateway_url),
                **runtime_popen_kwargs(),
            )
        finally:
            if stdout_f:
                stdout_f.close()
            if stderr_f:
                stderr_f.close()

        time.sleep(self.startup_wait)

        if proc is not None:
            ret = proc.poll()
            if ret is not None:
                self.write_log(
                    f"OpenClaw node exited immediately with code={ret}. "
                    f"See logs: {self.node_stdout_log_path}, {self.node_stderr_log_path}"
                )

        self.node_status = self.check_node_status()
        self.refresh_ui()

    def stop_node(self):
        self.write_log("Stopping OpenClaw node and SSH tunnel...")
        self.kill_processes(self.find_processes(self.is_node_process), "node")
        self.kill_processes(self.find_processes(self.is_ssh_process), "ssh")
        self.node_status = False
        self.refresh_ui()

    def start_vpn(self):
        if self.vpn_mode == "off":
            self.stop_vpn()
            return

        self.kill_processes(self.find_processes(self.is_vpn_process), "vpn")
        runtime_config = self.generate_vpn_runtime_config(self.vpn_mode)
        self.write_log(f"Starting sing-box VPN with config: {runtime_config} | mode={self.vpn_mode}")

        stdout_f = None
        stderr_f = None
        try:
            stdout_f, stderr_f = self._open_subprocess_logs(
                self.vpn_stdout_log_path, self.vpn_stderr_log_path
            )

            subprocess.Popen(
                [
                    self.resolve_path(self.vpn_cfg["singbox_exe"]),
                    "run",
                    "-c",
                    runtime_config,
                ],
                stdin=subprocess.DEVNULL,
                stdout=stdout_f,
                stderr=stderr_f,
                shell=False,
                **runtime_popen_kwargs(),
            )
        finally:
            if stdout_f:
                stdout_f.close()
            if stderr_f:
                stderr_f.close()

        time.sleep(self.startup_wait)
        self.vpn_status = self.check_vpn_status()
        self.update_vpn_speed(reset=not self.vpn_status)
        self.refresh_ui()

    def stop_vpn(self):
        self.write_log("Stopping sing-box VPN...")
        self.kill_processes(self.find_processes(self.is_vpn_process), "vpn")
        self.vpn_status = False
        self.update_vpn_speed(reset=True)
        self.refresh_ui()

    def reload_vpn_locked(self, icon=None, reason: Optional[str] = None):
        self.stop_vpn()
        self.reload_profile_from_disk(preserve_runtime_choices=True)
        if self.vpn_mode != "off":
            self.start_vpn()
        else:
            self.vpn_status = False
            self.refresh_ui()

        message = reason or f"VPN reloaded ({self.vpn_mode.upper()})"
        self.write_log(message)
        if icon:
            icon.notify(message, self.profile["profile_name"])

    def check_node_status(self) -> bool:
        node_procs = self.find_processes(self.is_node_process)
        if not node_procs:
            return False

        if len(self.find_processes(self.is_ssh_process)) > 0:
            return self.is_local_port_open(
                "127.0.0.1",
                int(self.node_cfg["gateway_tunnel_local_port"]),
                self.socket_timeout,
            )

        return True

    def check_vpn_status(self) -> bool:
        return len(self.find_processes(self.is_vpn_process)) > 0

    def load_base_icon(self) -> Image.Image:
        try:
            img = Image.open(self.icon_path).convert("RGBA")
            return img.resize((64, 64))
        except Exception as e:
            self.write_log(f"load_base_icon fallback: {e}")
            img = Image.new("RGBA", (64, 64), (22, 26, 34, 255))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(35, 45, 62, 255), outline=(95, 185, 255, 255), width=3)
            draw.ellipse((10, 22, 28, 40), fill=(70, 210, 120, 255))
            draw.ellipse((36, 22, 54, 40), fill=(70, 170, 255, 255))
            return img

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
            draw.ellipse(
                (cx - radius - 2, cy - radius - 2, cx + radius + 2, cy + radius + 2),
                fill=(255, 255, 255, 255),
            )
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                fill=color,
            )

        return base

    def refresh_ui(self):
        if self.tray_icon is None:
            return

        try:
            self.tray_icon.icon = self.make_status_icon()
            speed_text = self.vpn_speed_text() if self.vpn_mode != "off" else "↓0 B/s ↑0 B/s"
            self.tray_icon.title = (
                f"{self.profile['profile_name']} | "
                f"node={'ON' if self.node_status else 'OFF'} | "
                f"vpn={self.vpn_mode.upper()} ({'UP' if self.vpn_status else 'DOWN'}) | "
                f"{speed_text}"
            )
            if self.tray_ready.is_set() and not self.shutting_down:
                self.tray_icon.visible = True
                self.tray_icon.update_menu()
        except Exception as e:
            self.write_log(f"refresh_ui error: {e}")

    def noop(self, icon=None, menu_item=None):
        return

    def set_node_desired(self, desired: bool, icon=None):
        self.node_desired = desired
        if desired:
            self.start_node()
            if icon:
                icon.notify("OpenClaw node started", self.profile["profile_name"])
        else:
            self.stop_node()
            if icon:
                icon.notify("OpenClaw node stopped", self.profile["profile_name"])

    def set_vpn_mode(self, mode: str, icon=None):
        self.vpn_mode = self.normalize_vpn_mode(mode, True)
        self.stop_vpn()
        if self.vpn_mode != "off":
            self.start_vpn()
        else:
            self.refresh_ui()
        if icon:
            icon.notify(f"VPN mode switched to {self.vpn_mode.upper()}", self.profile["profile_name"])

    def node_on_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.set_node_desired(True, icon=icon)

    def node_off_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.set_node_desired(False, icon=icon)

    def vpn_on_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.set_vpn_mode("on", icon=icon)

    def vpn_auto_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.set_vpn_mode("auto", icon=icon)

    def vpn_off_menu(self, icon=None, menu_item=None):
        with self.state_lock:
            self.set_vpn_mode("off", icon=icon)

    def reload_vpn_menu(self, icon=None, menu_item=None):
        try:
            with self.state_lock:
                self.reload_vpn_locked(icon=icon)
        except Exception as e:
            self.write_exception("reload_vpn_menu error", e)
            if icon:
                icon.notify(f"VPN reload failed: {e}", self.profile["profile_name"])

    def add_keyword_menu(self, icon=None, menu_item=None):
        try:
            raw_input = self.prompt_for_keyword_input()
        except Exception as e:
            self.write_exception("add_keyword prompt error", e)
            if icon:
                icon.notify(f"Add Keyword failed: {e}", self.profile["profile_name"])
            return

        if raw_input is None:
            return

        try:
            with self.state_lock:
                added = self.add_proxy_keywords(raw_input)
                if not added:
                    message = "No new keyword added"
                    self.write_log(message)
                    if icon:
                        icon.notify(message, self.profile["profile_name"])
                    return
                self.reload_vpn_locked(
                    icon=icon,
                    reason=f"Added keyword: {', '.join(added)} | VPN reloaded",
                )
        except Exception as e:
            self.write_exception("add_keyword_menu error", e)
            if icon:
                icon.notify(f"Add Keyword failed: {e}", self.profile["profile_name"])

    def on_exit(self, icon=None, menu_item=None):
        self.write_log("Exit requested.")
        self.shutting_down = True
        self.stop_event.set()
        with self.state_lock:
            self.stop_vpn()
            self.stop_node()
        if icon:
            try:
                icon.visible = False
            except Exception:
                pass
            icon.stop()

    def monitor_loop(self):
        self.write_log("Monitor thread started.")
        last_status_check = 0.0
        loop_interval = max(0.5, min(float(self.check_interval), float(self.vpn_speed_refresh_interval)))
        while not self.stop_event.is_set():
            try:
                with self.state_lock:
                    now = time.time()
                    if now - last_status_check >= float(self.check_interval):
                        self.node_status = self.check_node_status()
                        self.vpn_status = self.check_vpn_status()
                        last_status_check = now
                    self.update_vpn_speed(reset=not self.vpn_status)
                    if not self.shutting_down:
                        self.refresh_ui()
            except Exception as e:
                self.write_exception("monitor_loop error", e)

            self.stop_event.wait(loop_interval)

        self.write_log("Monitor thread exited.")

    def _tray_setup(self, icon):
        self.write_log("Tray icon backend ready.")
        self.tray_ready.set()
        try:
            icon.visible = True
        except Exception as e:
            self.write_log(f"icon.visible setup error: {e}")

        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        with self.state_lock:
            if self.node_desired:
                self.start_node()

            if self.vpn_mode != "off":
                self.start_vpn()

            self.node_status = self.check_node_status()
            self.vpn_status = self.check_vpn_status()
            self.refresh_ui()

    def run(self):
        self.write_log("Tray app started.")

        self.tray_icon = pystray.Icon(
            self.profile["profile_name"],
            self.make_status_icon(),
            self.profile["profile_name"],
            menu=pystray.Menu(
                item("Node ON", self.node_on_menu, checked=lambda _: self.node_desired, radio=True),
                item("Node OFF", self.node_off_menu, checked=lambda _: not self.node_desired, radio=True),
                pystray.Menu.SEPARATOR,
                item("VPN ON", self.vpn_on_menu, checked=lambda _: self.vpn_mode == "on", radio=True),
                item("VPN AUTO", self.vpn_auto_menu, checked=lambda _: self.vpn_mode == "auto", radio=True),
                item("VPN OFF", self.vpn_off_menu, checked=lambda _: self.vpn_mode == "off", radio=True),
                item(lambda _: f"VPN Speed {self.vpn_speed_text()}", self.noop, enabled=False),
                item("Reload", self.reload_vpn_menu),
                item("Add Keyword", self.add_keyword_menu),
                pystray.Menu.SEPARATOR,
                item("Exit", self.on_exit),
            ),
        )

        self.tray_icon.run(setup=self._tray_setup)


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", help="Path to profile json")
    parser.add_argument("--console", action="store_true", help="Keep the console window attached")
    parser.add_argument("--no-pythonw", action="store_true", help="Do not relaunch with pythonw.exe")
    parser.add_argument("--no-admin", action="store_true", help="Do not request Windows admin elevation")
    parser.add_argument("--_openclaw_pythonw_relaunched", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--_openclaw_elevated", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    profile_path = discover_profile_path(args.profile)
    profile = load_profile(profile_path)

    if should_relaunch_in_background(args):
        if relaunch_in_background(sys.argv):
            return

    if should_relaunch_as_admin(args, profile):
        if relaunch_as_admin(sys.argv):
            return
        raise SystemExit("Administrator permission is required to run this tray app.")

    app = NodeTrayApp(profile)
    app.write_log(
        "Starting tray from source runtime. "
        f"profile={profile_path} | elevated={'yes' if is_running_as_admin() else 'no'} | "
        f"console={'yes' if args.console else 'no'}"
    )
    app.run()


if __name__ == "__main__":
    main()
