from typing import List, Optional, Set

from pydantic import BaseModel, Extra


class Group(BaseModel, extra=Extra.ignore):
    id: str
    name: str
    roles: list[str] = []
    members: list[str] = []
    memberCount: int = 0


class User(BaseModel, extra=Extra.ignore):
    email: str
    name: str
    role: Optional[str] = None
    picture: Optional[str] = None
    created_at: str
    last_login: Optional[str] = None
    ldap: Optional[bool] = False
    groups: Optional[list[Group]] = []


class Role(BaseModel):
    id: str
    name: str
    description: str
    scopes: Set[str]
    predefined: bool = True


class CreateOrUpdateRole(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    scopes: Optional[Set[str]] = None


class PermissionEntity(BaseModel):
    id: str  # permission id
    type: str  # 'user' or 'group'
    name: Optional[str] = None  # permission name


class ResourcePermission(BaseModel):
    resource_id: str
    resource_name: str
    resource_type: str
    permissions: List[PermissionEntity]
