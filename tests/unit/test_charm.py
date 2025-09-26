import json
from unittest.mock import MagicMock, patch

from scenario import Relation, State

EXAMPLE_SIMPLE_SCRIPT = """#!/bin/bash

ping -c 3 $1 > /dev/null 2>&1
exit $?
"""

EXAMPLE_SIMPLE_CONFIG = """scripts:
  - name: ping
    command: /etc/script
    args:
      - 127.0.0.1
"""

PROMETHEUS_SIMPLE_CONFIG = """scrape_configs:
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

# This is the output of the following command:
# tar -z --lzma script1.sh script2.sh | base64
# where script1.sh and script2.sh are:
#
# #!/bin/sh
# echo "hello{param=\"$1\"} 1"
#
# #!/bin/sh
# echo "bye{param=\"$1\"} 1"

EXAMPLE_B64_COMPRESSED_SCRIPTS = """
H4sIAAAAAAAAA+3TsQ6CMBCA4c4+Ra3O0iMtTL4JCxiSalQMxcEY313FQeOgExKT/1tuuBtu+eOq
XR86WcSgBmNvsszdp+Tevs4Hlyvx1uciqXOpsiIu80rb4V56OsaubLVWmybWn+6+7f/UbJpU630S
w6RehUabUG+3zflQtuVuWZi5FOaixUzGfhMDiX3/6cj9+2f/Puv7z4X+f+G9/+pUUz8AAAAAAAAA
AAAAAMAfuQIhncIHACgAAA==
"""

EXAMPLE_MULTIPLE_CONFIG = """scripts:
  - name: hello
    command: script1.sh
    args:
      - diego

  - name: bye
    command: script2.sh
    args:
      - maradona
"""

PROMETHEUS_MULTIPLE_CONFIG = """scrape_configs:
  - job_name: 'script_hello'
    metrics_path: /probe
    params:
      script: [hello]
      prefix: [script]
    static_configs:
      - targets:
        - 127.0.0.1

  - job_name: 'script_bye'
    metrics_path: /probe
    params:
      script: [bye]
      prefix: [script]
    static_configs:
      - targets:
        - 127.0.0.1
"""


@patch("charm.service_restart", MagicMock(return_value=True))
def test_status_no_config_file(ctx):
    state = State(config={"config_file": ""})
    state_out = ctx.run(ctx.on.config_changed(), state=state)
    assert state_out.unit_status.name == "blocked"


@patch("charm.service_restart", MagicMock(return_value=True))
def test_status_no_prometheus_config_file(ctx):
    state = State(config={"config_file": ""})
    state_out = ctx.run(ctx.on.config_changed(), state=state)
    assert state_out.unit_status.name == "blocked"


def test_cos_agent_relation_data_is_set_script_file(ctx):
    cos_agent_relation = Relation("cos-agent", remote_app_name="grafana-agent")
    state = State(
        relations=[cos_agent_relation],
        config={
            "config_file": EXAMPLE_SIMPLE_CONFIG,
            "script_file": EXAMPLE_SIMPLE_SCRIPT,
            "prometheus_config_file": PROMETHEUS_SIMPLE_CONFIG,
        },
    )
    state_out = ctx.run(ctx.on.relation_changed(cos_agent_relation), state=state)

    relation_data = json.loads(next(iter(state_out.relations)).local_unit_data["config"])
    assert len(relation_data["metrics_scrape_jobs"]) == 2


def test_cos_agent_relation_data_is_set_scripts_archive(ctx):
    cos_agent_relation = Relation("cos-agent", remote_app_name="grafana-agent")
    state = State(
        relations=[cos_agent_relation],
        config={
            "scripts_archive": EXAMPLE_B64_COMPRESSED_SCRIPTS,
            "script_file": EXAMPLE_MULTIPLE_CONFIG,
            "prometheus_config_file": PROMETHEUS_MULTIPLE_CONFIG,
        },
    )
    state_out = ctx.run(ctx.on.relation_changed(cos_agent_relation), state=state)

    relation_data = json.loads(next(iter(state_out.relations)).local_unit_data["config"])
    assert len(relation_data["metrics_scrape_jobs"]) == 3
