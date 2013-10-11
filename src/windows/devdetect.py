'''
devdetect.py

Runs a group of threads which monitor for potential forensic-related system events
and trigger the antiforensic module if the screen is locked

@author: Nia Catlin
'''

import AFroutines
import fileconfig, hardwareconfig, sendemail, winsockbtooth

import threading, queue, subprocess
import select
import os,time,datetime
import imapclient
import wmi, win32timezone #cx_freeze doesn't seem to get this unless imported explicitly
from pythoncom import CoInitialize, CoUninitialize

eventQueue = None
allStop = False

lockedStateText = {True:'Locked',False:'Not Locked'}
#trigger events go here to be checked for activation conditions
def eventHandle(event_type,eventReason):
    locked = hardwareconfig.checkLock()
    
    if (event_type in fileconfig.config['TRIGGERS']['ALWAYSTRIGGERS'].split(',')) or \
        (event_type in fileconfig.config['TRIGGERS']['LOCKEDTRIGGERS'].split(',') and locked == True):
        eventQueue.put(("Log","[%s - *Trigger activated*]. %s"%(lockedStateText[locked],eventReason)))
        eventQueue.put(("Kill",eventReason))
    else:
        '''log the ignored trigger (but not the 2nd killswitch because a logfile containing
        every press of the letter 'p' is going to be a mess)'''
        if event_type != 'E_KILL_SWITCH_2':
            eventQueue.put(("Log","[%s - Trigger ignored]. %s"%(lockedStateText[locked],eventReason)))
    
#running as a service makes exception handling more difficult
#write log directly instead of relying on eventqueue processing    
def debugLog(msg):
    logPath = fileconfig.config['TRIGGERS']['logfile']
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
    server = imapclient.IMAPClient(fileconfig.config['EMAIL']['email_imap_host'], use_uid=False, ssl=True)
    server.login(fileconfig.config['EMAIL']['email_username'], fileconfig.config['EMAIL']['email_password'])
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
        self.running = True
        while self.running == True:
            #refresh the connection every 14 mins so it doesnt timeout
            try:
                seqid = server.idle_check(840)
            except ValueError:
                if self.running == False: #terminate() was called
                    eventQueue.put(("Status",'email','Not Running')) 
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
            addressee = keys[2][0][2]
            intendedAddressee = fileconfig.config['EMAIL']['command_email_address'].split('@')[0]
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
        eventQueue.put(("Status",'bluetooth','Connecting to device...'))

        deviceIDStr = fileconfig.config['TRIGGERS']['bluetooth_device_id']
        deviceID = hardwareconfig.BTStrToHex(deviceIDStr)
        
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
        eventQueue.put(("Status",'netAdaptersIn','Connect: Not Running')) 
    def terminate(self):
        self.running = False        

#detect new network cable inserted
import socket,sys
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
            
            if data == '1':
                    if fileconfig.isActive('E_CHASSIS_MOTION')[0] != 'False':
                        eventHandle('E_CHASSIS_MOTION',"Chassis camera motion detected") 
                        
            elif data == '2':
                    if fileconfig.isActive('E_ROOM_MOTION')[0] != 'False':
                        eventHandle('E_ROOM_MOTION',"Room camera motion detected") 
                        
        eventQueue.put(("Status",'cameras',"Not Running"))   
    def terminate(self):
        self.running = False 
        self.socket.shutdown(socket.SHUT_RD)
        self.socket.close()
   
