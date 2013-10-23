'''
devdetect.py

Runs a group of threads which monitor for potential forensic-related system events
and trigger the antiforensic module if the screen is locked

@author: Nia Catlin
'''

import AFroutines
import fileconfig, hardwareconfig, sendemail, winsockbtooth

import socket,sys
import threading, Queue, subprocess
import select
import os,time,datetime
import imapclient
import wmi, win32timezone #cx_freeze doesn't seem to get this unless imported explicitly
from pythoncom import CoInitialize, CoUninitialize

eventQueue = None
allStop = False
startupTime = None

lockedStateText = {True:'Locked',False:'Not Locked'}
#trigger events go here to be checked for activation conditions
def eventHandle(event_type,eventReason):
    locked = hardwareconfig.checkLock()

    
    while True: #this can be a race condition with configfile alterations. try again if we get a bad reading
        try:   
            alwaysTriggers = fileconfig.config.get('TRIGGERS','ALWAYSTRIGGERS').split(',')
            lockedTriggers = fileconfig.config.get('TRIGGERS','LOCKEDTRIGGERS').split(',')
            
            if (event_type in alwaysTriggers) or (event_type in lockedTriggers and locked == True):
                
                eventQueue.put(("Log","[%s - *Trigger ACTIVATED*]. %s"%(lockedStateText[locked],eventReason)))
                
                if fileconfig.config.get('TRIGGERS','test_mode') == 'False':
                    #allow recovery in situations where the computer would shuts down as soon as it starts up
                    if time.time() < startupTime + 90:
                        eventQueue.put(("Log",'Shutdown cancelled - Not allowed within 90 seconds of lockwatcher start'))
                    else:
                        eventQueue.put(("Kill",eventReason))
                else:
                    eventQueue.put(("Log",'Shutdown cancelled - test mode active'))
            else:
                '''log the ignored trigger (but not the 2nd killswitch because a logfile containing
                every press of the letter 'p' is going to be a mess)'''
                if event_type not in  ['E_MOUSE_MOVE','E_MOUSE_BTN','E_KILL_SWITCH_2']:
                    eventQueue.put(("Log","[%s - Trigger ignored]. %s"%(lockedStateText[locked],eventReason)))
            
            break
        except:
            time.sleep(0.3)
            continue
    
#running as a service makes exception handling more difficult
#write log directly instead of relying on eventqueue processing    
def debugLog(msg):
    logPath = fileconfig.config.get('TRIGGERS','logfile')
    try:
        fd = open(logPath,'a+')
        fd.write(time.strftime('[%x %X]')+str(msg)+'\n') 
        fd.close()
    except:
        eventQueue.put(('Log','Failed to write debuglog: %s'%msg))

#check for logical disk creation events like cdrom insertion          
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
        self.watcher = self.c.Win32_LogicalDisk.watch_for("deletion")
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
        try:
            CoInitialize()
    
            self.c = wmi.WMI()
            self.watcher = self.c.Win32_SystemConfigurationChangeEvent.watch_for() #called before devicechangeevent
        except:
            eventQueue.put(("Status",'devices',"Error: WMI Error"))
            eventQueue.put(("Log","Unable to start device monitor: WMI error"))
            return
        eventQueue.put(("Status",'devices',"Active"))
        
        self.running = True
        while self.running == True:
            try:
                event = self.watcher(timeout_ms=2000)
            except wmi.x_wmi_timed_out:
                continue
            eventHandle('E_DEVICE',"Device Monitor (%s)"%deviceMessages[event.EventType])
            
        CoUninitialize ()
        eventQueue.put(("Status",'devices',"Not Running"))
    def terminate(self):
        self.running = False   

