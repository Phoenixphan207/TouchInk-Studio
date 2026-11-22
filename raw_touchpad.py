"""Windows Precision Touchpad Raw Input backend.

Non-invasive: registers for Raw Input, does not install a driver, change settings,
block OS gestures or acquire an exclusive device handle. Requires pywin32 and
Windows. Reports explicit diagnostics when a device/report isn't supported.
"""
import ctypes as C
from ctypes import wintypes as W
import queue, threading, time, sys

if sys.platform == 'win32':
    import win32gui, win32api, win32con
    user32=C.WinDLL('user32',use_last_error=True)
    hid=C.WinDLL('hid',use_last_error=True)
    HIDP_STATUS_SUCCESS=0x00110000

    class RAWINPUTDEVICE(C.Structure):
        _fields_=[('usUsagePage',W.USHORT),('usUsage',W.USHORT),('dwFlags',W.DWORD),('hwndTarget',W.HWND)]
    class RAWINPUTHEADER(C.Structure):
        _fields_=[('dwType',W.DWORD),('dwSize',W.DWORD),('hDevice',W.HANDLE),('wParam',W.WPARAM)]
    class RAWHID(C.Structure):
        _fields_=[('dwSizeHid',W.DWORD),('dwCount',W.DWORD)]
    class HIDP_CAPS(C.Structure):
        _fields_=[('Usage',W.USHORT),('UsagePage',W.USHORT),('InputReportByteLength',W.USHORT),('OutputReportByteLength',W.USHORT),('FeatureReportByteLength',W.USHORT),('Reserved',W.USHORT*17),('NumberLinkCollectionNodes',W.USHORT),('NumberInputButtonCaps',W.USHORT),('NumberInputValueCaps',W.USHORT),('NumberInputDataIndices',W.USHORT),('NumberOutputButtonCaps',W.USHORT),('NumberOutputValueCaps',W.USHORT),('NumberOutputDataIndices',W.USHORT),('NumberFeatureButtonCaps',W.USHORT),('NumberFeatureValueCaps',W.USHORT),('NumberFeatureDataIndices',W.USHORT)]
    class HIDP_RANGE(C.Structure):
        _fields_=[('UsageMin',W.USHORT),('UsageMax',W.USHORT),('StringMin',W.USHORT),('StringMax',W.USHORT),('DesignatorMin',W.USHORT),('DesignatorMax',W.USHORT),('DataIndexMin',W.USHORT),('DataIndexMax',W.USHORT)]
    class HIDP_NOT_RANGE(C.Structure):
        _fields_=[('Usage',W.USHORT),('Reserved1',W.USHORT),('StringIndex',W.USHORT),('Reserved2',W.USHORT),('DesignatorIndex',W.USHORT),('Reserved3',W.USHORT),('DataIndex',W.USHORT),('Reserved4',W.USHORT)]
    class HIDP_U(C.Union):
        _fields_=[('Range',HIDP_RANGE),('NotRange',HIDP_NOT_RANGE)]
    class HIDP_VALUE_CAPS(C.Structure):
        _fields_=[('UsagePage',W.USHORT),('ReportID',W.BYTE),('IsAlias',W.BYTE),('BitField',W.USHORT),('LinkCollection',W.USHORT),('LinkUsage',W.USHORT),('LinkUsagePage',W.USHORT),('IsRange',W.BYTE),('IsStringRange',W.BYTE),('IsDesignatorRange',W.BYTE),('IsAbsolute',W.BYTE),('HasNull',W.BYTE),('Reserved',W.BYTE),('BitSize',W.USHORT),('ReportCount',W.USHORT),('Reserved2',W.USHORT*5),('UnitsExp',W.ULONG),('Units',W.ULONG),('LogicalMin',W.LONG),('LogicalMax',W.LONG),('PhysicalMin',W.LONG),('PhysicalMax',W.LONG),('u',HIDP_U)]
    user32.RegisterRawInputDevices.argtypes=[C.POINTER(RAWINPUTDEVICE),W.UINT,W.UINT];user32.RegisterRawInputDevices.restype=W.BOOL
    user32.GetRawInputData.argtypes=[W.HANDLE,W.UINT,W.LPVOID,C.POINTER(W.UINT),W.UINT];user32.GetRawInputData.restype=W.UINT
    user32.GetRawInputDeviceInfoW.argtypes=[W.HANDLE,W.UINT,W.LPVOID,C.POINTER(W.UINT)];user32.GetRawInputDeviceInfoW.restype=W.UINT
    hid.HidP_GetCaps.argtypes=[C.c_void_p,C.POINTER(HIDP_CAPS)];hid.HidP_GetCaps.restype=W.ULONG
    hid.HidP_GetValueCaps.argtypes=[C.c_int,C.POINTER(HIDP_VALUE_CAPS),C.POINTER(W.USHORT),C.c_void_p];hid.HidP_GetValueCaps.restype=W.ULONG
    hid.HidP_GetUsageValue.argtypes=[C.c_int,W.USHORT,W.USHORT,W.USHORT,C.POINTER(W.ULONG),C.c_void_p,C.c_void_p,W.ULONG];hid.HidP_GetUsageValue.restype=W.ULONG
    hid.HidP_GetUsages.argtypes=[C.c_int,W.USHORT,W.USHORT,C.POINTER(W.USHORT),C.POINTER(W.ULONG),C.c_void_p,C.c_void_p,W.ULONG];hid.HidP_GetUsages.restype=W.ULONG


