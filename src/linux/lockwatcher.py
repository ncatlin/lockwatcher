#!/usr/bin/python3
'''
lockwatcher.py
@author: Nia Catlin

Runs a group of threads which monitor for potential forensic-related system events
and trigger the antiforensic module if appropriate

Requires 'motion' and 'ifplugd' to be running and properly configured
to use the motion and network connection triggers
'''

import os, sys, inspect
cmd_folder = os.path.realpath(os.path.abspath(os.path.split(inspect.getfile( inspect.currentframe() ))[0]))
if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

cmd_subfolder = os.path.realpath(os.path.abspath(os.path.join(os.path.split(inspect.getfile( inspect.currentframe() ))[0],"lib")))
if cmd_subfolder not in sys.path:
    sys.path.insert(0, cmd_subfolder)
    
import multiprocessing
import threading, queue, struct
import subprocess,time
import dbus, signal, socket
import pyudev, sensors #bastien leonards pysensors 
import imapclient, sendemail
from sendemail import sendEmail,validHMAC
import syslog, datetime

from gi.repository import GObject
from pwd import getpwnam
import dbus
from dbus.mainloop.glib import DBusGMainLoop

import fileconfig, AFroutines, hardwareconfig
from fileconfig import config

from daemon import daemon

DAEMONPORT = int(fileconfig.config['TRIGGERS']['daemonport'])

eventQueue = queue.Queue()

lockedStateText = {True:'Locked',False:'Not Locked'}
def eventHandle(event_type,eventReason):
    locked = hardwareconfig.checkLock()

    if (event_type in fileconfig.config['TRIGGERS']['ALWAYSTRIGGERS'].split(',')) or \
        (event_type in fileconfig.config['TRIGGERS']['LOCKEDTRIGGERS'].split(',') and locked == True):
        eventQueue.put(("log","[%s - Trigger %s activated]: %s"%(lockedStateText[locked],event_type,eventReason)))
        eventQueue.put(("kill",event_type,eventReason))
    else:
        eventQueue.put(("log","[%s - Trigger %s (ignored)]: %s"%(lockedStateText[locked],event_type,eventReason)))

def device_changed(action,device):
    eventHandle('E_DEVICE',"Device event trigger. Device: %s, Event: %s"%(device,action))


#------------------------------------------------------------------
lockQueue = None
def scrnLocked(state):
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(('127.0.0.1',DAEMONPORT))
    if state == 1:s.send(b'True')
    else: s.send(b'False')

#cannot interact with user screen as root,
#make new process to do it
def lockMonitorProcess(uid,q):
        if os.getuid()==0:
            os.setuid(uid)

        #this isnt great, there are a few different lock implementations floating around
        #lubuntu switching from xscreensaver-command to lightdm from locking next release
        if fileconfig.DBUSSUPPORTED == True:
            session_bus = dbus.SessionBus(mainloop=DBusGMainLoop())
            #subscribe to kde and gnome lock notification signals
            session_bus.add_signal_receiver(scrnLocked,'ActiveChanged','org.freedesktop.ScreenSaver')
            session_bus.add_signal_receiver(scrnLocked,'ActiveChanged','org.gnome.ScreenSaver')
            GObject.MainLoop().run()
        else:
            if fileconfig.config['TRIGGERS']['DESKTOP_ENV'] == 'LXDE':
                try:
                    currentState = ('locked' in str(subprocess.check_output(["/usr/bin/xscreensaver-command", "-time"])))
                except subprocess.CalledProcessError:
                    eventQueue.put(('log',"Screen status not set - lock screen once before running lockwatcher"))
                    currentState = False
                    
                while True:
                    time.sleep(1)
                    
                    try:
                        outp = subprocess.check_output(["/usr/bin/xscreensaver-command", "-time"])
                    except subprocess.CalledProcessError:
                        continue
                    
                    if 'locked' in str(outp):
                        if currentState == False:
                            currentState = True
                            scrnLocked(1)
                    else:
                        if currentState == True:
                            currentState = False
                            scrnLocked(0)  
                            
#-------------------------------------------------------------------------------
                         
