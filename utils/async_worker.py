import sys
import traceback
from typing import Callable, Any
from PySide6.QtCore import QRunnable, QObject, Signal, Slot

class WorkerSignals(QObject):
    """
    Defines the signals available from a running worker thread.
    Supported signals are:
    
    finished: No data
    error: tuple (exctype, value, traceback.format_exc() )
    result: object data returned from processing, anything
    progress: int indicating % progress
    """
    finished = Signal()
    error = Signal(tuple)
    result = Signal(object)
    progress = Signal(int)

class Worker(QRunnable):
    """
    Worker thread for running I/O or heavy CPU tasks (like PuLP optimization)
    outside of the main UI thread.
    
    Inherits from QRunnable to handler worker thread setup, signals and wrap-up.
    """
    def __init__(self, fn: Callable, *args, **kwargs):
        super(Worker, self).__init__()
        
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        
        # Add the callback to our kwargs if the function needs to report progress
        if 'progress_callback' in kwargs:
            self.kwargs['progress_callback'] = self.signals.progress

    @Slot()
    def run(self):
        """
        Initialize the runner function with passed args, kwargs.
        """
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            self.signals.result.emit(result)  # Return the result of the processing
        finally:
            self.signals.finished.emit()  # Done
