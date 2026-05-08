from datetime import datetime

from sqlmodel import Field, SQLModel
from pydantic import ConfigDict

class Secret(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
    
    last_updated: datetime = Field(
        default_factory=datetime.utcnow, 
    )
    model_config = ConfigDict(from_attributes=True)