monitoringRoom = False
class IPCMonitor(threading.Thread):
    def __init__(self,user):
        threading.Thread.__init__(self)
        self.name = "IPCMonThread"
        self.user = user
        self.listenSocket = None
        self.lockProcess = None
        
    def run(self):
        #start lock monitor process
        lockQueue = multiprocessing.Queue()
        p = multiprocessing.Process(target=lockMonitorProcess,args=(self.user,lockQueue))
        p.daemon = True
        p.start()
        self.lockProcess = p
        try:
            self.listenSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.listenSocket.bind(('127.0.0.1',DAEMONPORT))
        except:
            eventQueue.put(('log','Could not bind to 127.0.0.1:%s, please kill any other lockwatchers and try again'%DAEMONPORT))
            eventQueue.put(('status','ipc','Error: Lockwatcher already running'))
            eventQueue.put(('stop',None))
            return
        
        eventQueue.put(('status','ipc','Active'))
        
        self.running = True
        while self.running == True:
            try:
                ready = select.select([self.listenSocket],[],[],120)
                if not ready[0]: continue
            except socket.error:
                if self.running == False: break
                    
                try:
                    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                    s.bind(('127.0.0.1', DAEMONPORT))
                    self.listenSocket = s
                except: pass
                continue
            
            data = self.listenSocket.recv(1024)
            command = data.decode('UTF-8')  
            
            if ':' in command: 
                command,value = command.split(':')
            else: value = None
            
            if command == 'LockTrue': 
                eventQueue.put(('lock',True))
            elif command == 'LockFalse': 
                eventQueue.put(('lock',False))
            elif command == 'newListener' and value != None:
                eventQueue.put(('newListener',value))
            elif command == 'getStatuses':
                eventQueue.put(('getStatuses',None))
            elif command == 'startMonitor' or command == 'stopMonitor':
                eventQueue.put((command,value))
            elif command == 'reloadConfig':
                eventQueue.put(('reloadConfig',None))
            elif command == 'stop':
                eventQueue.put(('stop',None))
            else:
                eventQueue.put(('log','Bad local command received: %s'%command))
            
                
        eventQueue.put(('status','ipc','Not Running'))
                
    def stop(self):
        self.lockProcess.terminate()
        self.running = False
        try:
            self.listenSocket.shutdown(socket.SHUT_RD)
        except OSError:
            pass #107 endpoint not connected, but socket still gets shutdown so ignore it
        
class netcableMonitor(threading.Thread):
    def __init__(self):  
        threading.Thread.__init__(self)
        self.name = "netadapters"
    def run(self):
        monitorUpAdapters = {}
        for iface in fileconfig.config['TRIGGERS']['adapterconids'].split(','):
            monitorUpAdapters[iface] = None
        
        monitorDownAdapters = {}
        for iface in fileconfig.config['TRIGGERS']['adapterdisconids'].split(','):
            monitorDownAdapters[iface] = None
                
        #todo: tests etc
        
        out = subprocess.check_output(['/usr/sbin/ifplugstatus'])
        devString = out.decode("utf-8").strip('\n').split('\n')
        for dev in devString:
            devName,devStatus = dev.split(': ')
            if devName in monitorUpAdapters.keys():
                monitorUpAdapters[devName] = devStatus
            if devName in monitorDownAdapters.keys():
                monitorDownAdapters[devName] = devStatus

        self.running = True
        eventQueue.put(('status','netadapters',"Active"))
        while self.running == True:
            time.sleep(1)
            out = subprocess.check_output(['/usr/sbin/ifplugstatus'])
            devString = out.decode("utf-8").strip('\n').split('\n')
            for dev in devString:
                devName,devStatus = dev.split(': ')
                if devName in monitorUpAdapters.keys():
                    if monitorUpAdapters[devName] != devStatus:
                        if devStatus == 'link beat detected':
                            eventHandle('E_NETCABLE','%s: (%s->%s)'%(devName,monitorUpAdapters[devName],devStatus))
                        monitorUpAdapters[devName] = devStatus

                if devName in monitorDownAdapters.keys():
                    if monitorDownAdapters[devName] != devStatus:
                        if devStatus == 'unplugged':
                            eventHandle('E_NETCABLE','%s: (%s->%s)'%(devName,monitorUpAdapters[devName],devStatus))
                        monitorUpAdapters[devName] = devStatus      
        
        eventQueue.put(('status','netadapters',"Not Running"))     
         
    def stop(self):
        self.running = False               


