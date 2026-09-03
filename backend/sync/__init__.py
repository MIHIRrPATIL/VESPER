"""VESPER Cross-Device State Synchronization Subsystem.

Provides:
- Synchronized cluster models (`DeviceRegistration`, `SynchronizedState`)
- Central Sync Manager (`SyncManager`, `sync_manager`)
- Edge Sync Client (`SyncClient`)
"""

from backend.sync.models import DeviceRegistration, SynchronizedState
from backend.sync.sync_manager import SyncManager, sync_manager
from backend.sync.client import SyncClient

__all__ = [
    "DeviceRegistration",
    "SynchronizedState",
    "SyncManager",
    "sync_manager",
    "SyncClient",
]
