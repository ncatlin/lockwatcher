'''
Created on 20 Sep 2013

@author: UserX
'''

from ctypes import windll, WinError
from ctypes import c_char, c_char_p, c_ubyte, c_int, c_uint, c_ushort, c_ulong, c_ulonglong
from ctypes import Structure, POINTER, sizeof
from ctypes.wintypes import DWORD, WORD, BYTE

WSADESCRIPTION_LEN = 256
WSASYS_STATUS_LEN = 128

class WSADATA(Structure):
    _fields_ = [
        ("wVersion",        WORD),
        ("wHighVersion",    WORD),
        ("szDescription",   c_char * (WSADESCRIPTION_LEN+1)),
        ("szSystemStatus",  c_char * (WSASYS_STATUS_LEN+1)),
        ("iMaxSockets",     c_ushort),
        ("iMaxUdpDg",       c_ushort),
        ("lpVendorInfo",    c_char_p),
    ]

LP_WSADATA = POINTER(WSADATA)

WSAStartup = windll.Ws2_32.WSAStartup
WSAStartup.argtypes = (WORD, POINTER(WSADATA))
WSAStartup.restype = c_int

WSACleanup = windll.Ws2_32.WSACleanup
WSACleanup.argtypes = ()
WSACleanup.restype = c_int

def MAKEWORD(bLow, bHigh):
    return (bHigh << 8) + bLow

wsaData = WSADATA()
ret = WSAStartup(MAKEWORD(2, 2), LP_WSADATA(wsaData))
if ret != 0:
    raise WinError(ret)

SOCKET = c_uint

socket = windll.Ws2_32.socket
socket.argtypes = (c_int, c_int, c_int)
socket.restype = SOCKET

closesocket = windll.Ws2_32.closesocket
closesocket.argtypes = (SOCKET,)
closesocket.restype = c_int

AF_BTH = 32
SOCK_STREAM = 1
IPPROTO_RFCOMM = 3
INVALID_SOCKET = ~0

connectSocket = socket(AF_BTH, SOCK_STREAM, IPPROTO_RFCOMM)
if connectSocket == INVALID_SOCKET:
    raise WinError()
    WSACleanup()
else:
    print('socket created ok',connectSocket)

class GUID(Structure):
    _pack_ = 4
    _fields_ = [
    ("data1",   DWORD),
    ("data2",   WORD),
    ("data3",   WORD),
    ("data4",   BYTE * 6)
]



class sockaddr_bth(Structure):
    _pack_ = 2
    _fields_ = [
        ("addressfamily",      c_ushort),
        ("btAddr",        c_ulonglong),
        ("serviceClassID2",     GUID),
        ("port",            c_ulong)
    ]
    
sockaddr_bthp = POINTER(sockaddr_bth)
connect = windll.Ws2_32.connect
connect.argtypes = (SOCKET, sockaddr_bthp, c_int)
connect.restype = c_int

device = 0x3085a94bca88

sa = sockaddr_bth()
sa.addressfamily = AF_BTH
sa.btAddr = device
sa.port = 2

SOCKET_ERROR = -1

print('trying to connect')

ret = connect(connectSocket, sockaddr_bthp(sa), sizeof(sa))
if ret == SOCKET_ERROR:
    ret = WinError()
    closesocket(connectSocket)
    WSACleanup()
    raise ret
    

print ("SUCCESS")

closesocket(connectSocket)
WSACleanup()

