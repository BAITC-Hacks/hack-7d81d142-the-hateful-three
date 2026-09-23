"""Persistence for source rows, including otherwise identical transfers."""

from backend.models import Transaction
from backend.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction
