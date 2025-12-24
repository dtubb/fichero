"""
Base ViewModel for Fichero

Base class for all ViewModels with observer pattern support.
"""

from abc import ABC, abstractmethod
from typing import List, Callable, Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class ViewModelObserver(ABC):
    """Observer interface for ViewModels"""

    @abstractmethod
    def on_data_changed(self, data_type: str, data: Any):
        """Called when ViewModel data changes"""
        pass

    def on_loading_changed(self, is_loading: bool):
        """Called when loading state changes"""
        pass

    def on_error_occurred(self, error_type: str, message: str):
        """Called when an error occurs"""
        pass


class BaseViewModel(ABC):
    """Base class for all ViewModels"""

    def __init__(self):
        self.observers: List[ViewModelObserver] = []
        self.is_loading = False
        self.last_error: Optional[str] = None

    # ===== OBSERVER MANAGEMENT =====

    def add_observer(self, observer: ViewModelObserver):
        """Add an observer to this ViewModel"""
        if observer not in self.observers:
            self.observers.append(observer)
            logger.debug(f"Added observer to {self.__class__.__name__}")

    def remove_observer(self, observer: ViewModelObserver):
        """Remove an observer from this ViewModel"""
        if observer in self.observers:
            self.observers.remove(observer)
            logger.debug(f"Removed observer from {self.__class__.__name__}")

    def add_callback_observer(self,
                            on_data_changed: Optional[Callable] = None,
                            on_loading_changed: Optional[Callable] = None,
                            on_error_occurred: Optional[Callable] = None) -> 'CallbackObserver':
        """Add a simple callback-based observer"""
        observer = CallbackObserver(on_data_changed, on_loading_changed, on_error_occurred)
        self.add_observer(observer)
        return observer

    # ===== NOTIFICATION METHODS =====

    def notify_data_changed(self, data_type: str, data: Any):
        """Notify observers that data has changed"""
        for observer in self.observers:
            try:
                observer.on_data_changed(data_type, data)
            except Exception as e:
                logger.error(f"Error notifying observer of data change: {e}")

    def notify_loading_changed(self, is_loading: bool):
        """Notify observers that loading state has changed"""
        self.is_loading = is_loading
        for observer in self.observers:
            try:
                observer.on_loading_changed(is_loading)
            except Exception as e:
                logger.error(f"Error notifying observer of loading change: {e}")

    def notify_error_occurred(self, error_type: str, message: str):
        """Notify observers that an error occurred"""
        self.last_error = message
        for observer in self.observers:
            try:
                observer.on_error_occurred(error_type, message)
            except Exception as e:
                logger.error(f"Error notifying observer of error: {e}")

    # ===== STATE MANAGEMENT =====

    def get_loading_state(self) -> bool:
        """Get current loading state"""
        return self.is_loading

    def get_last_error(self) -> Optional[str]:
        """Get the last error message"""
        return self.last_error

    def clear_error(self):
        """Clear the last error"""
        self.last_error = None

    # ===== ABSTRACT METHODS =====

    @abstractmethod
    def refresh(self):
        """Refresh the ViewModel data"""
        pass

    def get_state_dict(self) -> Dict[str, Any]:
        """Get ViewModel state as dictionary for debugging"""
        return {
            'class': self.__class__.__name__,
            'is_loading': self.is_loading,
            'last_error': self.last_error,
            'observer_count': len(self.observers)
        }


class CallbackObserver(ViewModelObserver):
    """Simple callback-based observer implementation"""

    def __init__(self,
                 on_data_changed: Optional[Callable] = None,
                 on_loading_changed: Optional[Callable] = None,
                 on_error_occurred: Optional[Callable] = None):
        self.on_data_changed_callback = on_data_changed
        self.on_loading_changed_callback = on_loading_changed
        self.on_error_occurred_callback = on_error_occurred

    def on_data_changed(self, data_type: str, data: Any):
        """Handle data change"""
        if self.on_data_changed_callback:
            self.on_data_changed_callback(data_type, data)

    def on_loading_changed(self, is_loading: bool):
        """Handle loading change"""
        if self.on_loading_changed_callback:
            self.on_loading_changed_callback(is_loading)

    def on_error_occurred(self, error_type: str, message: str):
        """Handle error"""
        if self.on_error_occurred_callback:
            self.on_error_occurred_callback(error_type, message)