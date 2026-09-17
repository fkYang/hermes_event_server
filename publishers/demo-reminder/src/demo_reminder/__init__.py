"""Parameterized one-shot reminder publisher used to demo the provider chain.

It owns no user data: a caller passes a delay (``5m``, ``10m``, ``90s``) and the
Publisher turns it into ``notify_at`` on the publish request.  EventServer then
decides who is notified and when the delivery becomes claimable.
"""

__version__ = "0.1.0"
