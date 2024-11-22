from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Optional, Dict, Any, List
from bson import ObjectId


class User(BaseModel):
    id: str
    name: Optional[str] = None
    picture: Optional[str] = None
    username: Optional[str] = None
    timezone: Optional[str] = None
    clerk_id: Optional[str] = None
    email: str
    created_at: str
    deleted: bool = False
    deleted_at: Optional[str] = None
    is_pwa_installed: bool = False
    is_pwa_notifications_enabled: bool = False
    pwa_subscription_endpoint: Optional[str] = None
    pwa_subscription_key: Optional[str] = None
    pwa_subscription_auth_token: Optional[str] = None
    plan_ids: List[str] = Field(default_factory=list)
    friend_ids: List[str] = Field(default_factory=list)
    plan_invitations: List[str] = Field(default_factory=list)
    referred_user_ids: List[str] = Field(default_factory=list)

    @classmethod
    def new(
        cls,
        email: str,
        clerk_id: Optional[str] = None,
        picture: Optional[str] = None,
        name: Optional[str] = None,
        id: Optional[str] = None,
        username: Optional[str] = None,
        friend_ids: Optional[List[str]] = [],
    ) -> "User":
        return cls(
            id=id or str(ObjectId()),
            email=email,
            created_at=datetime.now(UTC).isoformat(),
            clerk_id=clerk_id,
            picture=picture,
            name=name,
            username=username,
            friend_ids=friend_ids,
        )