class RawTouchpad:
    def __init__(self):
        self.events=queue.Queue(maxsize=2048)
        self.running=False
        self.status='Waiting for RAW HID input...'
        self.packet_count=0
        self._cache={}
        self._current=None
        self._last_device=None

    def emit(self, event):
        try:self.events.put_nowait(event)
        except queue.Full:
            try:self.events.get_nowait();self.events.put_nowait(event)
            except queue.Empty:pass

    def start(self):
        if sys.platform!='win32':
            self.status='Available on Windows only';return
        self.running=True
        threading.Thread(target=self._run,daemon=True,name='PrecisionTouchpadRawInput').start()

    def _run(self):
        try:
            self._run_window()
        except Exception as e:
            self.status=f'RAW error: {type(e).__name__}: {e}'

    def _run_window(self):
        hinst=win32api.GetModuleHandle(None)
        def wndproc(hwnd,msg,wparam,lparam):
            if msg==0x00FF:
                try:self._raw(lparam)
                except Exception as e:self.status=f'RAW parser: {type(e).__name__}: {e}'
                return 0
            return win32gui.DefWindowProc(hwnd,msg,wparam,lparam)
        cls=win32gui.WNDCLASS();cls.hInstance=hinst;cls.lpszClassName='TouchInkRawInput'+str(id(self));cls.lpfnWndProc=wndproc
        atom=win32gui.RegisterClass(cls)
        hwnd=win32gui.CreateWindow(atom,'TouchInk RAW',0,0,0,0,0,0,0,hinst,None)
        self.hwnd=hwnd
        rid=RAWINPUTDEVICE(0x0D,0x05,0x00000100,hwnd) # RIDEV_INPUTSINK
        if not user32.RegisterRawInputDevices(C.byref(rid),1,C.sizeof(rid)):
            raise C.WinError(C.get_last_error())
        self.status='RAW registered; waiting for touchpad contacts...'
        while self.running:
            win32gui.PumpWaitingMessages()
            time.sleep(0.002)
        win32gui.DestroyWindow(hwnd)
        rid.dwFlags=0x00000001;rid.hwndTarget=None # RIDEV_REMOVE
        user32.RegisterRawInputDevices(C.byref(rid),1,C.sizeof(rid))

    def stop(self):self.running=False

    def _raw(self,lparam):
        size=W.UINT(0)
        hdrsz=C.sizeof(RAWINPUTHEADER)
        if user32.GetRawInputData(lparam,0x10000003,None,C.byref(size),hdrsz)==0xFFFFFFFF or size.value<=hdrsz:return
        buf=C.create_string_buffer(size.value)
        if user32.GetRawInputData(lparam,0x10000003,buf,C.byref(size),hdrsz)==0xFFFFFFFF:return
        head=RAWINPUTHEADER.from_buffer_copy(buf)
        if head.dwType!=2:return # RIM_TYPEHID
        hidinfo=RAWHID.from_buffer_copy(buf,hdrsz)
        base=hdrsz+C.sizeof(RAWHID)
        if not hidinfo.dwSizeHid or hidinfo.dwSizeHid>4096:return
        device=int(head.hDevice)
        parser=self._cache.get(device)
        if parser is None:
            parser=self._device_parser(head.hDevice)
            self._cache[device]=parser
        if parser is None:return
        for i in range(min(hidinfo.dwCount,32)):
            a=base+i*hidinfo.dwSizeHid
            if a+hidinfo.dwSizeHid>len(buf):break
            report=bytes(buf[a:a+hidinfo.dwSizeHid])
            self._decode(parser,report)

    def _device_parser(self,device):
        n=W.UINT(0)
        self.packet_count+=1
        if user32.GetRawInputDeviceInfoW(device,0x20000005,None,C.byref(n))==0xFFFFFFFF or not n.value:return None
        prep=C.create_string_buffer(n.value)
        if user32.GetRawInputDeviceInfoW(device,0x20000005,prep,C.byref(n))==0xFFFFFFFF:return None
        caps=HIDP_CAPS()
        if hid.HidP_GetCaps(prep,C.byref(caps))!=HIDP_STATUS_SUCCESS:return None
        count=W.USHORT(max(1,min(256,caps.NumberInputValueCaps)))
        values=(HIDP_VALUE_CAPS*count.value)()
        if hid.HidP_GetValueCaps(0,C.cast(values,C.POINTER(HIDP_VALUE_CAPS)),C.byref(count),prep)!=HIDP_STATUS_SUCCESS:return None
        groups={}
        for vc in values[:count.value]:
            if vc.UsagePage not in (0x01,0x0D):continue
            usages=range(vc.u.Range.UsageMin,min(vc.u.Range.UsageMax,vc.u.Range.UsageMin+8)+1) if vc.IsRange else [vc.u.NotRange.Usage]
            for usage in usages:
                if usage in (0x30,0x31) and vc.UsagePage==0x01 or usage==0x51 and vc.UsagePage==0x0D:
                    groups.setdefault(vc.LinkCollection,{})[(vc.UsagePage,usage)]=(int(vc.LogicalMin),int(vc.LogicalMax))
        actual=[(link,v) for link,v in groups.items() if (0x01,0x30) in v and (0x01,0x31) in v]
        if not actual:
            self.status='RAW HID device has no supported X/Y axes';return None
        self.status='RAW ABSOLUTE: X/Y axes detected'
        return (prep,actual)

    def _get(self,prep,report,page,link,usage):
        value=W.ULONG(0)
        rbuf=C.create_string_buffer(report)
        ok=hid.HidP_GetUsageValue(0,page,link,usage,C.byref(value),prep,rbuf,len(report))
        return int(value.value) if ok==HIDP_STATUS_SUCCESS else None

    def _tips(self,prep,report,link):
        rbuf=C.create_string_buffer(report)
        arr=(W.USHORT*32)();size=W.ULONG(32)
        ok=hid.HidP_GetUsages(0,0x0D,link,arr,C.byref(size),prep,rbuf,len(report))
        if ok!=HIDP_STATUS_SUCCESS:return None
        return 0x42 in arr[:size.value] # Tip Switch

    def _decode(self,parser,report):
        prep,groups=parser
        hits=[]
        for link,fields in groups:
            x=self._get(prep,report,0x01,link,0x30)
            y=self._get(prep,report,0x01,link,0x31)
            if x is None or y is None:continue
            xmin,xmax=fields[(0x01,0x30)];ymin,ymax=fields[(0x01,0x31)]
            if xmax<=xmin or ymax<=ymin:continue
            tip=self._tips(prep,report,link)
            cid=self._get(prep,report,0x0D,link,0x51)
            if tip is False:continue
            if tip is None:continue
            u=max(0,min(1,(x-xmin)/(xmax-xmin)))
            v=max(0,min(1,(y-ymin)/(ymax-ymin)))
            hits.append((cid if cid is not None else link,u,v))
        if hits:
            if self._current is None:self._current=hits[0][0]
            matching=[h for h in hits if h[0]==self._current]
            if len(hits)==1 and matching:
                _,u,v=matching[0]
                self.packet_count+=1
                self.emit(('point',u,v,time.perf_counter()))
            else:
                self.emit(('up',));self._current=None
        elif self._current is not None:
            self.emit(('up',));self._current=None
