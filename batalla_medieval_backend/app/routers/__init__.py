"""Router namespace: import submodules only when requested.

The scheduler imports services independently of HTTP. Eagerly importing every
router here caused circular imports through admin_permissions on worker boot.
"""

__all__ = [
    "achievement",
    "admin",
    "admin_bot",
    "alliance",
    "anticheat",
    "auth",
    "building",
    "city",
    "conquest",
    "event",
    "message",
    "movement",
    "notification",
    "premium",
    "protection",
    "queue",
    "ranking",
    "report",
    "season",
    "shop",
    "theme",
    "troop",
    "quest",
    "world",
    "wiki",
]
