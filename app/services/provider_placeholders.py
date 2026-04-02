from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass
class WorkloadMetadata:
    employee_uuid: UUID
    event_count: int
    total_duration_minutes: int
    back_to_back: bool


class CalendarWorkloadProvider(Protocol):
    async def fetch_workload(self, employee_uuid: UUID) -> WorkloadMetadata:
        ...


class OutlookWorkloadProvider:
    async def fetch_workload(self, employee_uuid: UUID) -> WorkloadMetadata:
        raise NotImplementedError("Outlook provider not implemented yet")


class GmailWorkloadProvider:
    async def fetch_workload(self, employee_uuid: UUID) -> WorkloadMetadata:
        raise NotImplementedError("Gmail provider not implemented yet")
