'''
@author: Nia Catlin

This was not fun to write

TODO:Get scanning for listening devices to work
'''
import ctypes
from ctypes import windll, WinError, cast, GetLastError
from ctypes import c_char, c_char_p, c_ubyte, c_int, c_uint, c_ushort, c_ulong, c_ulonglong
from ctypes import Structure, POINTER, sizeof
from ctypes.wintypes import DWORD, WORD, BYTE

SOCKET = c_uint

WSAStarted = None

def WSAStart():
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
    
    def MAKEWORD(bLow, bHigh):
        return (bHigh << 8) + bLow
    
    wsaData = WSADATA()
    ret = WSAStartup(MAKEWORD(2, 2), LP_WSADATA(wsaData))
    if ret != 0:
        raise WinError(ret)


WSACleanup = windll.Ws2_32.WSACleanup
WSACleanup.argtypes = ()
WSACleanup.restype = c_int  
    
closesocket = windll.Ws2_32.closesocket
closesocket.argtypes = (SOCKET,)
closesocket.restype = c_int
   
def connect(deviceID):
    global WSAStarted
    if WSAStarted == None: WSAStart()
    
    socket = windll.Ws2_32.socket
    socket.argtypes = (c_int, c_int, c_int)
    socket.restype = SOCKET

    AF_BTH = 32
    SOCK_STREAM = 1
    IPPROTO_RFCOMM = 3
    INVALID_SOCKET = ~0
    
    connectSocket = socket(AF_BTH, SOCK_STREAM, IPPROTO_RFCOMM)
    if connectSocket == INVALID_SOCKET:
        raise WinError()
        WSACleanup()
        WSAStarted = None
    
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

    sa = sockaddr_bth()
    sa.addressfamily = AF_BTH
    sa.btAddr = deviceID
    sa.port = 2
    
    SOCKET_ERROR = -1
    
    ret = connect(connectSocket, sockaddr_bthp(sa), sizeof(sa))
    if ret == SOCKET_ERROR:
        err = GetLastError()
        WSAStarted = None
        #print(WinError())
        closesocket(connectSocket)
        WSACleanup()
        return True, err
    
    return False, connectSocket
   
def recv(devSocket):
    if WSAStarted == None: WSAStart()
    
    BUFSIZE=64
    buf = ' '*BUFSIZE
    
    recv = windll.Ws2_32.recv
    recv.argtypes = (SOCKET,POINTER(c_char),c_int, c_int)
    recv.restype = c_int
    
    result = recv(devSocket,cast(buf,POINTER(c_char)),BUFSIZE,0)
    
    if result == 0 or result == -1:
        return True, GetLastError()
    else: #shouldn't really get here
        return False, result
    
def stop(socket):
        WSAStarted = None
        closesocket(socket)
        WSACleanup()
    
