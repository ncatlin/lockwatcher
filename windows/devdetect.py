'''
devdetect.py

Runs a group of threads which monitor for potential forensic-related system events
and trigger the antiforensic module if the screen is locked

@author: Nia Catlin
'''
import wmi 
import threading, queue
import time
import AFroutines
import winsockbtooth, imapclient, sendemail
import fileconfig, hardwareconfig

from pythoncom import CoInitialize, CoUninitialize

eventQueue = None
allStop = False

lockedStateText = {True:'Locked',False:'Not Locked'}
def eventHandle(event_type,eventReason):
    locked = hardwareconfig.checkLock()
    #print("[%s] Trigger activated. %s"%(lockedStateText[locked],eventReason)) 
    
    if (event_type in fileconfig.config['TRIGGERS']['ALWAYSTRIGGERS'].split(',')) or \
        (event_type in fileconfig.config['TRIGGERS']['LOCKEDTRIGGERS'].split(',') and locked == True):
        eventQueue.put(("Log","[%s - Trigger activated]. %s"%(lockedStateText[locked],eventReason)))
        eventQueue.put(("Kill",eventReason))
    else:
        eventQueue.put(("Log","[%s - Trigger ignored]. %s"%(lockedStateText[locked],eventReason)))
    

#check for logical disk events like cdrom insertion          
class logicalDiskCreateMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'LDMMonitorCreate'
    def run(self):
        CoInitialize()
        self.c = wmi.WMI()
        self.watcher = self.c.Win32_LogicalDisk.watch_for("creation") #deletion too?
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            #if event.DriveType in disksOfInterest: 
            eventHandle('E_DEVICE',"Logical disk creation (Drive Name: '%s', Drive type: '%s')"%(event.DeviceID,event.Description))
        CoUninitialize()
    def terminate(self):
        self.running = False   
        
#check for logical disk removal events like cdrom removal          
class logicalDiskRemoveMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'LDMMonitorRemove'
    def run(self):
        CoInitialize()
        self.c = wmi.WMI()
        self.watcher = self.c.Win32_LogicalDisk.watch_for("deletion") #operation might be a bit strong
        #disksOfInterest = [2,5,6] #removable,cdrom,ramdisk
        
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            #if event.DriveType in disksOfInterest: 
            eventHandle('E_DEVICE',"Logical disk deletion (Drive Name: '%s', Drive type: '%s')"%(event.DeviceID,event.Description))
        CoUninitialize()
    def terminate(self):
        self.running = False   

deviceMessages = {
            1:'Configuration Change',
           2:'Device Arrival',
           3:'Device Removal',
           4:'Docking'}       

#check for addition/removal of lettered storage volumes           
class volumeMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'VolumeMonitor'
    def run(self):
        CoInitialize()
        self.c = wmi.WMI()
        self.watcher = self.c.Win32_VolumeChangeEvent.watch_for()
        
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            eventHandle('E_DEVICE',"Volume Monitor (Drive: '%s' Event: '%s')"%(event.DriveName,deviceMessages[event.EventType]))
            
        CoUninitialize() 
    def terminate(self):
        self.running = False   


#detect device insertion/removal
class deviceMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'DeviceMonitor'
    def run(self):
        CoInitialize()

        self.c = wmi.WMI()
        self.watcher = self.c.Win32_SystemConfigurationChangeEvent.watch_for() #called before devicechangeevent
        eventQueue.put(("Status",'devices',"Active"))
        
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            eventHandle('E_DEVICE',"Device Monitor (%s)"%deviceMessages[event.EventType])
            
        CoUninitialize ()
        eventQueue.put(("Status",'devices',"Not Active"))
    def terminate(self):
        self.running = False   

