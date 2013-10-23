#https://github.com/spiwn/Interception-wrapper-for-Python/blob/master/interception.py#
#
# Python wrappings for
#   Interception by oblitum:
#       http://oblita.com/Interception
#       https://github.com/oblitum/Interception


#           !!!  Attention !!!
#                   WIP
#           Not completely tested

# May not run at all or may cause your system to stop accepting input
# And if you do not use it properly it will definetely do the later

# I am not responsible for any damage that may be caused by the use of
# this incomplete code

from ctypes import *
from ctypes import _CFuncPtr

try:
    interceptionDll = cdll['interception.32.dll']
except:
    interceptionDll = cdll['interception.64.dll']
        
MAX_KEYBOARD   = 10
MAX_MOUSE      = 10
MAX_DEVICE     = MAX_KEYBOARD + MAX_MOUSE
KEYBOARD       = lambda index: index+1
MOUSE          = lambda index: MAX_KEYBOARD + index + 1

class Context( c_void_p ):
    pass
class Device( c_int ):
    pass
class Precedence( c_int ):
    pass
class Filter( c_ushort ):
    pass

PredicateCache = {}

class PredicateType():
    def __init__( self, func ):
        if isinstance(func, _CFuncPtr):
            self._as_parameter_ = func
            self._as_parameter_.argtypes = [ c_int ]
            self._as_parameter_.restype = c_bool
        elif callable( func ):
            self._as_parameter_ = CFUNCTYPE( c_bool, c_int )( func )
        else:
            raise TypeError
    def from_param( self ):
        return self._as_parameter_
    def __call__( self, device ):
        return self._as_parameter_( device )

def Predicate ( func ):
    if isinstance( func, _CFuncPtr ):
        hashValue = id( func )
    elif callable( func ):
        hashValue = id( func )
    else:
        raise TypeError("Wrong type for a Predicate ( should be something like a function")
    predFunc = PredicateCache.get( hashValue , False )
    if not predFunc:
        predFunc = PredicateType(func)
        PredicateCache [ hashValue ] = predFunc
    return predFunc
        
        
KEY_DOWN             = 0x00
KEY_UP               = 0x01
KEY_E0               = 0x02
KEY_E1               = 0x04
KEY_TERMSRV_SET_LED  = 0x08
KEY_TERMSRV_SHADOW   = 0x10
KEY_TERMSRV_VKPACKET = 0x20

FILTER_KEY_NONE             = 0x0000
FILTER_KEY_ALL              = 0xFFFF
FILTER_KEY_DOWN             = KEY_UP
FILTER_KEY_UP               = KEY_UP << 1
FILTER_KEY_E0               = KEY_E0 << 1
FILTER_KEY_E1               = KEY_E1 << 1
FILTER_KEY_TERMSRV_SET_LED  = KEY_TERMSRV_SET_LED << 1
FILTER_KEY_TERMSRV_SHADOW   = KEY_TERMSRV_SHADOW << 1
FILTER_KEY_TERMSRV_VKPACKET = KEY_TERMSRV_VKPACKET << 1

MOUSE_LEFT_BUTTON_DOWN   = 0x001
MOUSE_LEFT_BUTTON_UP     = 0x002
MOUSE_RIGHT_BUTTON_DOWN  = 0x004
MOUSE_RIGHT_BUTTON_UP    = 0x008
MOUSE_MIDDLE_BUTTON_DOWN = 0x010
MOUSE_MIDDLE_BUTTON_UP   = 0x020

MOUSE_BUTTON_1_DOWN      = MOUSE_LEFT_BUTTON_DOWN
MOUSE_BUTTON_1_UP        = MOUSE_LEFT_BUTTON_UP
MOUSE_BUTTON_2_DOWN      = MOUSE_RIGHT_BUTTON_DOWN
MOUSE_BUTTON_2_UP        = MOUSE_RIGHT_BUTTON_UP
MOUSE_BUTTON_3_DOWN      = MOUSE_MIDDLE_BUTTON_DOWN
MOUSE_BUTTON_3_UP        = MOUSE_MIDDLE_BUTTON_UP

