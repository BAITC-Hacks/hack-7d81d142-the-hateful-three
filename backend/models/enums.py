"""Role values from the starter CSV contract."""

from enum import Enum

from sqlalchemy import Enum as SQLAlchemyEnum


class NodeRole(str, Enum):
    CONSOLIDATOR = "consolidator"
    TRANSIT = "transit"
    DISTRIBUTOR = "distributor"
    TERMINAL = "terminal"
    COORDINATOR = "coordinator"
    PERIPHERAL = "peripheral"


def node_role_type() -> SQLAlchemyEnum:
    return SQLAlchemyEnum(
        NodeRole,
        values_callable=lambda roles: [role.value for role in roles],
        name="node_role",
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
    )