#lack of access to DIMM SPD data means this only checks motherboard
class temperatureMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "TempMonThread"
        
        self.running = False
        for chip in sensors.get_detected_chips():
            if "acpi" in str(chip): break
        else:
            eventQueue.put(('log',"Could not read acpi bus: Temperature monitoring disabled"))
            eventQueue.put(('status','temperature',"Error: Could not read ACPI bus"))
            self.die = True
            return
        self.chip = chip
            
        for feature in chip.get_features():
            if 'Temperature' in str(feature): break
        else:
            eventQueue.put(('log',"Could not read temperature from acpi bus: Temperature monitoring disabled"))
            eventQueue.put(('status','temperature',"Error: Could not read temperature from ACPI"))
            return
            
        for subfeature in chip.get_all_subfeatures(feature):
            if 'input' in str(subfeature.name):break
        else: 
            eventQueue.put(('log',"Could not read input from ACPI temperature: Temperature monitoring disabled"))
            eventQueue.put(('status','temperature',"Error: Could not read input temperature from ACPI"))
            return
        
        self.subfeature = subfeature    
        self.running = True
      
    def run(self):
        if self.running == False: return
        
        eventQueue.put(('status','temperature',"Active"))
        while self.running == True:
            time.sleep(1)
            newTemp = self.chip.get_value(self.subfeature.number)
            if newTemp < fileconfig.config['TRIGGERS']['LOW_TEMP']: 
                eventHandle(('E_TEMPERATURE',"%s degrees C"%newTemp))
                
        eventQueue.put(('status','temperature',"Not running"))         
            
    def stop(self):
        self.running = False

#untested
'''
intrusionSwitchPath = '/sys/class/hwmon/hwmon*/device/intrusion0_alarm'
def intrusionSwitchStatus():
    try:
        fd = open(intrusionSwitchPath,'r')
        status = fd.read()
        fd.close()
    except:
        #if it was working when the process started then assume
        #any later problems are due to tampering
        return True 
    return status

#poll the chassis intrusion detection switch for activation
noSwitchNotified = False    
class intrusionMon(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self) 
        self.name = "IntrusionMonThread"

        self.die = False #prevents thread running if there are problems
        global noSwitchNotified 
        if noSwitchNotified == True:
            self.die = True
            return
        
        if not os.path.exists(intrusionSwitchPath) and noSwitchNotified == False:
            eventQueue.put(('log',"Error: No chassis intrusion detection switch found")) 
            noSwitchNotified = True
            self.die = True
            return
        
        #switch already triggered, try to reset it
        if intrusionSwitchStatus() != 0: 
            subprocess.Popen("echo 0 > %s"%intrusionSwitchPath,Shell=True)
            time.sleep(0.5)
            if intrusionSwitchStatus() != 0: 
                eventQueue.put(('log',"Error: Cannot reset an already triggered intrusion switch. Monitoring disabled."))
                self.die = True
                return
                
    def run(self):
        while self.die == False:
            time.sleep(1)
            if intrusionSwitchStatus != 0:
                eventHandle.put(('E_INTRUSION',None))
                
    def stop(self):
        self.die = True
'''                        
        
class bluetoothMon(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self) 
        self.name = "BluetoothMonThread"
        
    def run(self):
        
        BTDevID = fileconfig.config['TRIGGERS']['BLUETOOTH_DEVICE_ID']
        if BTDevID == '':
            eventQueue.put(('log',"Error: Bluetooth device not configured"))
            eventQueue.put(('status','bluetooth',"Error: Device not configured"))
            return
        
        try:
            self.s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.s.settimeout(50)
            self.s.connect((BTDevID,2))
        except:
            eventQueue.put(('log',"Error: Bluetooth connection to %s unavailable or unauthorised"%BTDevID))
            eventQueue.put(('status','bluetooth',"Error: Connection Failed"))
            return
        
        eventQueue.put(('status','bluetooth',"Active"))
        while self.running == True:
            try:
                self.s.recv(1024)
            except socket.timeout:
                pass
            except:
                if self.running == False: 
                    break
                    
                eventQueue.put(('log',"Bad connection to bluetooth device"))
                eventQueue.put(('status',"Error: Connection Lost"))
                eventHandle(('E_BLUETOOTH',None))
                time.sleep(20)
            
            self.s.close()
            self.s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.s.settimeout(600)
            self.s.connect((config['TRIGGERS']['BLUETOOTH_DEVICE_ID'],2)) #make this port configurable?
            
        eventQueue.put(('status','bluetooth',"Not running"))   
         
    def stop(self):
        self.running = False
        self.s.close()

