"""Best-effort Windows memory measurements, containing no application content."""
import ctypes as c
import sys


def memory_metrics(worker_pid=None):
    if sys.platform != "win32": return {}
    try:
        class Status(c.Structure):
            _fields_ = [("length",c.c_ulong),("load",c.c_ulong)] + [(name,c.c_ulonglong) for name in ("total","available","page_total","page_available","virtual_total","virtual_available","extended")]
        class Counters(c.Structure):
            _fields_ = [("size",c.c_ulong),("faults",c.c_ulong)] + [(name,c.c_size_t) for name in ("peak","working","paged_peak","paged","nonpaged_peak","nonpaged","pagefile","pagefile_peak","private")]
        kernel,psapi=c.WinDLL("kernel32"),c.WinDLL("psapi")
        kernel.GetCurrentProcess.restype=c.c_void_p
        kernel.OpenProcess.argtypes=[c.c_ulong,c.c_bool,c.c_ulong]
        kernel.OpenProcess.restype=c.c_void_p
        kernel.CloseHandle.argtypes=[c.c_void_p]
        psapi.GetProcessMemoryInfo.argtypes=[c.c_void_p,c.c_void_p,c.c_ulong]
        status=Status();status.length=c.sizeof(status)
        result={}
        if kernel.GlobalMemoryStatusEx(c.byref(status)):
            result.update(available_memory_mb=round(status.available/1024**2,1), memory_load_percent=status.load)
        for name,pid in (("controller",None),("worker",worker_pid)):
            if name == "worker" and pid is None: continue
            if pid is not None and (type(pid) is not int or pid <= 0): continue
            handle=kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x1000,False,pid)
            if not handle: continue
            try:
                counters=Counters(); counters.size=c.sizeof(counters)
                if psapi.GetProcessMemoryInfo(handle,c.byref(counters),counters.size):
                    result[name+"_peak_mb"]=round(counters.peak/1024**2,1)
                    result[name+"_private_mb"]=round(counters.private/1024**2,1)
            finally:
                if pid is not None: kernel.CloseHandle(handle)
        return result
    except (OSError,ValueError,TypeError,AttributeError):
        return {}
