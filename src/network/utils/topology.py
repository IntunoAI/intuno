"""Topology validation and routing rules for communication networks.

Enforces communication constraints based on the network's topology type:
- mesh: any participant can communicate with any other
- star: only the hub (first participant) can initiate
- ring: messages flow sequentially through participants
- custom: no enforcement (topology managed externally)
"""

from uuid import UUID

from src.exceptions import BadRequestException
from src.network.models.entities import (
    CommunicationNetwork,
    NetworkParticipant,
    TopologyType,
)


class TopologyValidator:
    """Validates whether communication is allowed given the network topology."""

    def validate(
        self,
        network: CommunicationNetwork,
        sender: NetworkParticipant,
        recipient: NetworkParticipant,
        participants: list[NetworkParticipant],
    ) -> None:
        """Raise BadRequestException if communication is not allowed."""
        topology = network.topology_type
        if topology == TopologyType.mesh or topology == TopologyType.custom:
            return  # no restrictions

        if topology == TopologyType.star:
            self._validate_star(sender, participants)
        elif topology == TopologyType.ring:
            self._validate_ring(sender, recipient, participants)

    def _validate_star(
        self,
        sender: NetworkParticipant,
        participants: list[NetworkParticipant],
    ) -> None:
        """In star topology, only the hub (first participant) can initiate."""
        if not participants:
            return
        hub = participants[0]
        if sender.id != hub.id:
            raise BadRequestException(
                f"Star topology: only the hub participant '{hub.name}' can initiate communication"
            )

    def _validate_ring(
        self,
        sender: NetworkParticipant,
        recipient: NetworkParticipant,
        participants: list[NetworkParticipant],
    ) -> None:
        """In ring topology, messages flow to the next participant in order."""
        if len(participants) < 2:
            return
        ids = [p.id for p in participants]
        try:
            sender_idx = ids.index(sender.id)
        except ValueError:
            raise BadRequestException("Sender is not in the participant list")
        next_idx = (sender_idx + 1) % len(ids)
        if recipient.id != ids[next_idx]:
            expected_name = participants[next_idx].name
            raise BadRequestException(
                f"Ring topology: '{sender.name}' can only send to the next participant "
                f"'{expected_name}', not '{recipient.name}'"
            )

    def get_reachable(
        self,
        network: CommunicationNetwork,
        sender: NetworkParticipant,
        participants: list[NetworkParticipant],
    ) -> list[NetworkParticipant]:
        """Return participants that the sender can communicate with."""
        topology = network.topology_type
        others = [p for p in participants if p.id != sender.id]

        if topology == TopologyType.mesh or topology == TopologyType.custom:
            return others

        if topology == TopologyType.star:
            hub = participants[0] if participants else None
            if hub and sender.id == hub.id:
                return others
            return [hub] if hub else []

        if topology == TopologyType.ring:
            ids = [p.id for p in participants]
            try:
                sender_idx = ids.index(sender.id)
            except ValueError:
                return []
            next_idx = (sender_idx + 1) % len(ids)
            return [participants[next_idx]]

        return others
