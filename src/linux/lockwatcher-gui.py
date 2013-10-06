# -*- coding: iso-8859-15 -*-
'''
@author: Nia Catlin

needs packages python3, python3-pyudev, lm-sensors, python3-tk, python3-imaging
module: imapclient
'''
import socket, subprocess
import re, os, time
import string, random

import fileconfig, hardwareconfig
from fileconfig import config
import lockwatcher, sendemail

from tkinter import *
from tkinter import ttk
from tooltip import createToolTip
from tkinter import filedialog
from PIL import Image
#import ImageTK

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
                    OPT_LOGS:'Message Log',
                    OPT_BT:'Bluetooth Triggers',
                    OPT_MOTION:'Motion Triggers',
                    OPT_KBD:'Keyboard Triggers',
                    OPT_CHAS:'Chassis Triggers',
                    OPT_NET:'Network Triggers',
                    OPT_EMAIL:'Email Settings',
                    OPT_SHUT:'Shutdown Actions'}
    
root = Tk()
s = ttk.Style()

s.configure('TLabelframe.Label', background='lightgrey',foreground='royalblue')
s.configure('TLabelframe', background='lightgrey')

#todo: root.wm_iconbitmap('favicon.ico')

class MainWindow(Frame):
    kbdThread = None
    tempThread = None
    
    def __init__(self, master=None):
        Frame.__init__(self, master)
        self.pack()
        
        master.title("Lockwatcher configuration")
        master.minsize(400, 400)
        
        self.create_widgets(master)
        
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
                'ipc' : StringVar(),
                'bluetooth' : StringVar(),
                'killSwitch' : StringVar(),
                'temperature' : StringVar(),
                'devices' : StringVar(),
                'chassis_camera' : StringVar(),
                'room_camera' : StringVar(),
                'netadapters' : StringVar(),
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
        logPath.trace("w", lambda name, index, mode, logPath=logPath: self.newLogFile(self.logPath.get()))
        
        msgFrame = ttk.Labelframe(parent,text='Recent events:',relief=SUNKEN)
        msgFrame.pack(expand=YES,fill=BOTH,padx=4,pady=4)
        
        scrollbar = Scrollbar(msgFrame)
        scrollbar.pack(side=RIGHT, fill=Y)
        
        #todo: resize with window
        messageListB = Text(msgFrame,width=60,height=21,yscrollcommand=scrollbar.set,wrap=WORD)
        messageListB.pack(side=LEFT,expand=YES,fill=BOTH,padx=4,pady=4)
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
            
    def setFilePath(self,path):
        config['TRIGGERS']['logfile'] = path
        fileconfig.writeConfig()
             
    def createStatusPanel(self,parent):
        
        self.sStatusText = StringVar()
        self.sButtonText = StringVar()
        Label(parent,textvariable=self.sStatusText).pack(pady=5)
        Button(parent,textvariable=self.sButtonText,command=self.lwActivate).pack(pady=5)
        
        self.threadFrames = Frame(parent)
        boxWidth = 28
        
        Label(self.threadFrames,text='Right click individual monitors to start/stop them').pack(pady=5)
        Frame1 = Frame(self.threadFrames)
        
        BTFrame = ttk.LabelFrame(Frame1,text="Bluetooth Connection",name='bluetooth')
        BTFrame.pack(side=LEFT,padx=5)
        BTFrame.bind('<Button-3>',self.rClick,add='')
        BTLabel = Label(BTFrame,textvariable=self.threadStatus['bluetooth'],width=boxWidth,name='bluetooth')
        BTLabel.pack()
        BTLabel.bind('<Button-3>',self.rClick,add='')
        self.sBTLabel = BTLabel
        
        KSFrame = ttk.LabelFrame(Frame1,text="Keyboard Killswitches",name='killSwitch')
        KSFrame.pack(side=RIGHT,padx=5)
        KSFrame.bind('<Button-3>',self.rClick,add='')
        KSLabel = Label(KSFrame,textvariable=self.threadStatus['killSwitch'],width=boxWidth,name='killSwitch')
        KSLabel.pack()
        KSLabel.bind('<Button-3>',self.rClick,add='')
        self.sKSLabel = KSLabel
        Frame1.pack(fill=X,expand=YES)
        
        Frame2 = Frame(self.threadFrames)
        RAMFrame = ttk.LabelFrame(Frame2,text="RAM Temperature Drop",name='temperature')
        RAMFrame.pack(side=LEFT, padx=5)
        RAMFrame.bind('<Button-3>',self.rClick,add='')
        RAMLabel = Label(RAMFrame,textvariable=self.threadStatus['temperature'],width=boxWidth,name='temperature')
        RAMLabel.pack()
        RAMLabel.bind('<Button-3>',self.rClick,add='')
        self.sRAMLabel = RAMLabel
        
        devFrame = ttk.LabelFrame(Frame2,text="Device Changes",name='devices')
        devFrame.pack(side=RIGHT, padx=5)
        devFrame.bind('<Button-3>',self.rClick,add='')
        devLabel = Label(devFrame,textvariable=self.threadStatus['devices'],width=boxWidth,name='devices')
        devLabel.pack()
        devLabel.bind('<Button-3>',self.rClick,add='')
        self.sDevLabel = devLabel
        Frame2.pack(fill=X,expand=YES)
        
        Frame3 = Frame(self.threadFrames)
        cCamFrame = ttk.LabelFrame(Frame3,text="Chassis Movement",name='chassis_camera')
        cCamFrame.pack(side=LEFT,padx=5)
        cCamFrame.bind('<Button-3>',self.rClick,add='')
        cCamLabel = Label(cCamFrame,textvariable=self.threadStatus['chassis_camera'],width=boxWidth,name='chassis_camera')
        cCamLabel.pack()
        cCamLabel.bind('<Button-3>',self.rClick,add='')
        self.scCamLabel = cCamLabel
        
        cCamFrame = ttk.LabelFrame(Frame3,text="Room Movement",name='room_camera')
        cCamFrame.pack(side=LEFT,padx=5)
        cCamFrame.bind('<Button-3>',self.rClick,add='')
        cCamLabel = Label(cCamFrame,textvariable=self.threadStatus['room_camera'],width=boxWidth,name='room_camera')
        cCamLabel.pack()
        cCamLabel.bind('<Button-3>',self.rClick,add='')
        self.srCamLabel = cCamLabel
        Frame3.pack()
        
        Frame4 = Frame(self.threadFrames)
        mailFrame = ttk.LabelFrame(Frame4,text="Email Commands",name='email')
        mailFrame.pack(side=RIGHT,padx=5)
        mailFrame.bind('<Button-3>',self.rClick,add='')
        mailLabel = Label(mailFrame,textvariable=self.threadStatus['email'],width=boxWidth,name='email')
        mailLabel.pack()
        mailLabel.bind('<Button-3>',self.rClick,add='')
        self.sEmailLabel = mailLabel
        
        IPCFrame = ttk.LabelFrame(Frame4,text="Lock monitor",name='ipc')
        IPCFrame.pack(side=RIGHT,padx=5)
        IPCFrame.bind('<Button-3>',self.rClick,add='')
        IPCLabel = Label(IPCFrame,textvariable=self.threadStatus['ipc'],width=boxWidth,name='ipc')
        IPCLabel.pack()
        IPCLabel.bind('<Button-3>',self.rClick,add='')
        self.sIPCLabel = IPCLabel
        Frame4.pack()
        
        NetFrame = ttk.LabelFrame(self.threadFrames,text="Netadapter monitor",name='netadapters')
        NetFrame.pack(side=RIGHT,padx=5)
        NetFrame.bind('<Button-3>',self.rClick,add='')
        NetLabel = Label(NetFrame,textvariable=self.threadStatus['netadapters'],width=boxWidth,name='netadapters')
        NetLabel.pack()
        NetLabel.bind('<Button-3>',self.rClick,add='')
        self.sNetLabel = NetLabel
        
        '''
        TODO: for linux

        self.loadOnStartCheck = StringVar()
        self.loadOnStartCheck.set(startupRun)
        checkLoadOnStart = Checkbutton(parent,text="Load lockwatcher when Windows starts",variable=self.loadOnStartCheck,
                                    onval='True',offval='False',command=(lambda: self.setLoadOnStart(self.loadOnStartCheck.get())))
        checkLoadOnStart.pack()
        '''
        
        self.immediateMonitor = StringVar()
        self.immediateMonitor.set(config['TRIGGERS']['immediatestart'])
        checkImmediateRun = Checkbutton(parent,text="Activate monitoring when lockwatcher starts",variable=self.immediateMonitor,
                                    onval='True',offval='False',command=(lambda: self.changeCheckBox('TRIGGERS:immediatestart',self.immediateMonitor)))
        checkImmediateRun.pack()
        
        #run on startup if needed
        if self.justStarted == True:
            self.justStarted = False
            if config['TRIGGERS']['immediatestart'] == 'True':
                lockwatcher.createLockwatcher(self.threadStatus,self.addMessage)
                lockwatcher.monitorThread.start() 
                self.setupMonitorStrings()
                pass

        if lockwatcher.monitorThread != None:
            threadAlive = lockwatcher.monitorThread.is_alive()
        else: threadAlive = False
        
        if threadAlive == True:
            self.sStatusText.set("Lockwatcher is currently not active")
            self.sButtonText.set("Stop lockwatcher")
            
            #give the statuses their appropriate colour
            self.threadFrames.pack(pady=20)
            for triggerName,trigger in self.threadStatus.items():
                self.statusChange(triggerName, trigger)
        else:
            self.sStatusText.set("Lockwatcher is not active")
            self.sButtonText.set("Start lockwatcher")
            self.setupMonitorStrings()
        
            
    
    def setupMonitorStrings(self):
        defaultStr = "Not Started"
        for triggerName,triggerStr in self.threadStatus.items():
        
            if triggerName == 'netAdaptersIn':
                triggerStr.set('In: '+defaultStr)
            elif triggerName == 'netAdaptersOut':
                triggerStr.set('Out: '+defaultStr)
            else: triggerStr.set(defaultStr)
            
            triggerStr.trace("w", lambda name, index, mode, triggerName=triggerName, triggerStr=triggerStr: self.statusChange(triggerName,triggerStr))
        
           
    def rClick(self,frame):
        print('clicked ',frame.widget._name)
        commands=[
               ('Start', lambda frame=frame: self.optMonClicked(frame,'start')),
               ('Stop', lambda frame=frame: self.optMonClicked(frame,'stop'))
               ]
        cmdMenu = Menu(None,tearoff=0,takefocus=0)
        for (name,function) in commands:
            cmdMenu.add_command(label=name, command=function)
        cmdMenu.tk_popup(frame.x_root+40, frame.y_root+10,entry="0")
    
    def optMonClicked(self,frame,action):
        widgetName = frame.widget._name
        
        monitor = widgetName
        
        if action == 'start':
            print('starting ',monitor)
            lockwatcher.eventQueue.put(('startMonitor',monitor))
        else:
            print('stopping ',monitor)
            lockwatcher.eventQueue.put(('stopMonitor',monitor))
            
        
        
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
        label = self.listbox.get(index)
        if label != optionCategories[OPT_STATUS]:
            return
            
        triggerText = trigger.get()
        
        if triggerText == 'Active' or ': Active' in triggerText:
            newColour = 'green'
        elif '...' in triggerText:
            newColour = 'orange'
        elif 'Not Started' in triggerText :
            newColour = 'black'
        else:
            newColour = 'red'
        
        try:
            if triggerName == 'bluetooth':
                self.sBTLabel.config(fg=newColour)
            elif triggerName == 'temperature':
                self.sRAMLabel.config(fg=newColour)
            elif triggerName == 'devices':
                self.sDevLabel.config(fg=newColour)
            elif triggerName == 'killSwitch':
                self.sKSLabel.config(fg=newColour)
            elif triggerName == 'chassis_camera':
                self.scCamLabel.config(fg=newColour)  
            elif triggerName == 'room_camera':
                self.srCamLabel.config(fg=newColour) 
            elif triggerName == 'email':
                self.sEmailLabel.config(fg=newColour)
            elif triggerName == 'ipc':
                self.sIPCLabel.config(fg=newColour)
            elif triggerName == 'netadapters':
                self.sNetLabel.config(fg=newColour)
            else:
                print('Unhandled trigger update: ',triggerName)     
        except:
            #user probably destroyed label by changing tab, don't care  
            pass

    def lwActivate(self):
        if lockwatcher.monitorThread != None:
            threadAlive = lockwatcher.monitorThread.is_alive()
        else: threadAlive = False
        
        if threadAlive == False:
            self.sStatusText.set("Lockwatcher is active")
            self.sButtonText.set("Stop lockwatcher")
            
            lockwatcher.createLockwatcher(self.threadStatus,self.addMessage)
            lockwatcher.monitorThread.start()

            self.threadFrames.pack(pady=20)
        else:
            self.sStatusText.set("Lockwatcher is not active")
            self.sButtonText.set("Start lockwatcher")
            lockwatcher.eventQueue.put(('stop',None))
            print('waiting for thread to temrinate')
            while lockwatcher.monitorThread.is_alive():
                time.sleep(0.2)
            print('thread temrinated')    
            lockwatcher.monitorThread = None
            self.threadFrames.pack_forget()
        
    def createBluetoothPanel(self,parent):
        Label(parent,text='Lockwatcher will establish a connection to this bluetooth device.\
        \nShutdown will be triggered if the connection is lost.').pack()
        BTBox = ttk.LabelFrame(parent,text="Bluetooth devices")
        BTBox.pack(side=TOP, fill=BOTH, expand=YES, padx=4, pady=4)
        
        self.DevIDDict = {}
        
        BTDevList = Listbox(BTBox)
        if len(self.DevIDDict.keys()) > 0:
            for idx,dev in self.DevIDDict.items():
                BTDevList.insert(idx,"Name: %s    ID: %s"%(dev[1],dev[0]))

        
        BTDevList.selection_set(0)
        BTDevList.pack(side=TOP, fill=BOTH, expand=YES, padx=4, pady=4)
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
        
        devInfoID = Entry(devIDFrame,textvariable=devIDVar,justify=CENTER,bg='white')
        devInfoID.pack(side=BOTTOM,padx=4)
        
        
        devStatusFrame = Frame(devInfo)
        devStatusFrame.pack(side=RIGHT, fill=X, expand=YES)
        devStatusLabel = Label(devStatusFrame,text="Status: Unknown")
        devStatusLabel.pack(side=TOP,fill=X)
        self.devStatusLabel = devStatusLabel
        
        devStatusButton = Button(devStatusFrame,text='Test')
        devStatusButton.pack(side=BOTTOM)
        devStatusButton.bind('<Button-1>',self.BTDevTest) 
        self.btDevTestButton =  devStatusButton

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
                fileconfig.writeConfig()
                break
            
    BTScanStatus = None
    def BTDoScan(self,btn):
        if self.BTScanStatus == None:
            self.BTScanStatus = 'Running'
            print("launching scan thread")
            self.DevIDDict = {}
            self.scanBtnText.set('Scanning...')
            self.BTScan = hardwareconfig.BTScanThread(self.BTGotDevices)
            self.BTScan.start()
            print("Scan thread launched")
    
    def BTGotDevices(self,out,err):
        if self.BTScanStatus == 'Running':
            self.BTScanStatus = None
        
            self.scanBtnText.set('Scan for devices')
            
            self.BTDevList.delete(0,self.BTDevList.size()-1)
            
            if 'Device is not available' in str(err):
                self.BTDevList.insert(0,'Bluetooth not available')
                return
                
                
            results = str(out).split('\\n')
            BTList = []
            for line in results:
                line = line.strip('\\t')
                listEntry = line.split('\\t')
                if len(listEntry) != 2: continue
                BTList = BTList + [listEntry]
                    
            
            
            if len(BTList) == 0:
                self.BTDevList.insert(0,'No results')
                
            i = 0
            for dev in BTList:
                self.BTDevList.insert(i,"ID: %s (%s)"%(dev[0],dev[1]))
                self.DevIDDict[i] = dev
                i += 1
    
    testStatus = None
    def BTDevTest(self,button):
        print(self.testStatus)
        if self.testStatus == 'Running':
            pass
        else:   
            self.testStatus = 'Running'
            print("Testing ",self.devIDVar.get())
            self.BTTest= hardwareconfig.BTTestThread(self.BTTestResults,self.devIDVar.get())
            self.BTTest.start()
            self.devStatusLabel.config(text="Status: Testing")

    #todo: check for button mashing on windows
    def BTTestResults(self,result):
        print('got result.. ts:',self.testStatus,result)
        if self.testStatus == None:
            return
        else: self.testStatus = None
        self.devStatusLabel.config(text=result)
    
        
    
    def createChassisPanel(self,parent):
        
        RAMFrame =  ttk.LabelFrame(parent,text="Chassis Low Temperature Detection",borderwidth=1,relief=GROOVE)
        RAMFrame.pack()
        
        Label(RAMFrame,text="Availability/support for RAM temperature sensors is poor.\n"+
                            "Until then, here is a fairly useless motherboard temperature monitor.\n"+
                            "Setup a chassis motion camera for better protection against internal hardware attacks."
                            ,background='red').pack()
        
        TempSettingsF = Frame(RAMFrame)
        TempSettingsF.pack(pady=8,side=LEFT)
            
        minTempFrame = Frame(TempSettingsF)
        minTempFrame.pack() 
        
        Label(minTempFrame,text='Minimum temperature (°C):').pack(side=LEFT)
        
        tempVar = StringVar()
        tempVar.set(config['TRIGGERS']['low_temp'])
        tempVar.trace("w", lambda name, index, mode, tempVar=tempVar: self.newTriggerTemp(tempVar.get()))
        self.tempVar = tempVar
        minTempEntry = Entry(minTempFrame,textvariable=tempVar,width=5,justify=CENTER,bg='white')
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
        
        TempList = Listbox(TestFrame,height=5,bg='white')
        TempList.pack(padx=5,pady=5)
        self.TempList = TempList
        
        tempStatusL = Label(parent)
        tempStatusL.pack()
        self.tempStatusL = tempStatusL
        
        self.startTempTest()
        
    def newTriggerTemp(self,temp):
        try:
            float(temp)
            config['TRIGGERS']['low_temp'] = temp
            fileconfig.writeConfig()
        except ValueError:
            return #not a valid number
              
          
    def startTempTest(self): 
        if self.tempThread != None:
                self.tempThread.terminate()
        self.tempThread = hardwareconfig.temperatureMonitor(self.newTemperature)
        if self.tempThread.error != None:
            self.tempStatusL.configure(text=self.tempThread.error)
        else:
            self.tempThread.start()
    
    def newTemperature(self,temp):
        try:
            self.TempList.insert(0,temp)
        except:
            pass #user changed tab
    
    camList =[]
    def refreshCams(self): 
        cameraDetails = hardwareconfig.getCamNames()
        camLookup = {}
        for idx,dev in enumerate(cameraDetails):
            self.camList.append(cameraDetails[dev]['ID_MODEL'])
            
        self.chasCombo.config(values=list(self.camList))
        self.roomCombo.config(values=list(self.camList))
        
        self.cameraListBox.delete(0, self.cameraListBox.size()-1)
        if len(cameraDetails.keys()) > 0:
            for dev,details in cameraDetails.items():
                if 'ID_VENDOR' in details and 'ID_MODEL' in details:
                    self.cameraListBox.insert(0,"%s - (%s) %s"%(dev,details['ID_VENDOR'],details['ID_MODEL'])) 
                else:
                    self.cameraListBox.insert(0,"%s"%(dev)) 
        
        
        
    def createMotionPanel(self,parent):
        
        MINFRAMES_TT = 'Consecutive frames of motion to trigger activation.\nLower to increase sensitivity and reaction speed.\nRaise to reduce false positives and improve chance of capturing image of intruder.'
        FPS_TT = 'Frames capture per second.\nRaise to improve accuracy.\nLower to improve performance.'
        
        availableFrame = ttk.LabelFrame(parent,text='Available video devices')
        availableFrame.pack(fill=X,expand=YES,padx=8)
        
        cameraListBox = Listbox(availableFrame,bg='white')
        cameraListBox.pack(fill=X,expand=YES,padx=8)
        self.cameraListBox = cameraListBox
        
        Button(parent,text='Refresh Cameras',command=self.refreshCams).pack()

        cameraSettingsFrame = Frame(parent)
        cameraSettingsFrame.pack(pady=8)
        
        #-------------------room camera box
        if config.has_option('CAMERAS', 'room_cam'):
            roomCamDev = config['CAMERAS']['room_cam']
        else: roomCamDev = ''
        
        boxRoomAll = ttk.Labelframe(cameraSettingsFrame,text='Room monitoring camera',borderwidth=1,relief=GROOVE)
        boxRoomAll.pack(side=LEFT,padx=8)
        
        roomCamDev = config['CAMERAS']['cam_room']
        room_combo =  ttk.Combobox(boxRoomAll,values=self.camList,state='readonly',name='roomCam',width=26)
        room_combo.set(roomCamDev)
        room_combo.pack(padx=2,pady=3)
        room_combo.bind('<<ComboboxSelected>>', self.videoDevChange)
        self.roomCombo = room_combo
        
        boxMinFrames = Frame(boxRoomAll)
        boxMinFrames.pack()
        
        Label(boxMinFrames,text='Minimum motion frames:').pack()
        minFramesStr = StringVar()
        minFramesStr.set(config['CAMERAS']['room_minframes'])
        changeMF = lambda name, index, mode, minFramesStr=minFramesStr: self.changeEntryBox('CAMERAS:room_minframes',self.devIDVar)
        minFramesStr.trace("w", changeMF)
        minFramesE = Entry(boxMinFrames,textvariable=minFramesStr,bg='white')
        createToolTip(minFramesE,MINFRAMES_TT)
        minFramesE.pack()
        
        boxFramerate = Frame(boxRoomAll)
        boxFramerate.pack()
        
        Label(boxFramerate,text='Camera Framerate:').pack()
        framerateStr = StringVar()
        framerateStr.set(config['CAMERAS']['room_fps'])
        changeFR = lambda name, index, mode, framerateStr=framerateStr: self.changeEntryBox('CAMERAS:room_fps',self.devIDVar)
        framerateStr.trace("w", changeFR)
        framerateE = Entry(boxFramerate,textvariable=framerateStr,bg='white')
        createToolTip(framerateE,MINFRAMES_TT)
        framerateE.pack()
        
        boxTol_TT='Number of changed pixels to signify motion.\nLower to improve sensitivity. Raise to reduce false positives.'
        boxTolerance = Frame(boxRoomAll)
        boxTolerance.pack()
        
        Label(boxTolerance,text='Pixel Change Threshold:').pack()
        pixchangeStr = StringVar()
        pixchangeStr.set(config['CAMERAS']['room_threshold'])
        changePC = lambda name, index, mode, pixchangeStr=pixchangeStr: self.changeEntryBox('CAMERAS:room_threshold',self.devIDVar)
        pixchangeStr.trace("w", changePC)
        pixchangeE = Entry(boxTolerance,textvariable=pixchangeStr,bg='white')
        createToolTip(pixchangeE,boxTol_TT)
        pixchangeE.pack()
        
        triggerFrame =  ttk.LabelFrame(boxRoomAll,text="Trigger Condition",borderwidth=1,relief=GROOVE)
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
        
        sendImgBox = Frame(boxRoomAll)
        sendImgBox.pack()
        
        doSave = config['CAMERAS']['room_savepicture']
        self.SICheckVar = StringVar()
        if doSave == '': self.SICheckVar.set('False')
        else: self.SICheckVar.set('True')
        sendImgCheck = Checkbutton(sendImgBox,text="Save Captured Image", variable = self.SICheckVar,
                                    onval='True',offval='False',command=(lambda: self.changeCheckBox('CAMERAS:room_savepicture',self.SICheckVar)))
        createToolTip(sendImgCheck,'Saves a JPEG of the detected movement to disk.\nConfigure to send by email in the email settings pane.')
        sendImgCheck.pack()
        
        #-----------------chassis camera box
        if config.has_option('CAMERAS', 'chassis_cam'):
            chasCamDev = config['CAMERAS']['chassis_cam']
        else: chasCamDev = ''
        
        boxChasAll = ttk.Labelframe(cameraSettingsFrame,text='Chassis monitoring camera',borderwidth=1,relief=GROOVE)
        boxChasAll.pack(side=RIGHT,padx=8,fill=Y)
        
        chasCamDev = config['CAMERAS']['cam_chassis']
        chas_combo =  ttk.Combobox(boxChasAll,values=self.camList,state='readonly',name='chasCam',width=26)
        chas_combo.set(chasCamDev)
        chas_combo.pack(padx=2,pady=3)
        chas_combo.bind('<<ComboboxSelected>>', self.videoDevChange)
        self.chasCombo = chas_combo
        
        boxMinFrames = Frame(boxChasAll)
        boxMinFrames.pack()
        
        Label(boxMinFrames,text='Minimum motion frames:').pack()
        minFramesStr = StringVar()
        minFramesStr.set(config['CAMERAS']['chassis_minframes'])
        changeMF = lambda name, index, mode, minFramesStr=minFramesStr: self.changeEntryBox('CAMERAS:chassis_minframes',self.devIDVar)
        minFramesStr.trace("w", changeMF)
        minFramesE = Entry(boxMinFrames,textvariable=minFramesStr,bg='white')
        createToolTip(minFramesE,MINFRAMES_TT)
        minFramesE.pack()
        
        boxFramerate = Frame(boxChasAll)
        boxFramerate.pack()
        
        Label(boxFramerate,text='Camera Framerate:').pack()
        framerateStr = StringVar()
        framerateStr.set(config['CAMERAS']['chassis_fps'])
        changeFR = lambda name, index, mode, framerateStr=framerateStr: self.changeEntryBox('CAMERAS:chassis_fps',self.devIDVar)
        framerateStr.trace("w", changeFR)
        framerateE = Entry(boxFramerate,textvariable=framerateStr,bg='white')
        createToolTip(framerateE,MINFRAMES_TT)
        framerateE.pack()
        
        boxTol_TT='Number of changed pixels to signify motion.\nLower to improve sensitivity. Raise to reduced false positives.'
        boxTolerance = Frame(boxChasAll)
        boxTolerance.pack()
        
        Label(boxTolerance,text='Pixel Change Threshold:').pack()
        pixchangeStr = StringVar()
        pixchangeStr.set(config['CAMERAS']['chassis_threshold'])
        changePC = lambda name, index, mode, pixchangeStr=pixchangeStr: self.changeEntryBox('CAMERAS:chassis_threshold',self.devIDVar)
        pixchangeStr.trace("w", changePC)
        pixchangeE = Entry(boxTolerance,textvariable=pixchangeStr,bg='white')
        createToolTip(pixchangeE,boxTol_TT)
        pixchangeE.pack()
                
        triggerFrame =  ttk.LabelFrame(boxChasAll,text="Trigger Condition",borderwidth=1,relief=GROOVE)
        triggerFrame.pack(pady=5)
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
        
        self.refreshCams()
        
    #choose whether to trigger before or after a camera capture has been saved
    #todo change this like the others
    def togglePictureEmail(self,newstate):
        config['CAMERAS']['room_savepicture'] = newstate
        fileconfig.writeConfig()   
           
    def videoDevChange(self,combo):
        

        newDev = combo.widget.get()
        
        if combo.widget._name == 'roomCam':
            config['CAMERAS']['cam_room'] = newDev
            
            if newDev == self.chasCombo.get():
                self.chasCombo.set('')
                config['CAMERAS']['cam_chassis'] = ''
        else:
            config['CAMERAS']['cam_chassis'] = newDev

            if newDev == self.roomCombo.get():
                self.roomCombo.set('')
                config['CAMERAS']['cam_room'] = ''
        fileconfig.writeConfig()
                 
    def motionEntryChange(self,entry):
        entryName = entry.get_name()
        var, cam = entryName.split('-')
        
        if cam == 'R':
            file = ROOM_MOTION_CONF
        elif cam == 'C':
            file = CHASSIS_MOTION_CONF
            
        value = entry.get_text()
        if var == 'MinFrames': 
            fileconfig.writeMotionConfig(file,'minimum_motion_frames',value)
        elif var == 'FPS':
            fileconfig.writeMotionConfig(file,'framerate',value)
        elif var == 'tol':
            fileconfig.writeMotionConfig(file,'threshold',value) 
            
    KCodes = [] 
    def createKeyboardPanel(self,parent):
        
        #if not os.path.exists(config['TRIGGERS']['keyboard_device']):
        fd = open('/proc/bus/input/devices')
        text = fd.read()
        #very important: test this on other hardware
        matchObj = re.search(r'sysrq kbd (event\d+)', text, flags=0)
        if matchObj:
            config['TRIGGERS']['keyboard_device'] = '/dev/input/'+matchObj.group(1)
            fileconfig.writeConfig()
        else: 
            if not os.path.exists(config['TRIGGERS']['keyboard_device']):
                print('Keyboard device not found')
            
        Label(parent,text='Setup a killswitch combination of one or more keys').pack(padx=5)
        
        entryFrame = Frame(parent)
        entryFrame.pack()
        
        IMVar = StringVar()
        IMVar.set('Captured key codes appear here')
        self.IMVar = IMVar
        showKeysBox = Entry(entryFrame,textvariable=IMVar,width=40,state=DISABLED,bg='white')
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
        Label(primaryFrame,text='Current Key Combination:').pack(pady=5)
        
        if config.has_option('TRIGGERS', 'kbd_kill_combo_1'):
            combo = config['TRIGGERS']['kbd_kill_combo_1_txt']
        else: combo = ''
        
        KS1Label = Label(primaryFrame,text=combo)
        KS1Label.pack()
        self.KS1Label = KS1Label
        
        self.kbdThread = hardwareconfig.kbdListenThread(self.gotKbdKey,config['TRIGGERS']['keyboard_device'])
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
        if config.has_option('TRIGGERS', 'kbd_kill_combo_2_txt'):
            combo = config['TRIGGERS']['kbd_kill_combo_2_txt']
        else: combo = ''
        KS2Label = Label(secondaryFrame,text=combo)
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
        
    def saveKbdCombo(self,number):
            newcombo = ''
            for x in self.KCodes:
                newcombo = newcombo+str(x)+'+'
            newcombo = newcombo.strip('+')

            if number == 1:
                config['TRIGGERS']['kbd_kill_combo_1'] = newcombo
                config['TRIGGERS']['kbd_kill_combo_1_txt'] = self.showKeysBox.get()
                self.KS1Label.config(text=self.showKeysBox.get())
            else:
                config['TRIGGERS']['kbd_kill_combo_2'] = newcombo
                config['TRIGGERS']['kbd_kill_combo_2_txt'] = self.showKeysBox.get()
                self.KS2Label.config(text=self.showKeysBox.get())
            fileconfig.writeConfig()
            
    def clearKeys(self):
        self.IMVar.set('')
        self.KCodes = []
    
    def gotKbdKey(self,key,keyName):
        if key == 0x01: return #bad things happen if mouse L used
        try:
            text = self.showKeysBox.get()
        except:
            pass #some keys move focus around and mess things up
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
        
    deviceList={}
    def createNetworkPanel(self,parent):

        if os.path.exists('./ifplugstatus'):
            ifppath = './ifplugstatus'
        elif os.path.exists('/usr/sbin/ifplugstatus'):
            ifppath = '/usr/sbin/ifplugstatus'
        else:
            ifppath = None
            
        if ifppath != None:
            Label(parent,text="Network adapter monitoring - Select devices to monitor").pack()
        else:
            Label(parent,text="Network adapter monitoring\nRequires ifplugstatus\nInstall ifplugd or place ifplugstatus in lockwatcher directory",bg='red').pack()
            return
        
        
        if not os.path.exists('./ifplugstatus'):
            Label(parent,text="ifplugd is required - disabling network interface monitoring").pack()
            return None
        else:
            
            out = subprocess.check_output(['./ifplugstatus'])
            devString = out.decode("utf-8").strip('\n').split('\n')
            for idx,dev in enumerate(devString):
                self.deviceList[idx] = dev.split(': ')
        
        adaptersFrame = Frame(parent)
        adaptersFrame.pack(pady=10,padx=8)
        
        adapterInFrame = ttk.LabelFrame(adaptersFrame,text="Adapter Connection",borderwidth=1,relief=GROOVE)
        adapterInFrame.pack(side=LEFT,padx=8)
        
        adapterListBoxIn = Listbox(adapterInFrame,selectmode=MULTIPLE,name='adaptercon',exportselection=False)
        adapterListBoxIn.pack(padx=4,pady=4)
        self.adaptersIn = adapterListBoxIn
        #("Available interfaces (Highlighted = Monitored)", combo_cell_text, text=0)
        #sel;ection mode multiple

        if len(devString) > 0:
            for idx,dev in self.deviceList.items():
                adapterListBoxIn.insert(idx,"%s (%s)"%(dev[0],dev[1]))
                if dev[0] in fileconfig.config['TRIGGERS']['adapterconids']:
                    adapterListBoxIn.selection_set(idx)

        else:
            adapterListBoxIn.insert(0,'No network interfaces found')
            
        adapterListBoxIn.bind('<<ListboxSelect>>', self.netDevSelect)
        
        triggerFrame =  ttk.LabelFrame(adapterInFrame,text="Trigger Condition",borderwidth=1,relief=GROOVE)
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
        
        adapterOutFrame = ttk.LabelFrame(adaptersFrame,text="Adapter Disconnection",borderwidth=1,relief=GROOVE)
        adapterOutFrame.pack(side=RIGHT,padx=8)
        
        adapterListBoxOut = Listbox(adapterOutFrame,selectmode=MULTIPLE,name='adapterdiscon',exportselection=False)
        adapterListBoxOut.pack(padx=4,pady=4)
        self.adaptersOut = adapterListBoxOut
        #("Available interfaces (Highlighted = Monitored)", combo_cell_text, text=0)
        #sel;ection mode multiple

        if len(devString) > 0:
            for idx,dev in self.deviceList.items():
                adapterListBoxOut.insert(idx,"%s (%s)"%(dev[0],dev[1]))
                if dev[0] in fileconfig.config['TRIGGERS']['adapterdisconids']:
                    adapterListBoxOut.selection_set(idx)

        else:
            adapterListBoxOut.insert(0,'No network interfaces found')
            
        adapterListBoxOut.bind('<<ListboxSelect>>', self.netDevSelect)
        
        triggerFrame =  ttk.LabelFrame(adapterOutFrame,text="Trigger Condition",borderwidth=1,relief=GROOVE)
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
        
    def netDevSelect(self,lbox):
        
        inselections= self.adaptersIn.curselection()
        
        inIFs = ''
        for interface in inselections:
            val=self.deviceList[int(interface)]
            ifname = val[0]
            inIFs = inIFs + ifname+','
        inIFs = inIFs.strip(',')
        
        outselections= self.adaptersOut.curselection()
        outIFs = ''
        for interface in outselections:
            val=self.deviceList[int(interface)]
            ifname = val[0]
            outIFs = outIFs + ifname+','
        outIFs = outIFs.strip(',')
        
        
        fileconfig.config['TRIGGERS']['adapterconids'] = inIFs
        fileconfig.config['TRIGGERS']['adapterdisconids'] = outIFs
        
        fileconfig.writeConfig()
        
    
    def changeCheckBox(self, keyname, val):
        section,key = keyname.split(':')
        config[section][key] = str(val.get())
        fileconfig.writeConfig()
        
    def changeEntryBox(self, keyname, val):
        section,key = keyname.split(':')
        config[section][key] = str(val.get())
        fileconfig.writeConfig()
        
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
        createToolTip(checkEmailSend,'Lockwatcher will send an alert by email when an emergency shutdown is triggered')
        checkEmailSend.pack()
        
        self.emailImageCheck = StringVar()
        if config['EMAIL']['email_alert'] == 'True': self.emailImageCheck.set('True')
        else: self.emailImageCheck.set('False')
        checkEmailSend = Checkbutton(box6,text="Email Captured Image",variable=self.emailImageCheck,
                                     onval='True',offval='False',command=(lambda: self.changeCheckBox('EMAIL:email_motion_picture',self.emailImageCheck)))
        createToolTip(checkEmailSend,'Lockwatcher will email an image captured by a motion trigger.\n'+ \
                                    'Requires email alerts and motion image saving to be enabled\n' +\
                                    'May delay shutdown by several seconds.')
        checkEmailSend.pack()
        
        
        emailAccFrame =  ttk.LabelFrame(parent,text="Email Account Settings",borderwidth=1,relief=GROOVE)
        emailAccFrame.pack(padx=2,pady=6,fill=X,expand=YES)
        
        Label(emailAccFrame,text='Used to send alerts and receive\n commands from your remote device').pack()
        
        box1 = Frame(emailAccFrame)
        box1.pack(fill=X,expand=YES)
        
        IMAPServerL = Label(box1,text='IMAP Server:',width=15)
        IMAPServerL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_IMAP_HOST'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_IMAP_HOST',IMVar))
        IMAPServerE = Entry(box1,textvariable=IMVar,bg='white')
        IMAPServerE.pack(side=RIGHT,fill=X,expand=YES)
        
        box2 = Frame(emailAccFrame)
        box2.pack(fill=X,expand=YES)
        
        SMTPServerL = Label(box2,text='SMTP Server:',width=15)
        SMTPServerL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_SMTP_HOST'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_SMTP_HOST',IMVar))
        SMTPServerE = Entry(box2, textvariable=IMVar,bg='white')
        SMTPServerE.pack(side=LEFT,fill=X,expand=YES)
        
        box3 = Frame(emailAccFrame)
        box3.pack(fill=X,expand=YES)
        
        unameL = Label(box3,text='Account Username:',width=15)
        unameL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_USERNAME'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_USERNAME',IMVar))
        unameE = Entry(box3, textvariable=IMVar,bg='white')
        unameE.pack(side=RIGHT,fill=X,expand=YES)
        
        box4 = Frame(emailAccFrame)
        box4.pack(fill=X,expand=YES)
        passwordL = Label(box4,text='Account Password:',width=15)
        passwordL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['EMAIL_PASSWORD'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:EMAIL_PASSWORD',IMVar))
        passwordE = Entry(box4, textvariable=IMVar,show='*',width=17,bg='white')
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
        createToolTip(boxCR,'Lockwatcher will process emails claiming to be from this email address')
        
        comRecL = Label(boxCR,text='Alert Sender Address:',width=17)
        comRecL.pack(side=LEFT)
        IMVar = StringVar()
        comRecE = Entry(boxCR,textvariable=IMVar,bg='white')
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
        alertRecE = Entry(boxAR, textvariable=IMVar,bg='white')
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
        authSecretE = Entry(box5, textvariable=IMVar,bg='white')
        authSecretE.pack(side=RIGHT,fill=X,expand=YES)
        
        genSecretBtn = Button(boxOtherEmail,text='Generate',command=self.genSecret)
        createToolTip(genSecretBtn,'Generate random secret code. This must also be updated on the mobile device.')
        genSecretBtn.pack(pady=5)
        
        box7 = Frame(boxOtherEmail)
        createToolTip(box7,'Number of bad commands to cause an emergency shutdown. 0 to disable.')
        box7.pack()
        numFailedL = Label(box7,text='Failed Command Limit:',width=17)
        numFailedL.pack(side=LEFT)
        IMVar = StringVar()
        IMVar.set(config['EMAIL']['BAD_COMMAND_LIMIT'])
        IMVar.trace("w", lambda name, index, mode, IMVar=IMVar: self.changeEntryBox('EMAIL:BAD_COMMAND_LIMIT',IMVar))
        numFailedE = Entry(box7, textvariable=IMVar,justify=CENTER, width = 5,bg='white')
        numFailedE.pack(side=RIGHT,padx=4)
    
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
        self.DMCheck = StringVar()
        if config['TRIGGERS']['dismount_dm'] == 'True': self.DMCheck.set('True')
        else: self.TCCheck.set('False')
        dmCheck = Checkbutton(parent,text="Dismount dm-crypt/LUKS volumes",variable=self.DMCheck,
                                     onval='True',offval='False',
                                     command=(lambda: self.changeCheckBox('TRIGGERS:dismount_dm',self.DMCheck)))
        createToolTip(dmCheck,'Will dismount any volumes in /dev/mapper containing the word "crypt"')
        dmCheck.pack()
        
        exeFrame = ttk.Labelframe(parent,text='Truecrypt',borderwidth=2,relief=GROOVE)
        exeFrame.pack()
        
        self.TCCheck = StringVar()
        if config['TRIGGERS']['dismount_tc'] == 'True': self.TCCheck.set('True')
        else: self.TCCheck.set('False')
        tcCheck = Checkbutton(exeFrame,text="Dismount Truecrypt volumes",variable=self.TCCheck,
                                     onval='True',offval='False',
                                     command=(lambda: self.changeCheckBox('TRIGGERS:dismount_tc',self.TCCheck)))
        createToolTip(tcCheck,'Will force dismount any mounted Truecrypt volumes using the Truecrypt executable below')
        tcCheck.pack()
        
        TCPath = StringVar()
        if os.path.exists(config['TRIGGERS']['tc_path']):
            TCPath.set(config['TRIGGERS']['tc_path'])
        else:
            try:
                TCPathGuess = '/usr/bin/truecrypt'
                if os.path.exists(TCPathGuess):
                    TCPath.set(TCPathGuess)
                    config['TRIGGERS']['tc_path'] = TCPathGuess
                    fileconfig.writeConfig()
                else:
                    TCPath.set('Truecrypt executable not found')
            except:
                TCPath.set('Truecrypt executable not found')
        
        Label(exeFrame,text='Truecrypt Executable:').pack(side=TOP)
        TCPathEntry = Entry(exeFrame,textvariable=TCPath,width=40,bg='white')
        TCPathEntry.pack(side=LEFT)
        Button(exeFrame,text='Browse',command=self.chooseTCFile).pack(side = RIGHT)
        self.TCPath = TCPath
        
        sdFrame = ttk.Labelframe(parent,text='Custom shutdown shell script',width=80)
        sdFrame.pack()
        
        self.ESCheck = StringVar()
        if config['TRIGGERS']['exec_shellscript'] == 'True': self.ESCheck.set('True')
        else: self.ESCheck.set('False')
        execCustom = Checkbutton(sdFrame,text="Execute Custom Script on shutdown", variable = self.ESCheck,
                                    onval='True',offval='False',command=(lambda: self.changeCheckBox('TRIGGERS:exec_shellscript',self.ESCheck)))
        createToolTip(execCustom, "On emergency shutdown, the script below will be executed as the last action before the system is powered off.")
        execCustom.pack()
        
        timeoutFrame = Frame(sdFrame)
        timeoutFrame.pack()
        
        scriptTO = StringVar()
        scriptTO.set(config['TRIGGERS']['script_timeout'])
        Label(timeoutFrame,text='Script maximum running time (seconds):').pack(side=LEFT)
        scriptTimeoutE = Entry(timeoutFrame,textvariable=scriptTO,width=8,bg='white')
        createToolTip(scriptTimeoutE,'Lockwatcher will wait this many seconds for the script to complete before shutting down.\n0 = Unlimited.')
        scriptTimeoutE.pack(side=RIGHT,padx=4)
        changeTO = lambda name, index, mode, scriptTO=scriptTO: self.changeEntryBox('TRIGGERS:script_timeout',scriptTO)
        scriptTO.trace("w", changeTO)

        sdScript = Text(sdFrame,width=65,height=20,bg='white')
        sdScript.pack(fill=BOTH,expand=YES,pady=5,padx=5)
        
        if not os.path.exists('./sd.sh'):
            try:
                fd = open('./sd.sh','w')
                fd.write('#shell script to execute on emergency shutdown')
                fd.close()
            except:
                addMessage('Failed to find or create shutdown batch file in lockwatcher directory')
            
        try:
            fd = open('./sd.sh','r')
            battext = fd.read()
            fd.close()
        except:
            battext = "Failed to open sd.bat"
            
        sdScript.insert(INSERT,battext)
        self.sdScript = sdScript
        
        saveBtn = Button(sdFrame,text='Save Script',command=self.writeSDScript).pack()
        
    def writeSDScript(self):
        fd = open('sd.sh','w')
        fd.write(self.sdScript.get(0.0,END))
        fd.close()
         
    def chooseTCFile(self):
        newpath = filedialog.askopenfilename(filetypes=[('Truecrypt.exe','.exe')])
        if newpath != '' and os.path.exists(newpath):
            self.TCPath.set(newpath)
            config['TRIGGERS']['tc_path'] = newpath
            fileconfig.writeConfig()

app = MainWindow(master=root)
app.config(background='white')
root.mainloop()

if lockwatcher.monitorThread != None and lockwatcher.monitorThread.is_alive():
    lockwatcher.eventQueue.put(('stop',None))
    
print('cleaned up, leaving')