'''
lDevMonStop = False
#This always fires after the device monitor so only really useful for more verbose logs
#containing name/manufacturer etc of the devies that were plugged in

#bug: actually this seems to wreck my operating system after a few starts and stops -
#    consent.exe hangs, can't open services.msc due to error 0x80041003, other bad things
#disabling it because it doesn't actually make lockwatcher work any better

class LogicalDeviceMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name='LogicalDeviceMonitor'
        global lDevMonStop
        lDevMonStop = False
    def run(self):
        print('ldevmon start')
        CoInitialize()
        self.c = wmi.WMI()
        self.watcher = self.c.CIM_LogicalDevice.watch_for('creation') #deletion too?
        
        #using self.running fails to terminate it most of the time - no idea why
        while lDevMonStop == False: 
            try:
                event = self.watcher(timeout_ms=1000)
            except wmi.x_wmi_timed_out:
                continue
            
            if event.Name != 'USB Composite Device': #not helpful in logs
                details = {}
                if hasattr(event,'Name'): details['Name']= event.Name
                if hasattr(event,'Manufacturer'): details['Manufacturer']= event.Manufacturer
                if hasattr(event,'CreationClassName'): details['CreationClass']= event.CreationClassName
                if hasattr(event,'DeviceID'): details['DeviceID']= event.DeviceID
                
                eventString = ""
                for name,value in details.items():
                    eventString = eventString + "%s: %s. "%(name,value)
                
                #creates a wall of horrible text, so add some whitespace
                eventHandle('E_DEVICE',"Logical Device addition. \n\t%s\n"%eventString)
                
        CoUninitialize()
                
    def terminate(self):
        global lDevMonStop
        lDevMonStop = True
'''

def setupIMAP():
    server = imapclient.IMAPClient(fileconfig.config['EMAIL']['email_imap_host'], use_uid=False, ssl=True)
    server.login(fileconfig.config['EMAIL']['email_username'], fileconfig.config['EMAIL']['email_password'])
    server.select_folder('INBOX')
    return server
      
from imapclient import IMAPClient
class emailMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "mailMonThread"
        self.running = True
    def run(self):
        eventQueue.put(("Status",'email','Connecting to server...'))
        try:
            server = setupIMAP()
        except socket.gaierror:
            eventQueue.put(("Status",'email',"Error: Connect Failed")) 
            return
        except IMAPClient.Error as err:
            eventQueue.put(("Status",'email',err.args[0].decode()))
            return
        self.server = server
        server.idle()

        connectionFails = 0
        
        #dont seem to get an exception when connection attempt interrupted by user
        #this checks if 'stop' was pressed during the connecting phase
        if self.running == False:
            eventQueue.put(("Status",'email','Not Active'))
            return
        
        eventQueue.put(("Status",'email','Active'))
        self.running = True
        while self.running == True:
            #refresh the connection every 14 mins so it doesnt timeout
            try:
                seqid = server.idle_check(840)
            except ValueError:
                if self.running == False: #terminate() was called
                    eventQueue.put(("Status",'email','Not Active')) 
                    return
            if seqid == []: #no mail
                try:
                    server.idle_done()
                    server.idle()
                    connectionFails = 0
                except:
                    eventQueue.put(("Status",'email','Attempting reconnect attempt %s'%(connectionFails)))
                    time.sleep(connectionFails * 3)
                    connectionFails += 1
                    if connectionFails >= 3:
                        eventQueue.put(("Status",'email','Error: Too many failed attempts'))
                        return
                    try:
                        server = setupIMAP()
                    except socket.gaierror:
                        eventQueue.put(("Status",'email',"Error: Connect Failed")) 
                        return
                    self.server = server
                    server.idle()
                continue
            
            #fetch header data using the sequence id of the new mail  
            seqid = seqid[0][0]
            server.idle_done()
            keys = server.fetch(seqid, ['ENVELOPE'])
            server.idle()
            keys = keys[seqid]['ENVELOPE']
            if keys[2][0][2] == 'niasphone':
                eventQueue.put(("Mail",keys[1]))
            else:
                print("Got an email, unknown addressee: %s"%keys[2][0][2]) 
                 
        eventQueue.put(("Status",'email','Not Active'))        
    def terminate(self):
        self.running = False
        print('trying server logout')
        try:
            self.server.logout()
        except:
            pass
        
     

