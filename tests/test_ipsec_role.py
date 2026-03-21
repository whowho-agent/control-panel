from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE_DIR = ROOT / 'deploy' / 'ansible' / 'roles' / 'ipsec_transport'
PLAYBOOKS_DIR = ROOT / 'deploy' / 'ansible' / 'playbooks'


def test_ipsec_role_defaults_keep_service_cutover_disabled() -> None:
    defaults = (ROLE_DIR / 'defaults' / 'main.yml').read_text()

    assert 'ipsec_manage_service_cutover: false' in defaults
    assert 'ipsec_interface_id: "{{ ipsec_mark }}"' in defaults



def test_ipsec_conf_template_is_route_based() -> None:
    template = (ROLE_DIR / 'templates' / 'ipsec.conf.j2').read_text()

    assert 'installpolicy=no' in template
    assert 'if_id_in={{ ipsec_interface_id }}' in template
    assert 'if_id_out={{ ipsec_interface_id }}' in template



def test_xfrm_unit_has_cleanup_hook() -> None:
    service = (ROLE_DIR / 'templates' / 'ipsec-xfrm.service.j2').read_text()

    assert 'ExecStart=/usr/local/sbin/ipsec-xfrm.sh' in service
    assert 'ExecStop=/usr/local/sbin/ipsec-xfrm-cleanup.sh' in service
    assert 'PartOf=strongswan-starter.service' in service



def test_validation_checks_established_sa_and_endpoint_reachability() -> None:
    validate = (ROLE_DIR / 'tasks' / 'validate.yml').read_text()

    assert 'ESTABLISHED' in validate
    assert 'Validate protected endpoint is reachable across the tunnel' in validate
    assert 'ipsec_protected_host' in validate



def test_recovery_playbooks_cleanup_xfrm_state() -> None:
    prepare = (PLAYBOOKS_DIR / 'prepare-ipsec-rollback.yml').read_text()
    recover = (PLAYBOOKS_DIR / 'recover-network.yml').read_text()

    assert 'ipsec-xfrm-cleanup.sh' in prepare
    assert 'Stop and disable XFRM interface unit' in recover
    assert 'Run XFRM cleanup helper when present' in recover
