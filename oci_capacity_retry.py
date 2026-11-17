#!/usr/bin/env python3
"""Retry launching an OCI compute instance while host capacity is unavailable."""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from pathlib import Path


LOG = logging.getLogger("oci-capacity-retry")


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keep retrying OCI instance launch until capacity is available."
    )
    parser.add_argument("--config-file", default=os.getenv("OCI_CONFIG_FILE") or None)
    parser.add_argument("--profile", default=os.getenv("OCI_PROFILE", "DEFAULT"))
    parser.add_argument("--compartment-id", default=os.getenv("OCI_COMPARTMENT_ID"))
    parser.add_argument("--availability-domain", default=os.getenv("OCI_AVAILABILITY_DOMAIN"))
    parser.add_argument("--subnet-id", default=os.getenv("OCI_SUBNET_ID"))
    parser.add_argument("--image-id", default=os.getenv("OCI_IMAGE_ID"))
    parser.add_argument("--shape", default=os.getenv("OCI_SHAPE"))
    parser.add_argument("--display-name", default=os.getenv("OCI_DISPLAY_NAME", "capacity-retry-instance"))
    parser.add_argument("--ssh-public-key-file", default=os.getenv("OCI_SSH_PUBLIC_KEY_FILE"))
    parser.add_argument("--ocpus", type=float, default=os.getenv("OCI_OCPUS") or None)
    parser.add_argument("--memory-gb", type=float, default=os.getenv("OCI_MEMORY_GB") or None)
    parser.add_argument("--boot-volume-gb", type=int, default=os.getenv("OCI_BOOT_VOLUME_GB") or None)
    parser.add_argument(
        "--assign-public-ip",
        action=argparse.BooleanOptionalAction,
        default=env_bool("OCI_ASSIGN_PUBLIC_IP", True),
    )
    parser.add_argument(
        "--retry-seconds", type=float, default=float(os.getenv("OCI_RETRY_SECONDS", "60"))
    )
    parser.add_argument(
        "--max-retry-seconds", type=float, default=float(os.getenv("OCI_MAX_RETRY_SECONDS", "900"))
    )
    parser.add_argument(
        "--max-attempts", type=int, default=int(os.getenv("OCI_MAX_ATTEMPTS", "0")),
        help="Maximum launch attempts; 0 retries forever (default).",
    )
    args = parser.parse_args()

    required = (
        "compartment_id",
        "availability_domain",
        "subnet_id",
        "image_id",
        "shape",
        "ssh_public_key_file",
    )
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        parser.error("missing required settings: " + ", ".join("--" + name.replace("_", "-") for name in missing))
    if (args.ocpus is None) != (args.memory_gb is None):
        parser.error("--ocpus and --memory-gb must be provided together")
    if args.retry_seconds <= 0 or args.max_retry_seconds <= 0 or args.max_attempts < 0:
        parser.error("retry intervals must be positive and max attempts cannot be negative")
    return args


def is_capacity_error(error: Exception) -> bool:
    code = getattr(error, "code", "") or ""
    message = str(getattr(error, "message", "") or error).lower()
    return code.lower() == "outofhostcapacity" or "out of host capacity" in message


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()

    try:
        import oci
        from oci.exceptions import ServiceError
    except ImportError:
        LOG.error("OCI SDK is missing. Install it with: pip install -r oci-requirements.txt")
        return 1

    try:
        config = oci.config.from_file(
            file_location=str(Path(args.config_file).expanduser()) if args.config_file else None,
            profile_name=args.profile,
        )
        compute = oci.core.ComputeClient(config)
    except Exception as error:
        LOG.error("Could not initialize OCI client: %s", error)
        return 1

    try:
        ssh_key = Path(args.ssh_public_key_file).expanduser().read_text(encoding="utf-8").strip()
    except OSError as error:
        LOG.error("Could not read SSH public key: %s", error)
        return 1
    if not ssh_key:
        LOG.error("SSH public key file is empty: %s", args.ssh_public_key_file)
        return 1

    shape_config = None
    if args.ocpus is not None:
        shape_config = oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=args.ocpus,
            memory_in_gbs=args.memory_gb,
        )

    source_details = oci.core.models.InstanceSourceViaImageDetails(
        source_type="image",
        image_id=args.image_id,
        boot_volume_size_in_gbs=args.boot_volume_gb,
    )
    launch_details = oci.core.models.LaunchInstanceDetails(
        availability_domain=args.availability_domain,
        compartment_id=args.compartment_id,
        display_name=args.display_name,
        shape=args.shape,
        shape_config=shape_config,
        source_details=source_details,
        create_vnic_details=oci.core.models.CreateVnicDetails(
            subnet_id=args.subnet_id,
            assign_public_ip=args.assign_public_ip,
        ),
        metadata={"ssh_authorized_keys": ssh_key},
    )

    attempt = 0
    while args.max_attempts == 0 or attempt < args.max_attempts:
        try:
            existing = oci.pagination.list_call_get_all_results(
                compute.list_instances,
                compartment_id=args.compartment_id,
                availability_domain=args.availability_domain,
                display_name=args.display_name,
            ).data
        except ServiceError as error:
            LOG.error("Could not check existing instances: %s (%s)", error.message, error.code)
            return 1

        active = next((item for item in existing if item.lifecycle_state != "TERMINATED"), None)
        if active:
            LOG.info(
                "Instance named %r already exists (%s, %s); nothing to do.",
                args.display_name,
                active.lifecycle_state,
                active.id,
            )
            return 0

        attempt += 1
        LOG.info("Launch attempt %d for %s", attempt, args.display_name)
        try:
            response = compute.launch_instance(launch_details)
            instance = response.data
            LOG.info("Instance launch accepted: %s (%s)", instance.display_name, instance.id)
            return 0
        except ServiceError as error:
            if not is_capacity_error(error):
                LOG.error("OCI rejected instance launch: %s (%s)", error.message, error.code)
                return 1
            if args.max_attempts and attempt >= args.max_attempts:
                LOG.error("Capacity is still unavailable after %d attempts.", attempt)
                return 1
            delay_cap = min(args.retry_seconds * (2 ** min(attempt - 1, 30)), args.max_retry_seconds)
            delay = min(random.uniform(delay_cap * 0.9, delay_cap * 1.1), args.max_retry_seconds)
            LOG.warning(
                "No host capacity in %s; retrying in %.0f seconds (%s).",
                args.availability_domain,
                delay,
                error.code,
            )
            try:
                time.sleep(delay)
            except KeyboardInterrupt:
                LOG.info("Stopped by user.")
                return 130
        except KeyboardInterrupt:
            LOG.info("Stopped by user.")
            return 130

    return 1


if __name__ == "__main__":
    sys.exit(main())