#receive commands from from config programs
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
            
            if ':' in command: 
                command,value = command.split(':')
            else: value = None
            
            if command == 'newListener' and value != None:
                eventQueue.put(('newListener',value))
            elif command == 'getStatuses':
                eventQueue.put(('getStatuses',None))
            elif command == 'startMonitor' or command == 'stopMonitor':
                eventQueue.put((command,value))
       
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
        primaryKillKeys = {}
        for key in fileconfig.config['TRIGGERS']['kbd_kill_combo_1'].split('+'):
            primaryKillKeys[int(key)] = False
            
        secondaryKillKeys = {}
        for key in fileconfig.config['TRIGGERS']['kbd_kill_combo_2'].split('+'):
            secondaryKillKeys[int(key)] = False
        
        keyQueue = queue.Queue()
        self.hookListener = hardwareconfig.kbdHookListenThread(keyQueue)
        self.hookListener.start()
        self.interceptListener = hardwareconfig.interceptListenThread(keyQueue)
        self.interceptListener.start()
        
        self.running = True
        eventQueue.put(("Status",'killSwitch',"Active"))
        while self.running == True:
            try:
                eventType,eventDetails = keyQueue.get(True,1)
            except: 
                if self.running == False: break
                continue
            
            key = eventDetails[0]

            if key in primaryKillKeys.keys(): 
                primaryKillKeys[key] = eventType
            if key in secondaryKillKeys.keys(): 
                secondaryKillKeys[key] = eventType

            for keyState in primaryKillKeys.values():
                if keyState == False: break
            else:
                eventHandle('E_KILL_SWITCH_1',"Kill switch 1 pressed")
                    
            for keyState in secondaryKillKeys.values():
                if keyState == False: break 
            else: eventHandle('E_KILL_SWITCH_2',"Kill switch 2 pressed")
                            
        eventQueue.put(("Status",'killSwitch',"Not Running"))
    def terminate(self):
        self.running = False
        self.hookListener.stop()
        self.interceptListener.stop()
        

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
            sendemail.sendEmail("Command successful","Screen locked")
        else:
            eventQueue.put(("Log",'Lock screen failed - command received while locked'))
            sendemail.sendEmail("Command failed","Screen already locked")
            
    elif command == REMOTE_STARTMONITOR:
        #cant check ispy camera status, just have to assume it was not monitoring
        iSpyPath = fileconfig.config['TRIGGERS']['ispy_path']
        roomCamID = fileconfig.config['TRIGGERS']['room_cam_id']
        eventQueue.put(("Log","Starting room camera after remote command"))
        subprocess.call([iSpyPath,'commands bringonline,2,%s'%roomCamID])
        sendemail.sendEmail("Command successful","Movement monitoring initiated. Have a nice day.")
        
        
    elif command == REMOTE_STOPMONITOR:
        #cant check ispy camera status, just have to assume it was already monitoring
        iSpyPath = fileconfig.config['TRIGGERS']['ispy_path']
        roomCamID = fileconfig.config['TRIGGERS']['room_cam_id']
        eventQueue.put(("Log","Stopping room camera after remote command"))
        subprocess.call([iSpyPath,'commands takeoffline,2,%s'%roomCamID])
        sendemail.sendEmail("Command successful","Movement monitoring disabled. Welcome home!")
        
    elif command == REMOTE_SHUTDOWN:
        sendemail.sendEmail("Command successful","Shutting down...")
        eventQueue.put(("Log","Initiating standard shutdown after remote command"))
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
    msg = msg+'@'
    for connection in listeners:
        try:
            connection.send(msg.encode())
            #print('lw service sent %s'%msg.encode())
        except: 
            badConnections.append(connection)
    
    for connection in badConnections:
        listeners.remove(connection)
             

