"""
Patron Command Repository - Infrastructure implementation.

Implements: IPatronCommandRepository
"""
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.patron import Patron
from src.domain.patron.exceptions import ConcurrentModificationException
from src.infrastructure.adapters.patron.patron_model import PatronModel
from src.infrastructure.exceptions import DatabaseException


class PatronCommandRepository:
    """Repository implementation for Patron aggregate."""

    def __init__(self, session: AsyncSession, identity_map: Optional[Dict[str, Patron]] = None):
        self.session = session
        self.identity_map = identity_map if identity_map is not None else {}

    async def add(self, patron: Patron) -> Patron:
        try:
            db_patron = PatronModel.from_entity(patron)
            self.session.add(db_patron)
            self.identity_map[patron.id.value] = patron
            return patron
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error adding patron: {str(e)}", original_exception=e)

    async def get_by_id(self, patron_id: str) -> Optional[Patron]:
        try:
            if patron_id in self.identity_map:
                return self.identity_map[patron_id]

            result = await self.session.execute(
                select(PatronModel).where(PatronModel.id == patron_id)
            )
            db_patron = result.scalar_one_or_none()
            if db_patron:
                entity = db_patron.to_entity()
                self.identity_map[entity.id.value] = entity
                return entity
            return None
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving patron {patron_id}: {str(e)}", original_exception=e)

    async def get_by_email(self, email: str) -> Optional[Patron]:
        try:
            result = await self.session.execute(
                select(PatronModel).where(PatronModel.email == email)
            )
            db_patron = result.scalar_one_or_none()
            if db_patron:
                if db_patron.id in self.identity_map:
                    return self.identity_map[db_patron.id]
                entity = db_patron.to_entity()
                self.identity_map[entity.id.value] = entity
                return entity
            return None
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving patron by email: {str(e)}", original_exception=e)

    async def get_all(self) -> List[Patron]:
        try:
            result = await self.session.execute(select(PatronModel))
            db_patrons = result.scalars().all()
            entities = []
            for db_patron in db_patrons:
                if db_patron.id in self.identity_map:
                    entities.append(self.identity_map[db_patron.id])
                else:
                    entity = db_patron.to_entity()
                    self.identity_map[entity.id.value] = entity
                    entities.append(entity)
            return entities
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error retrieving patrons: {str(e)}", original_exception=e)

    async def update(self, patron: Patron) -> None:
        try:
            expected_version = patron.version
            new_version = expected_version + 1

            result = await self.session.execute(
                update(PatronModel)
                .where(PatronModel.id == patron.id.value)
                .where(PatronModel.version == str(expected_version))
                .values(
                    first_name=patron.name.first_name,
                    last_name=patron.name.last_name,
                    email=patron.email.value,
                    membership_tier=patron.membership_tier.value,
                    is_suspended=patron.is_suspended,
                    suspended_reason=patron.suspended_reason,
                    version=str(new_version),
                )
            )

            if result.rowcount == 0:
                check_result = await self.session.execute(
                    select(PatronModel).where(PatronModel.id == patron.id.value)
                )
                if check_result.scalar_one_or_none() is None:
                    raise DatabaseException(f"Patron {patron.id.value} not found")
                else:
                    raise ConcurrentModificationException(patron.id.value)

            patron._version = new_version
            self.identity_map[patron.id.value] = patron

        except ConcurrentModificationException:
            raise
        except SQLAlchemyError as e:
            raise DatabaseException(f"Error updating patron: {str(e)}", original_exception=e)
