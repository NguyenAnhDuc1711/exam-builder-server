"""Shared SQLAlchemy 2.0 declarative base.

Every ORM model inherits from `Base`; `Base.metadata` is what Alembic's
`target_metadata` points at. Import `app.infrastructure.db.models` (the
package `__init__` imports every model module) before touching
`Base.metadata`, otherwise tables defined in un-imported modules are
missing from it.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
