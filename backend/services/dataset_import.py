"""Validate the starter ZIP completely before inserting any source rows."""

from collections import defaultdict
from decimal import Decimal
from io import BytesIO
from zipfile import BadZipFile, ZipFile

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import ValidationError as SchemaError
from sqlalchemy import func, insert, select

from backend.models import Edge, Node, Transaction
from backend.schemas.edge import EdgeCreate
from backend.schemas.node import NodeCreate
from backend.schemas.transaction import TransactionCreate
from backend.services.exceptions import ConflictError, ValidationError

MAX_UPLOAD = 30 * 1024 * 1024
MAX_UNPACKED = 100 * 1024 * 1024
MAX_ROWS = {"nodes": 20_000, "edges": 100_000, "transactions": 500_000}


def read_archive(content: bytes) -> dict:
    if len(content) > MAX_UPLOAD:
        raise ValidationError("Архив должен быть не больше 30 МБ.")
    tables = {}
    try:
        with ZipFile(BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED:
                raise ValidationError("Распакованный архив должен быть не больше 100 МБ.")
            for name in MAX_ROWS:
                candidates = [i for i in archive.infolist()
                              if i.filename in (f"data/{name}.parquet", f"{name}.parquet")]
                if len(candidates) != 1:
                    raise ValidationError(f"В ZIP необходим один файл data/{name}.parquet.")
                parquet = pq.ParquetFile(BytesIO(archive.read(candidates[0])))
                if parquet.metadata.num_rows > MAX_ROWS[name]:
                    raise ValidationError(f"Слишком много строк в {name}: максимум {MAX_ROWS[name]}.")
                tables[name] = parquet.read().to_pylist()
        parsed = {}
        for name, schema in [("nodes", NodeCreate), ("edges", EdgeCreate), ("transactions", TransactionCreate)]:
            rows = []
            for i, row in enumerate(tables[name]):
                for key in ("gid", "src", "dst"):
                    if key in row and isinstance(row[key], int) and not isinstance(row[key], bool):
                        row[key] = str(row[key])
                if "sum_kzt" in row:
                    row["sum_kzt"] = Decimal(str(row["sum_kzt"]))
                if name == "transactions":
                    row["row_id"] = i  # Keep identical transfers; source has no transaction ID.
                rows.append(schema.model_validate(row).model_dump())
            parsed[name] = rows
    except (BadZipFile, pa.ArrowException, SchemaError, ValueError, TypeError, OSError, RuntimeError) as exc:
        raise ValidationError("Некорректный ZIP/Parquet или поля датасета.") from exc
    gids = {r["gid"] for r in parsed["nodes"]}
    if not gids or len(gids) != len(parsed["nodes"]):
        raise ValidationError("Список узлов пуст или содержит повторные GID.")
    pairs = {(r["src"], r["dst"]): r for r in parsed["edges"]}
    if len(pairs) != len(parsed["edges"]):
        raise ValidationError("Повторные пары src/dst в рёбрах.")
    if any(src not in gids or dst not in gids for src, dst in pairs):
        raise ValidationError("Рёбра ссылаются на неизвестные GID.")
    totals = defaultdict(lambda: [Decimal(0), 0])
    for row in parsed["transactions"]:
        pair = row["src"], row["dst"]
        totals[pair][0] += row["sum_kzt"]
        totals[pair][1] += 1
    if pairs.keys() != totals.keys() or any(
        totals[pair][1] != edge["n_tx"] or abs(totals[pair][0] - edge["sum_kzt"]) > Decimal("0.01")
        for pair, edge in pairs.items()
    ):
        raise ValidationError("Суммы или количество транзакций не совпадают с рёбрами.")
    return parsed


def import_archive(session, content: bytes) -> None:
    if session.scalar(select(func.count()).select_from(Node)):
        raise ConflictError("В базе уже есть датасет. Повторный импорт не изменяет существующие данные.")
    parsed = read_archive(content)
    for name, model in [("nodes", Node), ("edges", Edge), ("transactions", Transaction)]:
        rows = parsed[name]
        for start in range(0, len(rows), 1000):
            session.execute(insert(model), rows[start:start + 1000])
        session.flush()
