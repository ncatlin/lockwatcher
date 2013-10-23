# -*- coding: iso-8859-15 -*-
'''
@author: Nia Catlin

Various hardware and system state interrogation routines
'''
import subprocess,threading,socket,os
import smtplib
import wmi,pythoncom,ctypes
import fileconfig
import win32con, win32api, time

lockState = False
def checkLock(): return lockState

import Queue
from interception import *
class interceptListenThread(threading.Thread):
    def __init__(self,keyQueue):
        threading.Thread.__init__(self) 
        self.keyQueue = keyQueue
        self.name='interceptThread'
        self.context = None
    def run(self):
        stroke = Stroke()
        context = create_context()
        set_filter( context, is_keyboard, FILTER_KEY_DOWN | FILTER_KEY_UP)
        set_filter( context, is_mouse, FILTER_MOUSE_ALL)
        keyStroke = KeyStroke()
        mouseStroke = MouseStroke()

        self.context = context
        self.listening = True
        lastMoveEvent = time.time() #dont want to spam event queue with mouse moves
        while self.listening == True:
                device=wait_with_timeout(context,1000)
                result = receive(context, device, stroke,1) 
                if result == 0: 
                    if self.listening == True: continue
                    else: break

                if is_keyboard(device):
                    stroke2KeyStroke( stroke, dest = keyStroke )
                    send(context,device, keyStroke,1)
                    kCode = win32api.MapVirtualKey(keyStroke.code,3) #MAPVK_VSC_TO_VK_EX
                    
                    if kCode in vkDict.keys():
                        keyname = vkDict[kCode]
                    else: keyname = 0
                
                    self.keyQueue.put(({1:False,0:True}[keyStroke.state],(kCode,keyname)))
                elif is_mouse(device):
                    stroke2MouseStroke( stroke, dest = mouseStroke )
                    send(context,device, mouseStroke,1)
                    
                    mouseMoveTotal = abs(mouseStroke.x) + abs(mouseStroke.y)
                    if mouseStroke.state != 0: 
                        self.keyQueue.put(('mouse','Button'))
                    elif mouseMoveTotal > 1: #implementation of sensitive mode goes here if needed
                        timeNow = time.time()
                        if timeNow>lastMoveEvent+1:
                            self.keyQueue.put(('mouse','Moved'))
                            lastMoveEvent = timeNow

                    
                else:
                    send(context,device, stroke,1)
          
        destroy_context(context)

    def stop(self):
        self.listening = False

class kbdHookListenThread(threading.Thread):
    def __init__(self,keyQueue):
        threading.Thread.__init__(self) 
        self.keyQueue = keyQueue
        self.name='kbdHookListenThread'
    def run(self):
        
        self.listening = True
        heldKeys = []
        releasedKeys=[]
        
        while self.listening == True:
            time.sleep(0.002)
            
            #stop keyholding from sending multiple keypresses
            for heldKey in heldKeys:
                if win32api.GetAsyncKeyState(heldKey)==0:
                    releasedKeys.append(heldKey)
            
            for key in releasedKeys:
                if key in heldKeys:
                    heldKeys.remove(key)
                    self.keyQueue.put((False,(key,'')))

            #find any new key presses
            for charkey in range(0x7,0xFF):
                if win32api.GetAsyncKeyState(charkey)==-32767:
                    if charkey not in heldKeys:
                        heldKeys.append(charkey)
                        if charkey in vkDict.keys():
                            keyname = vkDict[charkey]
                        else: keyname = 0
                        self.keyQueue.put((True,(charkey,keyname)))
    def stop(self):
        self.listening = False


#passes keystrokes from (eventFile device) to the callback function 
#used in the gui keyboard setup window
class kbdProcessThread(threading.Thread):
    def __init__(self,callback,eventFile):
        threading.Thread.__init__(self) 
        self.callback = callback
        self.name='kbdListenThread'
    def run(self):
        keyQueue = Queue.Queue()
        
        hookListener = kbdHookListenThread(keyQueue)
        hookListener.start()
        
        
        self.listening = True
        while self.listening == True:
            eventType,eventDetails = keyQueue.get(True)
            if eventType == True: self.callback(eventDetails[0],eventDetails[1])

        if hookListener.is_alive(): hookListener.stop()
                        

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
        try:
            scanprocess = subprocess.Popen(['btscanner'], stdout=subprocess.PIPE)
        except WindowsError as e:
            self.callback(e)
            return None
        
        if scanprocess == []:
            self.callback("[Error] Bluetooth does not appear to be enabled: skipping")
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
                csvfile = open(fileconfig.config.get('TRIGGERS','BALLISTIX_LOG_FILE'),mode='rb')
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
        adapters = c.Win32_NetworkAdapter(PhysicalAdapter=True)
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
        smtpHost = self.config.get('EMAIL','EMAIL_SMTP_HOST')
        if smtpHost != None:
            try:
                s = smtplib.SMTP(smtpHost, timeout=10)
                s.login(self.config.get('EMAIL','EMAIL_USERNAME'), self.config.get('EMAIL','EMAIL_PASSWORD'))
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
        
        imapHost = self.config.get('EMAIL','EMAIL_IMAP_HOST')
        if imapHost != None:    
            try:
                server = imapclient.IMAPClient(imapHost, use_uid=False, ssl=True)
                server.login(self.config.get('EMAIL','EMAIL_USERNAME'), self.config.get('EMAIL','EMAIL_PASSWORD'))
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
    
