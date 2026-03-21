from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE_DIR = ROOT / 'deploy' / 'ansible' / 'roles' / 'ipsec_transport'
PLAYBOOKS_DIR = ROOT / 'deploy' / 'ansible' / 'playbooks'


def test_ipsec_role_defaults_keep_service_cutover_disabled() -> None:
    defaults = (ROLE_DIR / 'defaults' / 'main.yml').read_text()

    assert 'ipsec_manage_service_cutover: false' in defaults
    assert 'ipsec_interface_id: "{{ ipsec_mark }}"' in defaults
    assert 'ipsec_backend: swanctl' in defaults
    assert 'ipsec_backend_service_map:' in defaults
    assert 'swanctl: strongswan' in defaults
    assert 'starter: strongswan-starter' in defaults
    assert 'ipsec_install_policy: false' in defaults
    assert 'ipsec_validate_external_reachability: true' in defaults
    assert 'ipsec_external_reachability_ports: []' in defaults
    assert 'ipsec_management_bypass_udp_ports:' in defaults
    assert 'ipsec_management_bypass_ip_protocols:' in defaults



def test_ipsec_conf_template_is_route_based() -> None:
    template = (ROLE_DIR / 'templates' / 'ipsec.conf.j2').read_text()

    assert "installpolicy={{ 'yes' if ipsec_install_policy | bool else 'no' }}" in template
    assert 'if_id_in={{ ipsec_interface_id }}' in template
    assert 'if_id_out={{ ipsec_interface_id }}' in template



def test_xfrm_unit_is_backend_aware_and_has_cleanup_hook() -> None:
    service = (ROLE_DIR / 'templates' / 'ipsec-xfrm.service.j2').read_text()
    helper = (ROLE_DIR / 'templates' / 'ipsec-xfrm.sh.j2').read_text()

    assert 'ExecStart=/usr/local/sbin/ipsec-xfrm.sh' in service
    assert 'ExecStop=/usr/local/sbin/ipsec-xfrm-cleanup.sh' in service
    assert 'PartOf={{ ipsec_service_unit }}.service' in service
    assert 'After=network-online.target {{ ipsec_service_unit }}.service' in service
    assert 'PROTECTED_DESTINATIONS=(' in helper
    assert 'while ip rule del priority "$RULE_PRIORITY" 2>/dev/null; do' in helper
    assert 'for destination in "${PROTECTED_DESTINATIONS[@]}"; do' in helper



def test_swanctl_templates_are_primary_route_based_backend() -> None:
    swanctl = (ROLE_DIR / 'templates' / 'swanctl.conf.j2').read_text()
    strongswan = (ROLE_DIR / 'templates' / 'strongswan.conf.j2').read_text()

    assert 'children {' in swanctl
    assert 'if_id_in = {{ ipsec_interface_id }}' in swanctl
    assert 'if_id_out = {{ ipsec_interface_id }}' in swanctl
    assert 'start_action = start' in swanctl
    assert 'install_routes = no' in strongswan



def test_apply_tasks_make_swanctl_the_primary_path_and_keep_starter_fallback() -> None:
    apply = (ROLE_DIR / 'tasks' / 'apply.yml').read_text()

    assert 'Render swanctl.conf for swanctl backend' in apply
    assert 'Render ipsec.conf for route-based fallback starter baseline' in apply
    assert "when: ipsec_backend == 'starter'" in apply
    assert "when: ipsec_backend == 'swanctl'" in apply
    assert 'name: "{{ ipsec_service_unit }}"' in apply
    assert 'command: swanctl --load-all' in apply
    assert 'Enable and start XFRM interface unit' in apply
    assert 'command: "{{ ipsec_status_command }}"' in apply



def test_precheck_enforces_supported_backends_and_narrow_protected_routes() -> None:
    precheck = (ROLE_DIR / 'tasks' / 'precheck.yml').read_text()

    assert 'Assert IPSec backend is supported' in precheck
    assert 'ipsec_backend_supported' in precheck
    assert 'ipsec_policy_route_destinations' in precheck
    assert 'ipsec_validation_host' in precheck
    assert 'Assert protected hosts stay narrow and never include public peer or default route' in precheck
    assert 'ipsec_protected_hosts must not include empty values' in precheck
    assert 'Warn when external reachability validation is disabled' in precheck



def test_validation_checks_established_sa_and_endpoint_reachability() -> None:
    validate = (ROLE_DIR / 'tasks' / 'validate.yml').read_text()

    assert 'ESTABLISHED' in validate
    assert 'Validate protected endpoint is reachable across the tunnel' in validate
    assert 'Validate route to each protected destination exists in IPSec route table' in validate
    assert 'retries: 5' in validate
    assert 'Validate policy rule for each protected destination exists' in validate
    assert 'Validate policy rules do not capture peer public IP' in validate
    assert 'Validate only narrow protected-host routes are installed' in validate
    assert 'Validate controller can still reach host public TCP ports after IPSec apply' in validate
    assert 'delegate_to: localhost' in validate
    assert 'ipsec_external_reachability_targets' in validate
    assert "ipsec_backend == 'starter'" in validate
    assert 'Collect backend-specific SA status output' in validate
    assert 'ipsec_status_command' in validate



def test_recovery_playbooks_cleanup_xfrm_state_and_both_backends() -> None:
    prepare = (PLAYBOOKS_DIR / 'prepare-ipsec-rollback.yml').read_text()
    recover = (PLAYBOOKS_DIR / 'recover-network.yml').read_text()

    assert 'ipsec-xfrm-cleanup.sh' in prepare
    assert 'strongswan strongswan-starter strongswan-swanctl charon-systemd' in prepare
    assert 'Stop and disable XFRM interface unit' in recover
    assert 'Run XFRM cleanup helper when present' in recover
    assert 'Stop and disable strongSwan primary swanctl service when present' in recover
    assert 'Stop and disable strongSwan swanctl backend when present' in recover
    assert 'Restore backed-up swanctl.conf if present' in recover



def test_app_cutover_validation_playbook_checks_live_runtime_and_control_plane() -> None:
    validate_app = (PLAYBOOKS_DIR / 'validate-ipsec-app-cutover.yml').read_text()

    assert 'ipsec_expect_private_app_path: false' in validate_app
    assert 'Validate live frontend runtime config points to the expected relay host' in validate_app
    assert "item.get('tag') == 'to-relay'" in validate_app
    assert '/api/xray-frontend/config/frontend' in validate_app
    assert '/api/xray-frontend/topology-health' in validate_app
    assert 'egress_probe_ok' in validate_app
    assert 'XRAY_RELAY_HOST={{ ipsec_expected_app_relay_host }}' in validate_app

