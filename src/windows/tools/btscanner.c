/* 
Scans for nearby bluetooth devices
To compile with Cygwin:
	gcc btscanner.c -lws2_32 -lBthprops -o btscanner.exe
*/
#include <stdlib.h>
#include <stdio.h>
//-lws2_32
#include <Winsock2.h>
#include <Ws2bth.h>
// -lBthprops
#include <BluetoothAPIs.h>

int main(){

BLUETOOTH_FIND_RADIO_PARAMS m_bt_find_radio = {sizeof(BLUETOOTH_FIND_RADIO_PARAMS)};
BLUETOOTH_RADIO_INFO m_bt_info = {sizeof(BLUETOOTH_RADIO_INFO),0,};
BLUETOOTH_DEVICE_SEARCH_PARAMS m_search_params = {
  sizeof(BLUETOOTH_DEVICE_SEARCH_PARAMS),1,1,1,1,1,5,NULL
};

BLUETOOTH_DEVICE_INFO m_device_info = {sizeof(BLUETOOTH_DEVICE_INFO),0,};

 
HBLUETOOTH_DEVICE_FIND m_bt_dev = BluetoothFindFirstDevice(&m_search_params , &m_device_info);

if (m_bt_dev == NULL)
{
    char errstring[10] = {0};
    sprintf(errstring,"!%d",GetLastError());
    errstring[0] = 0x94;
    printf("%s",errstring);
    return -1;
}
               

UCHAR address[225];
do
{
char name[225] = {0};
wcstombs((char*)name, m_device_info.szName, wcslen(m_device_info.szName));

sprintf(address,"%02X:%02X:%02X:%02X:%02X:%02X",m_device_info.Address.rgBytes[5],m_device_info.Address.rgBytes[4],m_device_info.Address.rgBytes[3], 
		m_device_info.Address.rgBytes[2],m_device_info.Address.rgBytes[1], m_device_info.Address.rgBytes[0]);
printf("%s,%s\n",address,name);

} while (BluetoothFindNextDevice(m_bt_dev , &m_device_info));

return 0;
}