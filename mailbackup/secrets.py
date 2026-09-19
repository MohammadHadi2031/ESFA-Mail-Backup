from __future__ import annotations

import base64
import ctypes
import os
from ctypes import wintypes


class SecretError(RuntimeError):
    pass


class DATA_BLOB(ctypes.Structure):
    _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _windows_api():
    crypt32 = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _crypt_protect(data: bytes) -> bytes:
    if os.name != 'nt':
        raise SecretError('ذخیره امن رمز عبور فقط روی ویندوز در دسترس است.')
    source, source_buffer = _blob(data)
    result = DATA_BLOB()
    crypt32, kernel32 = _windows_api()
    if not crypt32.CryptProtectData(ctypes.byref(source), 'EsfaMailBackup', None, None, None, 0, ctypes.byref(result)):
        raise SecretError('Windows نتوانست رمز عبور را رمزنگاری کند.')
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))
        del source_buffer


def _crypt_unprotect(data: bytes) -> bytes:
    if os.name != 'nt':
        raise SecretError('بازیابی امن رمز عبور فقط روی ویندوز در دسترس است.')
    source, source_buffer = _blob(data)
    result = DATA_BLOB()
    description = wintypes.LPWSTR()
    crypt32, kernel32 = _windows_api()
    if not crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description), None, None, None, 0, ctypes.byref(result)):
        raise SecretError('رمز عبور برای این حساب ویندوز قابل بازیابی نیست.')
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        if description:
            kernel32.LocalFree(ctypes.cast(description, ctypes.c_void_p))
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))
        del source_buffer


def protect(password: str) -> str:
    if not password:
        raise SecretError('رمز عبور خالی است.')
    return base64.b64encode(_crypt_protect(password.encode('utf-8'))).decode('ascii')


def unprotect(token: str) -> str:
    try:
        encrypted = base64.b64decode(token.encode('ascii'), validate=True)
        return _crypt_unprotect(encrypted).decode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise SecretError('اطلاعات رمز ذخیره‌شده معتبر نیست.') from exc
