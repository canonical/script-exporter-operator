import json

import charm
from unittest.mock import patch, MagicMock
from scenario import Context, Relation, State

EXAMPLE_SCRIPT = """#!/bin/bash

ping -c 3 $1 > /dev/null 2>&1
exit $?
"""

EXAMPLE_CONFIG = """scripts:
  - name: ping
    command: /etc/script
    args:
      - 127.0.0.1
"""

PROMETHEUS_CONFIG = """scrape_configs:
  - job_name: 'script_ping'
    metrics_path: /probe
    params:
      script: [ping]
      prefix: [script]
    static_configs:
      - targets:
        - 127.0.0.1
    relabel_configs:
      - target_label: script
        replacement: ping
"""

@patch("charm.service_restart", MagicMock(return_value=True))
def test_status_no_script():
    context = Context(charm_type=charm.ScriptExporterCharm)
    state = State(config={"config_file": "", "script_file": "", "prometheus_config_file": ""})
    state_out = context.run(event="config-changed", state=state)
    assert state_out.unit_status.name == "blocked"

def test_cos_agent_relation_data_is_set():
    cos_agent_relation = Relation("cos-agent", remote_app_name="grafana-agent")
    context = Context(charm_type=charm.ScriptExporterCharm)
    state = State(
        relations=[cos_agent_relation],
        config={"config_file": EXAMPLE_CONFIG, "script_file": EXAMPLE_SCRIPT, "prometheus_config_file": PROMETHEUS_CONFIG},
    )
    state_out = context.run(event=cos_agent_relation.changed_event, state=state)

    relation_data = json.loads(state_out.relations[0].local_unit_data["config"])
    assert len(relation_data["metrics_scrape_jobs"]) == 2
