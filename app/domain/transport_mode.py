from dataclasses import dataclass


@dataclass(frozen=True)
class TransportMode:
    mode: str  # "direct" | "ipsec"

    @classmethod
    def from_string(cls, value: str) -> "TransportMode":
        return cls(mode=(value or "direct").strip().lower())

    @property
    def is_ipsec(self) -> bool:
        return self.mode == "ipsec"

    def label(self, ipsec_active: bool = False, has_private_host: bool = False) -> str:
        if not self.is_ipsec:
            return "Direct public relay"
        if ipsec_active:
            return "IPSec private relay"
        if has_private_host:
            return "IPSec degraded: private relay unreachable"
        return "IPSec configured, waiting for private cutover"