'''triggers the killswitch if the reported RAM temperature falls below RAM_TRIGGER_TEMP#

requires the Ballistix MOD program to be generating a logfile in the specified location
would be much improved by reading the temperatures straight from the SPD interface'''
class RAMMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'RAM Monitor'
    def run(self):
        self.running = True
        eventQueue.put(("Status",'ram',"Active"))
        while self.running == True:
            try:
                csvfile = open(fileconfig.config['TRIGGERS']['BALLISTIX_LOG_FILE'],mode='rb')
            except IOError as e:
                if e.errno == 2:
                    print("Unable to open Ballistix MOD Log file: %s. Cannot monitor RAM temperature."%e)
                    return
                else:
                    continue #probably locked by logger writing
        
            csvfile.seek(-30, 2)
            line = csvfile.readline()
            csvfile.close()
            RAMTemp = line.decode("utf-8").split(',')[2]
            if float(RAMTemp) <= float(fileconfig.config['TRIGGERS']['low_temp']):  
                eventHandle('E_TEMPERATURE',"Low RAM temperature")
            time.sleep(1) #the MOD logger only writes once per second
            
        eventQueue.put(("Status",'ram',"Not Active"))    
    def terminate(self):
        self.running=False
        
        
'''
#detect chassis intrusion detection switch activation
class chasisMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'IntrusionSwitch'
    def run(self):
        CoInitialize()

        self.c = wmi.WMI()
        self.watcher = self.c.Win32_SystemEnclosure.watch_for()
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            
            if event.BreachDescription != None:
                eventHandle('E_INTRUSION',"Breach detected %s"%event.BreachDescription)
            else:
                print("system enclosure event: ",event)
        
        CoUninitialize()
    def terminate(self):
        self.running = False
'''
        
class BTMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'BTmonitor'
        self.socket = None
    def run(self):
        self.running = True
        eventQueue.put(("Status",'bluetooth','Connecting to device...'))

        deviceIDStr = fileconfig.config['TRIGGERS']['bluetooth_device_id']
        deviceID = hardwareconfig.BTStrToHex(deviceIDStr)
        
        error, result = winsockbtooth.connect(deviceID)
        if error == True:
            if result == 10060:
                print("Bluetooth: Error 10060: Couldn't connect")
                eventQueue.put(("Status",'bluetooth',"Error: Connect failed"))
                eventQueue.put(("Log",'Bluetooth: Could not connect to %s'%deviceIDStr))
            elif result == 10050:
                print("Bluetooth: Error 10050: No bluetooth enabled")
                eventQueue.put(("Status",'bluetooth',"Error: No bLuetooth"))
            else:
                print('Bluetooth: other error: %s'%result)
                eventQueue.put(("Status",'bluetooth','Error: %s'%result))
            return 
        
        self.socket = result
        eventQueue.put(("Status",'Bluetooth','Active'))
        while self.running == True:
            error,result=winsockbtooth.recv(self.socket)
            if error == True:
                    if self.running == False: 
                        eventQueue.put(("Status",'bluetooth','Not Active'))
                        return #lockwatcher stopped
                    #todo: add some (if locked_trigger and not_locked, wait on reconnect) code
                    print(' error:%s..'%result)
                    print('Connection to BT Dev lost')
                    eventHandle('E_BLUETOOTH',"Bluetooth connection lost")
                    return
                
        eventQueue.put(("Status",'bluetooth','Not Active'))       
    def terminate(self):
        self.running = False
        if self.socket != None:
            winsockbtooth.closesocket(self.socket)
        
        

#detect network cable removal or wifi AP loss
class adapterDisconnectMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'AdapterDisconnect'
    def run(self):
        try:
            CoInitialize()
            self.c = wmi.WMI(moniker="//./root/WMI")
            self.watcher = self.c.MSNdis_StatusMediaDisconnect.watch_for()
        except:
            eventQueue.put(("Status",'netAdaptersOut','Disconnect: WMI Error'))
            return
        eventQueue.put(("Status",'netAdaptersOut','Disconnect: Active'))
        
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            eventHandle('E_NET_CABLE_OUT',"Net adapter %s lost connection"%event.InstanceName)
            
        CoUninitialize()
        eventQueue.put(("Status",'netAdaptersOut','Disconnect: Not Active'))
    def terminate(self):
        self.running = False   
                    
