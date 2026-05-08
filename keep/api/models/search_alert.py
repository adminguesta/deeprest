from pydantic import field_validator, ConfigDict, BaseModel, Field

from keep.api.models.db.preset import PresetSearchQuery


class SearchAlertsRequest(BaseModel):
    query: PresetSearchQuery = Field(..., alias="query")
    timeframe: int = Field(..., alias="timeframe")

    @field_validator("query")
    @classmethod
    def validate_search_query(cls, value):
        if value.timeframe < 0:
            raise ValueError("Timeframe must be greater than or equal to 0.")
        return value
    model_config = ConfigDict(extra="allow")
