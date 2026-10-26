"""Windows user-bound encryption for pending operations in hosted profiles."""
import ctypes
import json
import os
from ctypes import wintypes


class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]


def protect(data,decrypt=False):
    if os.name!='nt':raise RuntimeError('Hosted desktop pending requests require Windows DPAPI.')
    buffer=ctypes.create_string_buffer(data)
    source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    result=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.LocalFree.argtypes=[ctypes.c_void_p];kernel.LocalFree.restype=ctypes.c_void_p
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if not fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(result)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:return ctypes.string_at(result.data,result.size)
    finally:kernel.LocalFree(result.data)


def read_pending(path,encrypted):
    if not path.exists():return None
    raw=path.read_bytes()
    return json.loads(protect(raw,True) if encrypted else raw)


def write_pending(path,payload,encrypted):
    raw=json.dumps(payload).encode()
    temp=path.with_suffix('.tmp')
    with open(temp,'wb') as stream:
        stream.write(protect(raw) if encrypted else raw)
        stream.flush();os.fsync(stream.fileno())
    os.replace(temp,path)