def setupIMAP():
    server = imapclient.IMAPClient(config['EMAIL']['EMAIL_IMAP_HOST'], use_uid=False, ssl=True)
    server.login(config['EMAIL']['EMAIL_USERNAME'], fileconfig.config['EMAIL']['EMAIL_PASSWORD'])
    server.select_folder('INBOX')
    eventQueue.put(('log',"Established IMAP connection"))
    return server
            
class emailMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "mailMonThread"
        self.running = True
        
    def run(self):
        eventQueue.put(('status','email',"Connecting to server..."))
        
        try:
            server = setupIMAP()
        except socket.gaierror:
            eventQueue.put(('log',"Error: Could not connect to mail IMAP server, will not listen for remote commands"))
            eventQueue.put(("Status",'email',"Error: IMAP Connection Failed")) 
            return
        except imapclient.IMAPClient.Error as err:
            eventQueue.put(('log',"Error: Could not connect to mail IMAP server, will not listen for remote commands"))
            eventQueue.put(("Status",'email',err.args[0].decode()))
            return
        
        self.server = server
        self.server.idle()

        eventQueue.put(('status','email',"Active"))
        connectionFails = 0
        
        if self.running == False:
            eventQueue.put(("Status",'email','Not Running'))
        
        
        while self.running == True:
            #refresh the connection every 14 mins so it doesnt timeout
            try:
                seqid = self.server.idle_check(840)
            except ValueError:
                if self.running == False: #terminate() was called
                    eventQueue.put(("Status",'email','Not Running')) 
                    return
                
            if seqid == []: #no mail
                try:
                    self.server.idle_done()
                    self.server.idle()
                    connectionFails = 0
                except:
                    if self.running == False: break
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
                eventQueue.put(("mail",keys[1]))
            else:
                eventQueue.put(('log',"Got an email with unknown addressee: %s (need addressee %s)"%
                                (addressee,intendedAddressee)))
                
        eventQueue.put(('status','email',"Not Running"))
        
    def stop(self):
        self.running = False
        try: 
            self.server.logout()
        except:
            pass

import select
#find better way to choose event - /proc/bus/input/devics is good       
class keyboardMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "KeyboardMonThread"
        self.dev = None
        self.pollobject = None
        self.running = False
        
        kbd_device = fileconfig.config['TRIGGERS']['KEYBOARD_DEVICE']
        if kbd_device == None:
            eventQueue.put(('log',"Keyboard not found"))
            eventQueue.put(('status','killSwitch',"Error: Keyboard not found"))
            return
        
        try:
            self.dev = open(kbd_device,'rb')
        except IOError as e:
            eventQueue.put(('log',"Cannot monitor keyboard: %s\n->Need to run as root"%e))
            eventQueue.put(('status','killSwitch',"Error: No permission to read keyboard device"))
            return
        
        self.running = True
        
    def run(self):
        while self.running == True:
            watchKeys = []
            triggerKeys1 = {}
            if 'E_KILL_SWITCH_1' in fileconfig.getActiveTriggers(config):
                triggerCombo = fileconfig.config['TRIGGERS']['kbd_kill_combo_1'].split('+')
                watchKeys.extend(triggerCombo)
                if len(triggerCombo) == 0: 
                        eventQueue.put(('log',"No trigger key combination provided: keyboard killswitch 1 inactive"))
                else:
                    for key in triggerCombo:
                        triggerKeys1[key] = False    
                            
            triggerKeys2 = {}   
            if 'E_KILL_SWITCH_2' in fileconfig.getActiveTriggers(config):
                triggerCombo = fileconfig.config['TRIGGERS']['kbd_kill_combo_2'].split('+')
                watchKeys.extend(triggerCombo)
                if len(triggerCombo) == 0: 
                        eventQueue.put(('log',"No trigger key combination provided: keyboard killswitch 2 inactive"))  
                else:
                    for key in triggerCombo:
                        triggerKeys2[key] = False
            
            watchKeys = list(set(watchKeys))
            
            keyEventFormat = 'llHHI'
            keyEventSize = struct.calcsize(keyEventFormat)
            
            self.running = True
            self.pollobject = select.poll()
            self.pollobject.register(self.dev)
            eventQueue.put(('status','killSwitch',"Active"))
            
            self.listening = True
            while self.listening == True:
                result = self.pollobject.poll(1)
                if self.listening == False: continue
                if result[0][1] != 5: continue 
                
                event = self.dev.read(keyEventSize)
                (time1, time2, eType, kCode, pressed) = struct.unpack(keyEventFormat, event)
                kCode = str(kCode)
                if eType != 1: continue
    
                if kCode in watchKeys:
                    if pressed == 1:
                        if kCode in triggerKeys1.keys():
                            triggerKeys1[kCode] = True
                            for key,state in triggerKeys1.items():
                                if state == False: break
                            else: eventHandle('E_KILL_SWITCH_1',None)
                            
                        if kCode in triggerKeys2.keys():
                            triggerKeys2[kCode] = True
                            for key,state in triggerKeys2.items():
                                if state == False: break
                            else: eventHandle('E_KILL_SWITCH_2',None)                   
                        
                    elif pressed == 0:
                        if kCode in triggerKeys1.keys(): triggerKeys1[kCode] = False
                        if kCode in triggerKeys2.keys(): triggerKeys2[kCode] = False
                    
        eventQueue.put(('status','killSwitch',"Not running")) 
        
    def reloadConfig(self):
        self.listening = False
    
    def stop(self):
        self.running = False
        self.listening = False
        self.dev.close()

