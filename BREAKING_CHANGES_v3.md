# Breaking Changes: script_exporter v2.15.1 → v3.2.0

This document covers all breaking changes when upgrading from script_exporter
v2.15.1 to v3.2.0. All breaking changes were introduced in **v3.0.0**. Releases
v3.1.0 and v3.2.0 contain only additive features and bug fixes.

## Upstream Breaking Changes

### Binary Distribution

- Release assets changed from raw binary files to `.tar.gz` archives.
  - v2: `script_exporter-linux-amd64` (raw binary)
  - v3: `script_exporter-linux-amd64.tar.gz` (tarball containing `script_exporter`)

### Command-Line Flags

All command-line flags were renamed. The following table summarises the changes:

| v2 Flag | v3 Flag | Notes |
|---|---|---|
| `-config.file` | `--config.files` | Now plural; supports glob patterns for multiple config files |
| `-timeout-offset` | `--script.timeout-offset` | |
| `-web.listen-address` | `--web.listen-address` | Now repeatable for multiple addresses |
| `-create-token` | *(removed)* | Bearer auth now via exporter-toolkit |
| `-version` | `--version` | |

New flags added in v3:
- `--config.reload-interval` — Periodic config reload interval
- `--config.check` — Validate config and exit
- `--log.env` — Log environment variables passed to scripts
- `--script.no-args` — Restrict scripts from accepting arguments
- `--web.external-url` — External URL for reverse proxy setups
- `--web.route-prefix` — Prefix for internal web routes
- `--web.config.file` — TLS/auth configuration via exporter-toolkit
- `--discovery.host`, `--discovery.port`, `--discovery.scheme` — Service discovery settings
- `--log.level`, `--log.format` — Logging configuration

### Configuration File Format

#### `command` type changed

The `command` field changed from a single string to a list of strings:

```yaml
# v2
scripts:
  - name: ping
    command: /usr/bin/ping
    args:
      - 127.0.0.1

# v3
scripts:
  - name: ping
    command:
      - /usr/bin/ping
    args:
      - 127.0.0.1
```

#### `ignoreOutputOnFail` replaced by `output` section

```yaml
# v2
scripts:
  - name: example
    command: /usr/bin/example
    ignoreOutputOnFail: true

# v3
scripts:
  - name: example
    command:
      - /usr/bin/example
    output:
      ignore_on_error: true
      # Additional new options:
      # ignore: true          — always ignore output
      # format: "nagios"      — parse Nagios plugin output (v3.2.0+)
```

#### `cacheDuration` replaced by `cache` section

```yaml
# v2
scripts:
  - name: example
    command: /usr/bin/example
    cacheDuration: 60s

# v3
scripts:
  - name: example
    command:
      - /usr/bin/example
    cache:
      duration: 60.0           # float seconds (not a duration string)
      cache_on_error: false
      use_expired_cache_on_error: false
```

#### `allowEnvOverwrite` renamed

```yaml
# v2
allowEnvOverwrite: true

# v3
allow_env_overwrite: true
```

#### `script` option removed

In v2, scripts could use a `script` key as an alias for `command`. This has been
removed; only `command` is supported.

#### Authentication configuration removed

