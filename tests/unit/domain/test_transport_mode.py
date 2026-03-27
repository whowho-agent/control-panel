import pytest

from app.domain.transport_mode import TransportMode


def test_from_string_normalises_whitespace_and_case():
    mode = TransportMode.from_string("  IPSec  ")
    assert mode.mode == "ipsec"


def test_from_string_defaults_to_direct_on_empty_string():
    mode = TransportMode.from_string("")
    assert mode.mode == "direct"


def test_is_ipsec_true_for_ipsec_mode():
    mode = TransportMode.from_string("ipsec")
    assert mode.is_ipsec is True


def test_is_ipsec_false_for_direct_mode():
    mode = TransportMode.from_string("direct")
    assert mode.is_ipsec is False


def test_label_direct_mode():
    mode = TransportMode.from_string("direct")
    assert mode.label() == "Direct public relay"


def test_label_ipsec_active():
    mode = TransportMode.from_string("ipsec")
    assert mode.label(ipsec_active=True) == "IPSec private relay"


def test_label_ipsec_degraded_with_private_host():
    mode = TransportMode.from_string("ipsec")
    assert mode.label(ipsec_active=False, has_private_host=True) == "IPSec degraded: private relay unreachable"


def test_label_ipsec_configured_waiting():
    mode = TransportMode.from_string("ipsec")
    assert mode.label(ipsec_active=False, has_private_host=False) == "IPSec configured, waiting for private cutover"
