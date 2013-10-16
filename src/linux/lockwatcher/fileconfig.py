'''
@author: Nia Catlin

Various config file handling routines
'''
import configparser,re,pickle,os
import sys,subprocess
from lockwatcher import hardwareconfig

TRIG_LOCKED = 0
TRIG_ALWAYS = 1
TRIG_NEVER = 2

CONFIG_FILE = '/etc/lockwatcher/lockwatcher.conf'
config = None

def writeConfig():
    with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile,space_around_delimiters=False)
    hardwareconfig.sendToLockwatcher('reloadConfig',config['TRIGGERS']['daemonport'])

def checkBtnChanged(btn):

    btnName = btn.get_name()
    if btnName == 'enable_remote':
        config['EMAIL']['enable_remote'] = str(btn.get_active())
    elif btnName == 'enable_alerts':
        config['EMAIL']['email_alert'] = str(btn.get_active())
    elif btnName == 'dismount_crypt':
        config['TRIGGERS']['dismount_crypt'] = str(btn.get_active())
    elif btnName == 'dismount_tc':
        config['TRIGGERS']['dismount_tc'] = str(btn.get_active())
    else: 
        print('unknown toggle box: ',btnName)
        return
    
    writeConfig()
    
def entryChanged(thing):
    entryName = thing.get_name()
    
    if entryName in config.options('EMAIL'):
        section = 'EMAIL'
    elif entryName in config.options('TRIGGERS'):
        section = 'TRIGGERS'
    else:
        print('Unknown section for',entryName)
        return
    
    config[section][entryName] = thing.get_text()
    writeConfig()

def tktrigStateChange(combo):
    LOCKED = config['TRIGGERS']['lockedtriggers'].split(',')
    ALWAYS = config['TRIGGERS']['alwaystriggers'].split(',')
    
    new_trigger = combo.widget.current()
    trigger_type = combo.widget._name.upper()
    
    if trigger_type in LOCKED:
        LOCKED.remove(trigger_type)
    if trigger_type in ALWAYS:
        ALWAYS.remove(trigger_type)
                
    if new_trigger == TRIG_LOCKED:
        LOCKED.append(trigger_type)
    elif new_trigger == TRIG_ALWAYS:
        ALWAYS.append(trigger_type)
    
    config['TRIGGERS']['lockedtriggers'] = str(LOCKED).strip("[]").replace("'","").replace(" ","")
    config['TRIGGERS']['alwaystriggers'] = str(ALWAYS).strip("[]").replace("'","").replace(" ","")
    writeConfig()

def isActive(trigger):
    if trigger in config['TRIGGERS']['alwaystriggers'].split(','):
        return (True,'Always')
    elif trigger in config['TRIGGERS']['lockedtriggers'].split(','):
        return (True,'Locked')
    else:
        return (False,False)
    
def getActiveTriggers():
    lockedTriggers = config['TRIGGERS']['lockedtriggers'].split(',')
    alwaysTriggers = config['TRIGGERS']['alwaystriggers'].split(',')
    return lockedTriggers+alwaysTriggers   
    
def trigStateChange(combo):
    new_trigger = combo.get_active()
    trigger_type = combo.get_title().strip()
    LOCKED = config['TRIGGERS']['lockedtriggers'].split(',')
    ALWAYS = config['TRIGGERS']['alwaystriggers'].split(',')
    
    if trigger_type in LOCKED:
        LOCKED.remove(trigger_type) 
    if trigger_type in ALWAYS:
        ALWAYS.remove(trigger_type)
          
    if new_trigger == TRIG_LOCKED:
        LOCKED.append(trigger_type)
    elif new_trigger == TRIG_ALWAYS:
        ALWAYS.append(trigger_type)
        
    config['TRIGGERS']['lockedtriggers'] = str(LOCKED).strip("[]").replace("'","").replace(" ","")
    config['TRIGGERS']['alwaystriggers'] = str(ALWAYS).strip("[]").replace("'","").replace(" ","")
    writeConfig()


#generate a keycode->keyname mapping
def generateKCodeTable():
    for path in ['/bin/dumpkeys','/usr/bin/dumpkeys','/usr/local/bin/dumpkeys']:
        if os.access(path, os.X_OK):
            dkPath = path
            break
    else:
        dkPath = None
        
    try:
        #needs root, sadly
        outp = subprocess.check_output([dkPath, "--keys-only"]).decode('UTF-8')
    except:
        e = sys.exc_info()
        print('kcodegen exception %s'%str(e))
        return False
       
    numNames = {'zero':'0','one':'1','two':'2','three':'3','four':'4','five':'5','six':'6','seven':'7','eight':'8','nine':'9'}      
    
    kCodeTable = {}
    #generate symbols table
    for line in outp.split('\n'):
        reg = re.search('^keycode\s*(\S*)\s*=\s*(\S*)[\S\s]*',line)
        if reg != None:
            hexCode = int(hex(int(reg.group(1))),16)
            symbol = reg.group(2).strip('+')
            if symbol in numNames.keys():
                symbol = numNames[symbol]
            
            kCodeTable[hexCode] = symbol
          
    return kCodeTable

