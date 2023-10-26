# script-exporter

Charmhub package name: script-exporter  
More information: https://charmhub.io/script-exporter

The Script Exporter charm exposes metrics from the output of executed scripts over a Prometheus compatible OpenMetrics endpoint.

## Running Script Exporter

### Quick-start reference

```sh
juju deploy script-exporter

# Pass the script
juju config script-exporter script_file=@script.sh
# Pass the script-exporter configuration
juju config script-exporter config_file=@script-exporter.yaml
# Pass the Prometheus scrape jobs configuration
juju config script-exporter prometheus_config_file=@prometheus.yaml

# Add the relations
juju relate script-exporter:juju-info <principal>
juju relate script-exporter:cos-agent grafana-agent
```

### How-To guide

The script-exporter is a subordinate charm; relating it to a *principal* over **juju-info** will deploy it to the machine.

For the exporter to function correctly, you need to configure three variables through `juju config`:
1. **script_file**: with the current implementation, you can only pass a single script for the exporter to execute; your script could be as straightforward as:
    ```sh
    #!/bin/sh
    echo "hello_world{param=\"$1\"} 1"
    ```
    This script is stored on disk at the `/etc/script-exporter-script` path.  
    You can find inspiration by looking at the [official examples](https://github.com/ricoberger/script_exporter/tree/main/examples).

2. **config_file**: this is the configuration for the Script Exporter itself; here is where you define which scripts the exporter should be able to execute and how they're called. An example configuration file is:
    ```yaml
    scripts:
      - name: hello # Name of the script, arbitrary
        command: /etc/script-exporter-script # any available shell command, or `/etc/script-exporter-script` for the custom one
        args:
          - argument # args to pass to the script
    ```
    Please note that if you want to run the script you passed through `juju config`, the **command** must be set to `/etc/script-exporter-script`. 
    This configuration file will be saved to `/etc/script-exporter.yaml`.  
    More details on how to write this configuration file can be found in the [official docs](https://github.com/ricoberger/script_exporter/tree/main#usage-and-configuration).

3. **prometheus_config_file**: this specifies the scrape jobs to finally execute the scripts; an example would be:
    ```yaml
    scrape_configs:
      - job_name: 'script_helloworld' # job name, arbitrary
        metrics_path: /probe
        params:
          script: [hello] # the name of the script as specified in the *config_file*
          prefix: [script] # a custom prefix for this metric
        static_configs:
          - targets:
            - 127.0.0.1
    ```
    The `relabel_configs` section will be overwritten by the charm, so it's optional.  
    For more details on this configuration, refer to the [official documentation](https://github.com/ricoberger/script_exporter/tree/main#prometheus-configuration).

### Environments with no internet access

The charm will automatically download the `script_exporter` binary from the internet. If your machine can't or you want to pass it locally, simply deploy the charm by passing the `script-exporter-binary` resource to it, as in:

```
juju deploy script-exporter --resource script-exporter-binary=@./script_exporter
```

## Building Script Exporter

The charm can be easily built with charmcraft.
```sh
charmcraft pack
```

## Testing Script Exporter

The run the standard set of linting and tests simply run tox with no arguments.

```sh
tox
```

To run just the unit tests:

```sh
tox -e unit,scenario
```

To run the integration tests:

```sh
tox -e integration
```

## Links
[Docs](https://charmhub.io/script-exporter)  
[Pull Requests](https://github.com/canonical/script-exporter-operator/pulls)  
[Issues](https://github.com/canonical/script-exporter-operator/issues)  