class lockwatcher(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'Lockwatcher'
    def run(self):
        
        #send log/status updates to connections in here - for config programs
        listeners = []
        
        
        cmon = configMonitor()
        cmon.start()
        
        LOCKED = fileconfig.config['TRIGGERS']['lockedtriggers'].split(',')
        ALWAYS = fileconfig.config['TRIGGERS']['alwaystriggers'].split(',')
        ACTIVE = LOCKED+ALWAYS
        
        global eventQueue
        eventQueue = queue.Queue()
        
        threadStatuses = {}
        threadDict = {}
        
        for trigger in ACTIVE:
            if trigger != '': startMonitor(threadDict,trigger)

        if fileconfig.config['EMAIL']['ENABLE_REMOTE'] == 'True':
            startMonitor(threadDict,'email')
        
        
        #new month, new log
        logPath = fileconfig.config['TRIGGERS']['logfile']
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
            eventType = event[0]
            
            #--------------trigger activated under shutdown conditions
            if eventType == 'Kill':
                eventReason = event[1]
                #don't trigger multiple shutdowns but keep logging while we can
                if shutdownActivated == False: 
                    shutdownActivated = True
                    
                    if fileconfig.config['EMAIL']['email_alert'] == 'True' and \
                        'Kill switch' not in eventReason:
                        try:
                            #has a 4 second timeout for blocking operations
                            sendemail.sendEmail('Emergency shutdown triggered',eventReason)
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
                
                entry = time.strftime('[%x %X] ')+event[1]+'\n'
                logPath = fileconfig.config['TRIGGERS']['logfile']
                try:
                    fd = open(logPath,'a+')
                    fd.write(entry) 
                    fd.close()
                except:
                    servicemanager.LogErrorMsg(event[1])
                
                broadcast(listeners,'Log::'+entry)
                
            elif eventType == 'stop':
                broadcast(listeners,'Shutdown')
                for thread in threadDict.values():
                    if thread == None: continue
                    if thread.is_alive(): 
                        thread.terminate()
                cmon.terminate()
                time.sleep(1) #give threads time to shutdown
                return
            
            elif eventType == 'startMonitor':
                monitor=event[1]
                thread = trigMonitorMap[monitor]
                if thread not in threadDict.keys() or threadDict[thread] == None or \
                    threadDict[thread].is_alive() == False:
                    startMonitor(threadDict,trigEventMap[monitor])
            
            elif eventType == 'stopMonitor':
                monitor = event[1]
                
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
                    sendemail.sendEmail("Command failed","Bad command or authentication code received: %s"%str(event[1]))
                    eventQueue.put(('Log','Mail not authenticated or bad command: %s'%str(event[1])))
                    badCommandLimit = int(fileconfig.config['EMAIL']['BAD_COMMAND_LIMIT'])
                    if badCommandLimit > 0 and badCommands >= badCommandLimit:
                        #todo: fixme
                        self.msgAdd('Emergency shutdown: Too many bad remote commands')
                        
                        if shutdownActivated == False:
                            AFroutines.emergency()
                            
                    continue
            elif eventType == 'reloadConfig':
                fileconfig.loadConfig()     
                eventQueue.put(('Log','Configreload forced'))  #debugmode
                
            elif eventType == 'newListener':
                port = int(event[1])
                s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                eventQueue.put(('Log','Lockwatcher connected to new configuration client'))
                try:
                    s.connect( ('127.0.0.1', port) )
                except: 
                    eventQueue.put(('Log','Error: Failed to connect to client port: '+str(port)))
                    continue
                
                s.send(b'True@')
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
    
    
import win32serviceutil
import win32service
import win32event
import servicemanager   

def plog(sf):
        fd = open(fileconfig.config['TRIGGERS']['logfile'],'a+')
        fd.write(time.strftime('[%x %X] ')+str(sf)+'\n') 
        fd.close()

class lockwatcherSvc (win32serviceutil.ServiceFramework):
    _svc_name_ = "LockWatcherSvc"
    _svc_display_name_ = "Lockwatcher"

    def __init__(self,args):
        win32serviceutil.ServiceFramework.__init__(self,args)
        self.hWaitStop = win32event.CreateEvent(None,0,0,None)
        socket.setdefaulttimeout(60)
        self.running = True
        
    def GetAcceptedControls(self):
        # Accept SESSION_CHANGE control
        rc = win32serviceutil.ServiceFramework.GetAcceptedControls(self)
        rc |= win32service.SERVICE_ACCEPT_SESSIONCHANGE
        return rc


    def SvcOtherEx(self, control, event_type=None, data=None):
        # This is only showing a few of the extra events - see the MSDN
        # docs for "HandlerEx callback" for more info.
        '''
        if control == win32service.SERVICE_CONTROL_SESSIONCHANGE:
            sess_id = data[0]
            msg = "Other session event: type=%s, sessionid=%s\n" % (event_type, sess_id)
            
        '''
        SESSION_LOCK = 0x7
        SESSION_UNLOCK = 0x8
        
        if control == 14: #session_change
            if event_type == SESSION_LOCK:
                hardwareconfig.lockState = True
            elif event_type == SESSION_UNLOCK:
                hardwareconfig.lockState = False
            else: return
            
        elif control == 1: 
            self.SvcStop()
            
        else:
            fd = open(fileconfig.config['TRIGGERS']['logfile'],'a+')
            fd.write(time.strftime('[%x %X]')+ 'unknown event %s %s %s\n'%(control, event_type,data)) 
            fd.close()
            
    def SvcStop(self):
        #self.running = False
        monitorThread.stop('Service Stop')
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        self.ReportServiceStatus(win32service.SERVICE_RUNNING)
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_,''))

        try:
            self.main()
        except:
            debugLog('EXCEPTION %s in main'%str(sys.exc_info()[0]))

    def main(self):
        createLockwatcher()
        monitorThread.start()
        while monitorThread.is_alive() == True:
            time.sleep(2)

#uninstalls and reinstalls service
#call with False to just uninstall
def installService(install=True):
    
        cls = lockwatcherSvc
        try:
            win32serviceutil.RemoveService( cls._svc_name_)
        except: pass
        
        if install == True:
            serviceName = cls._svc_name_
            serviceDisplayName = cls._svc_display_name_
            serviceClassString = win32serviceutil.GetServiceClassString(cls)
                
            win32serviceutil.InstallService(serviceClassString, serviceName, serviceDisplayName, 
                                            startType=win32service.SERVICE_DEMAND_START,  
                                            exeName='pythonservice.exe', description='Monitors for possible tampering and reacts accordingly')
