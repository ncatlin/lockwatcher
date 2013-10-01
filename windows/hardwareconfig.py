'''
@author: Nia Catlin

Various hardware and system state interrogation routines
'''
import subprocess,threading,socket,os
import smtplib
import wmi,pythoncom,ctypes
import fileconfig

#tests for locking by checking if desktop can be switched to
def checkLock(): 
    user32 = ctypes.windll.User32
    OpenInputDesktop = user32.OpenInputDesktop
    SwitchDesktop = user32.SwitchDesktop
    
    if SwitchDesktop (OpenInputDesktop (0, False, 0x100)) == 0:
        return True
    else:
        return False   

import win32con, win32api, time
#passes keystrokes from (eventFile device) to the callback function 
class kbdListenThread(threading.Thread):
    def __init__(self,callback,eventFile):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.name='kbdListenThread'
    def run(self):
        heldKeys = []
        releasedKeys = []
        
        self.listening = True
        while self.listening == True:
            time.sleep(0.001)
            
            #stop keyholding from sending multiple keypresses
            for heldKey in heldKeys:
                if win32api.GetAsyncKeyState(heldKey)==0:
                    releasedKeys.append(heldKey)

            for key in releasedKeys:
                heldKeys.remove(key)
            releasedKeys = []
            
            #find any new key presses
            for charkey in range(8,222):
                if win32api.GetAsyncKeyState(charkey)==-32767:
                    if charkey not in heldKeys:
                        heldKeys.append(charkey)
                        self.callback(charkey)

    def terminate(self):
        self.listening = False


import winsockbtooth
class BTTestThread(threading.Thread):
    def __init__(self,callback,deviceID):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.deviceID = deviceID
        self.name='btTestThreads'
    def run(self):
        error, result = winsockbtooth.connect(deviceID = self.deviceID)
        if error == False:
            winsockbtooth.WSACleanup()
        self.callback(error,result)
        return

#takes a '12:23:34:45:56:67' string, returns hex equivalent (0x122334455667)
def BTStrToHex(BTStr):
    devIDParts = BTStr.split(':')
        
    if BTStr == 'None' or len(devIDParts) != 6: 
        #self.devStatusLabel.config(text="Status: Invalid ID")
        return 0
    
    hexDevID = 0
    for i in range(5,-1,-1):
        hexDevID += (int(devIDParts[i],base=16)<<0x8*(5-i))
    
    return hexDevID      

#sends the output of 'hcitool scan' to the callback function
#ie: a list of nearby discoverable bluetooth devices
class BTScanThread(threading.Thread):
    def __init__(self,callback):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.name='btScanThread'
    def run(self):
        
        scanprocess = subprocess.Popen(['btscanner'], stdout=subprocess.PIPE)
        print("scanprocess = ",scanprocess)
        if scanprocess == []:
            print("Bluetooth does not appear to be enabled: skipping")
            return None

        out, err = scanprocess.communicate()
        self.callback(out)

        return None

#checks temperature.csv for updates
class RAMMonitor(threading.Thread):
    def __init__(self, callback):
        threading.Thread.__init__(self)
        self.callback = callback
        self.die = False
        self.name='ramMonitorThread'
    def run(self):
        lastTime = None
        startup = True
        while self.die == False:
            if startup == False: time.sleep(1) #the MOD logger only writes once per second
            else: startup = False
            
            try:
                csvfile = open(fileconfig.config['TRIGGERS']['BALLISTIX_LOG_FILE'],mode='rb')
                csvfile.seek(-30, 2)
                line = csvfile.readline()
                csvfile.close()
            except IOError as e:
                if e.errno == 2:
                    self.callback("Unable to open log file")
                    return
                else:
                    continue #probably locked by logger writing
                    time.sleep(0.5)
        
            
            
            logDetail = line.decode("utf-8").split(',')
            if len(logDetail) != 4 and len(logDetail) != 0: continue #empty or invalid
            
            logTime,RAMTemp =  (logDetail[0],logDetail[2])
            if lastTime == None or logTime != lastTime:
            #if RAMTemp <= fileconfig.config['TRIGGERS']['LOW_TEMP']:  
                self.callback('('+logTime+'): '+RAMTemp+'C')
                lastTime = logTime
                
    def terminate(self):
        self.die = True
            
#lists available network adapters (in a thread because it takes time)
class netScanThread(threading.Thread):
    def __init__(self,callback):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.name='netScanThread'
    def run(self):
        pythoncom.CoInitialize()
        c = wmi.WMI()
        adapters = c.Win32_NetworkAdapter()
        try:
            self.callback(adapters)
        except:
            pass #tab changed
        
#tries to connect to the email hosts listed with the given credentials    
import imapclient
class emailTestThread(threading.Thread):
    def __init__(self,callback,config):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.config = config
        self.name='mailTestThread'
    def run(self):
        print("in email test thread")
        if self.config['EMAIL']['EMAIL_SMTP_HOST']!= None:
            try:
                s = smtplib.SMTP(self.config['EMAIL']['EMAIL_SMTP_HOST'], timeout=10)
                s.login(self.config['EMAIL']['EMAIL_USERNAME'], self.config['EMAIL']['EMAIL_PASSWORD'])
                s.quit()
            except smtplib.SMTPAuthenticationError:
                resultS = 'Authentication Error'
            except socket.timeout:
                resultS = 'Connection Timeout'
            except socket.gaierror:
                resultS = 'Connection Failed'
            except:
                resultS = 'Failed'
            else:
                resultS = 'OK'
            
        if self.config['EMAIL']['EMAIL_IMAP_HOST']!= None:    
            try:
                server = imapclient.IMAPClient(self.config['EMAIL']['EMAIL_IMAP_HOST'], use_uid=False, ssl=True)
                server.login(self.config['EMAIL']['EMAIL_USERNAME'], self.config['EMAIL']['EMAIL_PASSWORD'])
                server.select_folder('INBOX')
                server.logout()
                resultI = "OK"
            except socket.gaierror:
                resultI = 'Connection Failed'
            except socket.timeout:
                resultI = 'Connection Timeout'
            except imapclient.IMAPClient.Error as e:
                resultI = e.args[0].decode('utf-8')
            
        self.callback('IMAP: '+resultI,'SMTP: '+resultS)
        return None