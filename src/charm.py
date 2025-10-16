#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import base64
import io
import logging
import os
import platform
import shutil
import tarfile
import textwrap
from lzma import LZMAError, decompress
from pathlib import Path
from typing import List

import ops
import yaml
from charmlibs.pathops import LocalPath, PathProtocol
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v1.systemd import (
    daemon_reload,
    service_restart,
    service_resume,
    service_running,
    service_stop,
)
from ops import ActiveStatus, BlockedStatus, StatusBase

logger = logging.getLogger(__name__)

EXPORTER_PORT = 9469


ARCH = platform.machine()
if platform.machine() == "x86_64":
    ARCH = "amd64"
elif platform.machine() in ("aarch64", "armv8b", "armv8l"):
    ARCH = "arm64"

SERVICE_FILENAME = "script-exporter.service"


class ScriptExporterCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, *args):
        super().__init__(*args)
        self._statuses: List[StatusBase] = []
        self._script_exporter_dir = LocalPath("/etc/script-exporter")
        self._scripts_dir_path = LocalPath(f"{self._script_exporter_dir}/scripts")
        self._single_script_path = LocalPath("/etc/script-exporter-script")
        self._config_path = LocalPath(f"{self._script_exporter_dir}/config.yaml")
        self._binary_path = LocalPath("/usr/local/bin/script_exporter")
        self._script_daemon_service = Path("/etc/systemd/system/{}".format(SERVICE_FILENAME))

        self.cos_agent = COSAgentProvider(
            charm=self,
            scrape_configs=self.self_scraping_job + self.scripts_scraping_jobs,
            refresh_events=[self.on.config_changed],
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.collect_unit_status, self._on_collect_unit_status)

    def _on_install(self, _: ops.InstallEvent):
        """Handle install event."""
        self._ensure_scripts_dir()

        if not self._config_path.exists():
            self._config_path.write_text("")

        self._ensure_binary()

    def _on_start(self, _: ops.StartEvent):
        """Handle start event."""
        if not service_running(SERVICE_FILENAME) and self.model.config["config_file"]:
            service_restart(SERVICE_FILENAME)

    def _on_stop(self, _: ops.StopEvent):
        """Ensure that script exporter is stopped."""
        if service_running(SERVICE_FILENAME):
            service_stop(SERVICE_FILENAME)

        self._remove_file_dir(self._script_exporter_dir)
        self._remove_file_dir(self._binary_path)
        self._remove_file_dir(self._single_script_path)

    def _on_config_changed(self, _: ops.ConfigChangedEvent):
        """Handle config changed event."""
        self._script_names = self._retrieve_script_names()
        self._ensure_scripts_dir()
        self._set_config_file()
        self._set_script_files()

        if self.model.config["config_file"]:
            service_restart(SERVICE_FILENAME)
        elif service_running(SERVICE_FILENAME):
            service_stop(SERVICE_FILENAME)

    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Calculate and set the unit status."""
        self._statuses.append(ActiveStatus())

        if not self.model.config["config_file"]:
            self._statuses.append(BlockedStatus('Please set the "config_file" config variable'))

        elif not self.model.config["prometheus_config_file"]:
            self._statuses.append(
                BlockedStatus('Please set the "prometheus_config_file" config variable')
            )

        for status in self._statuses:
            event.add_status(status)

    def _ensure_binary(self) -> None:
        # Make sure the exporter binary is present with a systemd service
        shutil.copy("script_exporter-linux-{}".format(ARCH), self._binary_path)
        os.chmod(self._binary_path, 0o755)
        logger.info(
            "Script Exporter binary installed from packaged files: %s", self._binary_path
        )


    def _ensure_scripts_dir(self) -> None:
        # Create the scripts directory if it doesn't exist
        self._scripts_dir_path.mkdir(parents=True, exist_ok=True)

    def _set_config_file(self) -> None:
        if not self.model.config["config_file"]:
            return

        config_file = self._insert_full_path_in_command(str(self.model.config["config_file"]))
        self._config_path.write_text(config_file)
        self._create_systemd_service()

    def _set_script_files(self) -> None:
        if scripts_archive := str(self.model.config["scripts_archive"]):
            self._extract_scripts_archive(scripts_archive)
            return

        if not (script_file := self.model.config["script_file"]):
            return

        self._single_script_path.write_text(str(script_file), mode=0o755)

    def _extract_scripts_archive(self, scripts_archive: str) -> None:
        try:
            tar_bytes = self._base64_compressed_to_tar_bytes(str(scripts_archive))
        except LZMAError as e:
            self._statuses.append(
                BlockedStatus(f"scripts_archive is not a valid lzma archive - {str(e)}")
            )
            return

        with tarfile.open(fileobj=tar_bytes) as tar:
            tar.extractall(path=self._scripts_dir_path)

            for p in Path(self._scripts_dir_path).rglob("*"):
                if not p.is_file():
                    continue

                p.chmod(0o755)

    def _insert_full_path_in_command(self, config: str) -> str:
        conf_dict = yaml.safe_load(config)
        scripts_def = conf_dict.get("scripts", [])

        for definition in scripts_def:
            if definition.get("command", "") not in self._script_names:
                msg = f"{definition.get('command', '')} is not part of the uploaded scripts"
                logger.debug(msg)
                continue

            if self._single_script_path in self._script_names:
                continue

            # Add prefix if the root is relative but keep as is if absolute.
            definition["command"] = os.path.join(self._scripts_dir_path, definition["command"])

        return yaml.dump(conf_dict)

    def _remove_file_dir(self, fd_path: PathProtocol) -> None:
        """Remove a file or directory if it exists."""
        try:
            if fd_path.is_dir():
                shutil.rmtree(str(fd_path), ignore_errors=True)
            else:
                fd_path.unlink()
        except (FileNotFoundError, PermissionError) as e:
            msg = f"'{fd_path}' could not be removed - {str(e)}"
            logger.warning(msg)
        except Exception as e:
            logger.error(e)

    def _retrieve_script_names(self) -> List[str]:
        if scripts_archive := self.model.config["scripts_archive"]:
            try:
                tar_bytes = self._base64_compressed_to_tar_bytes(str(scripts_archive))
            except LZMAError as e:
                msg = f"scripts_archive is not a valid lzma archive - {str(e)}"
                self._statuses.append(BlockedStatus(msg))
                return []

            with tarfile.open(fileobj=tar_bytes) as tar:
                return tar.getnames()

        return [str(self._single_script_path)] if self.model.config["script_file"] else []

    def _base64_compressed_to_tar_bytes(self, b64_compressed: str) -> io.BytesIO:
        data = base64.b64decode(b64_compressed)
        decompressed = decompress(data)
        return io.BytesIO(decompressed)

    @property
    def self_scraping_job(self):
        """The self-monitoring scrape job."""
        return [
            {
                "job_name": "script-exporter",
                "static_configs": [{"targets": [f"localhost:{EXPORTER_PORT}"]}],
            }
        ]

    @property
    def scripts_scraping_jobs(self):
        """The scraping jobs to execute scripts from Prometheus."""
        jobs = []
        prometheus_scrape_jobs = str(self.model.config.get("prometheus_config_file"))
        if prometheus_scrape_jobs:
            scrape_jobs = yaml.safe_load(prometheus_scrape_jobs)
            # Add the Script Exporter's `relabel_configs` to each job
            for scrape_job in scrape_jobs["scrape_configs"]:
                # The relabel configs come from the official Script Exporter docs; please refer
                # to that for further information on what they do
                scrape_job["relabel_configs"] = [
                    {"source_labels": ["__address__"], "target_label": "__param_target"},
                    {"source_labels": ["__param_target"], "target_label": "instance"},
                    # Copy the scrape job target to an extra label for dashboard usage
                    {"source_labels": ["__param_target"], "target_label": "script_target"},
                    # Set the address to scrape to the script exporter url
                    {
                        "target_label": "__address__",
                        "replacement": f"localhost:{EXPORTER_PORT}",
                    },
                ]
                jobs.append(scrape_job)

        return jobs

    # Methods around getting the Script Exporter binary

    def _create_systemd_service(self) -> None:
        """Create the systemd service for the custom exporter."""
        systemd_template = textwrap.dedent(
            f"""
            [Unit]
            Description=Prometheus Script exporter
            Wants=network-online.target
            After=network-online.target

            [Service]
            LimitNPROC=infinity
            LimitNOFILE=infinity
            ExecStart={self._binary_path} --config.file={self._config_path}
            Restart=always

            [Install]
            WantedBy=multi-user.target
            """
        )

        self._script_daemon_service.write_text(systemd_template)

        daemon_reload()
        service_restart(SERVICE_FILENAME)
        # `enable --now`, but it's the only method which ACTUALLY enables it
        # so it will survive reboots
        service_resume(SERVICE_FILENAME)



if __name__ == "__main__":  # pragma: nocover
    ops.main(ScriptExporterCharm)  # type: ignore
