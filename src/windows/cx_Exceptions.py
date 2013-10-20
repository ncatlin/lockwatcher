import sys
import traceback

registeredExceptionClasses = {}

def RegisterExceptionClass(cls):
    """Register the exception."""
    registeredExceptionClasses[cls.templateId] = cls


class BaseException(Exception):
    """Base exception for all configured exceptions."""
    message = "*** no message defined for exception ***"
    templateId = 0
    logLevel = 40

    def __init__(self, framesToSkip = 0, **arguments):
        self.details = []
        self.traceback = []
        self.arguments = {}
        if arguments:
            for name, value in arguments.iteritems():
                self.arguments[name] = self._FormatValue(value)
            try:
                self.message = self.message % arguments
            except:
                pass
        self._FormatStack(framesToSkip = framesToSkip)

    def __str__(self):
        return self.message

    def __AddFrame(self, frame, lineNo):
        """Add the frame to the traceback."""
        co = frame.f_code
        tbLine = "file %s, line %s, in %s" % \
                (co.co_filename, lineNo, co.co_name)
        self.traceback.append(tbLine)
        self.details.append(tbLine)
        localVariables = list(frame.f_locals.items())
        localVariables.sort()
        for name, value in localVariables:
            if name.startswith("_"):
                continue
            stringRep = self._FormatValue(value, maxLength = 500)
            self.details.append("  %s -> %s" % (name, stringRep))

    def __AddLocalVariables(self, frame, tb = None):
        self.details.append("Local Variables:")
        if tb:
            tbFrame = tb.tb_frame
            tbLineNo = tb.tb_lineno
        else:
            tbFrame = tbLineNo = None
        while frame is not None:
            if frame is tbFrame:
                self.__AddFrame(frame, tbLineNo)
            else:
                self.__AddFrame(frame, frame.f_lineno)
            frame = frame.f_back

    def _FormatException(self, excType, excValue, tb):
        """Format the traceback and put it in the traceback attribute."""
        self.details = []
        self.traceback = []
        if excType is not None:
            self.details.append("Exception type: %s" % (excType,))
        if excValue is not None:
            prefix = "Exception value: "
            for line in str(excValue).rstrip().splitlines():
                self.details.append(prefix + line)
                prefix = ""
        frame = None
        initialTb = tb
        while tb is not None:
            frame = tb.tb_frame
            tb = tb.tb_next
        self.__AddLocalVariables(frame, initialTb)

    def _FormatStack(self, framesToSkip = 0):
        """Format the traceback for the current location."""
        self.details = []
        self.traceback = []
        try:
            raise ZeroDivisionError
        except ZeroDivisionError:
            frame = sys.exc_info()[2].tb_frame
            framesToSkip += 2
            while framesToSkip > 0:
                frame = frame.f_back
                framesToSkip -= 1
        self.__AddLocalVariables(frame)

    def _FormatValue(self, value, maxLength = None):
        """Format the value for display in the exception."""
        try:
            stringRep = repr(value)
            if maxLength is not None and len(stringRep) > maxLength:
                stringRep = stringRep[:maxLength - 3] + "..."
        except:
            typeName = type(value).__name__
            stringRep = "Unable to repr object of type %s" % typeName
        return stringRep

    def Matches(self, templateId, **args):
        """Return true if the exception matches the template and arguments."""
        if self.templateId != templateId:
            return False
        for name, value in args.iteritems():
            if name not in self.arguments:
                return False
            valueToMatch = self.arguments[name]
            try:
                if isinstance(value, int):
                    valueToMatch = int(valueToMatch)
                elif isinstance(value, long):
                    valueToMatch = long(valueToMatch)
                elif isinstance(value, float):
                    valueToMatch = float(valueToMatch)
                elif value is None and valueToMatch == "":
                    valueToMatch = None
            except:
                return False
            if value != valueToMatch:
                return False
        return True

    def Print(self, f = None):
        """Print the exception to the given file."""
        if f is None:
            f = sys.stderr
        print >> f, "Exception encountered:", self.message.rstrip()
        print >> f, "Template Id:", self.templateId
        print >> f, "Arguments:"
        for name, value in self.arguments.iteritems():
            print >> f, name, "->", repr(value)
        print >> f, "Traceback:"
        for line in self.traceback:
            print >> f, line
        print >> f, "Details:"
        for line in self.details:
            print >> f, line


def ExceptionHandler(exceptionType, exceptionValue, traceback):
    """Exception handler suitable for placing in sys.excepthook."""
    errorObj = GetExceptionInfo(exceptionType, exceptionValue, traceback)
    errorObj.Print()


def GetExceptionClass(templateId):
    """Return the exception class given the template id. If the template is not
       found, None is returned."""
    return registeredExceptionClasses.get(templateId)


def GetExceptionInfo(excType, excValue, tb):
    """Return an exception of the base class."""
    if isinstance(excValue, BaseException):
        return excValue
    errorObj = BaseException()
    errorObj._FormatException(excType, excValue, tb)
    isSyntaxError = (excType is SyntaxError)
    if isSyntaxError:
        try:
            message, (fileName, lineNumber, offset, line) = excValue
        except:
            isSyntaxError = False
    if not isSyntaxError:
        lines = traceback.format_exception_only(excType, excValue)
        errorObj.message = "".join(lines).strip()
    else:
        errorObj.message = "%s: see details." % message.capitalize()
        if lineNumber is not None:
            errorObj.arguments["LineNumber"] = lineNumber
        if offset is not None:
            errorObj.arguments["ColumnNumber"] = offset
        if line is not None:
            errorObj.arguments["ErrorLine"] = line.rstrip()
            if offset is not None:
                errorObj.arguments["ErrorPos"] = " " * offset + "^"
    return errorObj


def RaiseExceptionWithInfo(excClassObj, **args):
    """Return an exception of the given class with the information of the
       current exception pending."""
    exceptionValue = excClassObj(**args)
    exceptionValue._FormatException(*sys.exc_info())
    raise exceptionValue


class DuplicateKey(BaseException):
    templateId = 1086
    message = 'Key %(key)s duplicated.'
RegisterExceptionClass(DuplicateKey)


class InvalidHandle(BaseException):
    templateId = 1088
    message = 'Invalid handle: %(handle)s'
RegisterExceptionClass(InvalidHandle)


class InvalidItem(BaseException):
    templateId = 1010
    message = '%(value)s is not a valid %(name)s.'
RegisterExceptionClass(InvalidItem)


class MissingConfigurationFile(BaseException):
    templateId = 1004
    message = 'Missing configuration file "%(fileName)s".'
RegisterExceptionClass(MissingConfigurationFile)


class NoDataFound(BaseException):
    templateId = 1001
    message = 'No data found.'
RegisterExceptionClass(NoDataFound)


class NotImplemented(BaseException):
    templateId = 1003
    message = 'Not implemented.'
RegisterExceptionClass(NotImplemented)


class TooManyRows(BaseException):
    templateId = 1002
    message = 'Too many rows (%(numRows)s) found.'
RegisterExceptionClass(TooManyRows)