The `tls`, `basicAuth`, and `bearerAuth` top-level configuration sections have
been removed. TLS and authentication are now configured using the Prometheus
Exporter Toolkit via the `--web.config.file` CLI flag. See the
[exporter-toolkit documentation](https://github.com/prometheus/exporter-toolkit/blob/master/docs/web-configuration.md)
for the configuration format.

#### `discovery` section removed from config file

The `discovery` top-level section (with `host`, `port`, `scheme`) has been
removed. Use the `--discovery.host`, `--discovery.port`, and
`--discovery.scheme` CLI flags instead.

#### `scripts_configs` removed

The `scripts_configs` option for specifying multiple configuration files has been
removed. Use the `--config.files` CLI flag with glob patterns instead
(e.g., `--config.files=./scripts/*.yaml`).

### Prometheus Scrape Configuration

#### `prefix` parameter removed

The `prefix` URL parameter is no longer supported. Metrics from scripts can no
longer be prefixed. Any Prometheus scrape configuration using
`params: { prefix: [value] }` must remove it.

```yaml
# v2
scrape_configs:
  - job_name: 'my_script'
    metrics_path: /probe
    params:
      script: [test]
      prefix: [my_prefix]    # ← remove this

# v3
scrape_configs:
  - job_name: 'my_script'
    metrics_path: /probe
    params:
      script: [test]
```

#### `output` URL parameter removed

The `output: [ignore]` URL parameter is no longer supported. Use the `output`
section in the script configuration file instead.

### Metrics Changes

#### `/metrics` endpoint

The metrics exposed on the `/metrics` endpoint have been reworked. New metrics:

- `script_exporter_script_unknown_total`
- `script_exporter_http_requests_inflight`
- `script_exporter_http_requests_total`
- `script_exporter_http_request_duration_seconds`
- `script_exporter_config_last_reload_successful`
- `script_exporter_config_last_reload_success_timestamp_seconds`

#### Script probe metrics

- `script_use_cache` — **removed**
- `script_use_expired_cache` — **removed**
- `script_cached` — **added** (indicates if the result was returned from cache)

### Output Parsing

Script output parsing has been reworked. Instead of a custom regular expression,
the exporter now uses
[github.com/prometheus/common/expfmt](https://pkg.go.dev/github.com/prometheus/common/expfmt)
to validate and export only valid Prometheus metrics from script output. Scripts
that previously output malformed metrics that happened to be accepted may now
have those metrics rejected.

### Docker Image

The Docker image has been moved from Docker Hub to the GitHub Container Registry:
`ghcr.io/ricoberger/script_exporter`

---

## Charm-Specific Breaking Changes

This section covers how the upstream breaking changes affect the
**script-exporter charm** and what was changed to accommodate them.

### Binary Packaging (charmcraft.yaml)

The `script-exporter-binary` part in `charmcraft.yaml` was updated:

- **Source URL**: Changed from a raw binary URL to a `.tar.gz` URL
- **`source-type`**: Changed from `file` to `tar`
- **`permissions` path**: Changed from `script_exporter-linux-${CRAFT_ARCH_BUILD_FOR}` to `script_exporter` (the binary name inside the tarball)

### CLI Flag (src/charm.py)

The systemd service `ExecStart` was updated:
- `--config.file=` → `--config.files=`

### Binary Name (src/charm.py)

The `_ensure_binary()` method was updated to copy `script_exporter` instead of
`script_exporter-linux-{arch}`, since the extracted tarball contains the binary
with the simpler name. The `ARCH` constant and `platform` import were removed as
they are no longer needed.

### Config File Parsing (src/charm.py)

The `_insert_full_path_in_command()` method was updated to handle `command` as a
list of strings instead of a single string. The first element of the list (the
executable) is compared against known script names and has its path updated.

### User-Facing Impact

Users of the charm who provide their own `config_file` values will need to
update their configuration to use the v3 format:

1. **`command` must be a list**: `command: /path/to/script` →
   `command: [/path/to/script]`
2. **`prefix` parameter removed**: Remove any `prefix` parameters from
   Prometheus scrape configurations
3. **`ignoreOutputOnFail` replaced**: Use `output: { ignore_on_error: true }`
4. **`cacheDuration` replaced**: Use `cache: { duration: <seconds> }`
5. **`allowEnvOverwrite` renamed**: Use `allow_env_overwrite`
6. **Auth config removed from YAML**: If using `tls`, `basicAuth`, or
   `bearerAuth` in config files, these must be migrated to the exporter-toolkit
   `--web.config.file` format

### Non-Breaking for the Charm

The following upstream changes do **not** affect the charm:

- Authentication changes (charm never configured `tls`/`basicAuth`/`bearerAuth`)
- Discovery configuration changes (charm doesn't use discovery)
- `scripts_configs` removal (charm uses a single config file)
- Docker image move (charm uses the binary, not Docker)
- Nagios output format support (v3.2.0 addition, not a breaking change)
- Configuration loading from URL (v3.1.0 addition, not a breaking change)