#detect new network cable inserted
class adapterConnectMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'AdapterConnect'
    def run(self):
        try:
            CoInitialize()
            self.c = wmi.WMI(moniker="//./root/WMI")
            self.watcher = self.c.MSNdis_StatusMediaConnect.watch_for()
        except:
            eventQueue.put(("Status",'netAdaptersIn','Connect: WMI Error'))
            return
            
        eventQueue.put(("Status",'netAdaptersIn','Connect: Active'))
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            eventHandle('E_NET_CABLE_IN',"net adapter %s gained connection"%event.InstanceName)    
            
        CoUninitialize()
        eventQueue.put(("Status",'netAdaptersIn','Connect: Not Active')) 
    def terminate(self):
        self.running = False        
        

#detect new network cable inserted
import socket
class cameraMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'CameraMonitor'
    def run(self):
        try:
            s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            s.bind( ('127.0.0.1', 22190) )
            self.socket = s
        except:
            eventQueue.put(("Status",'cameras',"Can't bind socket 22190\nIs another lockwatcher running?"))
            print('Camera listen exception')
            return
        
        eventQueue.put(("Status",'cameras',"Active"))

        self.running = True
        while self.running == True:
            try:
                data = s.recv(16)
            except socket.error:
                if self.running == False: return
                s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                s.bind( ('127.0.0.1', 22190) )
                continue
            
            data = data.decode('UTF-8')
            
            if data == '1':
                    if fileconfig.isActive('E_CHASSIS_MOTION')[0] != 'False':
                        eventHandle('E_CHASSIS_MOTION',"Chassis camera motion detected") 
                        
            elif data == '2':
                    if fileconfig.isActive('E_ROOM_MOTION')[0] != 'False':
                        eventHandle('E_ROOM_MOTION',"Room camera motion detected") 
                        
        eventQueue.put(("Status",'cameras',"Not Active"))   
    def terminate(self):
        self.running = False 
        self.socket.shutdown(socket.SHUT_RD)
        self.socket.close()
        

import win32api     
class keyboardMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'KeyboardMonitor'
    def run(self):
        heldKeys = []
        releasedKeys = []
        
        killKeys = {}
        for key in fileconfig.config['TRIGGERS']['kbd_kill_combo'].split('+'):
            killKeys[int(key)] = False
        
        self.listening = True
        eventQueue.put(("Status",'killSwitch',"Active"))
        while self.listening == True:
            time.sleep(0.002)
            
            #stop keyholding from sending multiple keypresses
            for heldKey in heldKeys:
                if win32api.GetAsyncKeyState(heldKey)==0:
                    releasedKeys.append(heldKey)

            for key in releasedKeys:
                heldKeys.remove(key)
                killKeys[key] = False
            releasedKeys = []
            
            #find any new key presses
            for charkey in killKeys.keys():
                if win32api.GetAsyncKeyState(charkey)==-32767:
                    if charkey not in heldKeys:
                        heldKeys.append(charkey)
                        killKeys[charkey] = True
                        
                        for keyState in killKeys.values():
                            if keyState == False: break
                        else:
                            eventHandle('E_KILL_SWITCH',"Kill switch pressed")
                            
        eventQueue.put(("Status",'killSwitch',"Not Active"))
    def terminate(self):
        self.listening = False
        

REMOTE_LOCK = 1
REMOTE_STARTMONITOR = 2
REMOTE_STOPMONITOR = 3
REMOTE_SHUTDOWN = 4
REMOTE_KILLSWITCH = 5
commandList = range(REMOTE_LOCK,REMOTE_KILLSWITCH+1)

from sendemail import sendEmail
import subprocess
def executeRemoteCommand(command):
    locked = hardwareconfig.checkLock()
    if command == REMOTE_LOCK:
        if locked == False:
            AFroutines.lockScreen()
            sendEmail("Command successful","Screen locked")
            print('Locking screen from remote command')
        else:
            sendEmail("Command failed","Screen was already locked")
            eventQueue.put(("Log",'Lock screen failed - command received while locked'))
        
    elif command == REMOTE_STARTMONITOR:
        #cant check ispy camera status, just have to assume it was not monitoring
        iSpyPath = fileconfig.config['TRIGGERS']['ispy_path']
        roomCamID = fileconfig.config['TRIGGERS']['room_cam_id']
        subprocess.call([iSpyPath,'commands bringonline,2,%s'%roomCamID])
        sendEmail("Command successful","Movement monitoring initiated. Have a nice day.")
        print("Movement monitoring initiated after remote command")
        
    elif command == REMOTE_STOPMONITOR:
        #cant check ispy camera status, just have to assume it was already monitoring
        iSpyPath = fileconfig.config['TRIGGERS']['ispy_path']
        roomCamID = fileconfig.config['TRIGGERS']['room_cam_id']
        subprocess.call([iSpyPath,'commands takeoffline,2,%s'%roomCamID])
        sendEmail("Command successful","Movement monitoring disabled. Welcome home!")
        print("Movement monitoring disabled after remote command")
        
    elif command == REMOTE_SHUTDOWN:
        sendEmail("Command successful","Shutting down...")
        AFroutines.standardShutdown()
        
    elif command == REMOTE_KILLSWITCH:
        AFroutines.emergency()

