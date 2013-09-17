'''
Created on Sep 15, 2013

@author: Nia Catlin
'''
import configparser, re

TRIG_LOCKED = 0
TRIG_ALWAYS = 1
TRIG_NEVER = 2

CONFIG_FILE = '/etc/lockwatcher/lockwatcher.ini'
config = configparser.ConfigParser()
config.read(CONFIG_FILE)

def writeConfig():
    with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile,space_around_delimiters=False)
            
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
    
def writeMotionConfig(file,stat,newVal):    
    fd = open(file,'r')
    text = fd.read()
    fd.close()
    
    regex = stat
    
    res = re.search('(^%s.*$)'%regex,text,re.MULTILINE)  
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
