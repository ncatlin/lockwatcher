'''
Created on 26 Aug 2013

@author: Administrator
'''
import os, ctypes

def AFShutdown():
    TC_PATH = 'C:\\Program Files\TrueCrypt\TrueCrypt.exe'
    
    #lock the screen 
    #ctypes.windll.user32.LockWorkStation()
    
    #forces truecrypt to dismount its volumes and discard any key data
    os.system('"'+TC_PATH+'"' +" /dismount /force /wipecache /quit /silent")
    
    #disable usb
    #devcon.exe ... #HKLM\system\currentcontrolset\services\USBstor
    #disable firewire
    #devcon.exe ...
    
    #close programs
    #cleanse memory
    
    #wipe temporary
    #wipe logs
    
    #shutdown
    #shutdown.exe -s -t 00 -f #force, no timeout, 
    
    #slow shutdown?- http://support.microsoft.com/kb/975777/en-us