#this is a travesty
trigMonitorMap = {'bluetooth': 'BTMonitor',
                'killSwitch' : 'keyboardMonitor',
                'ram' : 'RAMMonitor',
                'cameras': 'cameraMonitor',
                'netAdaptersIn' : 'adapterConnectMonitor',
                'netAdaptersOut' : 'adapterDisconnectMonitor',
                'email':'email'}

trigEventMap = {'bluetooth': 'E_BLUETOOTH',
                'killSwitch' : 'E_KILL_SWITCH',
                'ram' : 'E_TEMPERATURE',
                'devices' : 'E_DEVICE',
                'netAdaptersIn' : 'E_NET_CABLE_IN',
                'netAdaptersOut' : 'E_NET_CABLE_OUT',
                'chasCam' : 'E_CHASSIS_MOTION',
                'roomCam' : 'E_ROOM_MOTION',
                'email':'email'}

def startMonitor(threadDict,trigger):
            if trigger == 'E_DEVICE':
                threadDict['deviceMonitor'] = deviceMonitor()   
                threadDict['deviceMonitor'].start()
                
                threadDict['volumeMonitor'] = volumeMonitor()
                threadDict['volumeMonitor'].start()
                threadDict['logicalDiskRemoveMonitor'] = logicalDiskRemoveMonitor()
                threadDict['logicalDiskRemoveMonitor'].start()
                threadDict['logicalDiskCreateMonitor'] = logicalDiskCreateMonitor()
                threadDict['logicalDiskCreateMonitor'].start()
                #threadDict['logicalDeviceMonitor'] = LogicalDeviceMonitor()
            elif trigger == 'E_INTRUSION' :
                #threadDict['chasisMonitor'] = chasisMonitor()
                pass
            elif trigger == 'E_NET_CABLE_IN' :
                threadDict['adapterConnectMonitor'] = adapterConnectMonitor()   
                threadDict['adapterConnectMonitor'].start()    
            elif trigger == 'E_NET_CABLE_OUT' :
                threadDict['adapterDisconnectMonitor'] = adapterDisconnectMonitor() 
                threadDict['adapterDisconnectMonitor'].start()       
            elif trigger == 'E_TEMPERATURE':
                threadDict['RAMMonitor'] = RAMMonitor()    
                threadDict['RAMMonitor'].start()
            elif trigger == 'E_BLUETOOTH':
                threadDict['BTMonitor'] = BTMonitor() 
                threadDict['BTMonitor'].start()             
            elif trigger == 'E_CHASSIS_MOTION':
                if 'cameraMonitor' not in threadDict.keys():
                    threadDict['cameraMonitor'] = cameraMonitor()  
                    threadDict['cameraMonitor'].start()   
            elif trigger == 'E_ROOM_MOTION':
                if 'cameraMonitor' not in threadDict.keys():
                    threadDict['cameraMonitor'] = cameraMonitor()
                    threadDict['cameraMonitor'].start()
            elif trigger == 'E_KILL_SWITCH':
                threadDict['keyboardMonitor'] = keyboardMonitor()
                threadDict['keyboardMonitor'].start()
            elif trigger == 'email':
                threadDict['email'] = emailMonitor()    
                threadDict['email'].start()
  
