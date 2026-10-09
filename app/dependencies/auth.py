"""API-key authentication, exposed as an Authorize button in Swagger UI."""

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.core.exceptions import AccessDeniedException, AuthenticationException
from app.core.tiers import TIER_LIMITS
from app.dependencies.core import get_access_service, get_user_repository
from app.repositories.user_repository import UserRepository
from app.services.access_service import AccessService
from models import User

api_key_header = APIKeyHeader(name="api-key", auto_error=False)


def get_current_user(
    api_key: str | None = Security(api_key_header),
    user_repo: UserRepository = Depends(get_user_repository),
) -> User:
    if not api_key or len(api_key) > 256:
        raise AuthenticationException("Missing or invalid API Key")
    user = user_repo.get_by_api_key(api_key)
    if user is None:
        raise AuthenticationException("Invalid API Key")
    if user.subscription not in TIER_LIMITS:
        raise AccessDeniedException("Invalid subscription tier")
    return user


def get_authorized_user(
    user: User = Depends(get_current_user),
    access_service: AccessService = Depends(get_access_service),
) -> User:
    """Count authenticated attempts to analytical endpoints, including cache hits."""
    access_service.enforce_rate_limit(user)
    return user
