# -*- coding: iso-8859-15 -*-
'''
@author: Nia Catlin

'''
import wmi 
import pywin
import socket, subprocess
import re, os, time
import string, random, threading
 
import devdetect
import fileconfig, hardwareconfig
from fileconfig import config
import winsockbtooth
import sendemail

from tkinter import *
from tkinter import ttk
from tooltip import createToolTip
from tkinter import filedialog
import winreg
from PIL import Image, ImageTk
import win32api

lockStates = ('Screen Locked','Anytime','Never')

OPT_STATUS = 0
OPT_LOGS = OPT_STATUS+1
OPT_BT = OPT_LOGS+1
OPT_MOTION = OPT_BT+1
OPT_KBD = OPT_MOTION+1
OPT_CHAS = OPT_KBD+1
OPT_NET = OPT_CHAS+1
OPT_EMAIL = OPT_NET+1
OPT_SHUT = OPT_EMAIL+1

optionCategories = {OPT_STATUS:'Status',
                    OPT_LOGS:'Event Log',
                    OPT_BT:'Bluetooth Triggers',
                    OPT_MOTION:'Motion Triggers',
                    OPT_KBD:'Keyboard Triggers',
                    OPT_CHAS:'Chassis Triggers',
                    OPT_NET:'Network Triggers',
                    OPT_EMAIL:'Email Settings',
                    OPT_SHUT:'Shutdown Actions'}

lwMonitorThread = None


VERBOSELOGS = False
#run lockwatcher as a thread instead of a service

DEBUGMODE = False
CREATELW = False
if DEBUGMODE == True:
    if CREATELW == True:
        devdetect.createLockwatcher()
        devdetect.monitorThread.start()

root = Tk()
root.wm_iconbitmap('favicon.ico')

#a window showing a tutorial image
class exampleDialog:    
    def __init__(self, parent, category):

        top = self.top = Toplevel(parent)
        self.top.iconbitmap(bitmap='favicon.ico')
        
        try:
            if category == 'ID':
                Label(top,text='Once your cameras have been added to the iSpy surface:\n Right click on a camera, click "Edit" and look for the ID in the settings window title bar').pack()
                parent.exImg = ImageTk.PhotoImage(Image.open('camid.png'))
            elif category == 'room':
                Label(top,text='In the iSpy interface, right click your room camera and click "Edit".\nAdd the "roomtrigger.exe" program in your lockwatcher directory to the executable field.').pack()
                parent.exImg = ImageTk.PhotoImage(Image.open('roomcam.png'))
            elif category == 'chas':
                Label(top,text='In the iSpy interface, right click your chassis camera and click "Edit".\nAdd the "chastrigger.exe" program in your lockwatcher directory to the executable field.').pack()
                parent.exImg = ImageTk.PhotoImage(Image.open('roomcam.png'))
        except:
            print('Failed to open the example image')
            return
        
        exampleFrame = ttk.LabelFrame(top,text="Example",borderwidth=1,relief=GROOVE)
        exampleFrame.pack(padx=2)
        examPanel = Label(exampleFrame, image = parent.exImg)
        examPanel.pack() 
        
        Button(top,text='Close',command=self.ok).pack()

    def ok(self):
        self.top.destroy()

class updateListenThread(threading.Thread):
    def __init__(self,statusCallback,logCallback):
        threading.Thread.__init__(self) 
        self.logCallback = logCallback
        self.statusCallback = statusCallback
        self.name='updateListenThread'
        self.s = None
        self.conn = None
        self.listening = False
        self.listenPort = None
        
        
        port = 22195
        attempts = 0
        while attempts < 20: 
            try:
                self.s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
                self.s.bind(('127.0.0.1', port))
                break
            except:
                self.s.close()
                port = random.randint(22193,22900)
                attempts = attempts + 1
                continue
        else: 
            self.listenPort = None
            return
            
        self.listenPort = port

    def run(self):
        if self.listenPort == None: 
            return
        self.s.listen(1)
        self.running = True
        while self.running == True:
            try:
                conn,addr = self.s.accept()
            except:
                print(sys.exc_info()[0])
                if self.running == True:
                    time.sleep(2)
                    continue
                else: break #window closed
            
            self.conn = conn
            conEstablished = False
            self.listening = True
            
            if VERBOSELOGS == True: self.logCallback('Connection to lockwatcher established. Ready for data.')
            while self.listening == True:
                try:
                    data = conn.recv(1024).decode('UTF-8')
                    if VERBOSELOGS == True: self.logCallback('Got data from lockwatcher: '+data)
                except socket.error:
                    break
                
                for msg in data.split('@'):
                    if msg == '': continue
                    if conEstablished == False:
                        if msg == 'True':
                            conEstablished = True
                            
                            continue
                        else: continue
                        
                    operation,sep, value = msg.partition('::')
                    if operation == 'Log':
                        self.logCallback(value)
                        
                    elif operation == 'Status':
                        name,sep, updateText = value.partition('::')
                        self.statusCallback(name,updateText)
                        
                    elif operation == 'AllStatuses':
                        for update in value.split('|'):
                            try:
                                name,updateText = update.split('::')
                            except:
                                print('split fucked')
                            self.statusCallback(name,updateText)
                            
                    elif operation == 'Shutdown':
                        self.conn.close()
                        break

    def stop(self):
        self.running = False
        self.listening = False
        if self.conn != None:
            self.conn.close()
        if self.s != None: 
            self.s.close()
        
def writeConfig():
    fileconfig.writeConfig()
    sendToLockwatcher('reloadConfig')

def sendToLockwatcher(msg):
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            s.connect(('127.0.0.1', 22191))
        except:
            return
        s.send(msg.encode())
        s.close()

def lwServiceStatus():
    c = wmi.WMI ()
    lwServiceStatus = c.Win32_Service (["State"],Caption="Lockwatcher")
    if lwServiceStatus == []: return None
    else: return lwServiceStatus[0].State
    

