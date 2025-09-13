#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Charm the application."""

import base64
import io
import logging
import lzma
import os
import shutil
import tarfile
import textwrap
from hashlib import sha256
from pathlib import Path
from typing import List, Union
from urllib import request
from urllib.error import HTTPError

import ops
import yaml
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v1.systemd import (
    daemon_reload,
    service_restart,
    service_resume,
    service_running,
    service_stop,
)
from ops.model import ModelError
from ops.pebble import APIError

logger = logging.getLogger(__name__)

EXPORTER_PORT = 9469

EXPORTER_BINARY_URL = "https://github.com/ricoberger/script_exporter/releases/download/v2.15.1/script_exporter-linux-amd64"
EXPORTER_BINARY_SHA = "e7962a9863c015f721e3cec9af24c85e6b93be79ff992230d9d12029c89f456f"


class ScriptExporterCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, *args):
        super().__init__(*args)

        self._script_exporter_dir = "/etc/script-exporter"
        self._scripts_dir_path = f"{self._script_exporter_dir}/scripts"
        self._single_script_path = "/etc/script-exporter-script"
        self._config_path = f"{self._script_exporter_dir}/config.yaml"
        self._binary_path = "/usr/local/bin/script_exporter"
        self._binary_resource_name = "script-exporter-binary"
        self._script_daemon_service = Path("/etc/systemd/system/script-exporter.service")

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

        # Create an empty configuration file
        try:
            open(self._config_path, "x")
        except FileExistsError:
            logger.debug("config file already exists; skipping its initialization")

        self._ensure_binary()

    def _on_start(self, _: ops.StartEvent):
        """Handle start event."""
        service_restart("script-exporter.service")
        self.set_status()

    def _on_stop(self, _: ops.StopEvent):
        """Ensure that script exporter is stopped."""
        if service_running("script-exporter"):
            service_stop("script-exporter")

        self._remove_file_dir(self._script_exporter_dir)
        self._remove_file_dir(self._binary_path)
        self._remove_file_dir(self._single_script_path)

    def _on_config_changed(self, _: ops.ConfigChangedEvent):
        """Handle config changed event."""
        self._ensure_scripts_dir()
        self._set_config_file()
        self._set_script_files()
        service_restart("script-exporter.service")
        self.set_status()
    def _on_collect_unit_status(self, event: ops.CollectStatusEvent) -> None:
        """Calculate and set the unit status."""
        statuses: List[StatusBase] = []

        if not self.model.config["config_file"]:
            statuses.append(ops.BlockedStatus('Please set the "config_file" config variable'))
        if not (self.model.config["script_file"] or self.model.config["scripts_archive"]):
            statuses.append(ops.BlockedStatus('Please set the "script_file" or "scripts_archive" config variable'))
        elif not self.model.config["prometheus_config_file"]:
            statuses.append(ops.BlockedStatus(
                'Please set the "prometheus_config_file" config variable'
            ))
        else:
            statuses.append(ops.ActiveStatus())

        for status in statuses:
            event.add_status(status)

    def _ensure_binary(self) -> None:
        # Make sure the exporter binary is present with a systemd service
        try:
            self._obtain_exporter(exporter_url=EXPORTER_BINARY_URL, binary_sha=EXPORTER_BINARY_SHA)
        except HTTPError as e:
            msg = "Script Exporter binary couldn't be downloaded - {}".format(str(e))
            logger.warning(msg)
            return

    def _ensure_scripts_dir(self) -> None:
        # Create the scripts directory if it doesn't exist
        if not os.path.exists(self._scripts_dir_path):
            os.makedirs(self._scripts_dir_path)

    def _set_config_file(self) -> None:
        if not self.model.config["config_file"]:
            return

        config_file = self._insert_full_path_in_command(str(self.model.config["config_file"]))
        self._write_file(self._config_path, config_file)
        self._create_systemd_service()

    def _set_script_files(self) -> None:
        if scripts_archive := str(self.model.config["scripts_archive"]):
            self._extract_scripts_archive(scripts_archive)
            return

        if not self.model.config["script_file"]:
            return

        self._write_file(self._single_script_path, str(self.model.config["script_file"]))
        os.chmod(self._single_script_path, 0o755)


    def _extract_scripts_archive(self, scripts_archive: str) -> None:
        data = base64.b64decode(str(scripts_archive))
        decompressed = lzma.decompress(data)
        tar_bytes = io.BytesIO(decompressed)

        with tarfile.open(fileobj=tar_bytes) as tar:
            tar.extractall(path=self._scripts_dir_path)

        for path in Path(self._scripts_dir_path).rglob("*"):
            if not path.is_file():
                continue

            os.chmod(path, 0o755)

    def _insert_full_path_in_command(self, config: str) -> str:
        conf_dict = yaml.safe_load(config)
        scripts_def = conf_dict.get("scripts", [])

        for definition in scripts_def:
            if definition.get("command", '') not in self._script_names:
                msg  = f"{definition.get('command', '')} is not part of the uploaded scripts"
                logger.debug(msg)
                continue

            if self._single_script_path in self._script_names:
                continue

            definition["command"] = os.path.join(self._scripts_dir_path, definition["command"])

        return yaml.dump(conf_dict)

    def _write_file(self, path: Union[str, Path], content: str) -> None:
        """Write content to a file."""
        with open(path, "w") as f:
            f.write(content)

    def _remove_file_dir(self, fd_path: str) -> None:
        """Remove a file or directory if it exists."""
        try:
            if os.path.isdir(fd_path):
                shutil.rmtree(fd_path, ignore_errors=True)
            else:
                os.remove(fd_path)
        except FileNotFoundError as e:
            msg = f"file: '{fd_path}' could not be removed - {str(e)}"
            logger.warning(msg)
        except OSError as e:
            msg = f"directory: '{fd_path}' could not be removed - {str(e)}"
            logger.warning(msg)
        except Exception as e:
            logger.error(e)

    def set_status(self):
        """Calculate and set the unit status."""
        if not self.model.config["config_file"]:
            self.unit.status = ops.BlockedStatus('Please set the "config_file" config variable')
        if not (self.model.config["script_file"] or self.model.config["scripts_archive"]):
            self.unit.status = ops.BlockedStatus('Please set the "script_file" or "scripts_archive" config variable')
        elif not self.model.config["prometheus_config_file"]:
            self.unit.status = ops.BlockedStatus(
                'Please set the "prometheus_config_file" config variable'
            )
        else:
            self.unit.status = ops.ActiveStatus()

    @property
    def _script_names(self) -> List[str]:
        if scripts_archive := self.model.config["scripts_archive"]:
            data = base64.b64decode(str(scripts_archive))
            decompressed = lzma.decompress(data)
            tar_bytes = io.BytesIO(decompressed)

            with tarfile.open(fileobj=tar_bytes) as tar:
                return tar.getnames()

        if str(self.model.config["script_file"]):
            return [self._single_script_path]

        return []

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
        service_restart("script-exporter.service")
        # `enable --now`, but it's the only method which ACTUALLY enables it
        # so it will survive reboots
        service_resume("script-exporter.service")

    def _obtain_exporter(self, exporter_url: str, binary_sha: str) -> None:
        """Obtain Script Exporter binary from an attached resource or download it.

        Args:
            exporter_url: url of script exporter binary
            binary_sha: sha of the script exporter binary
        """
        # If not coming from resource and not existing already, download the exporter
        if not self._push_exporter_if_attached() and self._script_exporter_must_be_downloaded(
            binary_sha
        ):
            self._download_exporter_binary(exporter_url)

    def _push_exporter_if_attached(self) -> bool:
        """Check whether Script Exporter binary is attached to the charm or not.

        Returns:
            a boolean representing whether Script Exporter binary is attached or not.
        """
        try:
            resource_path = self.model.resources.fetch(self._binary_resource_name)
        except ModelError:
            return False
        except NameError as e:
            if "invalid resource name" in str(e):
                return False
            raise

        if resource_path:
            logger.info("Script Exporter binary file has been obtained from an attached resource.")
            shutil.copy(resource_path, self._binary_path)
            os.chmod(self._binary_path, 0o755)
            return True
        return False

    def _script_exporter_must_be_downloaded(self, binary_sha: str) -> bool:
        """Check whether script exporter binary must be downloaded or not.

        Args:
            binary_sha: string sha of the script exporter binary

        Returns:
            a boolean representing whether Script Exporter should be downloaded
        """
        if not self._is_exporter_binary_in_charm(self._binary_path):
            return True

        if not self._sha256sums_matches(self._binary_path, binary_sha):
            return True

        logger.debug("Script Exporter binary file is already in the the charm container.")
        return False

    def _sha256sums_matches(self, file_path: str, sha256sum: str) -> bool:
        """Check whether a file's sha256sum matches or not with a specific sha256sum.

        Args:
            file_path: A string representing the files' patch.
            sha256sum: The sha256sum against which we want to verify.

        Returns:
            a boolean representing whether a file's sha256sum matches or not with
            a specific sha256sum.
        """
        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                result = sha256(file_bytes).hexdigest()

                if result != sha256sum:
                    msg = "File sha256sum mismatch, expected:'{}' but got '{}'".format(
                        sha256sum, result
                    )
                    logger.debug(msg)
                    return False

                return True
        except (APIError, FileNotFoundError):
            msg = "File: '{}' could not be opened".format(file_path)
            logger.error(msg)
            return False

    def _is_exporter_binary_in_charm(self, binary_path: str) -> bool:
        """Check if Script Exporter binary is already stored locally.

        Args:
            binary_path: string path of the binary to check

        Returns:
            a boolean representing whether Script Exporter is present or not.
        """
        return True if Path(binary_path).is_file() else False

    def _download_exporter_binary(self, exporter_url: str) -> None:
        """Download the Script Exporter binary file and move it to its new location.

        Args:
            exporter_url: url where to get Script Exporter binary from
        """
        with request.urlopen(exporter_url) as r:
            file_bytes = r.read()
            with open(self._binary_path, "wb") as f:
                f.write(file_bytes)
                logger.info(
                    "Script Exporter binary file has been downloaded and stored in: %s",
                    self._binary_path,
                )
                os.chmod(self._binary_path, 0o755)


if __name__ == "__main__":  # pragma: nocover
    ops.main(ScriptExporterCharm)  # type: ignore
