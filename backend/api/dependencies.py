"""Compose services and repositories around one transaction per request."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from backend.core.database import get_db
from backend.core.security import verify_token
from backend.models.user import User
from backend.repositories import (
    ClusterRepository,
    EdgeRepository,
    NodeAssessmentRepository,
    NodeRepository,
    RankedNodeRepository,
    TransactionRepository,
    UserRepository,
)
from backend.services import (
    AuthService,
    ClusterService,
    EdgeService,
    NodeAssessmentService,
    NodeService,
    RankedNodeService,
    TransactionService,
    UserService,
    NotFoundError,
)


# Finish the transaction before sending the response, including an empty 204.
DbSession = Annotated[Session, Depends(get_db, scope="function")]
bearer_scheme = HTTPBearer(auto_error=False)


def credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_token_subject(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> int:
    # Reject absent/invalid credentials before opening a database connection.
    if credentials is None:
        raise credentials_exception()
    try:
        return int(verify_token(credentials.credentials)["sub"])
    except InvalidTokenError as exc:
        raise credentials_exception() from exc


def get_current_user(
    user_id: Annotated[int, Depends(get_token_subject)],
    session: DbSession,
) -> User:
    try:
        return UserService(UserRepository(session)).get_by_id(user_id)
    except NotFoundError as exc:
        raise credentials_exception() from exc


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_auth_service(session: DbSession) -> AuthService:
    return AuthService(UserRepository(session))


def get_node_service(session: DbSession) -> NodeService:
    return NodeService(NodeRepository(session))


def get_edge_service(session: DbSession) -> EdgeService:
    return EdgeService(EdgeRepository(session))


def get_transaction_service(session: DbSession) -> TransactionService:
    return TransactionService(TransactionRepository(session))


def get_cluster_service(session: DbSession) -> ClusterService:
    return ClusterService(ClusterRepository(session))


def get_node_assessment_service(session: DbSession) -> NodeAssessmentService:
    return NodeAssessmentService(NodeAssessmentRepository(session))


def get_ranked_node_service(session: DbSession) -> RankedNodeService:
    return RankedNodeService(RankedNodeRepository(session))
