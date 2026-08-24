from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

_SQL = (
    "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH "
    "FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = :table"
)


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    # None for non-character columns, and -1 for varchar(max).
    max_length: int | None = None


class SchemaUnavailable(RuntimeError):
    """The schema could not be read. Raised rather than returning an empty map,
    which would look identical to "this table has no such column" and would
    reject every valid proposal instead of reporting the outage."""


class SchemaProbe:
    """The sole authority on which column identifiers exist.

    Nothing else may vouch for a column name: write_executor interpolates
    column names into its INSERT statement, so a name that reaches the rule
    document without passing through here is an injection vector.
    """

    def __init__(self, reader: Callable[[str, dict], list[dict]]) -> None:
        self._read = reader
        self._cache: dict[str, dict[str, ColumnInfo]] = {}

    def columns(self, table: str) -> dict[str, ColumnInfo]:
        """Columns of `table`, keyed by lowercased name. Unknown table -> {}."""
        key = table.lower()
        if key not in self._cache:
            try:
                rows = self._read(_SQL, {"table": table})
            except Exception as e:      # noqa: BLE001 - any read failure is an outage
                raise SchemaUnavailable(f"cannot read schema for {table}: {e}") from e
            # Assigned only on success, so a transient outage is not cached.
            self._cache[key] = {
                r["COLUMN_NAME"].lower(): ColumnInfo(
                    name=r["COLUMN_NAME"],
                    data_type=r["DATA_TYPE"],
                    nullable=r["IS_NULLABLE"] == "YES",
                    max_length=r.get("CHARACTER_MAXIMUM_LENGTH"),
                )
                for r in rows
            }
        return self._cache[key]

    def resolve(self, table: str, column: str) -> str | None:
        """The schema's exact spelling of `column`, or None if it does not exist."""
        info = self.columns(table).get(column.lower())
        return info.name if info else None

    def refresh(self) -> None:
        self._cache.clear()