class lockwatcher(threading.Thread):
    def __init__(self,statuses,msgAddFunc):
        threading.Thread.__init__(self)
        self.name = 'Lockwatcher'
        self.statuses = statuses
        self.msgAdd = msgAddFunc
    def run(self):
        
        LOCKED = fileconfig.config['TRIGGERS']['lockedtriggers'].split(',')
        ALWAYS = fileconfig.config['TRIGGERS']['alwaystriggers'].split(',')
        ACTIVE = LOCKED+ALWAYS
        
        global eventQueue
        eventQueue = queue.Queue()
        
        threadDict = {}
        
        for trigger in ACTIVE:
            startMonitor(threadDict,trigger)

        if fileconfig.config['EMAIL']['ENABLE_REMOTE'] == 'True':
            startMonitor(threadDict,'email')
        
        badCommands = 0
        shutdownActivated = False
        while True:
            event = eventQueue.get(block=True, timeout=None)
            eventType = event[0]
            if eventType == 'Kill':
                eventReason = event[1]
                #don't trigger multiple shutdowns but keep logging while we can
                if shutdownActivated == False: 
                    shutdownActivated = True
                    
                    if fileconfig.config['EMAIL']['email_alert'] == 'True' and \
                        'Kill switch' not in eventReason:
                        try:
                            #has a 4 second timeout for blocking operations
                            sendEmail('Emergency shutdown triggered',eventReason)
                            print('email sent')
                        except:
                            pass #email failed, oh well. 
                    AFroutines.emergency()
            elif eventType == 'Status':
                self.statuses[event[1]].set(event[2])
            elif eventType == 'Log':
                logPath = fileconfig.config['TRIGGERS']['logfile']
                try:
                    fd = open(logPath,'a+')
                    fd.write(time.strftime('[%x %X] ')+event[1]+'\n') 
                    fd.close()
                except:
                    print('failed to write log')
                self.msgAdd(event[1])
                
            elif eventType == 'stop':
                for tname,thread in threadDict.items():
                    if thread == None: continue
                    if thread.is_alive(): 
                        if tname == 'logicalDeviceMonitor': print('ldevm alive, terminating')
                        thread.terminate()
                    else:
                        if tname == 'logicalDeviceMonitor': print('ldevm dead, cant terminate')
                time.sleep(1)
                return
            
            elif eventType == 'startMonitor':
                for monitor in event[1]:
                    print('starting monitor',monitor)
                    if monitor not in threadDict or threadDict[monitor] == None or \
                        threadDict[monitor].is_alive() == False:
                        startMonitor(threadDict,trigEventMap[monitor])
                        
            
            elif eventType == 'stopMonitor':
                for monitor in event[1]:
                    print('stop monitor',monitor)
                    
                    if monitor == 'devices':
                        threadnames = ['deviceMonitor','volumeMonitor',
                                       'logicalDiskRemoveMonitor','logicalDiskCreateMonitor']
                    else:
                        threadnames = [trigMonitorMap[monitor]]
                        
                    for threadname in threadnames:
                        if threadname in threadDict and threadDict[threadname] != None \
                            and threadDict[threadname].is_alive():
                            threadDict[threadname].terminate()
                            threadDict[threadname] = None
            
            elif eventType == 'Mail':
                command, code = event[1].split(' ')
                self.msgAdd('Received mail %s %s'%(command,code))
                command = int(command)
                if command in commandList and sendemail.validHMAC(code,command) == True:
                    print('Mail authenticated')
                    executeRemoteCommand(command) 
                    badCommands = 0 #good command resets limit
                else:
                    badCommands += 1
                    sendEmail("Command failed","Bad command or authentication code received: %s"%command)
                    self.msgAdd('Mail not authenticated or bad command: %s'%command)
                    badCommandLimit = int(fileconfig.config['EMAIL']['BAD_COMMAND_LIMIT'])
                    if badCommandLimit > 0 and badCommands >= badCommandLimit:
                        self.msgAdd('Emergency shutdown: Too many bad remote commands')
                        if shutdownActivated == False:
                            AFroutines.emergency()
                            
                    continue     
            else:
                print("Event queue item: "+event)
                self.msgAdd('otherevent'+event)
                
monitorThread = None
def createLockwatcher(statuses,msgAddFunc):
    global monitorThread
        
    monitorThread = lockwatcher(statuses,msgAddFunc)