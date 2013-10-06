#!/usr/bin/python3
'''
lockwatcher.py
@author: Nia Catlin

Runs a group of threads which monitor for potential forensic-related system events
and trigger the antiforensic module if appropriate

Requires 'motion' and 'ifplugd' to be running and properly configured
to use the motion and network connection triggers
'''
import multiprocessing
import threading, queue, struct, sys
import os,subprocess,time
import dbus, signal, socket
import pyudev, sensors #bastien leonards pysensors 
import imapclient, sendemail
from sendemail import sendEmail,validHMAC
import syslog

from gi.repository import GObject
from pwd import getpwnam
import dbus
from dbus.mainloop.glib import DBusGMainLoop

import fileconfig, AFroutines, hardwareconfig
from fileconfig import config
#from lwconfig import triggerList, printMessage

from daemon import daemon

eventQueue = queue.Queue()

#sends messages to stdout and the logfile
def logMessage(str): 
    print(str)
    syslog.syslog(str)

lockedStateText = {True:'Locked',False:'Not Locked'}
def eventHandle(event_type,eventReason):
    locked = hardwareconfig.checkLock()
    #print("[%s] Trigger activated. %s"%(lockedStateText[locked],eventReason)) 
    
    if (event_type in fileconfig.config['TRIGGERS']['ALWAYSTRIGGERS'].split(',')) or \
        (event_type in fileconfig.config['TRIGGERS']['LOCKEDTRIGGERS'].split(',') and locked == True):
        eventQueue.put(("log","[%s - Trigger %s activated]: %s"%(lockedStateText[locked],event_type,eventReason)))
        eventQueue.put(("kill",event_type,eventReason))
    else:
        eventQueue.put(("log","[%s - Trigger %s (ignored)]: %s"%(lockedStateText[locked],event_type,eventReason)))

def device_changed(action,device):
    eventHandle('E_DEVICE',"Device event trigger. Device: %s, Event: %s"%(device,action))

lockQueue = None
def scrnLocked(state):
    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(('127.0.0.1',22190))
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
            if config['TRIGGERS']['DESKTOP_ENV'] == 'LXDE':
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
        
        pidfd = open('/var/run/lockpid','w')
        pidfd.write(str(p.pid))
        pidfd.close()

        try:
            self.listenSocket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.listenSocket.bind(('127.0.0.1',22190))
        except:
            eventQueue.put(('log','Could not bind to 127.0.0.1:22190, please kill any other lockwatchers and try again'))
            eventQueue.put(('status','ipc','Error: Lockwatcher already running'))
            eventQueue.put(('stop',None))
            return
        
        eventQueue.put(('status','ipc','Active'))
        self.running = True
        while self.running == True:
            result = self.listenSocket.recv(16)
            if self.running == False: break
            
            if result == b'True': 
                eventQueue.put(('lock',True))
            elif result == b'False': 
                eventQueue.put(('lock',False))
                    
            elif result == b'netCable':
                eventHandle(('E_NET_CABLE',True))
                
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
        for iface in config['TRIGGERS']['adapterconids'].split(','):
            monitorUpAdapters[iface] = None
        
        monitorDownAdapters = {}
        for iface in config['TRIGGERS']['adapterdisconids'].split(','):
            monitorDownAdapters[iface] = None
                
        #todo: tests etc
        out = subprocess.check_output(['./ifplugstatus'])
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
            out = subprocess.check_output(['./ifplugstatus'])
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
            if newTemp < config['TRIGGERS']['LOW_TEMP']: 
                eventHandle(('E_TEMPERATURE',"%s degrees C"%newTemp))
                
        eventQueue.put(('status','temperature',"Not running"))         
            
    def stop(self):
        self.running = False

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
        
        BTDevID = config['TRIGGERS']['BLUETOOTH_DEVICE_ID']
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
    try:
        server = imapclient.IMAPClient(config['EMAIL']['EMAIL_IMAP_HOST'], use_uid=False, ssl=True)
        server.login(config['EMAIL']['EMAIL_USERNAME'], config['EMAIL']['EMAIL_PASSWORD'])
        server.select_folder('INBOX')
        eventQueue.put(('log',"Established IMAP connection"))
        return server
    except:
        return False
            