vkDict= {
0xC1 : 'C1',
0xC2 : 'C2',
0x6B : 'Num+',
0xF6 : 'Attn',
0x08 : 'Bkspc',
0x03 : 'Break',
0x0C : 'Clear',
0xF7 : 'CrSel',
0x6E : 'Num.',
0x6F : 'Num/',
0xF9 : 'EeEo',
0x1B : 'Esc',
0x2B : 'Exec',
0xF8 : 'ExSel',
0xE6 : 'Clr',
0xE3 : 'Hlp',
0x30 : '0',
0x31 : '1',
0x32 : '2',
0x33 : '3',
0x34 : '4',
0x35 : '5',
0x36 : '6',
0x37 : '7',
0x38 : '8',
0x39 : '9',
0x41 : 'A',
0x42 : 'B',
0x43 : 'C',
0x44 : 'D',
0x45 : 'E',
0x46 : 'F',
0x47 : 'G',
0x48 : 'H',
0x49 : 'I',
0x4A : 'J',
0x4B : 'K',
0x4C : 'L',
0x4D : 'M',
0x4E : 'N',
0x4F : 'O',
0x50 : 'P',
0x51 : 'Q',
0x52 : 'R',
0x53 : 'S',
0x54 : 'T',
0x55 : 'U',
0x56 : 'V',
0x57 : 'W',
0x58 : 'X',
0x59 : 'Y',
0x5A : 'Z',
0x6A : 'Num*',
0xFC : 'None',
0x60 : 'Num0',
0x61 : 'Num1',
0x62 : 'Num2',
0x63 : 'Num3',
0x64 : 'Num4',
0x65 : 'Num5',
0x66 : 'Num6',
0x67 : 'Num7',
0x68 : 'Num8',
0x69 : 'Num9',
0xBA : ';',
0xE2 : '><',
0xBF : '?/',
0xC0 : '~`',
0xDB : '{[',
0xDC : '|\\',
0xDD : '}]',
0xDE : '"\'',
0xDF : '`¬§!',
0xF0 : 'Attn',
0xF3 : 'Auto',
0xE1 : 'Ax',
0xF5 : 'BkTab',
0xFE : 'Clr',
0xBC : '<,',
0xF2 : 'Copy',
0xEF : 'CuSel',
0xF4 : 'Enlw',
0xF1 : 'Fnsh',
0x95 : 'Loya',
0x93 : 'Mashu',
0x96 : 'Roya',
0x94 : 'Troku',
0xEA : 'Jump',
0xBD : '_-',
0xEB : 'Pa1',
0xEC : 'Pa2',
0xED : 'Pa3',
0xBE : '>.',
0xBB : '+=',
0xE9 : 'Reset',
0xEE : 'WCtrl',
0xFD : 'Pa1',
0xE7 : 'Pket',
0xFA : 'Play',
0xE5 : 'Pcess',
0x0D : 'Enter',
0x29 : 'Sel',
0x6C : 'Sepr',
0x20 : 'Space',
0x6D : 'Num-',
0x09 : 'Tab',
0xFB : 'Zoom',
0xFF : '???',
0x1E : 'Accpt',
0x5D : 'CMenu',
0xA6 : 'Back',
0xAB : 'Fav',
0xA7 : 'Fwd',
0xAC : 'BHome',
0xA8 : 'BRef',
0xAA : 'BSearc',
0xA9 : 'BStop',
0x14 : 'CLock',
0x1C : 'Convt',
0x2E : 'Del',
0x28 : 'Down',
0x23 : 'End',
0x70 : 'F1',
0x79 : 'F10',
0x7A : 'F11',
0x7B : 'F12',
0x7C : 'F13',
0x7D : 'F14',
0x7E : 'F15',
0x7F : 'F16',
0x80 : 'F17',
0x81 : 'F18',
0x82 : 'F19',
0x71 : 'F2',
0x83 : 'F20',
0x84 : 'F21',
0x85 : 'F22',
0x86 : 'F23',
0x87 : 'F24',
0x72 : 'F3',
0x73 : 'F4',
0x74 : 'F5',
0x75 : 'F6',
0x76 : 'F7',
0x77 : 'F8',
0x78 : 'F9',
0x18 : 'Final',
0x2F : 'Help',
0x24 : 'Home',
0xE4 : 'Ico0',
0x2D : 'Inst',
0x17 : 'Junja',
0x15 : 'Kana',
0x19 : 'Kanji',
0xB6 : 'App1',
0xB7 : 'App2',
0xB4 : 'Mail',
0xB5 : 'Media',
0x01 : 'MouseL',
0xA2 : 'LCtrl',
0x25 : 'Left',
0xA4 : 'LAlt',
0xA0 : 'LShift',
0x5B : 'LWin',
0x04 : 'MouseM',
0xB0 : 'NextT',
0xB3 : 'PlayP',
0xB1 : 'PrevT',
0xB2 : 'Stop',
0x1F : 'ModeC',
0x22 : 'PgDn',
0x1D : '????',
0x90 : 'NumLk',
0x92 : 'Jisho',
0x13 : 'Pause',
0x2A : 'Print',
0x21 : 'PgUp',
0x02 : 'MouseR',
0xA3 : 'RCtrl',
0x27 : 'Right',
0xA5 : 'RAlt',
0xA1 : 'RShift',
0x5C : 'RWin',
0x91 : 'ScrLk',
0x5F : 'Sleep',
0x2C : 'PScr',
0x26 : 'Up',
0xAE : 'VolDn',
0xAD : 'VolMu',
0xAF : 'VolUp',
0x05 : 'XBtn1',
0x06 : 'XBtn2'}

'''
#works interactively, not as a service
def clo():
    user32 = ctypes.windll.User32
    OpenInputDesktop = user32.OpenInputDesktop
    
    if OpenInputDesktop (0, False, win32con.STANDARD_RIGHTS_READ|win32con.DESKTOP_CREATEWINDOW) == 0:
        return True
    else:
        return False   
'''