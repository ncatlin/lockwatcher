'''
@author: Nia Catlin

Various config file handling routines
'''
import configparser,re,pickle,os
import sys,subprocess

TRIG_LOCKED = 0
TRIG_ALWAYS = 1
TRIG_NEVER = 2

CONFIG_FILE = '/etc/lockwatcher/lockwatcher.conf'
config = None

def writeConfig():
    with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile,space_around_delimiters=False)

def writeMotionConfig(file,stat,newVal):    
    fd = open(file,'r')
    text = fd.read()
    fd.close()
    
    regex = stat
    
    res = re.search('(^;?\s*%s.*$)'%regex,text,re.MULTILINE)  
    if res != None: 
        x,y = res.span(1)
    else: 
        print(stat+' not found')
        return
        
    try:
        fd = open(file,'w')
        fd.write(text[:x]+'%s %s'%(regex,newVal)+text[y:])
        fd.close()
    except:
        print("cant edit config file ",file)
    return  
           
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
    try:
        #needs root, sadly
        outp = subprocess.check_output(["/bin/dumpkeys", "--keys-only"]).decode('UTF-8')
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
        config = configparser.ConfigParser()
        config.add_section('TRIGGERS')
        trig = config['TRIGGERS']
        trig['bluetooth_device_id']=''
        trig['kbd_kill_combo_1']=''
        trig['kbd_kill_combo_1_txt']=''
        trig['kbd_kill_combo_2']=''
        trig['kbd_kill_combo_2_txt']=''
        trig['low_temp']='21'
        trig['lockedtriggers']='E_DEVICE,E_NETCABLE,E_CHASSIS_MOTION,E_ROOM_MOTION,E_NET_CABLE_IN,E_NET_CABLE_OUT,E_KILL_SWITCH_2'
        trig['alwaystriggers']='E_KILL_SWITCH_1'
        trig['dismount_tc']='False'
        trig['dismount_dm']='False'
        trig['exec_shellscript']='False'
        trig['adapterconids']=''
        trig['adapterdisconids']=''
        trig['tc_path']=''
        trig['logfile']=''
        trig['immediatestart']='False'
        trig['daemonport']='22191'
        trig['lockprogram']='None'
        
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
        
        writeConfig()
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

def getLockProgram(deskEnv):

    if deskEnv == 'ksmserver':
        if os.path.exists('/usr/lib/kde4/libexec/kscreenlocker'):
            return '/usr/lib/kde4/libexec/kscreenlocker --force'
        elif os.path.exists('/usr/lib/kde4/libexec/kscreenlocker_greet'):
            return '/usr/lib/kde4/libexec/kscreenlocker_greet'
    else: 
        print('no lock program found')
        return 'None'
    

#find the lock program to watch for/activate, as well as the user to activate it with
sp = subprocess.Popen(['/usr/bin/pgrep','-xl', '"gnome-session|ksmserver|lxsession|mate-session|xfce4-session"'],stdout=subprocess.PIPE)
out = sp.communicate()
results = out[0].decode('UTF-8')
if results == '':
    print('No desktop environment detected, cannot monitor for lock changes')
    DBUSSUPPORTED = False
    DESK_UID = None
else:
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
    
    config['TRIGGERS']['lockprogram'] = getLockProgram(deskenv.strip())
    writeConfig()
            




