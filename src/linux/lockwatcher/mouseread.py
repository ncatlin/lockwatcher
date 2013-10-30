'''
Created on 15 Oct 2013

@author: root
'''
import struct, select, re

def getMouseDevice():
    fd = open('/proc/bus/input/devices')
    text = fd.read()
    #very important: test this on other hardware
    matchObj = re.search(r'mouse0 (event\d+)', text, flags=0)
    if matchObj:
        newInput = '/dev/input/'+matchObj.group(1)
        return newInput

mouse_device = '/dev/input/event3'
dev = open(mouse_device,'rb')
running = True
print(getMouseDevice())
while running == True:

    mouseEventFormat = 'llHHI'
    keyEventSize = struct.calcsize(mouseEventFormat)
    
    #wait for new input on keyboard device
    pollobject = select.poll()
    pollobject.register(dev)

    print('kes: %s'%keyEventSize)
    listening = True
    while listening == True:
        result = pollobject.poll(1)
        
        if result[0][1] != 5: continue
        
        event = dev.read(keyEventSize)
        (time1, time2, eType, kCode, value) = struct.unpack(mouseEventFormat, event)
        if eType == 0: continue
        if kCode in [8,272,273,274] or value < 0:print('pressed')
        if value > 1: print('moved')
        print(str(struct.unpack(mouseEventFormat, event)))

        