class camera_monitor(threading.Thread):
    def __init__(self,device,settings):
        threading.Thread.__init__(self)
        self.device = device
        self.settings = settings
        self.process = None
        self.event = None
        self.name = "UnnamedCameraMon"
        
    def run(self):
        if self.event == 'E_CHASSIS_MOTION':
            statusName = 'chassis_camera'
        elif self.event == 'E_ROOM_MOTION':
            statusName = 'room_camera'
        else:
            #no reason to get here 
            eventQueue.put(('log',"%s: Error: Camera event not set"%(self.name))) 
            return
        
        threshold = self.settings['threshold']
        fps = self.settings['fps']
        minframes = self.settings['minframes']
        savepic = self.settings['savepic']

        args = ["./motion-lw","-v%s"%self.device,"-t %s"%threshold,"-m %s"%minframes,"-f %s"%fps]
        if savepic == True: args.append("-j")
        
        try:
            monitorproc = subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            eventQueue.put(('status',statusName,"Error: Could not run camera monitor")) 
            eventQueue.put(('log',"%s: Error: Could not run camera monitor: %s"%(self.name,e))) 
            return
        
        if monitorproc == []:
            eventQueue.put(('status',statusName,"Error: Could not run camera monitor")) 
            eventQueue.put(('log',"%s: Error: Could not run camera monitor (2)"%(self.name))) 
            return
        
        self.process = monitorproc
        self.running = True
        eventQueue.put(('status',statusName,"Active"))
        while self.running == True:
            try:
                output = monitorproc.stderr.readline().decode('UTF-8').rstrip().split(':')
            except:
                if self.running == False: break
                eventQueue.put(('status',statusName,"Error: Failed communicating with motion process")) 
                eventQueue.put(('log',"%s: Error: Failed communicating with motion process: %s"%(sys.exc_info()[0]))) 
                return

            if output[0] == 'motion':
                if self.event == 'E_CHASSIS_MOTION' or fileconfig.config['CAMERAS']['room_savepicture'] == 'False':
                    eventHandle(self.event,('Motion detected'))
            elif output[0] == 'path': #a new image capture
                if self.event == 'E_ROOM_MOTION' and fileconfig.config['CAMERAS']['room_savepicture'] == 'True':
                    eventHandle(self.event,('Motion capture generated',output[1]))  
            else: 
                if self.running == False: break
                eventQueue.put(('log',"%s: Motion error for %s: %s"%(self.name,self.device,[output]))) 
                if 'Failed' in output:
                    self.process.kill()
                    return
                
        eventQueue.put(('status',statusName,"Not Running"))
                    
    def stop(self):
        self.running = False
        self.process.kill()

REMOTE_LOCK = 1
REMOTE_STARTMONITOR = 2
REMOTE_STOPMONITOR = 3
REMOTE_SHUTDOWN = 4
REMOTE_KILLSWITCH = 5
commandList = range(REMOTE_LOCK,REMOTE_KILLSWITCH+1)