MOUSE_BUTTON_4_DOWN      = 0x040
MOUSE_BUTTON_4_UP        = 0x080
MOUSE_BUTTON_5_DOWN      = 0x100
MOUSE_BUTTON_5_UP        = 0x200

MOUSE_WHEEL              = 0x400
MOUSE_HWHEEL             = 0x800

FILTER_MOUSE_NONE               = 0x0000
FILTER_MOUSE_ALL                = 0xFFFF

FILTER_MOUSE_LEFT_BUTTON_DOWN   = MOUSE_LEFT_BUTTON_DOWN
FILTER_MOUSE_LEFT_BUTTON_UP     = MOUSE_LEFT_BUTTON_UP
FILTER_MOUSE_RIGHT_BUTTON_DOWN  = MOUSE_RIGHT_BUTTON_DOWN
FILTER_MOUSE_RIGHT_BUTTON_UP    = MOUSE_RIGHT_BUTTON_UP
FILTER_MOUSE_MIDDLE_BUTTON_DOWN = MOUSE_MIDDLE_BUTTON_DOWN
FILTER_MOUSE_MIDDLE_BUTTON_UP   = MOUSE_MIDDLE_BUTTON_UP

FILTER_MOUSE_BUTTON_1_DOWN      = MOUSE_BUTTON_1_DOWN
FILTER_MOUSE_BUTTON_1_UP        = MOUSE_BUTTON_1_UP
FILTER_MOUSE_BUTTON_2_DOWN      = MOUSE_BUTTON_2_DOWN
FILTER_MOUSE_BUTTON_2_UP        = MOUSE_BUTTON_2_UP
FILTER_MOUSE_BUTTON_3_DOWN      = MOUSE_BUTTON_3_DOWN
FILTER_MOUSE_BUTTON_3_UP        = MOUSE_BUTTON_3_UP

FILTER_MOUSE_BUTTON_4_DOWN      = MOUSE_BUTTON_4_DOWN
FILTER_MOUSE_BUTTON_4_UP        = MOUSE_BUTTON_4_UP
FILTER_MOUSE_BUTTON_5_DOWN      = MOUSE_BUTTON_5_DOWN
FILTER_MOUSE_BUTTON_5_UP        = MOUSE_BUTTON_5_UP

FILTER_MOUSE_WHEEL              = MOUSE_WHEEL
FILTER_MOUSE_HWHEEL             = MOUSE_HWHEEL

FILTER_MOUSE_MOVE               = 0x1000

MOUSE_MOVE_RELATIVE      = 0x000
MOUSE_MOVE_ABSOLUTE      = 0x001
MOUSE_VIRTUAL_DESKTOP    = 0x002
MOUSE_ATTRIBUTES_CHANGED = 0x004
MOUSE_MOVE_NOCOALESCE    = 0x008
MOUSE_TERMSRV_SRC_SHADOW = 0x100

class MouseStroke( Structure ):
    _fields_ = [
        ( "state", c_ushort ),
        ( "flags",     c_ushort ),
        ( "rolling",     c_short ),
        ( "x",  c_int ),
        ( "y",  c_int ),
        ( "information", c_uint )
    ]

class KeyStroke( Structure ):
    _fields_ = [
        ( "code", c_ushort ),
        ( "state",     c_ushort ),
        ( "information",     c_uint )
    ]
def stroke2KeyStroke( stroke, dest = None ):
    if not dest:
        result = KeyStroke()
        memmove( byref( result ), stroke, sizeof( result ) )
        return result
    else:
        return memmove( byref( dest ), stroke, sizeof( KeyStroke ))

def stroke2MouseStroke( stroke, dest = None ):
    if not dest:
        result = MouseStroke()
        memmove( byref( result ), stroke, sizeof( MouseStroke ) )
        return result
    else:
        return memmove( byref( dest ), stroke, sizeof( MouseStroke ) )

