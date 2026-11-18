"""Telegram Bot API publishing, restricted to explicitly configured target chats."""
import json
import mimetypes
import secrets
import urllib.request
from pathlib import Path

def send_photo(token,target,image_path,caption='',timeout=50):
    if not token or not token.strip():raise ValueError('未设置 Telegram Bot Token')
    if not target or not str(target).strip():raise ValueError('未设置接收群组或频道 ID')
    path=Path(image_path)
    if not path.is_file():raise FileNotFoundError(str(path))
    if len(caption)>1024:raise ValueError('图片说明超过 Telegram 1024 字符限制')
    boundary='DS_'+secrets.token_hex(12)
    def field(name,value):
        return (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n').encode('utf-8')
    body=field('chat_id',target)+field('caption',caption)
    mime=mimetypes.guess_type(path.name)[0] or 'image/png'
    body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="capture.png"\r\nContent-Type: {mime}\r\n\r\n').encode()
    body+=path.read_bytes()+b'\r\n'+f'--{boundary}--\r\n'.encode()
    req=urllib.request.Request(f'https://api.telegram.org/bot{token}/sendPhoto',data=body,
       headers={'Content-Type':f'multipart/form-data; boundary={boundary}'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:payload=json.loads(r.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Telegram HTTP {exc.code}；请核对机器人权限、群组 ID、限流情况') from exc
    if not payload.get('ok'):raise RuntimeError('Telegram 发布失败：'+str(payload.get('description','未知错误')))
    return payload['result']['message_id']

# No plaintext credential persistence: Windows DPAPI protects tokens at rest.
def protect_token(token):
    if not token:return ''
    import ctypes,base64
    from ctypes import wintypes
    if __import__('os').name!='nt':raise RuntimeError('凭据加密只支持 Windows')
    class BLOB(ctypes.Structure):_fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_byte))]
    raw=token.encode();buffer=ctypes.create_string_buffer(raw)
    a=BLOB(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));b=BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(a),None,None,None,None,0,ctypes.byref(b)):
        raise ctypes.WinError()
    ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
    try:return base64.b64encode(ctypes.string_at(b.pbData,b.cbData)).decode()
    finally:ctypes.windll.kernel32.LocalFree(b.pbData)

def unprotect_token(blob):
    if not blob:return ''
    import ctypes,base64
    from ctypes import wintypes
    if __import__('os').name!='nt':raise RuntimeError('凭据解密只支持 Windows')
    class BLOB(ctypes.Structure):_fields_=[('cbData',wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_byte))]
    raw=base64.b64decode(blob);buffer=ctypes.create_string_buffer(raw)
    a=BLOB(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_byte)));b=BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(a),None,None,None,None,0,ctypes.byref(b)):
        raise ctypes.WinError()
    ctypes.windll.kernel32.LocalFree.argtypes=[ctypes.c_void_p]
    try:return ctypes.string_at(b.pbData,b.cbData).decode()
    finally:ctypes.windll.kernel32.LocalFree(b.pbData)
