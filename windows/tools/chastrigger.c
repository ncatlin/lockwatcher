/*
Just sends a number to port 22190
To compile with cygwin: 
	gcc chastrigger.c -lws2_32 -o chastrigger.exe
*/
#define WIN32_LEAN_AND_MEAN

#include <winsock2.h>
#include <Ws2tcpip.h>

// Link with ws2_32.lib
#pragma comment(lib, "Ws2_32.lib")

int main() {
    int iResult;
    WSADATA wsaData;

    iResult = WSAStartup(MAKEWORD(2,2), &wsaData);
    if (iResult != NO_ERROR) {
        wprintf(L"WSAStartup failed with error: %d\n", iResult);
        return 1;
    }

    SOCKET ConnectSocket = INVALID_SOCKET;
    ConnectSocket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    if (ConnectSocket == INVALID_SOCKET) {
        wprintf(L"socket failed with error: %ld\n", WSAGetLastError());
        WSACleanup();
        return 1;
    }

    struct sockaddr_in lockwatcher; 
    lockwatcher.sin_family = AF_INET;
    lockwatcher.sin_addr.s_addr = inet_addr( "127.0.0.1" );
    lockwatcher.sin_port = htons( 22190 );

    char *sendbuf = "1";
    iResult = sendto( ConnectSocket, sendbuf, (int)strlen(sendbuf), 0, (SOCKADDR *)&lockwatcher, sizeof(lockwatcher));
    if (iResult == SOCKET_ERROR) {
        wprintf(L"send failed with error: %d\n", WSAGetLastError());
        closesocket(ConnectSocket);
        WSACleanup();
        return 1;
    }

    iResult = shutdown(ConnectSocket, SD_SEND);
    if (iResult == SOCKET_ERROR) {
        closesocket(ConnectSocket);
        WSACleanup();
        return 1;
    }
}