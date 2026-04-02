from __future__ import annotations

from uuid import UUID

from app.core.state_machine import InvalidStateTransition, StateMachine
from app.models.schemas import Channel, EmployeeState
from app.services.supabase import SupabaseService


class EmployeeService:
    def __init__(self, supabase_service: SupabaseService, state_machine: StateMachine) -> None:
        self._supabase = supabase_service
        self._state_machine = state_machine

    async def resolve_by_channel_identifier(self, channel: Channel, identifier: str) -> dict | None:
        return await self._supabase.get_employee_by_channel_identifier(channel, identifier)

    async def get_by_uuid(self, employee_uuid: UUID) -> dict | None:
        return await self._supabase.get_employee_by_uuid(employee_uuid)

    async def transition_state(self, employee_uuid: UUID, target_state: EmployeeState) -> dict:
        employee = await self._supabase.get_employee_by_uuid(employee_uuid)
        if employee is None:
            raise InvalidStateTransition(f"employee {employee_uuid} not found")
        current_state = EmployeeState(employee["current_state"])
        self._state_machine.assert_transition(current_state, target_state)
        updated = await self._supabase.update_employee_state(employee_uuid, target_state.value)
        if updated is None:
            raise InvalidStateTransition(f"failed to update employee state for {employee_uuid}")
        return updated

    async def move_to_awaiting_for_inbound(self, employee_uuid: UUID) -> EmployeeState:
        employee = await self._supabase.get_employee_by_uuid(employee_uuid)
        if employee is None:
            raise InvalidStateTransition(f"employee {employee_uuid} not found")
        current_state = EmployeeState(employee["current_state"])
        if current_state in {EmployeeState.idle, EmployeeState.scored}:
            await self.transition_state(employee_uuid, EmployeeState.prompted)
            await self.transition_state(employee_uuid, EmployeeState.awaiting)
            return EmployeeState.awaiting
        if current_state == EmployeeState.prompted:
            await self.transition_state(employee_uuid, EmployeeState.awaiting)
            return EmployeeState.awaiting
        if current_state == EmployeeState.awaiting:
            return EmployeeState.awaiting
        raise InvalidStateTransition(
            f"cannot process inbound event while employee is in state {current_state.value}",
        )

    async def complete_scoring(self, employee_uuid: UUID) -> None:
        await self.transition_state(employee_uuid, EmployeeState.scored)

    async def close_cycle_if_delivered(self, employee_uuid: UUID) -> None:
        await self.transition_state(employee_uuid, EmployeeState.idle)

    async def reset_after_inbound_failure(self, employee_uuid: UUID) -> EmployeeState:
        employee = await self._supabase.get_employee_by_uuid(employee_uuid)
        if employee is None:
            raise InvalidStateTransition(f"employee {employee_uuid} not found")
        current_state = EmployeeState(employee["current_state"])
        if current_state == EmployeeState.idle:
            return current_state
        if current_state not in {EmployeeState.prompted, EmployeeState.awaiting, EmployeeState.scored}:
            raise InvalidStateTransition(
                f"cannot reset employee state from {current_state.value}",
            )
        # Failure recovery intentionally bypasses the normal transition graph so a stuck cycle
        # does not block the next inbound message forever.
        updated = await self._supabase.update_employee_state(employee_uuid, EmployeeState.idle.value)
        if updated is None:
            raise InvalidStateTransition(f"failed to reset employee state for {employee_uuid}")
        return EmployeeState(updated["current_state"])
