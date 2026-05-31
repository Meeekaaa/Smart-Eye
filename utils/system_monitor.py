import contextlib
import ctypes
import logging
import os
import threading
import time

import psutil

try:
    from ctypes import byref, c_ulong, c_void_p, windll, wintypes
except Exception:
    windll = None

logger = logging.getLogger(__name__)


class SystemMonitor:
    def __init__(self):
        self._cpu_percent = 0.0
        self._ram_percent = 0.0
        self._gpu_percent = 0.0
        self._gpu_mem_percent = 0.0
        self._gpu_name = ""
        self._cpu_name_long = ""
        self._running = False
        self._thread = None
        self._pdh_failed = False
        self._wmi_gpu_failed = False
        self._wmi_ohm_failed = False
        self._wmi_enabled = str(os.getenv("SMARTEYE_ENABLE_WMI_MONITOR", "0")).strip().lower() in ("1", "true", "yes")
        self._wmi_instance = None
        self._wmi_ohm_instance = None
        self._gpu_name_cached = ""
        self._last_wmi_gpu_query_ts = 0.0
        self._last_ohm_query_ts = 0.0
        self._wmi_query_interval_sec = 2.5
        self._cpu_name_attempted = False
        try:
            import platform

            self._cpu_name = platform.processor() or ""
        except Exception:
            self._cpu_name = ""

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)

    def _get_wmi(self):
        if self._wmi_instance is None:
            import wmi

            self._wmi_instance = wmi.WMI(namespace="root\\cimv2")
        return self._wmi_instance

    def _get_wmi_ohm(self):
        if self._wmi_ohm_instance is None:
            import wmi

            self._wmi_ohm_instance = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        return self._wmi_ohm_instance

    def _loop(self):
        while self._running:
            self._cpu_percent = psutil.cpu_percent(interval=1)

            mem = psutil.virtual_memory()
            self._ram_percent = mem.percent

            raw_gpu = 0.0
            found_gpu = False

            if not found_gpu:
                try:
                    import GPUtil

                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu = gpus[0]
                        raw_gpu = gpu.load * 100
                        self._gpu_mem_percent = gpu.memoryUtil * 100
                        self._gpu_name = gpu.name
                        found_gpu = True
                except Exception:
                    pass

            now = time.time()

            if (
                self._wmi_enabled
                and not found_gpu
                and not self._wmi_ohm_failed
                and (now - self._last_ohm_query_ts) >= self._wmi_query_interval_sec
            ):
                try:
                    self._last_ohm_query_ts = now
                    w = self._get_wmi_ohm()
                    sensors = w.Sensor()
                    for s in sensors:
                        if s.SensorType == "Load" and "GPU" in (s.Name or ""):
                            raw_gpu = float(s.Value or 0)
                            found_gpu = True
                        if "GPU" in (s.Name or "") and "Core" in (s.Name or ""):
                            self._gpu_name = s.Hardware.Name if hasattr(s, "Hardware") else "GPU"
                except Exception:
                    self._wmi_ohm_failed = True

            if (
                self._wmi_enabled
                and not found_gpu
                and not self._wmi_gpu_failed
                and (now - self._last_wmi_gpu_query_ts) >= self._wmi_query_interval_sec
            ):
                try:
                    self._last_wmi_gpu_query_ts = now
                    result = self._wmi_gpu_perf()
                    if result is not None:
                        load, name = result
                        raw_gpu = load
                        if name:
                            self._gpu_name = name
                        elif not self._gpu_name:
                            self._gpu_name = "Intel Iris Xe"
                        found_gpu = True
                except Exception:
                    logger.debug("WMI GPU perf query failed", exc_info=True)
                    self._wmi_gpu_failed = True

            if not found_gpu and not self._pdh_failed and os.name == "nt" and windll is not None:
                try:
                    val = self._pdh_gpu_util()
                    if val is not None:
                        raw_gpu = float(val)
                        if not self._gpu_name:
                            self._gpu_name = "Windows GPU"
                        found_gpu = True
                    else:
                        self._pdh_failed = True
                except Exception:
                    logger.debug("PDH GPU sampling failed", exc_info=True)
                    self._pdh_failed = True

            if not self._gpu_name:
                try:
                    import onnxruntime as ort

                    avail = ort.get_available_providers()
                    for ep in ("OpenVINOExecutionProvider", "DmlExecutionProvider", "CUDAExecutionProvider"):
                        if ep in avail:
                            self._gpu_name = ep.replace("ExecutionProvider", "")
                            break
                except Exception:
                    pass

            if not self._cpu_name_long and not self._cpu_name_attempted:
                self._cpu_name_attempted = True
                try:
                    if not self._wmi_enabled:
                        raise RuntimeError("WMI monitor disabled")
                    import wmi

                    w = wmi.WMI()
                    cpus = w.Win32_Processor()
                    if cpus:
                        proc = cpus[0]
                        raw_name = (getattr(proc, "Name", "") or "").strip()
                        mhz = getattr(proc, "MaxClockSpeed", None)
                        cores = getattr(proc, "NumberOfCores", None)
                        threads = getattr(proc, "NumberOfLogicalProcessors", None)
                        extras = []
                        if mhz:
                            extras.append(f"{mhz} MHz")
                        if cores:
                            extras.append(f"{cores} Core(s)")
                        if threads:
                            extras.append(f"{threads} Logical Processor(s)")
                        extra_str = ", ".join(extras)
                        self._cpu_name_long = f"{raw_name}, {extra_str}" if extra_str else raw_name
                        self._cpu_name = raw_name
                except Exception:
                    try:
                        import platform

                        raw_name = platform.processor() or "CPU"
                        self._cpu_name = raw_name
                        self._cpu_name_long = raw_name
                    except Exception:
                        self._cpu_name = "CPU"
                        self._cpu_name_long = "CPU"

            try:
                import re

                raw = self._cpu_name or ""
                name = raw
                for token in ("(R)", "(TM)", "CPU", "Processor", "GenuineIntel", "AuthenticAMD", "@"):
                    name = name.replace(token, "")
                name = re.sub(r"Stepping\\s*\\d+", "", name, flags=re.IGNORECASE)
                name = re.sub(r"Family\\s+\\d+\\s+Model\\s+\\d+", "", name, flags=re.IGNORECASE)
                name = re.sub(r"\\s+GHz.*", "", name, flags=re.IGNORECASE)
                name = re.sub(r"\\s+", " ", name).strip()
                parts = name.split()
                if len(parts) > 10:
                    name = " ".join(parts[:10])
                self._cpu_name = name or "CPU"
            except Exception:
                pass

            self._gpu_percent = min(raw_gpu, 100.0)

            time.sleep(0)

    def _wmi_gpu_perf(self):
        try:
            w = self._get_wmi()
            entries = w.query("SELECT Name, UtilizationPercentage FROM Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine")
        except Exception:
            logger.debug("Win32_PerfFormattedData_GPUPerformanceCounters_GPUEngine unavailable", exc_info=True)
            self._wmi_gpu_failed = True
            return None

        if not entries:
            return None

        if not self._gpu_name_cached:
            try:
                w = self._get_wmi()
                controllers = w.query("SELECT Name FROM Win32_VideoController")
                for c in controllers:
                    n = getattr(c, "Name", "") or ""
                    if n and any(k in n.lower() for k in ("intel", "iris", "amd", "radeon", "nvidia")):
                        self._gpu_name_cached = n
                        break
                if not self._gpu_name_cached and controllers:
                    self._gpu_name_cached = getattr(controllers[0], "Name", "") or ""
            except Exception:
                pass

        engine_totals = {}

        for entry in entries:
            try:
                name = (getattr(entry, "Name", "") or "").lower()
                val = float(getattr(entry, "UtilizationPercentage", 0) or 0)

                engtype = "other"
                if "engtype_" in name:
                    engtype = name.split("engtype_")[-1]

                engine_totals[engtype] = engine_totals.get(engtype, 0.0) + val
            except Exception:
                continue

        if not engine_totals:
            return None

        total = max(engine_totals.values())

        return min(total, 100.0), self._gpu_name_cached

    def _pdh_gpu_util(self):
        val = self._pdh_gpu_util_native()
        if val is not None:
            return val
        return self._pdh_gpu_util_powershell()

    def _pdh_gpu_util_native(self):
        PDH_FMT_DOUBLE = 0x00000200
        PDH_MORE_DATA = 0x800007D2

        class _PdhFmtCounterValueDouble(ctypes.Structure):
            _fields_ = [
                ("CStatus", wintypes.DWORD),
                ("doubleValue", ctypes.c_double),
            ]

        class _PdhFmtCounterValueItemW(ctypes.Structure):
            _fields_ = [
                ("szName", wintypes.LPWSTR),
                ("FmtValue", _PdhFmtCounterValueDouble),
            ]

        try:
            query = c_void_p()
            counter = c_void_p()

            res = windll.pdh.PdhOpenQueryW(None, 0, byref(query))
            if res != 0:
                return None

            path = "\\GPU Engine(*)\\Utilization Percentage"
            res = windll.pdh.PdhAddEnglishCounterW(query, path, 0, byref(counter))
            if res != 0:
                windll.pdh.PdhCloseQuery(query)
                return None

            windll.pdh.PdhCollectQueryData(query)
            time.sleep(0.5)
            windll.pdh.PdhCollectQueryData(query)

            buf_size = c_ulong(0)
            item_count = c_ulong(0)
            res = windll.pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT_DOUBLE, byref(buf_size), byref(item_count), None)

            if (res & 0xFFFFFFFF) not in (PDH_MORE_DATA, 0):
                windll.pdh.PdhCloseQuery(query)
                return None

            if item_count.value <= 0:
                windll.pdh.PdhCloseQuery(query)
                return None

            buffer = ctypes.create_string_buffer(buf_size.value)
            res = windll.pdh.PdhGetFormattedCounterArrayW(counter, PDH_FMT_DOUBLE, byref(buf_size), byref(item_count), buffer)
            windll.pdh.PdhCloseQuery(query)

            if res != 0:
                return None

            engine_totals = {}

            item_size = ctypes.sizeof(_PdhFmtCounterValueItemW)
            raw_len = len(buffer.raw)
            for i in range(item_count.value):
                offset = i * item_size
                if offset + item_size > raw_len:
                    break
                item = _PdhFmtCounterValueItemW.from_buffer_copy(buffer.raw, offset)
                try:
                    name = str(item.szName or "").lower()
                except Exception:
                    name = ""
                try:
                    val = float(item.FmtValue.doubleValue)
                except Exception:
                    val = 0.0

                engtype = "other"
                if "engtype_" in name:
                    engtype = name.split("engtype_")[-1]
                engine_totals[engtype] = engine_totals.get(engtype, 0.0) + val

            if engine_totals:
                return min(max(engine_totals.values()), 100.0)

        except Exception:
            logger.debug("PDH GPU array query failed", exc_info=True)

        return None

    def _pdh_gpu_util_powershell(self):
        try:
            import json
            import subprocess

            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                r"Get-Counter -Counter '\GPU Engine(*)\Utilization Percentage' -MaxSamples 2 | "
                r"Select-Object -ExpandProperty CounterSamples | ConvertTo-Json",
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, timeout=8)
            if not out.strip():
                return None
            data = json.loads(out)
            samples = data if isinstance(data, list) else [data]
            engine_totals = {}
            for s in samples:
                inst = str(s.get("InstanceName") or "").lower()
                val = 0.0
                with contextlib.suppress(Exception):
                    val = float(s.get("CookedValue", 0))
                engtype = "other"
                if "engtype_" in inst:
                    engtype = inst.split("engtype_")[-1]
                engine_totals[engtype] = engine_totals.get(engtype, 0.0) + val
            if engine_totals:
                return min(max(engine_totals.values()), 100.0)
        except Exception:
            logger.debug("PowerShell PDH fallback failed", exc_info=True)

        return None

    @property
    def cpu(self):
        return self._cpu_percent

    @property
    def ram(self):
        return self._ram_percent

    @property
    def gpu_load(self):
        return self._gpu_percent

    @property
    def gpu_name(self):
        return self._gpu_name

    @property
    def cpu_name(self):
        return self._cpu_name

    @property
    def cpu_name_long(self):
        return self._cpu_name_long or self._cpu_name


_instance = None


def get_monitor():
    global _instance
    if _instance is None:
        _instance = SystemMonitor()
    return _instance
