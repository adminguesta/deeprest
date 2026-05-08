from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ValidationInfo, field_validator
from sqlalchemy import String
from sqlmodel import JSON, Column, Field, SQLModel


class MappingRule(SQLModel, table=True):
    id: Optional[int] = Field(primary_key=True, default=None)
    tenant_id: str = Field(foreign_key="tenant.id")
    priority: int = Field(default=0, nullable=False)
    name: str = Field(max_length=255, nullable=False)
    description: Optional[str] = Field(max_length=2048)
    file_name: Optional[str] = Field(max_length=255)
    created_by: Optional[str] = Field(max_length=255)
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    disabled: bool = Field(default=False)
    # Whether this rule should override existing attributes in the alert
    override: bool = Field(default=True)
    condition: Optional[str] = Field(max_length=2000)
    # The type of this mapping rule
    type: str = Field(
        sa_column=Column(
            String(255),
            name="type",
            server_default="csv",
        ),
        max_length=255,
    )
    # The attributes to match against (e.g. [["service","region"], ["pod"]])
    # Within a list it's AND, between lists it's OR: (service AND pod) OR pod
    matchers: list[list[str]] = Field(sa_column=Column(JSON))
    # The rows of the CSV file [{service: "service1", region: "region1", ...}, ...]
    rows: Optional[list[dict]] = Field(
        sa_column=Column(JSON),
    )  # max_length=204800)
    updated_by: Optional[str] = Field(max_length=255, default=None)
    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Multi-level mapping fields
    is_multi_level: bool = Field(default=False)
    new_property_name: Optional[str] = Field(max_length=255)
    prefix_to_remove: Optional[str] = Field(max_length=255)


class MappRuleDtoBase(BaseModel):
    name: str
    description: Optional[str] = None
    file_name: Optional[str] = None
    priority: int = 0
    matchers: list[list[str]]
    type: Literal["csv", "topology"] = "csv"
    is_multi_level: bool = False
    new_property_name: Optional[str] = None
    prefix_to_remove: Optional[str] = None

    @field_validator("new_property_name")
    @classmethod
    def validate_new_property_name(cls, v, info: ValidationInfo):
        if info.data.get("is_multi_level") and not v:
            raise ValueError(
                "new_property_name is required when is_multi_level is True"
            )
        return v

    @field_validator("matchers")
    @classmethod
    def validate_matchers(cls, v, info: ValidationInfo):
        if info.data.get("is_multi_level") and len(v) > 1:
            raise ValueError("Multi-level mapping can only have one matcher group")
        return v


class MappingRuleDtoOut(MappRuleDtoBase, extra="ignore"):
    id: int
    created_by: Optional[str] = None
    created_at: datetime
    attributes: list[str] = []
    updated_by: Optional[str] | None = None
    last_updated_at: Optional[datetime] | None = None
    rows: Optional[list[dict]] = None


class MappingRuleDtoIn(MappRuleDtoBase):
    rows: Optional[list[dict]] = None

    @field_validator("rows", mode="before")
    @classmethod
    def validate_rows(cls, rows, info: ValidationInfo):
        if not rows and info.data.get("type") == "csv":
            raise ValueError("Mapping of type CSV cannot have empty rows")
        return rows


class MappingRuleUpdateDtoIn(MappRuleDtoBase):
    rows: Optional[list[dict]] = None