class Stroke ():
    def __init__( self, initial = None ):
        if initial:
            self._as_parameter_ = ( c_ushort * ( sizeof ( MouseStroke ) // sizeof( c_ushort ) ) ) (*initial)
        else:
            self._as_parameter_ = ( c_ushort * ( sizeof ( MouseStroke ) // sizeof( c_ushort ) ) ) ()

    def from_param( self ):
        return self._as_parameter_

    def __getitem__( self, index):
        return self.data[ index ]

    def __setitem__( self, index, value):
        self.data[ index ] = value

create_context          = interceptionDll.interception_create_context
create_context.argtypes = []
create_context.restype  = Context

destroy_context         = interceptionDll.interception_destroy_context
destroy_context.argtypes= [Context]
destroy_context.restype = c_void_p

get_precedence          = interceptionDll.interception_get_precedence
get_precedence.argtypes = [Context, Device]
get_precedence.restype  = Precedence

set_precedence          = interceptionDll.interception_set_precedence
set_precedence.argtypes = [Context, Device, Precedence]
set_precedence.restype  = c_void_p

get_filter              = interceptionDll.interception_get_filter
get_filter.argtypes     = [Context, Device]
get_filter.restype      = Filter

set_filter_proto              = interceptionDll.interception_set_filter
set_filter_proto.argtypes     = [Context, PredicateType, Filter]
set_filter_proto.restype      = c_void_p

def set_filter(cont,pred,filt):
    if isinstance(pred,PredicateType):
        return set_filter_proto(cont,pred,filt)
    else:
        return set_filter_proto(cont,Predicate(pred),filt)

wait                    = interceptionDll.interception_wait
wait.argtypes           = [Context]
wait.restype            = Device

wait_with_timeout               = interceptionDll.interception_wait_with_timeout
wait_with_timeout.argtypes       = [Context, c_ulong]
wait_with_timeout.restype        = Device

send_proto              = interceptionDll.interception_send
send_proto.argtypes     = [Context, Device, Stroke, c_uint]
send_proto.restype      = c_int

__temp_Stroke = Stroke()

def send( context, device, stroke, nstroke ):
    if isinstance( stroke, Stroke ):
        return send_proto( context, device, stroke, nstroke)
    if isinstance( stroke, ( KeyStroke, MouseStroke ) ):
        memmove( __temp_Stroke, byref( stroke ), sizeof( stroke ))
        return send_proto( context, device, __temp_Stroke, nstroke )
    raise TypeError( "Argument 3. Expected <'Stroke'>, <'KeyStroke'> or <'MouseStroke'>, got {0} instead.".format( type( stroke ) ) )

receive                 = interceptionDll.interception_receive
receive.argtypes        = [ Context, Device, Stroke, c_uint ]
receive.restype         = c_int

get_hardware_id_proto           = interceptionDll.interception_get_hardware_id
get_hardware_id_proto.argtypes  = [ Context, Device, c_void_p, c_uint ]
get_hardware_id_proto.restype   = c_uint

def memoryChunk2Strings( string, lenght = 0 ):
    if lenght:
        limit = lenght
    else:
        limit = sizeof(string)
    result = []
    offset = 0
    while offset < sizeof( string ):
        part = wstring_at( addressof( string ) + offset * 2 )
        if part:
            result.append( part )
            offset += len( part )+1
        else:
            break
    return result

__hardware_Id_Data = [ create_unicode_buffer( 300 ), 300 ]

def get_hardware_id ( context, device, max_size = 0):
    if max_size > __hardware_Id_Data[ 1 ]:
        __hardware_Id_Data[ 1 ] = max_size
        __hardware_Id_Data[ 0 ] = create_unicode_buffer( max_size )
    lenght = get_hardware_id_proto( context, device, __hardware_Id_Data[ 0 ], __hardware_Id_Data[ 1 ] )
    if lenght > 0:
        return memoryChunk2Strings( __hardware_Id_Data[ 0 ], lenght)
    return None

is_invalid  = Predicate( interceptionDll.interception_is_invalid )

is_keyboard     = Predicate( interceptionDll.interception_is_keyboard )

is_mouse        = Predicate( interceptionDll.interception_is_mouse )
