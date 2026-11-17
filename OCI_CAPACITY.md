# OCI Capacity Retry

This standalone script retries an Oracle Cloud Infrastructure instance launch when the selected availability domain has no host capacity. It stops after OCI accepts the launch request. It does not create, delete, resize, or modify other instances.

## Setup

1. On the machine that will run the script, configure OCI API key authentication with `oci setup config`. The config profile must include the correct region and have permissions to launch compute instances and use the selected network resources.
2. Create a Python virtual environment and install the isolated OCI dependency:

   ```sh
   python3 -m venv .venv
   . .venv/bin/activate
   pip install -r oci-requirements.txt
   ```

3. Copy `oci-capacity.env.example` to `.oci-capacity.env` and set the compartment OCID, availability domain, subnet OCID, image OCID, shape, and path to an SSH **public** key. The image, subnet, and availability domain must be in the configured region and compatible with the selected shape.
4. Load the settings and run from the `server` directory:

   ```sh
   cp oci-capacity.env.example .oci-capacity.env
   set -a
   . ./.oci-capacity.env
   set +a
   python oci_capacity_retry.py
   ```

The script retries indefinitely by default, starting at `OCI_RETRY_SECONDS` and increasing the interval exponentially up to `OCI_MAX_RETRY_SECONDS`. Set `OCI_MAX_ATTEMPTS` to a positive number to stop after that many launch attempts. The script also checks for an existing non-terminated instance with the same display name in the same compartment and availability domain before launching.

For a Flex shape, set both `OCI_OCPUS` and `OCI_MEMORY_GB`; omit both for fixed shapes. `OCI_BOOT_VOLUME_GB` can be left empty to use the image default. `OCI_ASSIGN_PUBLIC_IP=false` disables public IP assignment; ensure the subnet and your network configuration provide another way to connect.

Before running, verify that the requested shape and resource allocation fit your tenancy's Always Free limits. Larger allocations or resources outside the Always Free offer can incur charges. The script intentionally does not enforce free-tier quotas because those vary by tenancy and region.