def executeRemoteCommand(command,threadDict):
    if command == REMOTE_LOCK:
        if hardwareconfig.checkLock() == False:
            AFroutines.lockScreen()
            sendEmail("Command successful","Screen locked")
            eventQueue.put(('log','Locking screen from remote command'))
        else:
            sendEmail("Command failed","Screen was already locked")
            eventQueue.put(('log','Lock screen failed - command received while locked'))
        
    elif command == REMOTE_STARTMONITOR:
        if threadDict['roomCamera'] == None:
            eventQueue.put(('startMonitor','room_camera'))
            sendEmail("Command successful","Movement monitoring initiated. Have a nice day.")
            eventQueue.put(('log',"Movement monitoring initiated after remote command"))
        else:
            sendEmail("Command failed","Movement monitoring already active.")
            eventQueue.put(('log',"Remote movement monitoring activation failed: already active"))
            
    elif command == REMOTE_STOPMONITOR:
        if monitoringRoom == True:
            monitoringRoom = False
            eventQueue.put(('stopMonitor','room_camera'))
            sendEmail("Command successful","Movement monitoring disabled. Welcome home!")
            eventQueue.put(('log',"Movement monitoring disabled after remote command"))
        else:
            sendEmail("Command failed","Movement monitoring was not active.")
            eventQueue.put(('log',"Remote movement monitoring deactivation failed: not active"))
            
    elif command == REMOTE_SHUTDOWN:
        sendEmail("Command successful","Shutting down...")
        addLogEntry("Standard shutdown due to remote command")
        AFroutines.standardShutdown()
        
    elif command == REMOTE_KILLSWITCH:
        addLogEntry("Emergency shutdown due to remote command")
        AFroutines.emergency()   

def startMonitor(threadDict,monitor):
    if monitor == 'ipc':
        #the dbus interface we use to catch and send lock signals
        #requires we run as that users UID, so we save it here
        #todo: may not get uid as daemon?
        if (os.getenv("SUDO_USER")) != None:
            suUser = getpwnam(os.getenv("SUDO_USER")).pw_uid
            AFroutines.screenOwner = suUser
        else: 
            suUser = None
            AFroutines.screenOwner = os.getuid()
            
        #monitor socket for lock and netadapter events
        threadDict['ipc'] = IPCMonitor(suUser)
        threadDict['ipc'].start()
        return True
    
    elif monitor == 'killSwitch':
        threadDict['killSwitch'] = keyboardMonitor()
        threadDict['killSwitch'].start()
        return True
    
    elif monitor == 'chassis_camera':
        deviceName = fileconfig.config['CAMERAS']['cam_chassis']
        cameraDetails = hardwareconfig.getCamNames()
        for dev in cameraDetails:
            if cameraDetails[dev]['ID_MODEL'] == deviceName:
                devicePath = dev
                break
        else:
            eventQueue.put(('status',monitor,"Error: Camera device not found"))
            eventQueue.put(('log',"Camera device %s not found, chassis motion monitoring aborted"%deviceName))
            return False
            
        
        settings = {
        'threshold' : fileconfig.config['CAMERAS']['chassis_threshold'],
        'minframes' : fileconfig.config['CAMERAS']['chassis_minframes'],
        'fps' : fileconfig.config['CAMERAS']['chassis_fps'],
        'savepic' : False
        }
        
        threadDict['chassis_camera'] = camera_monitor(devicePath,settings)
        threadDict['chassis_camera'].name = "chassisCamMon"
        threadDict['chassis_camera'].event = "E_CHASSIS_MOTION"
        threadDict['chassis_camera'].start()
        return True
    
    elif monitor == 'room_camera':
        
        deviceName = fileconfig.config['CAMERAS']['cam_room']
        cameraDetails = hardwareconfig.getCamNames()
        for dev in cameraDetails:
            if cameraDetails[dev]['ID_MODEL'] == deviceName:
                devicePath = dev
                break
        else:
            eventQueue.put(('status',monitor,"Error: Camera device not found"))
            eventQueue.put(('log',"Camera device %s not found, room motion monitoring aborted"%deviceName))
            return False
        
        settings = {
        'threshold' : fileconfig.config['CAMERAS']['room_threshold'],
        'minframes' : fileconfig.config['CAMERAS']['room_minframes'],
        'fps' : fileconfig.config['CAMERAS']['room_fps'],
        }
        if fileconfig.config['CAMERAS']['room_savepicture'] == 'True':
            settings['savepic'] = True
        else: settings['savepic'] = False
        
        threadDict['room_camera'] = camera_monitor(devicePath,settings)
        threadDict['room_camera'].name = "roomCamMon"
        threadDict['room_camera'].event = "E_ROOM_MOTION"
        threadDict['room_camera'].start() 
        return True 
    
    elif monitor == 'bluetooth':
        threadDict['bluetooth'] = bluetoothMon() 
        threadDict['bluetooth'].start()
        return True
    
    elif monitor == 'email':
        threadDict['email'] = emailMonitor()
        threadDict['email'] .start()
        return True
        
    elif monitor == 'devices':
        context = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(context,source='kernel')
        monitor.start()
        threadDict['devices'] = pyudev.MonitorObserver(monitor, event_handler=device_changed)
        threadDict['devices'].start()
        eventQueue.put(('status','devices',"Active"))
        return True
    
    elif monitor == 'temperature':
        threadDict['temperature'] = temperatureMonitor()
        threadDict['temperature'].start()
        return True
    
    elif monitor == 'netadapters':
        threadDict['netadapters'] = netcableMonitor()
        threadDict['netadapters'].start()
        return True






