"""Business rules for transfers; only row_id identifies a source row."""

from typing import Any

from backend.models import Transaction
from backend.repositories import EdgeRepository
from backend.schemas import TransactionCreate, TransactionUpdate
from backend.services.base import BaseService


class TransactionService(BaseService[Transaction, TransactionCreate, TransactionUpdate]):
    create_schema = TransactionCreate

    def _validate(self, values: dict[str, Any], current: Transaction | None) -> None:
        self._ensure_unique(current, row_id=values["row_id"])
        # An existing directed edge also guarantees both endpoint nodes exist.
        self._require_reference(
            EdgeRepository(self.repository.session), src=values["src"], dst=values["dst"]
        )
