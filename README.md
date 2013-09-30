lockwatcher
===========

Anti-forensic monitor program: watches for signs of tampering or forensic aquisition, purges encryption keys and shuts 
everything down.

It was thought up when writing a proof of concept for defeating live forensic analysis as part of a masters thesis
 that evaluated anti-forensic techniques.
 
Why?
=====
Operating systems have improved physical security over recent years (eg: by not allowing auto-run when 
the screen is locked) but even if they ignore a CD being inserted into the drive while the computer is locked, they
 are still sitting there happily allowing someone to keep trying to get your data. 
 
 This is bad. 
 
 Lockwatcher is built around the assumption that if someone tries to use your computer while it is locked
 then they are trying to get your live data, so it needs to be destroyed.
 
*How lockwatcher works*

* You lock computer whenever not physically present at it.

* Interaction* with the computer while locked triggers an emergency shutdown.

* Encryption keys are purged from memory and the computer shuts down to help prevent live data from being aquired.


Caveats:
==========
The software was designed for running on live-CD/live-USB Linux, where dismounting (deniably) encrypted storage and 
powering down is accomplished in 3-5 seconds or less, with little warning given to the attacker. 
 
There is a Windows version but even forced shutdown is SLOW and obvious, and the difficulty in running it 
from ramdisk (live-usb,etc) means you are likely to have lots of interesting things on disk even if they can't 
get your RAM out in time.
 
It is specifically designed for defeating live memory aquisition.

It does not protect against disk analysis. That is what encryption is for, but Lockwatcher will help keep your
keys safe.

It does not stop malicious software from stealing your data. Good information security practice will help, running 
a live distribution from read-only media will help and doing your sensitive stuff on a computer that does not 
talk to the internet will help but this is a big problem.

It offers very little protection from surveillance. Although it can be configured to save (or email) a photo of
an intruder in the room, this isn't an insurmountable obstacle to someone who wants to use cameras, microphones, 
RF monitoring equipment and so on.

It does not protect you from having someone beat you with a wrench (or threaten prison time) to get your 
encryption keys. Deniable encryption might help, but using it effectively requires a lot of diligence.

There can be false positives. A device failing or a cat walking around the room can scare the system into 
shutting down. By defauly a shutdown isn't very destructive, so this should only be a nuisance if it happens.

*What kind of 'Interaction' are we talking about?
=============
There are lots of triggers for an emergency shutdown which can be tailored for the environment 
the computer is running in.

* Device monitoring

Any devices or disks being plugged into the system or removed. USB, Firewire, CDs, etc.

* Keyboard killswitch

One or more keyboard keys can be set to trigger an emergency shutdown if you are at the computer when it is required.

* Network interface monitoring

If the standard procedure of isolating the computer from the network is followed, or an attacker inserts/removes 
a network cable to listen to traffic then lockwatcher will notice this and trigger a shutdown.

* Bluetooth monitoring

Lockwatcher can connect to a Bluetooth device and trigger a shutdown if this connection is severed. This is useful 
if your devices are removed, turned off or placed in a shielded container by an attacker. If you have a device which
 can be quickly turned off or parted from its batteries then this becomes a handy portable killswitch when you are 
 not at the computer.
 
* RAM temperature detection

The first defence against RAM aquisition by freezing/removing memory modules 
(see: https://citp.princeton.edu/research/memory/)

The availability of memory modules with temperature sensors is bad so at the moment Lockwatcher only
supports monitoring Crucial Ballistix modules, and only on Windows (requires installing the Ballistix MOD utility).
Anyone who would like to contribute code to read temperature directly and/or from other types of RAM like 
HWMonitor does then would be appreciated.

* Chassis movement detection

A much better defence against RAM aquisition, but fiddly to set up and requires some hardware.

You need a webcam. Any webcam: A £5 no-brand horror will be fine. Your motherboard or camera should also have an
LED or two to give the case a bit of light inside.

Now the tricky bit: Suspend it in the computer case so it can swing freely. Use tape, string, whatever: just make sure
 the camera is free to swing a little when the case itself is moved. It also needs to be plugged in to USB, 
 preferably to an internal USB port.
 
 ![It is easier if your case is not cable-managment hell](casepicture1.png)
 
If the case is securely shut (preferably with a lock) then any movement of the case or attempts to open it up will
 either move the camera or change the lighting conditions in the chassis, triggering a shutdown long before the
 RAM or BIOS can be tampered with. This also helps prevent hot-plug attacks against self-encrypting hard drives.

This trigger (and the one below) requires some free motion detection software: motion on Linux, iSpy on Windows. 

* Room movement detection

A camera can be pointed at the room to shut down when any motion is detected. Not too useful if pets/family/coworkers
 are expected to be in the same room as the computer while you are away.
 
This trigger can be activated and deactivated remotely so the system doesn't shutdown 
whenever you return to the computer. 

This also allows a photo to be saved or emailed to alert you to the identity of the attacker.

* Not yet implemented - Intrusion switch monitoring

Trigger a shutdown if the case is opened and the motherboard intrusion detection switch is activated. 

* Not yet implemented - Power supply monitoring

The room motion trigger could in theory be circumvented by cutting power to the room and then taking the memory
 modules. If the case is reasonably secure then there is minimal chance of this being successful, but a transition 
 from mains power to uninterruptable power supply could be used as a trigger. And cause false positives in a 
 power outage.


Linux Installation
================
These packages are required
* sudo apt-get install motion ifplugd lm-sensors 

* Install Imapclient (https://pypi.python.org/pypi/IMAPClient/0.10.2) by whatever method is convenient 

* [download/unzip lockwatcher]

* sudo setupfiles/setup.sh

Linux Configuration
================
sudo src/lockwatcher-gui/lockwatcher-gui.py

![Configure further via the GUI](guipicture.png)


Running on Linux
============
sudo src/lockwatcher.py start


Windows Installation
================
*The free, open-source iSpy software is required for room and chassis motion detection

Get it here: http://www.ispyconnect.com/download.aspx
Install it, configure your cameras (covered later).

* Install lockwatcher from the msi, or just extract the .zip somewhere

Windows Configuration and Running
================

* Run lockwatcher.exe, play with the settings
* 

Installing + Using remote control
====================
(I know this is a bit of a pain, hopefully a native app will be up and running for iOS and Android at some point)
* Install QPython on your Android device

* Go to http://qpython.com/create.php, paste in mobilecontrol.py

* Edit emails,password to your liking and add the authentication secret

* Generate the QRCode, scan with QPython on your phone

* Save it as a script
 
* Whenever you want to use it, open QPython and execute the script

![The mobile control interface](mcpicture.png)


To-do list
===========
The whole qpython thing is a bit of a pain to use: an app could be much nicer

RAM temperature monitoring on Linux. My motherboard won't play nice with decode-dimms and I havent had much luck 
doing what the ballistix MOD utility does. 
Also: other types of RAM

Testing and better install configurations for other linux distros
