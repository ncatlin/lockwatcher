'''
@author: Nia Catlin

Various config file handling routines
'''
import configparser, os, re

TRIG_LOCKED = 0
TRIG_ALWAYS = 1
TRIG_NEVER = 2

CONFIG_FILE = 'lockwatcher.ini'

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
    
def getActiveTriggers(config):
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

if not os.path.exists(CONFIG_FILE):
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
    writeConfig()
else:    
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)
    
DBUSSUPPORTED = True
#review this code later
ACTIVE = getActiveTriggers(config)