'''
gets information about inserted/removed devices like name,manufacturer,bus,etc

This always fires after the device monitor so only really useful for more verbose logs
containing name/manufacturer etc of the devies that were plugged in

------
#bug: actually this seems to wreck my operating system after a few starts and stops -
#    consent.exe hangs, can't open services.msc due to error 0x80041003, other bad things
#disabling it because it doesn't actually make lockwatcher work any better
------

lDevMonStop = False
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

#logs in to specified imap server and selects the inbox
def setupIMAP():
    server = imapclient.IMAPClient(fileconfig.config.get('EMAIL','email_imap_host'), use_uid=False, ssl=True)
    server.login(fileconfig.config.get('EMAIL','email_username'), fileconfig.config.get('EMAIL','email_password'))
    server.select_folder('INBOX')
    return server



#waits for new mail, places it in the event queue if the addressee is correct
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
        except imapclient.IMAPClient.Error as err:
            eventQueue.put(("Status",'email',err.args[0].decode()))
            return
        self.server = server
        server.idle()

        connectionFails = 0
        
        #dont seem to get an exception when connection attempt interrupted by user
        #this checks if 'stop' was pressed during the connecting phase
        if self.running == False:
            eventQueue.put(("Status",'email','Not Running'))
            return
        
        eventQueue.put(("Status",'email','Active'))

        while self.running == True:
            #refresh the connection every 14 mins so it doesnt timeout
            try:
                seqid = server.idle_check(840)
            except:
                if self.running == False: #terminate() was called
                    eventQueue.put(("Status",'email','Not Running')) 
                    return
                
            if seqid == []: #no mail
                try:
                    server.idle_done()
                    server.idle()
                    connectionFails = 0
                except:
                    if self.running == False: break
                    
                    eventQueue.put(("Status",'email','Attempting reconnect #%s'%(connectionFails)))
                    eventQueue.put(('Log',"IMAP connection lost. Attempting reconnect #%s"%(connectionFails)))
                    
                    if connectionFails > 0: time.sleep(connectionFails * 3)
                    connectionFails += 1
                    if connectionFails >= 3:
                        eventQueue.put(("Status",'email','Error: Too many failed attempts'))
                        eventQueue.put(('Log',"IMAP connection lost. Giving up."))
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
            addressee = keys[2][0][2]
            intendedAddressee = fileconfig.config.get('EMAIL','command_email_address').split('@')[0]
            if addressee == intendedAddressee:
                eventQueue.put(("Mail",keys[1]))
            else:
                eventQueue.put(('Log',"Got an email with unknown addressee: %s (need addressee %s)"%
                                (addressee,intendedAddressee)))
                 
        eventQueue.put(("Status",'email','Not Running'))        
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
                csvfile = open(fileconfig.config.get('TRIGGERS','BALLISTIX_LOG_FILE'),mode='rb')
            except IOError as e:
                eventQueue.put(("Status",'ram',"Error: Cannot read Temperature.csv"))
                eventQueue.put(("Log","Unable to open Ballistix MOD Log file: %s. Cannot monitor RAM temperature."%e))
                return
            except:
                time.sleep(0.7)
                continue #probably locked by logger writing
        
            csvfile.seek(-30, 2)
            line = csvfile.readline()
            csvfile.close()
            RAMTemp = line.decode("utf-8").split(',')[2]
            if float(RAMTemp) <= float(fileconfig.config.get('TRIGGERS','low_temp')):  
                eventHandle('E_TEMPERATURE',"Low RAM temperature")
            time.sleep(1) #the MOD logger only writes once per second
            
        eventQueue.put(("Status",'ram',"Not Running"))    
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
        

        deviceIDStr = fileconfig.config.get('TRIGGERS','bluetooth_device_id')
        deviceID = hardwareconfig.BTStrToHex(deviceIDStr)
        
        if ':' not in deviceIDStr:
            eventQueue.put(("Status",'bluetooth','Error: Not configured'))
            eventQueue.put(("Log",'Bluetooth monitor error: Device not configured'))
            return
        eventQueue.put(("Status",'bluetooth','Connecting to device...'))
        
        error, result = winsockbtooth.connect(deviceID)
        if error == True:
            if result == 10060:
                eventQueue.put(("Status",'bluetooth',"Error: Connect failed"))
                eventQueue.put(("Log",'Bluetooth: Could not connect to %s'%deviceIDStr))
            elif result == 10050:
                eventQueue.put(("Status",'bluetooth',"Error: No Bluetooth"))
                eventQueue.put(("Log","Bluetooth: Error 10050: Bluetooth not enabled"))
            else:
                eventQueue.put(("Status",'bluetooth','Error: %s'%result))
                eventQueue.put(("Log",'Bluetooth: other error: %s'%result))
                
            return 
        
        self.socket = result
        eventQueue.put(("Log",'Bluetooth: Connected to device %s'%deviceIDStr))
        eventQueue.put(("Status",'bluetooth','Active'))
        while self.running == True:
            error,result=winsockbtooth.recv(self.socket)
            if error == True:
                    if self.running == False: 
                        eventQueue.put(("Status",'bluetooth','Not Running'))
                        return
                    
                    eventHandle('E_BLUETOOTH',"Bluetooth connection lost")
                    
                    #if we didnt lose connection under trigger conditions
                    #assume user wants auto-reconnect (?)
                    error = True
                    attempts = 0
                    while error == True and attempts < 7:
                        time.sleep(10*1+(attempts*5))
                        error, result = winsockbtooth.connect(deviceID)
                        attempts = attempts + 1
                    self.socket = result

                
        eventQueue.put(("Status",'bluetooth','Not Running'))       
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
            
            #this code repeated in lw-gui; put it in a function somewhere
            c = wmi.WMI()
            networkAdapters = c.Win32_NetworkAdapter(PhysicalAdapter=True)
            
            guidDict={}
            for ad in networkAdapters:
                guidDict[ad.Name] = ad.GUID
            
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
            if event.InstanceName in guidDict.keys() and \
                guidDict[event.InstanceName] in fileconfig.config.get('TRIGGERS','adapterDisconGUIDS').split(';'):
                eventHandle('E_NET_CABLE_OUT',"Net adapter '%s' lost connection"%event.InstanceName)
            
        CoUninitialize()
        eventQueue.put(("Status",'netAdaptersOut','Disconnect: Not Running'))
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
            
            #this code repeated in lw-gui; put it in a function somewhere
            c = wmi.WMI()
            networkAdapters = c.Win32_NetworkAdapter(PhysicalAdapter=True)
            
            guidDict={}
            for ad in networkAdapters:
                guidDict[ad.Name] = ad.GUID
                
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
            if event.InstanceName in guidDict.keys() and \
                guidDict[event.InstanceName] in fileconfig.config.get('TRIGGERS','adapterConGUIDS').split(';'):
                eventHandle('E_NET_CABLE_IN',"net adapter '%s' gained connection"%event.InstanceName)    
            
        CoUninitialize()
        eventQueue.put(("Status",'netAdaptersIn','Connect: Not Running')) 
    def terminate(self):
        self.running = False        

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
            eventQueue.put(("Log","Can't bind socket 22190. Is another lockwatcher running?"))
            print('Camera listen exception: %s'%sys.exc_info()[0])
            return
        
        eventQueue.put(("Status",'cameras',"Active"))

        self.running = True
        while self.running == True:
            try:
                data = s.recv(16)
            except socket.error:
                if self.running == False: break
                print('socket error.. rebinding and trying')
                s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                s.bind( ('127.0.0.1', 22190) )
                continue
            
            data = data.decode('UTF-8')
            
            if data == '1': eventHandle('E_CHASSIS_MOTION',"Chassis camera motion detected") 
            elif data == '2': eventHandle('E_ROOM_MOTION',"Room camera motion detected") 
                        
        eventQueue.put(("Status",'cameras',"Not Running"))   
    def terminate(self):
        self.running = False 
        self.socket.shutdown(socket.SHUT_RD)
        self.socket.close()
   
#listen on port 22191, receive commands from from config programs
class configMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'ConfigMonitor'
    def run(self):
        try:
            s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            s.bind( ('127.0.0.1', 22191) )
            self.socket = s
        except:
            eventQueue.put(("Log","Can't bind socket 22191"))
            return
        
        self.running = True
        while self.running == True:
            try:
                ready = select.select([s],[],[],120)
                if not ready[0]: continue
            except socket.error:
                if self.running == False: break
                debugLog('Socketerror in configmonitor %s'%str(sys.exc_info()))
    
                try:
                    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                    s.bind(('127.0.0.1', 22191))
                    self.socket = s
                except:
                    debugLog('Socketerror in configmonitor rebinding.. %s'%str(sys.exc_info()))
                
                continue
            
            data = s.recv(1024)
            command = data.decode('UTF-8')             
            plog('In confmon: '+str(command))
            if ':' in command: 
                command,value = command.split(':')
            else: value = None
            
            if command == 'newListener' and value != None:
                eventQueue.put(('newListener',value))
            elif command == 'getStatuses':
                eventQueue.put(('getStatuses',None))
            elif command == 'startMonitor' or command == 'stopMonitor':
                eventQueue.put((command,value))
            elif command == 'reloadConfig':
                eventQueue.put(('reloadConfig',None))
            else:
                eventQueue.put(('Log','Bad local command received: %s'%command))
       
    def terminate(self):
        self.running = False
        if self.socket != None:
            try:
                self.socket.shutdown(socket.SHUT_RD)
            except:
                pass
            self.socket.close()


#monitor for killswitch keypresses
class keyboardMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'KeyboardMonitor'
    def run(self):  
        
        version = sys.getwindowsversion()
        if version.major == 6 and version.minor > 1:
            eventQueue.put(("Status",'killSwitch',"Error: Win8 Not Supported"))
            return
            
        keyQueue = Queue.Queue()
        self.interceptListener = hardwareconfig.interceptListenThread(keyQueue)
        self.interceptListener.start()
        
        self.reloadKeys = True
        self.running = True
        eventQueue.put(("Status",'killSwitch',"Active"))
        while self.running == True:
            if self.reloadKeys == True:
                primaryKillKeys = {}
                for key in fileconfig.config.get('TRIGGERS','kbd_kill_combo_1',0).split('+'):
                    if key == '': break
                    primaryKillKeys[int(key)] = False
                    
                
                secondaryKillKeys = {}
                for key in fileconfig.config.get('TRIGGERS','kbd_kill_combo_2').split('+'):
                    if key == '': break
                    secondaryKillKeys[int(key)] = False
                self.reloadKeys = False
        
            try:
                eventType,eventDetails = keyQueue.get(True,1)
            except: 
                if self.running == False: break
                continue
            
            if eventType == 'mouse':
                if eventDetails == 'Moved':
                    eventHandle('E_MOUSE_MOVE',"Mouse moved")
                elif eventDetails == 'Button':
                    eventHandle('E_MOUSE_BTN',"Mouse button pressed")
                continue
            else:      
                key = eventDetails[0]
        
            if key in primaryKillKeys.keys(): 
                primaryKillKeys[key] = eventType
            if key in secondaryKillKeys.keys(): 
                secondaryKillKeys[key] = eventType

            if len(primaryKillKeys.keys()) > 0:
                for keyState in primaryKillKeys.values():
                    if keyState == False: break
                else:
                    eventHandle('E_KILL_SWITCH_1',"Kill switch 1 pressed")
                    
            if len(secondaryKillKeys.keys()) > 0:        
                for keyState in secondaryKillKeys.values():
                    if keyState == False: break 
                else: eventHandle('E_KILL_SWITCH_2',"Kill switch 2 pressed")
                            
        eventQueue.put(("Status",'killSwitch',"Not Running"))
        
    def reloadConfig(self):
        self.reloadKeys = True
    
    def terminate(self):
        self.running = False
        self.interceptListener.stop()

def isRunning(threadName,threadDict):
    if threadName in threadDict.keys() and \
        threadDict[threadName] != None and \
            threadDict[threadName].is_alive() == True:
                return True
    else: return False
      

REMOTE_LOCK = 1
REMOTE_STARTMONITOR = 2
REMOTE_STOPMONITOR = 3
REMOTE_SHUTDOWN = 4
REMOTE_KILLSWITCH = 5
commandList = range(REMOTE_LOCK,REMOTE_KILLSWITCH+1)

def executeRemoteCommand(command):
    if command == REMOTE_LOCK:
        if hardwareconfig.checkLock() == False:
            AFroutines.lockScreen()
            result = sendemail.sendEmail("Command successful","Screen locked")
            eventQueue.put(("Log",'Screen locked due to remote command'))
        else:
            eventQueue.put(("Log",'Lock screen failed - command received while locked'))
            result = sendemail.sendEmail("Command failed","Screen already locked")
            
        if result != True:
            eventQueue.put(('Log','Mail send failed: %s'%result))
            
    elif command == REMOTE_STARTMONITOR:
        #cant check ispy camera status, just have to assume it was not monitoring
        iSpyPath = fileconfig.config.get('TRIGGERS','ispy_path')
        roomCamID = fileconfig.config.get('TRIGGERS','room_cam_id')
        if os.path.exists(iSpyPath):
            eventQueue.put(("Log","Starting room camera due to remote command"))
        else:
            eventQueue.put(("Log","iSpy executable not found - cannot fulfill remote command"))
            return
        
        subprocess.call([iSpyPath,'commands bringonline,2,%s'%roomCamID])
        result = sendemail.sendEmail("Command successful","Movement monitoring initiated. Have a nice day.")
        if result != True:
            eventQueue.put(('Log','Mail send failed: %s'%result))
        
        
    elif command == REMOTE_STOPMONITOR:
        #cant check ispy camera status, just have to assume it was already monitoring
        iSpyPath = fileconfig.config.get('TRIGGERS','ispy_path')
        roomCamID = fileconfig.config.get('TRIGGERS','room_cam_id')
        if os.path.exists(iSpyPath):
            eventQueue.put(("Log","Stopping room camera due to remote command"))
        else:
            eventQueue.put(("Log","iSpy executable not found - cannot fulfill remote command"))
            return
            
        subprocess.call([iSpyPath,'commands takeoffline,2,%s'%roomCamID])
        result = sendemail.sendEmail("Command successful","Movement monitoring disabled. Welcome home!")
        if result != True:
            eventQueue.put(('Log','Mail send failed: %s'%result))
        
    elif command == REMOTE_SHUTDOWN:
        result = sendemail.sendEmail("Command successful","Shutting down...")
        if result != True:
            eventQueue.put(('Log','Mail send failed: %s'%result))
        eventQueue.put(("Log","Initiating standard shutdown due to remote command"))
        AFroutines.standardShutdown()
        
    elif command == REMOTE_KILLSWITCH:
        AFroutines.emergency()

#this is a travesty
trigMonitorMap = {'bluetooth': 'BTMonitor',
                'killSwitch' : 'keyboardMonitor',
                'ram' : 'RAMMonitor',
                'cameras': 'cameraMonitor',
                'devices': 'deviceMonitor',
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
                'cameras' : 'E_CHASSIS_MOTION',
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
                
            elif trigger == 'E_CHASSIS_MOTION' or trigger == 'E_ROOM_MOTION':
                if 'cameraMonitor' not in threadDict.keys() or threadDict['cameraMonitor'] == None:
                    threadDict['cameraMonitor'] = cameraMonitor()  
                    threadDict['cameraMonitor'].start()   

            elif 'E_KILL_SWITCH' in trigger:
                if 'keyboardMonitor' not in threadDict.keys() or threadDict['keyboardMonitor'] == None:
                    threadDict['keyboardMonitor'] = keyboardMonitor()
                    threadDict['keyboardMonitor'].start()
                    
            elif trigger == 'email':
                threadDict['email'] = emailMonitor()    
                threadDict['email'].start()
            else:
                eventQueue.put(("Log","Error: Startmonitor passed unknown trigger: %s"%trigger))

#send message to every connected listener
def broadcast(listeners,msg):
    badConnections = []
    msg = msg+'@@'
    for connection in listeners:
        try:
            connection.send(msg.encode())
            #print('lw service sent %s'%msg.encode())
        except: 
            badConnections.append(connection)
    
    for connection in badConnections:
        listeners.remove(connection)

def addLogEntry(msg,listeners):
    entry = time.strftime('[%x %X] ')+msg+'\n'
    logPath = fileconfig.config.get('TRIGGERS','logfile')
    try:
        fd = open(logPath,'a+')
        fd.write(entry) 
        fd.close()
    except:
        servicemanager.LogErrorMsg(entry)
    
    broadcast(listeners,'Log::'+entry)   
    
class lockwatcher(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'Lockwatcher'
    def run(self):
        
        plog('Lockwatcher Started')
        global startupTime 
        startupTime = time.time()
        
        #send log/status updates to connections in here - for config programs
        listeners = []
        
        confMonThread = configMonitor()
        confMonThread.start()
        
        LOCKED = fileconfig.config.get('TRIGGERS','lockedtriggers').split(',')
        ALWAYS = fileconfig.config.get('TRIGGERS','alwaystriggers').split(',')
        ACTIVE = LOCKED+ALWAYS
        
        global eventQueue
        eventQueue = Queue.Queue()

        threadStatuses = {}
        threadDict = {}
        
        for trigger in ACTIVE:
            if trigger != '': startMonitor(threadDict,trigger)

        if fileconfig.config.get('EMAIL','ENABLE_REMOTE') == 'True':
            startMonitor(threadDict,'email')
        
        
        #new month, new log
        logPath = fileconfig.config.get('TRIGGERS','logfile')
        if os.path.exists(logPath):
            creationTime = time.ctime(os.path.getctime(logPath))
            creationMonth = datetime.datetime.strptime(creationTime, "%a %b %d %H:%M:%S %Y")
            monthNow = time.strftime('%m %Y')
            if creationMonth != monthNow:
                try:
                    open(logPath, 'w').close()
                except: pass
                    
        eventQueue.put(('Log','Lockwatcher monitoring started'))
        
        badCommands = 0
        shutdownActivated = False
        while True:
            event = eventQueue.get(block=True, timeout=None)
            plog('In eventq: '+str(event))
            eventType = event[0]
            
            #--------------trigger activated under shutdown conditions
            if eventType == 'Kill':
                eventReason = event[1]
                #don't trigger multiple shutdowns but keep logging while we can
                if shutdownActivated == False: 
                    shutdownActivated = True
                    
                    if fileconfig.config.get('EMAIL','email_alert') == 'True' and \
                        'Kill switch' not in eventReason:
                        try:
                            #has a 4 second timeout for blocking operations
                            result = sendemail.sendEmail('Emergency shutdown triggered',eventReason)
                            if result != True:
                                eventQueue.put(('Log','Mail send failed: %s'%result))
                        except:
                            pass #email failed, oh well. 
                    AFroutines.emergency()
            
            #--------------thread status changed, inform any listeners        
            elif eventType == 'Status':
                #if self.statuses != None: self.statuses[event[1]].set(event[2])
                threadStatuses[event[1]] = event[2]
                msg = 'Status::%s::%s'%(event[1],event[2])
                broadcast(listeners,msg)
                
            #-----------config programs can request all the current statuses
            elif eventType == 'getStatuses':
                msg = 'AllStatuses::'
                for name,value in threadStatuses.items():
                    msg = msg+ '%s::%s|'%(name,value)
                msg = msg[:-1]
                
                broadcast(listeners,msg)
            
            #--------------add to log file + listener log window if they exist
            elif eventType == 'Log':
                #if self.msgAdd != None: self.msgAdd(event[1])
                addLogEntry(str(event[1]),listeners)
                
            elif eventType == 'stop':
                broadcast(listeners,'Shutdown')
                for threadname in threadDict.keys():
                    if isRunning(threadname,threadDict): threadDict[threadname].terminate()
                confMonThread.terminate()
                time.sleep(1) #give threads time to shutdown
                return
            
            elif eventType == 'startMonitor':
                monitor=event[1]
                if monitor in trigMonitorMap.keys():
                    thread = trigMonitorMap[monitor]
                else: continue
                if not isRunning(thread,threadDict): startMonitor(threadDict,trigEventMap[monitor])
            
            elif eventType == 'stopMonitor':
                monitor = event[1]
                
                if monitor == 'devices':
                    threadnames = ['deviceMonitor','volumeMonitor',
                                   'logicalDiskRemoveMonitor','logicalDiskCreateMonitor']
                else:
                    threadnames = [trigMonitorMap[monitor]]
                    
                for threadname in threadnames:
                    if isRunning(threadname,threadDict):
                        threadDict[threadname].terminate()
                        threadDict[threadname] = None
            
            elif eventType == 'Mail':
                #malformed emails would be a good way of crashing lockwatcher
                #be careful to valididate mail here
                validMail = True
                try:
                    command, code = event[1].split(' ')
                    eventQueue.put(('Log','Received mail "%s %s"'%(command,code)))
                except:
                    validMail = False
                    
                #forgive bad command codes - crappy attack and causes
                #loop if we look at our returned emails with same sender/recv addresss
                if validMail == True:
                    try: 
                        command = int(command)
                        if command not in commandList:
                            continue
                    except:
                        continue
                    
                if validMail == True and sendemail.validHMAC(code,command) == True:
                    executeRemoteCommand(command) 
                    badCommands = 0 #good command resets limit
                else:
                    badCommands += 1
                    result = sendemail.sendEmail("Command failed","Bad command or authentication code received: %s"%str(event[1]))
                    if result != True:
                        eventQueue.put(('Log','Mail send failed: %s'%result))
                    eventQueue.put(('Log','Mail not authenticated or bad command: %s'%str(event[1])))
                    badCommandLimit = int(fileconfig.config.get('EMAIL','BAD_COMMAND_LIMIT'))
                    if badCommandLimit > 0 and badCommands >= badCommandLimit:
                        addLogEntry(str(event[1]),listeners)
                        
                        if shutdownActivated == False:
                            shutdownActivated = True
                            AFroutines.emergency()
                            
                    continue
            elif eventType == 'reloadConfig':
                fileconfig.reloadConfig()
                if isRunning('keyboardMonitor',threadDict): threadDict['keyboardMonitor'].reloadConfig()
                #eventQueue.put(('Log','Config reload forced'))  #debugmode
                
            elif eventType == 'newListener':
                port = int(event[1])
                s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                eventQueue.put(('Log','Lockwatcher connected to new configuration client'))
                try:
                    s.connect( ('127.0.0.1', port) )
                except: 
                    eventQueue.put(('Log','Error: Failed to connect to client port: '+str(port)))
                    continue
                
                s.send(b'True@@')
                listeners.append(s)
                
            else:
                eventQueue.put(('Log','Error: Unknown event in queue: '+str(event)))
                
    def stop(self,msg=None):
        if msg != None: eventQueue.put(('Log',msg))
        eventQueue.put(('stop',None))
        
                
monitorThread = None
def createLockwatcher():
    global monitorThread
        
    monitorThread = lockwatcher()
    
import cx_Logging #including here so cx_Freeze adds the .pyd for sm.exe to use
import servicemanager
 
class lockwatcherSvc (object):
    def __init__(self):
        socket.setdefaulttimeout(60.0)
        self.running = True
        
    def Initialize(self, configFileName):
        pass

    def SessionChanged(self, sessionID, event_type):
        SESSION_LOCK = 0x7
        SESSION_UNLOCK = 0x8
        
        if event_type == SESSION_LOCK:
                hardwareconfig.lockState = True
        elif event_type == SESSION_UNLOCK:
                hardwareconfig.lockState = False
        else: return
            
    def Stop(self):
        monitorThread.stop('Service Stop')

    def Run(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              ('Lockwatcher',''))
        plog('starting service: Run')
        try:
            self.main()
        except:
            debugLog('EXCEPTION %s in main'%str(sys.exc_info()[0]))

    def main(self):
        createLockwatcher()
        monitorThread.start()
        while monitorThread.is_alive() == True:
            time.sleep(2) 

def plog(sf):
        try:
            fd = open('c:\loglock.txt','a+')
            fd.write(time.strftime('[%x %X] ')+str(sf)+'\n') 
            fd.close()
        except:
            pass