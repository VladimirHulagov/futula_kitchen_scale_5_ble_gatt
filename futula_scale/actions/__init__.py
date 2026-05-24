"""Action base class for FUTULA scale weight notifications."""

from abc import ABC, abstractmethod


class BaseAction(ABC):
    """Base class for scale weight actions.

    Implement `on_weight()` to react to stable weight readings.
    Implement `on_start()` / `on_stop()` for lifecycle hooks (optional).
    """

    def __init__(self, config: dict):
        self.config = config

    def on_start(self):
        """Called once when the daemon starts. Optional."""
        pass

    def on_stop(self):
        """Called once when the daemon stops. Optional."""
        pass

    @abstractmethod
    def on_weight(self, weight_g: int, stable: bool):
        """Called on every weight notification from the scale.

        Args:
            weight_g: Weight in grams.
            stable: True if the reading has stabilized.
        """
        ...