class emailMonitor(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = "mailMonThread"
    def run(self):
        self.server = setupIMAP()
        
        if self.server == False:
            eventQueue.put(('log',"Error: Could not connect to mail IMAP server, will not listen for remote commands"))
            eventQueue.put(('status','email',"Error: IMAP connection failed"))
            return
        
        self.server.idle()

        eventQueue.put(('status','email',"Active"))
        connectionFails = 0
        self.running = True
        while self.running == True:
            #refresh the connection every 14 mins so it doesnt timeout
            seqid = self.server.idle_check(840)
            if seqid == []: #no mail
                try:
                    self.server.idle_done()
                    self.server.idle()
                    connectionFails = 0
                except:
                    if self.running == False: break
                    eventQueue.put(('log','Connection exception on imap IDLE: %s. Attempting reconnect attempt %s'%(sys.exc_info()[0],connectionFails)))
                    eventQueue.put(('status','email',"Connection Lost. Waiting for reconnect..."))
                    
                    #sleep for up to 30 seconds. 
                    #Worried that this can be used to remotely detect presence of the program
                    #-> perhaps randomise or standardise the time slept?
                    time.sleep(min(connectionFails,10) * 3) 
                    connectionFails += 1
                    
                    self.server = setupIMAP()
                    self.server.idle()

                continue
            
            #fetch header data using the sequence id of the new mail  
            #this is ugly but so is IMAP
            seqid = seqid[0][0]
            self.server.idle_done()
            keys = self.server.fetch(seqid, ['ENVELOPE'])
            self.server.idle()
            keys = keys[seqid]['ENVELOPE']
            
            if keys[2][0][2] == config['EMAIL']['command_email_address']:
                eventQueue.put(("mail",keys[1]))
            else:
                eventQueue.put(('log',"Got an email, unknown addressee: %s"%keys[2][0][2]))
                
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
    def run(self):
        kbd_device = config['TRIGGERS']['KEYBOARD_DEVICE']
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
        
        watchKeys = []
        triggerKeys1 = {}
        if 'E_KILL_SWITCH_1' in fileconfig.getActiveTriggers(config):
            triggerCombo = config['TRIGGERS']['kbd_kill_combo_1'].split('+')
            watchKeys.extend(triggerCombo)
            if len(triggerCombo) == 0: 
                    eventQueue.put(('log',"No trigger key combination provided: keyboard killswitch 1 inactive"))
            else:
                for key in triggerCombo:
                    triggerKeys1[key] = False    
                        
        triggerKeys2 = {}   
        if 'E_KILL_SWITCH_2' in fileconfig.getActiveTriggers(config):
            triggerCombo = config['TRIGGERS']['kbd_kill_combo_2'].split('+')
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
        while self.running == True:

            result = self.pollobject.poll(1)
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
    def stop(self):
        self.running = False
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
                if self.event == 'E_CHASSIS_MOTION' or config['CAMERAS']['room_savepicture'] == 'False':
                    eventHandle(self.event,('Motion detected'))
            elif output[0] == 'path': #a new image capture
                if self.event == 'E_ROOM_MOTION' and config['CAMERAS']['room_savepicture'] == 'True':
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
            subprocess.Popen(['/etc/init.d/motion','restart'],stderr= subprocess.DEVNULL)
            sendEmail("Command successful","Movement monitoring initiated. Have a nice day.")
            eventQueue.put(('log',"Movement monitoring initiated after remote command"))
        else:
            sendEmail("Command failed","Movement monitoring already active.")
            eventQueue.put(('log',"Remote movement monitoring activation failed: already active"))
            
    elif command == REMOTE_STOPMONITOR:
        if monitoringRoom == True:
            monitoringRoom = False
            subprocess.Popen(['/etc/init.d/motion','stop'],stderr= subprocess.DEVNULL)
            sendEmail("Command successful","Movement monitoring disabled. Welcome home!")
            eventQueue.put(('log',"Movement monitoring disabled after remote command"))
        else:
            sendEmail("Command failed","Movement monitoring was not active.")
            eventQueue.put(('log',"Remote movement monitoring deactivation failed: not active"))
            
    elif command == REMOTE_SHUTDOWN:
        sendEmail("Command successful","Shutting down...")
        logMessage("Standard shutdown due to remote command")
        AFroutines.standardShutdown()
        
    elif command == REMOTE_KILLSWITCH:
        reason = "Emergency shutdown due to remote command"
        logMessage(reason)
        AFroutines.emergency(reason)   

def startMonitor(threadDict,monitor):
    if monitor == 'ipc':
        #the dbus interface we use to catch and send lock signals
        #requires we be that users UID, so we save it here
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
        deviceName = config['CAMERAS']['cam_chassis']
        cameraDetails = hardwareconfig.getCamNames()
        for dev in cameraDetails:
            if cameraDetails[dev]['ID_MODEL'] == deviceName:
                devicePath = dev
                break
        else:
            eventQueue.put(('log',"Camera device %s not found, chassis motion monitoring aborted"%deviceName))
            return False
            
        
        settings = {
        'threshold' : config['CAMERAS']['chassis_threshold'],
        'minframes' : config['CAMERAS']['chassis_minframes'],
        'fps' : config['CAMERAS']['chassis_fps'],
        'savepic' : False
        }
        
        threadDict['chassis_camera'] = camera_monitor(devicePath,settings)
        threadDict['chassis_camera'].name = "chassisCamMon"
        threadDict['chassis_camera'].event = "E_CHASSIS_MOTION"
        threadDict['chassis_camera'].start()
        return True
    
    elif monitor == 'room_camera':
        
        deviceName = config['CAMERAS']['cam_room']
        cameraDetails = hardwareconfig.getCamNames()
        for dev in cameraDetails:
            if cameraDetails[dev]['ID_MODEL'] == deviceName:
                devicePath = dev
                break
        else:
            eventQueue.put(('log',"Camera device %s not found, room motion monitoring aborted"%deviceName))
            return False
        
        settings = {
        'threshold' : config['CAMERAS']['room_threshold'],
        'minframes' : config['CAMERAS']['room_minframes'],
        'fps' : config['CAMERAS']['room_fps'],
        }
        if config['CAMERAS']['room_savepicture'] == 'True':
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

'''  
class lockWatcherDaemon(daemon): 
        def run(self):
        lockwatcher()  
'''
class lockwatcher(threading.Thread):
    def __init__(self,statuses,msgAddFunc):
        threading.Thread.__init__(self)
        self.name = 'Lockwatcher'
        self.statuses = statuses
        self.msgAdd = msgAddFunc
    def run(self):
        eventQueue.put(('log','Starting lockwatcher'))
        global monitoringRoom
        
        threadDict= {}
        startMonitor(threadDict,'ipc')
        
        activeTriggers = fileconfig.getActiveTriggers(config)
        #monitor for the keyboard killswitch command
        if 'E_KILL_SWITCH_1' in activeTriggers or 'E_KILL_SWITCH_2' in activeTriggers:
            startMonitor(threadDict,'killSwitch')
            
        if 'E_CHASSIS_MOTION' in config['TRIGGERS']['alwaystriggers']:
            startMonitor(threadDict,'chassis_camera')
            
        if 'E_BLUETOOTH 'in activeTriggers:
            startMonitor(threadDict,'bluetooth')
        
        badCommands = 0
        if config['EMAIL']['enable_remote']=='True':
            startMonitor(threadDict,'email')

        #monitor for device change events from the kernel
        #hopefully intervene before the device can do anything
        if 'E_DEVICE' in activeTriggers: 
            startMonitor(threadDict,'devices')
            
        if 'E_TEMPERATURE' in activeTriggers:
            startMonitor(threadDict,'temperature') 
        
        ''' not tested yet
        if 'E_INTRUSION' in config['TRIGGERS']['alwaystriggers']: 
            startMonitor(threadDict,'intrusion') 
        '''
            
        startMessage = "AF detection started at %s"%time.strftime('%x %X')
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
                    logMessage('Emergency shutdown triggered: %s'%str(eventDetails))
                    
                    if config['EMAIL']['email_alert'] == 'True':
                        emailResult = True
                        if eventTrigger == 'E_ROOM_MOTION' and \
                            eventDetails[0] == 'Motion capture generated' and config['EMAIL']['EMAIL_MOTION_PICTURE'] == 'True':
                                    picPath = eventDetails[1]
                                    if os.path.exists(picPath):
                                        emailResult = sendemail.sendEmail("Emergency shutdown + Image",str(eventDetails),attachment=picPath)
                                
                        else:
                            emailResult = sendemail.sendEmail("Emergency shutdown",str(eventDetails))   
                        
                        if emailResult != True:
                            logMessage('Failed to send email: %s'%emailResult)
                        else: logMessage('Shutdown alert email sent')
                                    
                    
                    print('shutdown called')
                    if eventTrigger == 'E_DEVICE':
                        device = eventDetails.split("'")[1]
                    else: device = None
                    AFroutines.emergency(eventDetails,device)
                    
            #--------------lock state of system changed
            elif eventType == 'lock':
                lockState = event[1]
                hardwareconfig.setLock(lockState)
                
                'previously started/stopped the polling threads here but no real benefits'
                        
            #--------------thread status changed, update GUI if it exists
            elif eventType == 'status':
                if self.statuses != None:
                    self.statuses[event[1]].set(event[2])
            
            #--------------add to log file + gui log window if it exists  
            elif eventType == 'log':
                logPath = fileconfig.config['TRIGGERS']['logfile']
                if os.path.exists(logPath):
                    try:
                        fd = open(logPath,'a+')
                        fd.write(time.strftime('[%x %X] ')+event[1]+'\n') 
                        fd.close()
                    except:
                        print('failed to write log to %s'%logPath)
                    
                if self.msgAdd != None: 
                    self.msgAdd(event[1])
            
            #--------------shutdown lockwatcher monitor
            elif eventType == 'stop':
                killLockmon()
                for thread in threadDict.values():
                    if thread == None: continue
                    if thread.is_alive(): 
                        thread.stop()
                return    
            
            #--------------new mail in imap inbox addressed to us
            elif eventType == 'mail': 
                command, code = event[1].split(' ')
                eventQueue.put(('log','Received mail %s %s'%(command,code)))
                command = int(command)
                if command not in commandList or validHMAC(code,command) == False:
                    badCommands += 1
                    sendEmail("Command failed","Bad command or authentication code received: %s"%command)
                    eventQueue.put(('log','Mail not authenticated or bad command'))
                    if badCommands >= config['EMAIL']['BAD_COMMAND_LIMIT']:
                        reason = "Too many bad remote commands received"
                        AFroutines.emergency(reason,lockState)
                else:
                    eventQueue.put(('log','Mail authenticated'))
                
                #a successful command resets the counter
                badCommands = 0       
                executeRemoteCommand(command,threadDict)
                
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
                
            else:
                eventQueue.put(('log','Unknown event %s on event queue'%[event]))

monitorThread = None
def createLockwatcher(statuses,msgAddFunc):
    global monitorThread
    monitorThread = lockwatcher(statuses,msgAddFunc)

#kill lock watching process
def killLockmon():
    lockmonFD = open('/var/run/lockpid','r')
    lockmonPID = lockmonFD.read()
    lockmonFD.close()
    subprocess.Popen(['/bin/kill',lockmonPID],stderr= subprocess.DEVNULL)  

     
    if os.path.exists('/var/run/lockpid'): 
        os.remove('/var/run/lockpid')

def kill_self(signal, frame):
        '''
        #this doesnt work, os.path.exists() thinks it exists then
        #we get filenotfound for trying to kill it
        if os.path.exists(lwconfig.PID_FILE): 
            print(lwconfig.PID_FILE, 'exists!')
            os.remove(lwconfig.PID_FILE)
        '''
        killLockmon()
        exit()    

'''
if __name__ == "__main__":
        if len(sys.argv) == 2:
                if sys.argv[1] == 'console':
                    try:
                        fd = open(lwconfig.PID_FILE,'w')
                        fd.write(str(os.getpid()))
                        fd.close()
                    except PermissionError:
                        print("Do not have permission to write PID to %s"%lwconfig.PID_FILE)
                        #exit()
                    
                    lwconfig.errorTarget = 'console'
                    signal.signal(signal.SIGINT, kill_self)   
                    lockWatcher.run(lockWatcher)

                        
                daemon = lockWatcher(lwconfig.PID_FILE)
                if 'start' == sys.argv[1]:
                        lwconfig.errorTarget = 'syslog'
                        daemon.start()
                elif 'stop' == sys.argv[1]:
                        killLockmon()
                        daemon.stop()
                elif 'restart' == sys.argv[1]:
                        lwconfig.errorTarget = 'syslog'
                        daemon.restart()
                else:
                        print( "Unknown command")
                        sys.exit(2)
                sys.exit(0)
        else:
                print( "usage: %s start|stop|restart|console" % sys.argv[0])
                sys.exit(2)  
            '''              
