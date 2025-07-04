from typing import Tuple
from app.infrastructure.database.repositories import (
    TortoiseUserRepository,
    TortoiseAPIKeyRepository,
)
from encryption_src.fernet.service import FernetEncryptionHelper
from app.core.exceptions.base import AuthenticationError, TokenLimitExceededError


class AuthService:
    def __init__(
        self,
        user_repository: TortoiseUserRepository,
        api_key_repository: TortoiseAPIKeyRepository,
        encryption_service: FernetEncryptionHelper,
    ):
        self.user_repository = user_repository
        self.api_key_repository = api_key_repository
        self.encryption_service = encryption_service

    async def authenticate_request(self, api_key: str) -> Tuple[str, dict]:
        """Authenticate request and return user_id and user info"""
        # Find API key
        api_key_record = await self.api_key_repository.find_active_by_key(api_key)
        if not api_key_record:
            raise AuthenticationError("Invalid API key")

        # Get user
        user = await self.user_repository.find_by_user_id(api_key_record.user_id)
        if not user or not user.active:
            raise AuthenticationError("User not found or inactive")

        return user.user_id, {
            "user_id": user.user_id,
            "email": user.email,
            "membership_level": user.membership_level,
            "token_limit": user.token_limit,
            "token_used": user.token_used,
        }

    async def check_token_limit(self, user_id: str, estimated_tokens: int) -> None:
        """Check if user has enough tokens for the operation"""
        user = await self.user_repository.find_by_user_id(user_id)
        if not user:
            raise AuthenticationError("User not found")

        if user.token_used + estimated_tokens > user.token_limit:
            raise TokenLimitExceededError(
                f"Token limit exceeded. Used: {user.token_used}, Limit: {user.token_limit}"
            )

    async def consume_tokens(self, user_id: str, tokens_used: int) -> None:
        """Consume tokens for a user"""
        await self.user_repository.update_token_usage(user_id, tokens_used)