class MainWindow(Frame):
    kbdThread = None
    tempThread = None
    
    
    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.pack()
        
        master.title("Lockwatcher configuration")
        master.minsize(400, 400)
        
        global lwMonitorThread
        lwMonitorThread = updateListenThread(self.newStatus,self.newLog)
        lwMonitorThread.start()
        
        self.firstRun = True
        self.create_widgets(master)
        
        
        
    minVar = BooleanVar()    
    def create_widgets(self,parent):
        self.windowFrame = parent
        self.justStarted = True
        self.messageList = []
        
        #setup options list
        optionsFrame = Frame(parent)
        optionsFrame.pack(side=LEFT,fill=Y)
        
        listbox = Listbox(parent,exportselection=0)
        for i in range(0,len(optionCategories.keys())):
            listbox.insert(i,optionCategories[i])
        listbox.selection_set(0)
        listbox.bind('<<ListboxSelect>>', self.optionClicked)
        listbox.pack(side=LEFT, fill=Y, expand=NO)
        self.listbox = listbox  
        
        #create the box for the selected option
        self.settingFrame = None
        self.draw_selected_panel(parent) 

    def optionClicked(self, event):
        #shutdown monitoring threads if we just left their tab
        if self.kbdThread != None:
            self.kbdThread.terminate()
            self.kbdThread = None
            
        if self.tempThread != None:
            self.tempThread.terminate()
            self.tempThread = None
            
        self.draw_selected_panel(self.windowFrame)  
        
    def draw_selected_panel(self,parent):
        
        if self.settingFrame != None: 
            self.settingFrame.destroy()
        self.settingFrame = Frame(parent)
        self.settingFrame.pack(side=RIGHT,fill=BOTH,expand=YES)
        
        index = self.listbox.curselection()
        label = self.listbox.get(index)
        if label == optionCategories[OPT_STATUS]:
            self.createStatusPanel(self.settingFrame)
        elif label == optionCategories[OPT_LOGS]:
            self.createLogsPanel(self.settingFrame)
        elif label == optionCategories[OPT_BT]:
            self.createBluetoothPanel(self.settingFrame)            
        elif label == optionCategories[OPT_MOTION]:
            self.createMotionPanel(self.settingFrame)
        elif label == optionCategories[OPT_KBD]:
            self.createKeyboardPanel(self.settingFrame)
        elif label == optionCategories[OPT_CHAS]:
            self.createChassisPanel(self.settingFrame)
        elif label == optionCategories[OPT_NET]:
            self.createNetworkPanel(self.settingFrame)
        elif label == optionCategories[OPT_EMAIL]:
            self.createEMailPanel(self.settingFrame)
        elif label == optionCategories[OPT_SHUT]:
            self.createShutdownPanel(self.settingFrame)
    
    threadStatus = {
                'bluetooth' : StringVar(),
                'killSwitch' : StringVar(),
                'ram' : StringVar(),
                'devices' : StringVar(),
                'netAdaptersIn' : StringVar(),
                'netAdaptersOut' : StringVar(),
                'cameras' : StringVar(),
                'email':StringVar()}
    
    def createLogsPanel(self,parent):
        logFileFrame = Frame(parent)
        logFileFrame.pack(side=TOP,fill=X,expand=YES)
        Label(logFileFrame,text='Logfile location:').pack(side=LEFT)
        
        logPath = StringVar()
        logPath.set(config['TRIGGERS']['logfile'])
        
        logfileEntry = Entry(logFileFrame,textvariable=logPath,width=40)
        logfileEntry.pack(side=LEFT,fill=X,expand=YES)
        Button(logFileFrame,text='Select',command=self.chooseLogFile).pack(side=LEFT)
        self.logPath = logPath
        logPath.trace("w", lambda name, index, mode, logPath=logPath: self.changeEntryBox('TRIGGERS:logfile',self.logPath))
        
        msgFrame = ttk.Labelframe(parent,text='Recent events:',relief=SUNKEN)
        msgFrame.pack(expand=YES,fill=BOTH,padx=4,pady=4)
        
        scrollbar = Scrollbar(msgFrame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        #todo: resize with window
        messageListB = Text(msgFrame,width=60,height=21,yscrollcommand=scrollbar.set,wrap=WORD)
        messageListB.pack(side=LEFT,expand=YES,fill=BOTH)
        self.messageListB = messageListB
        scrollbar.config(command=messageListB.yview)
        
        
        if len(self.messageList) > 0:
            for idx,msg in enumerate(self.messageList):
                messageListB.insert(0.0,msg)
        
        messageListB.config(state=DISABLED)
        
    #todo: consolidate these for tc/log/mod
    def chooseLogFile(self):
        path = filedialog.asksaveasfilename(filetypes=[('txt files','.txt')])
        if path != '':
            if '.txt' not in path: path = path+'.txt'
            self.logPath.set(path)
             
    def createStatusPanel(self,parent):
        if lwMonitorThread.listenPort == None:
            Label(parent,text='Failed to bind any ports on 127.0.0.1, cannot connect to Lockwatcher service').pack(pady=5)
            return
        
        self.sStatusText = StringVar()
        Label(parent,textvariable=self.sStatusText).pack(pady=5)
        
        self.threadFrames = Frame(parent)
        
        Label(self.threadFrames,text='Right click individual monitors to start/stop them').pack(pady=5)
        Frame1 = Frame(self.threadFrames)
        
        BTFrame = ttk.LabelFrame(Frame1,text="Bluetooth Connection",name='bluetooth')
        BTFrame.pack(side=LEFT,padx=5)
        BTFrame.bind('<Button-3>',self.rClick,add='')
        BTLabel = Label(BTFrame,textvariable=self.threadStatus['bluetooth'],width=26,name='bluetooth')
        BTLabel.pack()
        BTLabel.bind('<Button-3>',self.rClick,add='')
        self.sBTLabel = BTLabel
        
        KSFrame = ttk.LabelFrame(Frame1,text="Killswitch Activation",name='killSwitch')
        KSFrame.pack(side=RIGHT,padx=5)
        KSFrame.bind('<Button-3>',self.rClick,add='')
        KSLabel = Label(KSFrame,textvariable=self.threadStatus['killSwitch'],width=26,name='killSwitch')
        KSLabel.pack()
        KSLabel.bind('<Button-3>',self.rClick,add='')
        self.sKSLabel = KSLabel
        Frame1.pack(fill=X,expand=YES)
        
        Frame2 = Frame(self.threadFrames)
        RAMFrame = ttk.LabelFrame(Frame2,text="RAM Temperature Drop",name='ram')
        RAMFrame.pack(side=LEFT, padx=5)
        RAMFrame.bind('<Button-3>',self.rClick,add='')
        RAMLabel = Label(RAMFrame,textvariable=self.threadStatus['ram'],width=26,name='ram')
        RAMLabel.pack()
        RAMLabel.bind('<Button-3>',self.rClick,add='')
        self.sRAMLabel = RAMLabel
        
        devFrame = ttk.LabelFrame(Frame2,text="Device Changes",name='devices')
        devFrame.pack(side=RIGHT, padx=5)
        devFrame.bind('<Button-3>',self.rClick,add='')
        devLabel = Label(devFrame,textvariable=self.threadStatus['devices'],width=26,name='devices')
        devLabel.pack()
        devLabel.bind('<Button-3>',self.rClick,add='')
        self.sDevLabel = devLabel
        Frame2.pack(fill=X,expand=YES)
        
        Frame3 = Frame(self.threadFrames)
        cCamFrame = ttk.LabelFrame(Frame3,text="Camera Movement",name='cameras')
        cCamFrame.pack(side=LEFT,padx=5)
        cCamFrame.bind('<Button-3>',self.rClick,add='')
        cCamLabel = Label(cCamFrame,textvariable=self.threadStatus['cameras'],width=26,name='cameras')
        cCamLabel.pack()
        cCamLabel.bind('<Button-3>',self.rClick,add='')
        self.scCamLabel = cCamLabel
        
        mailFrame = ttk.LabelFrame(Frame3,text="Email Commands",name='email')
        mailFrame.pack(side=RIGHT,padx=5)
        mailFrame.bind('<Button-3>',self.rClick,add='')
        mailLabel = Label(mailFrame,textvariable=self.threadStatus['email'],width=26,name='email')
        mailLabel.pack()
        mailLabel.bind('<Button-3>',self.rClick,add='')
        self.sEmailLabel = mailLabel
        Frame3.pack()
        
        Frame4 = Frame(self.threadFrames)
        NAFrame = ttk.LabelFrame(Frame4,text="Network Adapters",name='naFrame')
        NAFrame.pack(side=LEFT,padx=5)
        NAFrame.bind('<Button-3>',self.rClick,add='')
        NAInLabel = Label(NAFrame,textvariable=self.threadStatus['netAdaptersIn'],width=26,name='netAdaptersIn')
        NAInLabel.pack()
        NAInLabel.bind('<Button-3>',self.rClick,add='')
        self.sNAInLabel = NAInLabel
        NAOutLabel = Label(NAFrame,textvariable=self.threadStatus['netAdaptersOut'],width=26,name='netAdaptersOut')
        NAOutLabel.pack()
        NAOutLabel.bind('<Button-3>',self.rClick,add='')
        self.sNAOutLabel = NAOutLabel
        Frame4.pack()
        
        if DEBUGMODE == True:
            status = 'Running'
        else:
            threadAlive = False
            status = lwServiceStatus()
            
        
        if status == 'Running':
            if self.firstRun == True:
                self.setupMonitorStrings()
                sendToLockwatcher('newListener:%s'%lwMonitorThread.listenPort)
                while lwMonitorThread.listening == False:
                    time.sleep(0.1)
                    #check for timeout
                    
                sendToLockwatcher('getStatuses')
                self.firstRun = False
                
                
            self.sStatusText.set("The Lockwatcher service is running")
            
            #give the statuses their appropriate colour
            self.threadFrames.pack(pady=20)
            
            for triggerName,trigger in self.threadStatus.items():
                self.statusChange(triggerName, trigger)
        else:
            if status  != []:
                self.sStatusText.set("The Lockwatcher service is not running")
            else:
                try:
                    devdetect.installService(True)
                except:
                    self.sStatusText.set("The Lockwatcher service is not registered with Windows.\nRun this program in administrator mode to register it.")
                time.sleep(1)
                self.settingFrame.destroy()
                self.createStatusPanel(self.settingFrame)
                
            
    
    def setupMonitorStrings(self):
        defaultStr = "Not Running"
        for triggerName,triggerStr in self.threadStatus.items():
        
            if triggerName == 'netAdaptersIn':
                triggerStr.set('In: '+defaultStr)
            elif triggerName == 'netAdaptersOut':
                triggerStr.set('Out: '+defaultStr)
            else: triggerStr.set(defaultStr)
            
            triggerStr.trace("w", lambda name, index, mode, triggerName=triggerName, triggerStr=triggerStr: self.statusChange(triggerName,triggerStr))
        
           
    def rClick(self,frame):
        commands=[
               ('Start', lambda frame=frame: self.optMonClicked(frame,'startMonitor')),
               ('Stop', lambda frame=frame: self.optMonClicked(frame,'stopMonitor'))
               ]
        cmdMenu = Menu(None,tearoff=0,takefocus=0)
        for (name,function) in commands:
            cmdMenu.add_command(label=name, command=function)
        cmdMenu.tk_popup(frame.x_root+40, frame.y_root+10,entry="0")
    
    def optMonClicked(self,frame,action):
        widgetName = frame.widget._name
        
        if widgetName == 'naFrame':
            sendToLockwatcher('%s:netAdaptersIn'%action)
            sendToLockwatcher('%s:netAdaptersOut'%action)
        else:
            sendToLockwatcher('%s:%s'%(action,widgetName))

        
        
    def addMessage(self,message):
        
        timeMsg = time.strftime('%X')+': '+message+'\n'
        
        #cuts down on the duplicates generated by some events
        if timeMsg in self.messageList: return
        
        self.messageList.append(timeMsg)
        
        index = self.listbox.curselection()
        label = self.listbox.get(index)
        if label != optionCategories[OPT_LOGS]:
            return
        
        self.messageListB.config(state=NORMAL)
        self.messageListB.insert(0.0,timeMsg)
        self.messageListB.config(state=DISABLED)
            
    #if status of monitor changes, may need to change its label colour
    def statusChange(self,triggerName,trigger):
        
        #dont update status label - it doesnt exist
        index = self.listbox.curselection()
        if index[0] == 'None': 
            return
        
        try:#has thrown odd option exception once, check just in case
            label = self.listbox.get(index)
        except:
            return
        
        if label != optionCategories[OPT_STATUS]:
            return
            
        triggerText = trigger.get()
        
        if triggerText == 'Active' or ': Active' in triggerText:
            newColour = 'green'
        elif '...' in triggerText:
            newColour = 'orange'
        elif 'Not Running' in triggerText :
            newColour = 'black'
        else:
            newColour = 'red'
        
        try:
            if triggerName == 'bluetooth':
                self.sBTLabel.config(fg=newColour)
            elif triggerName == 'ram':
                self.sRAMLabel.config(fg=newColour)
            elif triggerName == 'devices':
                self.sDevLabel.config(fg=newColour)
            elif triggerName == 'killSwitch':
                self.sKSLabel.config(fg=newColour)
            elif triggerName == 'netAdaptersIn':
                self.sNAInLabel.config(fg=newColour)
            elif triggerName == 'netAdaptersOut':
                self.sNAOutLabel.config(fg=newColour)
            elif triggerName == 'cameras':
                self.scCamLabel.config(fg=newColour)  
            elif triggerName == 'email':
                self.sEmailLabel.config(fg=newColour)
            else:
                print('Unhandled trigger update: ',triggerName)     
        except:
            #user probably destroyed label by changing tab, don't care  
            pass
    
    def newStatus(self,threadname,text): 
        self.threadStatus[threadname].set(text)
    
    def newLog(self,msg): 
        try:
            self.addMessage(msg)
        except: pass
    def createBluetoothPanel(self,parent):
        Label(parent,text='Lockwatcher will establish a connection to this bluetooth device.\
        \nShutdown will be triggered if the connection is lost.').pack()
        BTBox = ttk.LabelFrame(parent,text="Bluetooth devices")
        BTBox.pack(side=TOP, fill=BOTH, expand=YES)
        
        self.DevIDDict = {}
        
        BTDevList = Listbox(BTBox)
        if len(self.DevIDDict.keys()) > 0:
            for idx,dev in self.DevIDDict.items():
                BTDevList.insert(idx,"Name: %s    ID: %s"%(dev[1],dev[0]))

        
        BTDevList.selection_set(0)
        BTDevList.pack(side=TOP, fill=BOTH, expand=YES)
        BTDevList.bind('<<ListboxSelect>>', self.BTDevSelected)
        self.BTDevList = BTDevList  
        
        scanBtnBox = Frame(BTBox)
        scanBtnBox.pack(fill=X, expand=NO)
        
        self.scanBtnText = StringVar()
        self.scanBtnText.set("Scan for devices")
        scanBtn = Button(scanBtnBox,textvariable=self.scanBtnText)
        scanBtn.pack()
        scanBtn.bind('<Button-1>',self.BTDoScan)
        
        devInfo = Frame(parent)
        devInfo.pack(side=TOP, fill=X, expand=YES)
        
        devIDFrame = Frame(devInfo)
        devIDFrame.pack(side=LEFT)
        devInfoLabel = Label(devIDFrame,text="Current Device")
        devInfoLabel.pack(side=TOP,fill=X)
        
        devIDVar = StringVar()
        self.devIDVar = devIDVar
        devIDVar.set(config['TRIGGERS']['bluetooth_device_id'])
        devIDVar.trace("w", lambda name, index, mode, devIDVar=devIDVar: self.changeEntryBox('TRIGGERS:bluetooth_device_id',self.devIDVar))
        
        devInfoID = Entry(devIDFrame,textvariable=devIDVar,justify=CENTER)
        devInfoID.pack(side=BOTTOM,padx=4)
        
        
        devStatusFrame = Frame(devInfo)
        devStatusFrame.pack(side=RIGHT, fill=X, expand=YES)
        devStatusLabel = Label(devStatusFrame,text="Status: Unknown")
        devStatusLabel.pack(side=TOP,fill=X)
        self.devStatusLabel = devStatusLabel
        
        devStatusButton = Button(devStatusFrame,text='Test')
        devStatusButton.pack(side=BOTTOM)
        devStatusButton.bind('<Button-1>',self.BTDevTest) 

        triggerFrame =  ttk.LabelFrame(parent,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_BLUETOOTH'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
        
        
    def BTDevSelected(self,listbox):
        
        for item in self.BTDevList.curselection():
            deviceInfo = self.BTDevList.get(item).split()
            if deviceInfo[0] == 'ID:':
                self.devIDVar.set(deviceInfo[1])
                config['TRIGGERS']['bluetooth_device_id'] = deviceInfo[1] 
                writeConfig()
                break
            
            
    def BTDoScan(self,btn):
        print("launching scan thread")
        self.DevIDDict = {}
        self.scanBtnText.set('Scanning...')
        self.BTScan = hardwareconfig.BTScanThread(self.BTGotDevices)
        self.BTScan.start()
        print("Scan thread launched")
    
    def BTGotDevices(self,out):
        self.BTDevList.delete(0,self.BTDevList.size()-1)
        
        self.scanBtnText.set('Scan for devices')
        
        if '[Error' in str(out):
            self.BTDevList.insert(0,'Failed to launch btscanner.exe: %s'%out)
            return
        
        if out[0] == 0x94: #error flag that cant be used in bluetooth names. usually.
            errcode = str(out[1:],'UTF-8')
            if errcode == '259': #no results found
                out = out[1:]
            else:
                if errcode == '6': #invalid handle
                    self.BTDevList.insert(0,'Scan failed: Bluetooth not enabled.')
                else:
                    self.BTDevList.insert(0,'Bluetooth scan failed: error %s'%errcode) #todo: make this code nice
                return
                
            
        results = str(out,'UTF-8').split('\n')
        
        BTList = []
        if out != '259': #'no results found' error
            for line in results:
                line = line.strip()
                listEntry = line.split(',')
                if len(listEntry) != 2: continue
                BTList = BTList + [listEntry]
                
        self.BTDevList.delete(0,self.BTDevList.size()-1)
        if len(BTList) == 0:
            self.BTDevList.insert(0,'No results')
            
        i = 0
        for dev in BTList:
            self.BTDevList.insert(i,"ID: %s (%s)"%(dev[0],dev[1]))
            self.DevIDDict[i] = dev
            i += 1    
    
    def BTDevTest(self,button):
        DevID = self.devIDVar.get()
        hexDevID = hardwareconfig.BTStrToHex(DevID)
        
        if hexDevID == 0:
            self.devStatusLabel.config(text="Status: Invalid ID")
            return
        
        print("Testing ",hex(hexDevID))
        self.devStatusLabel.config(text="Testing...")
        
        self.BTTest = hardwareconfig.BTTestThread(self.BTTestResults,hexDevID)
        self.BTTest.start()
        
    def BTTestResults(self,error,result):
           
        if error==True:
            if result == 10060:
                self.devStatusLabel.config(text="Status: Connect Failed")
            elif result == 10050:
                self.devStatusLabel.config(text="Status: No Bluetooth")
            else:
                print('Status: Error %s'%result)
            return
        else:
            self.devStatusLabel.config(text="Status: OK")
    
    
        
    
    def createChassisPanel(self,parent):
        
        RAMFrame =  ttk.LabelFrame(parent,text="RAM Low Temperature Detection",borderwidth=1,relief=GROOVE)
        RAMFrame.pack()
        
        if not os.path.exists(config['TRIGGERS']['BALLISTIX_LOG_FILE']):
            Label(RAMFrame,text="'Crucial Ballistix' RAM modules must be used in conjunction\nwith the MOD utility to monitor memory temperature",background='red').pack()
        
        
        FileFrame = Frame(RAMFrame)
        FileFrame.pack()
        
        Label(FileFrame,text='Ballistix MOD RAM temperature log file').pack()
        Label(FileFrame,text='The Ballistix MOD utility must be actively logging to this file').pack()
        createToolTip(FileFrame, "Typically located at 'Program Files\\Crucial\\Ballistix MOD Utility\\temperature.csv'")

        MODVar = StringVar()
        MODVar.set(config['TRIGGERS']['BALLISTIX_LOG_FILE'])
        MODVar.trace("w", lambda name, index, mode, MODVar=MODVar: self.newMODFile())
        self.MODVar = MODVar
        showKeysBox = Entry(FileFrame,textvariable=MODVar,width=60)
        showKeysBox.pack()
        self.showKeysBox = showKeysBox
        
        Button(FileFrame,text='Locate file',command=self.chooseMODFile).pack()
        
        TempSettingsF = Frame(RAMFrame)
        TempSettingsF.pack(pady=8,side=LEFT)
            
        minTempFrame = Frame(TempSettingsF)
        minTempFrame.pack() 
        
        Label(minTempFrame,text='Minimum temperature (°C):').pack(side=LEFT)
        
        tempVar = StringVar()
        tempVar.set(config['TRIGGERS']['low_temp'])
        tempVar.trace("w", lambda name, index, mode, tempVar=tempVar: self.newTriggerTemp(tempVar.get()))
        self.tempVar = tempVar
        minTempEntry = Entry(minTempFrame,textvariable=tempVar,width=5,justify=CENTER)
        minTempEntry.pack(side=RIGHT)
        
        
        triggerFrame =  ttk.LabelFrame(TempSettingsF,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5,side=RIGHT)

        triggerName = 'E_TEMPERATURE'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack(side=RIGHT)
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
        TestFrame = Frame(RAMFrame)
        TestFrame.pack(side=RIGHT)
        Label(TestFrame,text='Latest measurements').pack()
        
        TempList = Listbox(TestFrame,height=5)
        TempList.pack(padx=5,pady=5)
        self.TempList = TempList
        
        if os.path.exists(config['TRIGGERS']['BALLISTIX_LOG_FILE']):
            self.startTempTest()
        
    def newTriggerTemp(self,temp):
        try:
            float(temp)
            config['TRIGGERS']['low_temp'] = temp
            writeConfig()
        except ValueError:
            return #not a valid number
            
    def chooseMODFile(self):
        path = filedialog.askopenfilename(filetypes=[('csv files','.csv')])
        if path != '':
            self.MODVar.set(path)
            
    def newMODFile(self):
        path = self.MODVar.get()
        if '.csv' in path and os.path.exists(path):
            config['TRIGGERS']['BALLISTIX_LOG_FILE'] = path
            writeConfig()
            
          
    def startTempTest(self): 
        if self.tempThread != None:
                self.tempThread.terminate()
        self.tempThread = hardwareconfig.RAMMonitor(self.newTemperature)
        self.tempThread.start()
    
    def newTemperature(self,temp):
        try:
            self.TempList.insert(0,temp)
        except:
            pass #user changed tab
    
        
    def createMotionPanel(self,parent):
        ISpyPath = StringVar()
        if os.path.exists(config['TRIGGERS']['ispy_path']):
            ISpyPath.set(config['TRIGGERS']['ispy_path'])
        else:
            try:
                
                key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "iSpy Object List\\shell\\open\\command")
                value =  winreg.QueryValue(key, None).split('"')[1]
                if os.path.exists(value):
                    ISpyPath.set(value)
                    config['TRIGGERS']['ispy_path'] = value
                    writeConfig()
            
            except:
                ISpyPath.set('iSpy executable not found')
                Label(parent,text='Chassis and room motion detection requires the iSpy software to be installed',background='red').pack()
        
        
        self.ISpyPath = ISpyPath
        iSpyFrame =  ttk.LabelFrame(parent,text="iSpy application location",borderwidth=1,relief=GROOVE)
        iSpyFrame.pack()
        
        iSpyEntry = Entry(iSpyFrame,textvariable=ISpyPath,width=40)
        iSpyEntry.pack(side=LEFT)
        Button(iSpyFrame,text='Browse',command=self.chooseTCFile).pack(side = RIGHT)
       
        idFrame =  ttk.LabelFrame(parent,text="Camera IDs",borderwidth=1,relief=GROOVE)
        idFrame.pack(pady=10)
        
        roomIDFrame = Frame(idFrame)
        roomIDFrame.pack()
        Label(roomIDFrame,text='iSpy ID number of the room monitoring camera:').pack(side=LEFT)
        roomCamID = StringVar()
        self.roomCamID = roomCamID
        roomCamID.set(config['TRIGGERS']['room_cam_id'])
        roomCamID.trace("w", lambda name, index, mode, roomCamID=roomCamID: self.changeEntryBox('TRIGGERS:room_cam_id',self.roomCamID))
        Entry(roomIDFrame,textvariable=roomCamID,width=5,justify=CENTER).pack(side=RIGHT)
        
        Label(idFrame,text='(This ID is used by lockwatcher to activate/deactivate your camera)').pack()
        Button(idFrame,text='How to find this ID',command=(lambda: self.exampleShow('ID'))).pack()
        
        chasConfig  = ttk.LabelFrame(parent,text="Chassis movement monitoring settings",borderwidth=1,relief=GROOVE)
        chasConfig.pack()
        
        cframe = Frame(chasConfig)
        cframe.pack()
        Label(cframe,text="Configure iSpy to execute 'chastrigger.exe' on motion").pack(side=LEFT)
        Button(cframe,text='Show me',command=(lambda: self.exampleShow('chas'))).pack(side=RIGHT)
        
        triggerFrame =  ttk.LabelFrame(chasConfig,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5,side=BOTTOM)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_CHASSIS_MOTION'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
        
        roomConfig = ttk.LabelFrame(parent,text="Room movement monitoring settings",borderwidth=1,relief=GROOVE)
        roomConfig.pack()
        
        cframe = Frame(roomConfig)
        cframe.pack()
        Label(cframe,text="Configure iSpy to execute 'roomtrigger.exe' on motion").pack(side=LEFT)
        Button(cframe,text='Show me',command=(lambda: self.exampleShow('room'))).pack(side=RIGHT)
        
        triggerFrame =  ttk.LabelFrame(roomConfig,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_ROOM_MOTION'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
    def exampleShow(self,category):
        d = exampleDialog(root,category)
    
    KCodes = []
    def createKeyboardPanel(self,parent):
        
        Label(parent,text='Setup a killswitch combination of one or more keys').pack(padx=5)
        
        entryFrame = Frame(parent)
        entryFrame.pack()
        
        IMVar = StringVar()
        IMVar.set('Captured key codes appear here')
        self.IMVar = IMVar
        showKeysBox = Entry(entryFrame,textvariable=IMVar,width=40,state=DISABLED)
        showKeysBox.pack(side=LEFT, fill=X, expand=YES)
        showKeysBox.focus_set()
        self.showKeysBox = showKeysBox
        
        Button(entryFrame,text='Clear',command=self.clearKeys).pack(side=RIGHT, fill=X, expand=YES)
        
        KSRecordBtn = Button(parent,text='Set as primary killswitch',command = (lambda:self.saveKbdCombo(1)))
        KSRecordBtn.pack()
        
        KSRecordBtn = Button(parent,text='Set as secondary killswitch',command = (lambda:self.saveKbdCombo(2)))
        KSRecordBtn.pack()
        


        primaryFrame =  ttk.LabelFrame(parent,text="Primary killswitch",borderwidth=1,relief=GROOVE)
        primaryFrame.pack(pady=5,padx=5)
        
        Label(primaryFrame,text='Reccommended activation: Anytime').pack()
        Label(primaryFrame,text='"A quick-access panic switch for activation by the user."',width=48).pack()
        KSLLabel = Label(primaryFrame,text='Current Key Combination:').pack(pady=5)
        comboString = ''
        for n in config['TRIGGERS']['kbd_kill_combo_1'].split('+'):
            if int(n) in hardwareconfig.vkDict.keys():
                comboString = comboString+hardwareconfig.vkDict[int(n)]+'+'
            else: comboString = comboString+n+'+'
            
        KS1Label = Label(primaryFrame,text=comboString[:-1])
        KS1Label.pack()
        self.KS1Label = KS1Label
        
        self.kbdThread = hardwareconfig.kbdProcessThread(self.gotKbdKey,None)
        self.kbdThread.daemon = True
        self.kbdThread.start()
        
        triggerFrame =  ttk.LabelFrame(primaryFrame,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_KILL_SWITCH_1'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
        secondaryFrame =  ttk.LabelFrame(parent,text="Secondary killswitch",borderwidth=1,relief=GROOVE)
        secondaryFrame.pack(pady=5,padx=5)
        
        Label(secondaryFrame,text='Reccommended activation: Screen Locked').pack()
        Label(secondaryFrame,text='"A false password containing this key is revealed to attackers."').pack()
        Label(secondaryFrame,text='Current Key Combination:').pack(pady=5)
        comboString = ''
        for n in config['TRIGGERS']['kbd_kill_combo_2'].split('+'):
            if int(n) in hardwareconfig.vkDict.keys():
                comboString = comboString+hardwareconfig.vkDict[int(n)]+'+'
            else: comboString = comboString+n+'+'
        KS2Label = Label(secondaryFrame,text=comboString[:-1])
        KS2Label.pack()
        self.KS2Label = KS2Label
        
        triggerFrame =  ttk.LabelFrame(secondaryFrame,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_KILL_SWITCH_2'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
        
        if os.path.exists('C:\Windows\sysnative\drivers\keyboard.sys'):
            frameText='Interception Driver Status: Installed'
        else: frameText='Interception Driver Status: Not Installed'
        
        ICLabelFrame = ttk.LabelFrame(parent,text=frameText)
        ICLabelFrame.pack(pady=5)
        Label(ICLabelFrame,text='The Interception driver is required to capture keystrokes while locked').pack()
        
        ICBtns = Frame(ICLabelFrame)
        ICBtns.pack()
        installFunc = lambda: self.installIntercept('install')
        Button(ICBtns,text='Install Interception',command=installFunc).pack(side=LEFT,padx=4)
        uninstallFunc = lambda: self.installIntercept('uninstall')
        Button(ICBtns,text='Uninstall Interception',command=uninstallFunc).pack(side=RIGHT,padx=4)
        Label(ICLabelFrame,text='A reboot is required to complete these operations').pack()
        
    def installIntercept(self,task):
        
        try:
            win32api.ShellExecute(0,
                                  "open",
                                  '.\install-interception.exe',
                                  "/%s"%task,
                                  ".",1)
        except win32api.error as e:
            self.addMessage('Interception %s failed: %s'%(task,e.args[2]))
     
    def saveKbdCombo(self,number):
            newcombo = ''
            for x in self.KCodes:
                newcombo = newcombo+str(x)+'+'
            newcombo = newcombo.strip('+')

            if number == 1:
                config['TRIGGERS']['kbd_kill_combo_1'] = newcombo
                self.KS1Label.config(text=self.showKeysBox.get())
            else:
                config['TRIGGERS']['kbd_kill_combo_2'] = newcombo
                self.KS2Label.config(text=self.showKeysBox.get())
            writeConfig()
            
    def clearKeys(self):
        self.IMVar.set('')
        self.KCodes = []
    
    def gotKbdKey(self,key,keyName):
        if key == 0x01: return #bad things happen if mouse L used
        try:
            text = self.showKeysBox.get()
        except:
            return #some keys move focus around and mess things up
        
        if len(text) > 30:
            self.IMVar.set('')
            text = ''
        
        if keyName != 0:
            keyStr = keyName
        else:
            keyStr = str(key)
        keyStr = '('+keyStr+')'
              
        if 'appear' in text or len(text)==0:
            text = keyStr
        else:
            text = text+'+'+keyStr    
        self.IMVar.set(text)
        self.KCodes.append(key)
    
    def createNetworkPanel(self,parent):
        
        inFrame =  ttk.LabelFrame(parent,text="Monitor for connection",borderwidth=1,relief=GROOVE)
        inFrame.pack(fill=BOTH, expand=YES,pady=5,padx=5)
        
        Label(inFrame,text='Select devices to monitor for connection\neg: Cable insertion').pack()  
        NetDevListBox = Listbox(inFrame, selectmode=MULTIPLE,activestyle=NONE,name='connect',exportselection=0)
        NetDevListBox.insert(0,'Listing network adapters...')
        NetDevListBox.pack(side=TOP, fill=BOTH, expand=YES)
        self.NetDevListBoxC = NetDevListBox  
    
        triggerFrame =  ttk.LabelFrame(inFrame,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_NET_CABLE_IN'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
    
    
        outFrame =  ttk.LabelFrame(parent,text="Monitor for disconnection",borderwidth=1,relief=GROOVE)
        outFrame.pack(fill=BOTH, expand=YES,pady=5,padx=5)
        
        Label(outFrame,text='Select devices to monitor for disconnection\neg: Cable removal, Access point power loss').pack() 
        NetDevListBox = Listbox(outFrame, selectmode=MULTIPLE,activestyle=NONE,name='disconnect',exportselection=0)
        NetDevListBox.insert(0,'Listing network adapters...')
        NetDevListBox.pack(side=TOP, fill=BOTH, expand=YES)
        self.NetDevListBoxD = NetDevListBox   
        
        triggerFrame =  ttk.LabelFrame(outFrame,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
        createToolTip(triggerFrame, "Choose when the trigger will cause an emergency shutdown")
        
        triggerName = 'E_NET_CABLE_OUT'
        trigBox =  ttk.Combobox(triggerFrame,values=lockStates,state='readonly',name=triggerName.lower())
        if triggerName in config['TRIGGERS']['lockedtriggers'].split(','):
            trigBox.current(0)
        elif triggerName in config['TRIGGERS']['alwaystriggers'].split(','):
            trigBox.current(1)
        else: trigBox.current(2)
        trigBox.pack()
        trigBox.bind('<<ComboboxSelected>>', fileconfig.tktrigStateChange)
        
        self.netdevScan = hardwareconfig.netScanThread(self.netDevsEnumerated)
        self.netdevScan.start()

    guidDict = {}    
    def netDevsEnumerated(self,networkAdapters):
        self.NetDevListBoxC.delete(0,self.NetDevListBoxC.size()-1)
        self.NetDevListBoxD.delete(0,self.NetDevListBoxD.size()-1)
        
        self.guidDict={}
        devList = []
        for ad in networkAdapters:
            if ad.PhysicalAdapter == True: 
                devList.append(ad)
                self.guidDict[ad.Name] = ad.GUID
        
        if len(devList) > 0:
            for idx,dev in enumerate(devList):
                self.NetDevListBoxC.insert(idx,"%s"%(dev.Name))
                self.NetDevListBoxD.insert(idx,"%s"%(dev.Name))
                if dev.GUID in config['TRIGGERS']['adapterConGUIDS'].split(';'):
                    self.NetDevListBoxC.selection_set(idx) 
                if dev.GUID in config['TRIGGERS']['adapterDisconGUIDS'].split(';'):
                    self.NetDevListBoxD.selection_set(idx)    
                    
            self.NetDevListBoxC.bind('<<ListboxSelect>>', self.netDevSelect)
            self.NetDevListBoxD.bind('<<ListboxSelect>>', self.netDevSelect)
                                
        else:
            self.NetDevListBoxC.insert(0,'No network interfaces found')    
            self.NetDevListBoxD.insert(0,'No network interfaces found') 
            
            
    def netDevSelect(self,lbox):
        
        configString = ""
        for item in lbox.widget.curselection():
            adapterName = lbox.widget.get(item)
            configString = configString + self.guidDict[adapterName] +';'
        
        if lbox.widget._name == 'connect':
            config['TRIGGERS']['adapterConGUIDS'] = configString
        elif lbox.widget._name == 'disconnect':
            config['TRIGGERS']['adapterDisconGUIDS'] = configString
            
        writeConfig()
    
    def changeCheckBox(self, keyname, val):
        section,key = keyname.split(':')
        newValue = val.get()
        config[section][key] = str(newValue)
        writeConfig()
        
        if keyname == 'EMAIL:enable_remote':
            if newValue == 'True':
                sendToLockwatcher('%s:%s'%('startMonitor','email'))
            else: sendToLockwatcher('%s:%s'%('stopMonitor','email'))
        
        
    def changeEntryBox(self, keyname, val):
        section,key = keyname.split(':')
        config[section][key] = str(val.get())
        writeConfig()
        
    testThread = None
    def createEMailPanel(self,parent):
        box6 = Frame(parent)
        box6.pack()
        
        self.ERCheck = StringVar()
        if config['EMAIL']['enable_remote'] == 'True': self.ERCheck.set('True')
        else: self.ERCheck.set('False')
        checkEmailCMD = Checkbutton(box6,text="Enable Remote Control", variable = self.ERCheck,
                                    onval='True',offval='False',command=(lambda: self.changeCheckBox('EMAIL:enable_remote',self.ERCheck)))
        createToolTip(checkEmailCMD, "Lockwatcher will check the specified email inbox for remote commands")
        checkEmailCMD.pack()
        
        
        
        self.EACheck = StringVar()
        if config['EMAIL']['email_alert'] == 'True': self.EACheck.set('True')
        else: self.EACheck.set('False')
        checkEmailSend = Checkbutton(box6,text="Send Shutdown Alerts",variable=self.EACheck,
                                     onval='True',offval='False',command=(lambda: self.changeCheckBox('EMAIL:email_alert',self.EACheck)))
        createToolTip(checkEmailSend,'When an emergency shutdown is triggered, Lockwatcher will send an alert by email.')
        checkEmailSend.pack()
        
        
        emailAccFrame =  ttk.LabelFrame(parent,text="Email Account Settings",borderwidth=1,relief=GROOVE)
        emailAccFrame.pack(padx=2,fill=X,expand=YES)
        
        Label(emailAccFrame,text='Used to send alerts and receive\n commands from your remote device').pack()
        
        box1 = Frame(emailAccFrame)
        box1.pack(fill=X,expand=YES)
        
        IMAPServerL = Label(box1,text='IMAP Server:',width=15)
        IMAPServerL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_IMAP_HOST'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_IMAP_HOST',IMVar))
        IMAPServerE = Entry(box1,textvariable=IMVar)
        IMAPServerE.pack(side=RIGHT,fill=X,expand=YES)
        
        box2 = Frame(emailAccFrame)
        box2.pack(fill=X,expand=YES)
        
        SMTPServerL = Label(box2,text='SMTP Server:',width=15)
        SMTPServerL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_SMTP_HOST'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_SMTP_HOST',IMVar))
        SMTPServerE = Entry(box2, textvariable=IMVar)
        SMTPServerE.pack(side=LEFT,fill=X,expand=YES)
        
        box3 = Frame(emailAccFrame)
        box3.pack(fill=X,expand=YES)
        
        unameL = Label(box3,text='Account Username:',width=15)
        unameL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_USERNAME'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_USERNAME',IMVar))
        unameE = Entry(box3, textvariable=IMVar)
        unameE.pack(side=RIGHT,fill=X,expand=YES)
        
        box4 = Frame(emailAccFrame)
        box4.pack(fill=X,expand=YES)
        passwordL = Label(box4,text='Account Password:',width=15)
        passwordL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_PASSWORD'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_PASSWORD',IMVar))
        passwordE = Entry(box4, textvariable=IMVar,show='*',width=17)
        passwordE.pack(side=LEFT,fill=X,expand=YES)
        passShowB = Button(box4,text='A',command=(lambda: self.showhidePWD(passwordE,passShowB)))
        passShowB.pack(side=RIGHT)
        createToolTip(passShowB,text='Show/Hide password')
        
        box4a = Frame(emailAccFrame)
        box4a.pack(pady=8)
        
        
        testSettingsVar = StringVar()
        self.testLabel = testSettingsVar
        self.testLabel.set('IMAP: Not Tested\nSMTP: Not Tested')
        testSetL = Label(box4a,textvariable=testSettingsVar)
        self.emailTestLabel = testSetL
        testSetL.pack()
        self.testBtnLabel = StringVar()
        self.testBtnLabel.set('Test Account Settings')
        testSetB = Button(box4a,textvariable=self.testBtnLabel,command=self.testEmail)
        testSetB.pack()
        
        boxOtherEmail = Frame(parent)
        boxOtherEmail.pack(fill=X,expand=YES)
        
        boxCR = Frame(boxOtherEmail)
        boxCR.pack(fill=X,expand=YES)
        createToolTip(boxCR,'Mail sent by lockwatcher will show this email address as sender')
        
        comRecL = Label(boxCR,text='Alert Sender Address:',width=17)
        comRecL.pack(side=LEFT)
        IMVar = StringVar()
        comRecE = Entry(boxCR,textvariable=IMVar)
        comRecE.pack(side=RIGHT,fill=X,expand=YES)
        IMVar.set(config['EMAIL']['COMMAND_EMAIL_ADDRESS'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:COMMAND_EMAIL_ADDRESS',IMVar))
        
        boxAR = Frame(boxOtherEmail)
        boxAR.pack(fill=X,expand=YES)
        createToolTip(boxAR,'Lockmonitor will send alerts, command responses and captured images to this email address.')
        authSecretL = Label(boxAR,text='Alert Email Address:',width=17)
        authSecretL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['ALERT_EMAIL_ADDRESS'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:ALERT_EMAIL_ADDRESS',IMVar))
        alertRecE = Entry(boxAR, textvariable=IMVar)
        alertRecE.pack(side=RIGHT,fill=X,expand=YES)
        
        
        box5 = Frame(boxOtherEmail)
        createToolTip(box5,'Secret code used by Lockwatcher to authenticate remote commands')
        box5.pack(fill=X,expand=YES)
        
        authSecretL = Label(box5,text='Authentication Secret:',width=17)
        authSecretL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_SECRET'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_SECRET',IMVar))
        self.secretCode = IMVar
        authSecretE = Entry(box5, textvariable=IMVar)
        authSecretE.pack(side=RIGHT,fill=X,expand=YES)
        
        genSecretBtn = Button(boxOtherEmail,text='Generate',command=self.genSecret)
        createToolTip(genSecretBtn,'Generate random new code. This must also be updated on the mobile device.')
        genSecretBtn.pack()
        
        box7 = Frame(boxOtherEmail)
        createToolTip(box7,'Number of bad commands to cause an emergency shutdown. 0 to disable.')
        box7.pack()
        numFailedL = Label(box7,text='Failed Command Limit:',width=17)
        numFailedL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['BAD_COMMAND_LIMIT'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:BAD_COMMAND_LIMIT',IMVar))
        numFailedE = Entry(box7, textvariable=IMVar,justify=CENTER, width = 5)
        numFailedE.pack(side=RIGHT)
    
    def genSecret(self):
        chars = string.ascii_letters + string.digits
        newCode = ''.join(random.choice(chars) for x in range(9))
        self.secretCode.set(newCode)
    
    def showhidePWD(self,entry,btn):
        if entry.cget('show') == '*':
            entry.config(show='')
            btn.config(text='*')
        else:
            entry.config(show='*')
            btn.config(text='A')
    
    def testEmail(self):
        if self.testThread == None:
            self.testBtnLabel.set('Test in progress...')
            self.testThread = hardwareconfig.emailTestThread(self.testEmailResults,fileconfig.config)
            self.testThread.start() 
        
    def testEmailResults(self,imapresult,smtpresult):
        self.testThread = None
        self.testBtnLabel.set('Test Account Settings')
        self.testLabel.set('%s\n%s'%(imapresult,smtpresult))
        
    def createShutdownPanel(self,parent):
        Label(parent,text='Shutdown Actions').pack()
        
        exeFrame = Frame(parent,borderwidth=2,relief=GROOVE)
        exeFrame.pack()
        
        self.TCCheck = StringVar()
        if config['TRIGGERS']['dismount_tc'] == 'True': self.TCCheck.set('True')
        else: self.TCCheck.set('False')
        tcCheck = Checkbutton(exeFrame,text="Dismount Truecrypt volumes",variable=self.TCCheck,
                                     onval='True',offval='False',
                                     command=(lambda: self.changeCheckBox('TRIGGERS:dismount_tc',self.TCCheck)))
        tcCheck.pack()
        
        TCPath = StringVar()
        if os.path.exists(config['TRIGGERS']['tc_path']):
            TCPath.set(config['TRIGGERS']['tc_path'])
        else:
            try:
                key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "TrueCryptVolume\\Shell\\open\\command")
                value =  winreg.QueryValue(key, None).split('"')[1]
                if os.path.exists(value):
                    TCPath.set(value)
                    config['TRIGGERS']['tc_path'] = value
                    writeConfig()
            except:
                TCPath.set('Truecrypt executable not found')
        
        
        
        Label(exeFrame,text='Truecrypt Executable:').pack(side=TOP)
        TCPathEntry = Entry(exeFrame,textvariable=TCPath,width=40)
        TCPathEntry.pack(side=LEFT)
        Button(exeFrame,text='Browse',command=self.chooseTCFile).pack(side = RIGHT)
        self.TCPath = TCPath
        
        
        self.ESCheck = StringVar()
        if config['TRIGGERS']['exec_shellscript'] == 'True': self.ESCheck.set('True')
        else: self.ESCheck.set('False')
        execCustom = Checkbutton(parent,text="Execute Custom Script on Shutdown", variable = self.ESCheck,
                                    onval='True',offval='False',command=(lambda: self.changeCheckBox('TRIGGERS:exec_shellscript',self.ESCheck)))
        createToolTip(execCustom, "Lockwatcher will check the specified IMAP inbox for remote commands")
        execCustom.pack()
        
        Label(parent,text='Custom shutdown batch script:',anchor=W,width=80).pack()

        sdScript = Text(parent,width=65,height=20)
        sdScript.pack(fill=BOTH,expand=YES,pady=5,padx=5)
        
        if not os.path.exists('sd.bat'):
            try:
                fd = open('sd.bat','w')
                fd.write('::batch script to execute on emergency shutdown')
                fd.close()
            except:
                addMessage('Failed to find or create shutdown batch file in lockwatcher directory')
            
        try:
            fd = open('sd.bat','r')
            battext = fd.read()
            fd.close()
        except:
            battext = "Failed to open sd.bat"
            
        sdScript.insert(INSERT,battext)
        self.sdScript = sdScript
        
        saveBtn = Button(parent,text='Save',command=self.writeSDScript).pack()
        
    def writeSDScript(self):
        fd = open('sd.bat','w')
        fd.write(self.sdScript.get(0.0,END))
        fd.close()
         
    def chooseTCFile(self):
        newpath = filedialog.askopenfilename(filetypes=[('Truecrypt.exe','.exe')])
        if newpath != '' and os.path.exists(newpath):
            self.TCPath.set(newpath)
            config['TRIGGERS']['tc_path'] = newpath
            writeConfig()
        




app = MainWindow(master=root)
root.mainloop()

lwMonitorThread.stop()