def loadConfig():
    if not os.path.exists(CONFIG_FILE) or os.path.getsize(CONFIG_FILE)<30:
        if not os.access(CONFIG_FILE,os.W_OK):
            print('Either lockwatcherd or lockwatcher-gui must first be run as root to perform some initial configuration')
            sys.exit()
        fd = open(CONFIG_FILE, 'w')
        fd.close()
        if os.geteuid() == 0:
            os.chmod(CONFIG_FILE, 438) #rw-rw-rw-
        
        config = configparser.ConfigParser()
        config.add_section('TRIGGERS')
        trig = config['TRIGGERS']
        trig['bluetooth_device_id']=''
        trig['kbd_kill_combo_1']=''
        trig['kbd_kill_combo_1_txt']=''
        trig['kbd_kill_combo_2']=''
        trig['kbd_kill_combo_2_txt']=''
        trig['keyboard_device']='None'
        trig['mouse_device']='None'
        trig['low_temp']='21'
        trig['lockedtriggers']='E_DEVICE,E_NETCABLE,E_CHASSIS_MOTION,E_ROOM_MOTION,E_NET_CABLE_IN,E_NET_CABLE_OUT,E_KILL_SWITCH_2'
        trig['alwaystriggers']='E_KILL_SWITCH_1'
        trig['dismount_tc']='False'
        trig['dismount_dm']='False'
        trig['exec_shellscript']='False'
        trig['script_timeout']='5'
        trig['adapterconids']=''
        trig['adapterdisconids']=''
        trig['tc_path']=''
        trig['logfile']='/var/log/lockwatcher'
        trig['daemonport']='22191'
        trig['test_mode']='False'
        
        config.add_section('CAMERAS')
        cameras = config['CAMERAS']
        cameras['cam_chassis']=''
        cameras['chassis_minframes']='2'
        cameras['chassis_fps']='2'
        cameras['chassis_threshold']='5000'
        cameras['cam_room']=''
        cameras['room_minframes']='5'
        cameras['room_fps']='10'
        cameras['room_threshold']='10000'
        cameras['room_savepicture']='True'
        cameras['image_path']='/tmp'
        
        config.add_section('EMAIL')
        email = config['EMAIL']
        
        email['email_alert']='False'
        email['email_imap_host']='imap.changeme.domain'
        email['email_smtp_host']='smtp.changeme.domain'
        email['email_username']='changeme'
        email['email_password']='changeme'
        email['email_secret']='changeme'
        email['bad_command_limit']='3'
        email['enable_remote']='False'
        email['email_motion_picture']='False'
        email['alert_email_address']='changeme@mail.domain'
        email['command_email_address']='yourpc@mail.domain'
        
        config.add_section('KEYBOARD')
        config['KEYBOARD']['MAP'] = 'None'
    else:    
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
    return config

config = loadConfig()

def reloadConfig():
    global config
    config = loadConfig()

#generate a keyboard map if none exists
if not os.path.exists('/etc/lockwatcher/keymap') and os.geteuid() == 0:
    mapfile = '/etc/lockwatcher/keymap'
    
    kCodes = generateKCodeTable()
    if kCodes != False:
        pickle.dump( kCodes, open( mapfile, "wb" ))
        config['KEYBOARD']['MAP'] = mapfile
        writeConfig()

#there must be a better way
def getLockProgram():
    if os.access('/usr/lib/kde4/libexec/kscreenlocker', os.X_OK):
            return '/usr/lib/kde4/libexec/kscreenlocker --force'
    elif os.access('/usr/lib/kde4/libexec/kscreenlocker_greet', os.X_OK):
            return '/usr/lib/kde4/libexec/kscreenlocker_greet'
    elif os.access('/usr/bin/gnome-screensaver-command', os.X_OK):
            return '/usr/bin/gnome-screensaver-command -l'
    elif os.access('/usr/bin/xscreensaver-command', os.X_OK):
            return '/usr/bin/xscreensaver-command -lock'   
    elif os.access('/usr/bin/mate-screensaver-command', os.X_OK):
            return '/usr/bin/mate-screensaver-command -l'   
    else: 
        print('No lock program found - cannot force lock activation')
        return None

#find the UID to use with the dbus
DESK_UID = None
sp = subprocess.Popen(['/usr/bin/pgrep','-xl', 'gnome-session|ksmserver|lxsession|mate-session|xfce4-session'],stdout=subprocess.PIPE)
out = sp.communicate()
results = out[0].decode('UTF-8')
if results != '':
    processes = results.split('\\n')
    if len(processes) > 1 and processes[-1] == '':
        del processes[-1]
    
    if len(processes) > 1:
        '''multiple desktop environment running?
        I don't know how to deal with that, I guess by running lock 
        detection/response on all of them at once. 
        todo it if it turns out to be needed'''
        pass
    
    pid,deskenv = processes[0].split(' ')
    for ln in open('/proc/%d/status' % int(pid)):
        if ln.startswith('Uid:'):
            DESK_UID = int(ln.split()[1])
            break 

#find the lock program to activate
if os.geteuid() == 0:
    LOCKCMD = None
    lockCmdFile = '/etc/lockwatcher/lockcmd'
    if os.path.exists(lockCmdFile):
        fd = open(lockCmdFile)
        cmd = fd.read().split(' ')[0]
        fd.close()
        if os.access(lockCmdFile, os.X_OK):
            LOCKCMD = cmd
    
    if LOCKCMD == None:
        LOCKCMD = getLockProgram()
        if LOCKCMD != None:
            fd = open(lockCmdFile,'w')
            fd.write(LOCKCMD)
            fd.close()


            




