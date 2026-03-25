from __future__ import annotations

import uuid

from fastapi import Depends

from src.workflow.exceptions import DSLParseError
from src.workflow.models.schemas import CreateWorkflowRequest, WorkflowResponse
from src.workflow.repositories.workflows import WorkflowRepository
from src.workflow.utils.dsl_parser import parse_dict, parse_yaml


class WorkflowService:
    def __init__(self, repo: WorkflowRepository = Depends()) -> None:
        self._repo = repo

    async def create(self, request: CreateWorkflowRequest) -> WorkflowResponse:
        if request.yaml_definition:
            wf_def = parse_yaml(request.yaml_definition)
            definition_dict = wf_def.model_dump(mode="json")
        elif request.definition:
            wf_def = parse_dict(request.definition)
            definition_dict = wf_def.model_dump(mode="json")
        else:
            raise DSLParseError(
                "Either 'yaml_definition' or 'definition' must be provided"
            )

        latest = await self._repo.get_latest_version(request.name)
        next_version = (latest.version + 1) if latest else 1

        entity = await self._repo.create(
            name=request.name,
            version=next_version,
            owner_id=request.owner_id,
            definition=definition_dict,
            triggers=request.triggers,
            recovery=request.recovery,
        )
        return WorkflowResponse.model_validate(entity)

    async def get(self, workflow_id: uuid.UUID) -> WorkflowResponse | None:
        entity = await self._repo.get_by_id(workflow_id)
        if entity is None:
            return None
        return WorkflowResponse.model_validate(entity)

    async def list(
        self,
        name: str | None = None,
        owner_id: uuid.UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[WorkflowResponse]:
        entities = await self._repo.list(
            name=name, owner_id=owner_id, limit=limit, offset=offset
        )
        return [WorkflowResponse.model_validate(e) for e in entities]
