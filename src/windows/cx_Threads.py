"""Defines methods for managing threads, events and queues."""

import cx_Exceptions
import cx_Logging
import time

try:
    import _thread as thread
except ImportError:
    import thread

class Thread(object):
    """Base class for threads which is a little more lightweight than the
       threading module exports and allows for finer control."""

    def __init__(self, function, *args, **keywordArgs):
        self.function = function
        self.args = args
        self.keywordArgs = keywordArgs
        self.started = False
        self.stopped = False
        self.errorObj = None
        self.event = None
        self.name = None

    def OnThreadEnd(self):
        """Called when the thread is ended. Override in child classes."""
        cx_Logging.Info("thread %r ending", self.name)

    def OnThreadStart(self):
        """Called when the thread is started. Override in child classes."""
        cx_Logging.Info("thread %r starting", self.name)

    def Start(self, loggingState = None):
        """Start the thread."""
        self.started = True
        self.stopped = False
        self.errorObj = None
        thread.start_new_thread(self._Run, (loggingState,))

    def _Run(self, loggingState):
        """Execute the function associated with the thread."""
        cx_Logging.SetExceptionInfo(cx_Exceptions.BaseException,
                cx_Exceptions.GetExceptionInfo)
        try:
            if loggingState is not None:
                cx_Logging.SetLoggingState(loggingState)
            self.OnThreadStart()
            try:
                self.function(*self.args, **self.keywordArgs)
            except:
                self.errorObj = cx_Logging.LogException()
                cx_Logging.Error("Thread %r terminating", self.name)
        finally:
            self.stopped = True
            self.OnThreadEnd()
            if self.event:
                self.event.Set()


class Event(object):
    """Event class which permits synchronization between threads."""

    def __init__(self):
        self.lock = thread.allocate_lock()
        self.isSet = False
        self.waiters = []

    def Clear(self):
        """Clear the flag."""
        self.lock.acquire()
        self.isSet = False
        self.lock.release()

    def Set(self):
        """Set the flag and notify all waiters of the event."""
        self.lock.acquire()
        self.isSet = True
        if self.waiters:
            for waiter in self.waiters:
                waiter.release()
            self.waiters = []
            self.isSet = False
        self.lock.release()

    def Wait(self):
        """Wait for the flag to be set and immediately reset it."""
        self.lock.acquire()
        if self.isSet:
            self.isSet = False
            self.lock.release()
        else:
            waiterLock = thread.allocate_lock()
            waiterLock.acquire()
            self.waiters.append(waiterLock)
            self.lock.release()
            waiterLock.acquire()


class Queue(object):
    """Light weight implementation of stacks and queues."""

    def __init__(self):
        self.lock = thread.allocate_lock()
        self.queueEvent = Event()
        self.items = []

    def Clear(self):
        """Clear the queue of all items."""
        self.lock.acquire()
        self.items = []
        self.lock.release()

    def QueueItem(self, item):
        """Add an item to end of the list of items (for queues)."""
        self.lock.acquire()
        self.items.append(item)
        self.lock.release()
        self.queueEvent.Set()

    def PopItem(self, returnNoneIfEmpty=False):
        """Get the next item from the beginning of the list of items,
           optionally returning None if nothing is found."""
        self.lock.acquire()
        while not self.items:
            self.lock.release()
            if returnNoneIfEmpty:
                return None
            self.queueEvent.Wait()
            self.lock.acquire()
        item = self.items.pop(0)
        self.lock.release()
        return item

    def PushItem(self, item):
        """Add an item to the beginning of the list of items (for stacks)."""
        self.lock.acquire()
        self.items.insert(0, item)
        self.lock.release()
        self.queueEvent.Set()


class ResourcePool(object):
    """Implements a pool of resources."""

    def __init__(self, maxResources, newResourceFunc):
        self.lock = thread.allocate_lock()
        self.poolEvent = Event()
        self.freeResources = []
        self.busyResources = []
        self.maxResources = maxResources
        self.newResourceFunc = newResourceFunc

    def Destroy(self):
        """Destroy the resource pool, this blocks until all resources are
           returned to the pool for destruction."""
        self.lock.acquire()
        self.freeResources = []
        self.maxResources = 0
        self.lock.release()
        while self.busyResources:
            self.poolEvent.Wait()

    def Get(self):
        """Gets a resource form the pool, creating new resources as necessary.
           The calling thread will block until a resource is available, if
           necessary."""
        resource = None
        self.lock.acquire()
        while resource is None:
            try:
                if self.freeResources:
                    resource = self.freeResources.pop()
                elif len(self.busyResources) < self.maxResources:
                    resource = self.newResourceFunc()
                elif not self.maxResources:
                    raise "No resources not available."
                else:
                    self.lock.release()
                    self.poolEvent.Wait()
                    self.lock.acquire()
            except:
                if self.lock.locked():
                    self.lock.release()
                raise
        self.busyResources.append(resource)
        self.lock.release()
        return resource

    def Put(self, resource, addToFreeList = True):
        """Put a resource back into the pool."""
        self.lock.acquire()
        try:
            index = self.busyResources.index(resource)
            del self.busyResources[index]
            if self.maxResources and addToFreeList:
                self.freeResources.append(resource)
        finally:
            self.lock.release()
        self.poolEvent.Set()


class Timer(Thread):
    """Operates a timer."""

    def __init__(self, timeInSeconds):
        Thread.__init__(self, time.sleep, timeInSeconds)