'''
Created on 30 Oct 2013

@author: Nia Catlin

This is the little program that waits for lock commands from the lockwatcher service
and locks the screen from the users session (since local system services are not allowed)
'''
import socket, select, threading
import time, ctypes, sys
#should probably put this in a different module or something
#
#when the ui is run this thread is created and listens for lock commands from the service
#we dont really give any way of closing it thought so it makes uninstalling a pain
class lockerThread(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self.name = 'lockerThread'
    def run(self):
        try:
            s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            s.bind( ('127.0.0.1', 22189) )
            self.socket = s
        except:
            #already running, no problem. Unless something else is on 22189, then there is a problem.
            return
        
        while True:
            try:
                ready = select.select([s],[],[],120)
                if not ready[0]: continue
            except socket.error:
                try:
                    s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
                    s.bind(('127.0.0.1', 22189))
                    self.socket = s
                except:
                    time.sleep(1)
                    continue
            
            data = s.recv(64)
            command = data.decode('UTF-8')             
            
            if command == '1':
                ctypes.windll.user32.LockWorkStation()
            elif command == 'x':
                s.close()
                return

#allow starting/stopping the locker thread from the commandline 
#used on system startup and uninstallation         
if len(sys.argv) != 1:
    #terminate locker thread to allow uninstallation
    if sys.argv[1] == 'KillLocker':
        s = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        s.connect(('127.0.0.1', 22189))
        s.send('x')
        s.close()

else:   
    myLocker = lockerThread()
    myLocker.start()
    sys.exit()