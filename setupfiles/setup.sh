#!/bin/bash
SETUPDIR="./new"

#backup any old motion config
MOTDIR="/etc/motion"
if [ -d "$MOTDIR" ]; then
	mv /etc/motion/motion.conf /etc/motion/motion.conf.bk
else
	echo /etc/motion not found... is motion installed?
	exit
fi
cp -r ./Init/motion/motion.conf /etc/motion/motion.conf

if [ -d "/etc/motion2" ]; then
	mv /etc/motion2/motion2.conf /etc/motion2/motion2.conf.bk
else
	mkdir /etc/motion2
fi

#copy preconfigured files to the system for motion
cp -r $SETUPDIR/motion2/motion2.conf /etc/motion2/motion2.conf

cp $SETUPDIR/init.d/motion /etc/init.d
cp $SETUPDIR/init.d/motion2 /etc/init.d
ln -s /usr/bin/motion /usr/bin/motion2

cp $SETUPDIR/defaults/motion /etc/default
cp $SETUPDIR/defaults/motion2 /etc/default

ARCH=`/bin/uname -m` 
PYDIST=/usr/local/lib/python3.3/dist-packages/
if [ $ARCH = "x86_64" ]; then  
	cp $SETUPDIR/sensors.cpython-33m.so.64 $PYDIST/sensors.cpython-33m.so
else  
	cp $SETUPDIR/sensors.cpython-33m.so.32 $PYDIST/sensors.cpython-33m.so
fi

#preconfigured ifplugd settings
if [ -f "/etc/ifplugd/action.d/ifupdown" ]; then
	mv /etc/ifplugd/action.d/ifpdown /etc/ifplugd/action.d/ifupdown.bk
	
cp $SETUPDIR/ifupdown /etc/ifplugd/action.d

mkdir /etc/lockwatcher
cp $SETUPDIR/lockwatcher.ini /etc/lockwatcher
cp $SETUPDIR/othercmds.sh /etc/lockwatcher