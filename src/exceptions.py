class EmptyChannelException(Exception):
    """Raised when a channel has no videos, or its upload playlist is empty."""


class ProblemChannelException(Exception):
    """Raised when a channel's upload playlist cannot be resolved."""