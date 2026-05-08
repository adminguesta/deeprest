from collections import OrderedDict
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ValidationInfo, field_validator

from keep.functions import cyaml


def represent_ordered_dict(dumper, data):
    filtered_data = {k: v for k, v in data.items() if v is not None}
    return dumper.represent_mapping("tag:yaml.org,2002:map", filtered_data.items())


cyaml.add_representer(OrderedDict, represent_ordered_dict)


class ProviderDTO(BaseModel):
    type: str
    id: str | None = None  # if not installed - no id
    name: str
    installed: bool


class WorkflowDTO(BaseModel):
    id: str
    name: Optional[str] = "Workflow file doesn't contain name"
    description: Optional[str] = "Workflow file doesn't contain description"
    created_by: str
    creation_time: datetime
    triggers: Optional[List[dict]] = None
    interval: int | None = None
    disabled: bool = False
    last_execution_time: Optional[datetime] = None
    last_execution_status: Optional[str] = None
    providers: List[ProviderDTO]
    workflow_raw: str
    revision: int = 1
    last_updated: Optional[datetime] = None
    last_updated_by: Optional[str] = None
    invalid: bool = False  # whether the workflow is invalid or not (for UI purposes)
    last_executions: Optional[List[dict]] = None
    last_execution_started: Optional[datetime] = None
    provisioned: bool = False
    provisioned_file: Optional[str] = None
    alertRule: bool = False
    canRun: bool = True

    @property
    def workflow_raw_id(self):
        workflow_id = cyaml.safe_load(self.workflow_raw).get("id")
        return workflow_id

    @field_validator("workflow_raw", mode="after")
    @classmethod
    def manipulate_raw(cls, raw, info: ValidationInfo):
        values = info.data
        """We want to control the "sort" of a workflow when it gets to the front:
            1. id
            2. desc
            3. triggers
            4 --- all the rest ---
            5. steps
            6. actions

        Args:
            raw (_type_): _description_

        Returns:
            _type_: _description_
        """
        ordered_raw = OrderedDict()
        d = cyaml.safe_load(raw)
        # id desc and triggers
        ordered_raw["id"] = d.get("id")
        values["workflow_raw_id"] = d.get("id")
        ordered_raw["description"] = d.get("description")
        ordered_raw["disabled"] = d.get("disabled")
        ordered_raw["triggers"] = d.get("triggers")
        for key, val in d.items():
            if key not in [
                "id",
                "description",
                "disabled",
                "triggers",
                "steps",
                "actions",
            ]:
                ordered_raw[key] = val
        # than steps and actions
        ordered_raw["steps"] = d.get("steps")
        # last, actions
        ordered_raw["actions"] = d.get("actions")
        return cyaml.dump(ordered_raw, width=99999)


class WorkflowExecutionLogsDTO(BaseModel):
    id: int
    timestamp: datetime
    message: str
    context: Optional[dict] = None


class WorkflowToAlertExecutionDTO(BaseModel):
    workflow_id: str
    workflow_execution_id: str
    alert_fingerprint: str
    workflow_status: str
    workflow_started: datetime
    event_id: str | None = None


class WorkflowExecutionDTO(BaseModel):
    id: str
    workflow_id: str | None = None  # None for test runs
    workflow_revision: int | None = None
    started: datetime
    triggered_by: str
    status: str
    workflow_name: Optional[str] = None  # for UI purposes
    logs: Optional[List[WorkflowExecutionLogsDTO]] = None
    error: Optional[str] = None
    execution_time: Optional[float] = None
    results: Optional[dict] = None
    event_id: Optional[str] = None
    event_type: Optional[str] = None


class WorkflowCreateOrUpdateDTO(BaseModel):
    workflow_id: str
    status: Literal["created", "updated"]
    revision: int = 1


class WorkflowRunResponseDTO(BaseModel):
    workflow_execution_id: str


class WorkflowRawDto(BaseModel):
    workflow_raw: str


class WorkflowVersionDTO(BaseModel):
    revision: int
    updated_by: str | None = None
    updated_at: datetime


class WorkflowVersionListDTO(BaseModel):
    versions: List[WorkflowVersionDTO]


class PreparsedWorkflowDTO(BaseModel):
    id: str
    name: str
    description: Optional[str] = "Workflow file doesn't contain description"
    interval: int | None = None
    disabled: bool = False