def broadcast(listeners,msg):
    badConnections = []
    msg = msg+'@'#message separator

    for connection in listeners:
        try:
            connection.send(msg.encode())
        except: 
            badConnections.append(connection)
    
    for connection in badConnections:
        listeners.remove(connection)

def addLogEntry(msg,listeners=None):
    entry = time.strftime('[%x %X] ')+msg+'\n'
    logPath = fileconfig.config['TRIGGERS']['logfile']
    try:
        fd = open(logPath,'a+')
        fd.write(entry) 
        fd.close()
    except:
        syslog.syslog(entry)
    
    if listeners != None:
        broadcast(listeners,'Log::'+entry)       

monitorThread = None
def createLockwatcher():
    global monitorThread
        
    monitorThread = lockwatcher()

class lockwatcher(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'Lockwatcher'
    def run(self):
        eventQueue.put(('log','Starting lockwatcher'))
        global monitoringRoom
        
        listeners = []
        threadDict= {}
        threadStatuses = {}
        startMonitor(threadDict,'ipc')
        
        activeTriggers = fileconfig.getActiveTriggers(config)
        #monitor for the keyboard killswitch command
        if 'E_KILL_SWITCH_1' in activeTriggers or 'E_KILL_SWITCH_2' in activeTriggers:
            startMonitor(threadDict,'killSwitch')
            
        if 'E_CHASSIS_MOTION' in fileconfig.config['TRIGGERS']['alwaystriggers']:
            startMonitor(threadDict,'chassis_camera')
            
        if 'E_BLUETOOTH 'in activeTriggers:
            startMonitor(threadDict,'bluetooth')
        
        badCommands = 0
        if fileconfig.config['EMAIL']['enable_remote']=='True':
            startMonitor(threadDict,'email')

        #monitor for device change events from the kernel
        #hopefully intervene before the device can do anything
        if 'E_DEVICE' in activeTriggers: 
            startMonitor(threadDict,'devices')
            
        if 'E_TEMPERATURE' in activeTriggers:
            startMonitor(threadDict,'temperature') 
        
        ''' not tested yet
        if 'E_INTRUSION' in fileconfig.config['TRIGGERS']['alwaystriggers']: 
            startMonitor(threadDict,'intrusion') 
        '''
            
        logPath = fileconfig.config['TRIGGERS']['logfile']
        if os.path.exists(logPath):
            creationTime = time.ctime(os.path.getctime(logPath))
            creationMonth = datetime.datetime.strptime(creationTime, "%a %b %d %H:%M:%S %Y")
            monthNow = time.strftime('%m %Y')
            if creationMonth != monthNow:
                try:
                    open(logPath, 'w').close()
                except: pass
        
        
        startMessage = "Lockwatcher monitoring started"
        eventQueue.put(('log',startMessage))
        
        shutdownActivated = False
        
        while True:
            event = eventQueue.get(block=True, timeout=None)
            eventType = event[0]
        
            #--------------trigger activated under shutdown conditions
            if eventType == 'kill':
                eventTrigger = event[1]
                eventDetails = event[2]
                if shutdownActivated == False: 
                    
                    #shutdownActivated = True
                    addLogEntry('Emergency shutdown triggered: %s'%str(eventDetails),listeners)
                    
                    if fileconfig.config['EMAIL']['email_alert'] == 'True':
                        emailResult = True
                        if eventTrigger == 'E_ROOM_MOTION' and \
                            eventDetails[0] == 'Motion capture generated' and fileconfig.config['EMAIL']['EMAIL_MOTION_PICTURE'] == 'True':
                                    picPath = eventDetails[1]
                                    if os.path.exists(picPath):
                                        emailResult = sendemail.sendEmail("Emergency shutdown + Image",str(eventDetails),attachment=picPath)
                                
                        else:
                            emailResult = sendemail.sendEmail("Emergency shutdown",str(eventDetails))   
                        
                        if emailResult != True:
                            addLogEntry('Failed to send email: %s'%emailResult,listeners)
                        else: addLogEntry('Shutdown alert email sent',listeners)
                                    
                    
                    if eventTrigger == 'E_DEVICE':
                        device = eventDetails.split("'")[1]
                    else: device = None
                    AFroutines.emergency(device)
                    
            #--------------lock state of system changed
            elif eventType == 'lock':
                lockState = event[1]
                hardwareconfig.setLock(lockState)
                
                'previously started/stopped the polling threads here but no real benefits'
                        
            #--------------thread status changed, inform any listeners
            elif eventType == 'status':
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
                
            #--------------add to log file + gui log window if it exists  
            elif eventType.lower() == 'log':
                addLogEntry(str(event[1]),listeners)
            
            #--------------shutdown lockwatcher monitor
            elif eventType == 'stop':
                for thread in threadDict.values():
                    if thread == None: continue
                    if thread.is_alive(): 
                        thread.stop()
                return    
            
            #--------------new mail in imap inbox addressed to us
            elif eventType == 'mail': 
                #malformed emails would be a good way of crashing lockwatcher
                #be careful to valididate mail here
                validMail = True
                try:
                    command, code = event[1].split(' ')
                    eventQueue.put(('log','Received mail "%s %s"'%(command,code)))
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
                        addLogEntry(str(event[1]),listeners)
                        
                        if shutdownActivated == False:
                            shutdownActivated = True
                            AFroutines.emergency()
                            
                    continue
                
            elif eventType == 'startMonitor':
                monitor = event[1]
                if monitor not in threadDict or threadDict[monitor].is_alive() == False:
                    startMonitor(threadDict,monitor)
                else: eventQueue.put(('log','Error starting thread %s: Already running '%monitor))
                
            elif eventType == 'stopMonitor':    
                monitor = event[1]
                if monitor in threadDict and threadDict[monitor].is_alive() == True:
                    threadDict[monitor].stop()
                    if monitor == 'devices': eventQueue.put(('status','devices',"Not Running"))
                else: 
                    eventQueue.put(('log','Failed to stop thread %s: Not running '%monitor))
                    
            elif eventType == 'Status':
                #if self.statuses != None: self.statuses[event[1]].set(event[2])
                threadStatuses[event[1]] = event[2]

                msg = 'Status::%s::%s'%(event[1],event[2])
                broadcast(listeners,msg)
                    
            elif eventType == 'getStatuses':
                msg = 'AllStatuses::'
                for name,value in threadStatuses.items():
                    msg = msg+ '%s::%s|'%(name,value)
                msg = msg[:-1]
                
                broadcast(listeners,msg)  
                    
            elif eventType == 'reloadConfig':
                fileconfig.reloadConfig()
                if 'killSwitch' in threadDict.keys() and threadDict['killSwitch'].is_alive():
                    threadDict['killSwitch'].reloadConfig()
                
            elif eventType == 'newListener':
                port = int(event[1])
                s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                eventQueue.put(('log','Lockwatcher connected to new configuration client'))
                try:
                    s.connect( ('127.0.0.1', port) )
                except: 
                    eventQueue.put(('log','Error: Failed to connect to client port: '+str(port)))
                    continue
                
                s.send(b'True@')
                listeners.append(s)      
                  
            else:
                eventQueue.put(('log','Unknown event %s on event queue'%[event]))

monitorThread = None

class lockWatcherDaemon(daemon): 
    lwThread = None
    def run(self):
        lwThread = lockwatcher()  
        lwThread.start()
        
    def stop(self):
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            s.connect(('127.0.0.1', DAEMONPORT))
        except:
            return
        s.send(b'stop')
        s.close()

if __name__ == "__main__":
        if len(sys.argv) == 2:
                if sys.argv[1] == 'console':
                    pass
                    #signal.signal(signal.SIGINT, kill_self)   
                    #lockWatcher.run(lockWatcher)
 
                daemon = lockWatcherDaemon('/var/run/lockwatcher.pid')
                if 'start' == sys.argv[1]:
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        daemon.restart()
                else:
                        print( "Unknown command")
                        sys.exit(2)
                sys.exit(0)
        else:
                print( "usage: %s start|stop|restart|console" % sys.argv[0])
                sys.exit(2)  
                       
