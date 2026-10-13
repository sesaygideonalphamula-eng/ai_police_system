"""Common building blocks for the multi-agent design: a Message and an Agent."""
from dataclasses import dataclass, field


@dataclass
class Message:
    sender: str
    receiver: str
    type: str
    payload: dict = field(default_factory=dict)


class Agent:
    """Every agent has a name and one method, handle(), that receives a Message
    and returns a reply Message. The Controller routes messages between agents."""
    name = "agent"

    def handle(self, msg):
        raise NotImplementedError

    def reply(self, msg, type_, payload):
        return Message(sender=self.name, receiver=msg.sender, type=type_, payload=payload)
