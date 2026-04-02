from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import EmployeeState


class InvalidStateTransition(Exception):
    pass


VALID_TRANSITIONS: dict[EmployeeState, set[EmployeeState]] = {
    EmployeeState.idle: {EmployeeState.prompted},
    EmployeeState.prompted: {EmployeeState.awaiting},
    EmployeeState.awaiting: {EmployeeState.scored, EmployeeState.prompted},
    EmployeeState.scored: {EmployeeState.idle, EmployeeState.prompted},
}


@dataclass
class StateMachine:
    transitions: dict[EmployeeState, set[EmployeeState]] = None

    def __post_init__(self) -> None:
        if self.transitions is None:
            self.transitions = VALID_TRANSITIONS

    def can_transition(self, current: EmployeeState, target: EmployeeState) -> bool:
        return target in self.transitions.get(current, set())

    def assert_transition(self, current: EmployeeState, target: EmployeeState) -> None:
        if not self.can_transition(current, target):
            raise InvalidStateTransition(
                f"invalid transition from {current.value} to {target.value}",
            )
