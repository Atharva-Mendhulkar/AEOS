import yaml

with open("docker-compose.yml", "r") as f:
    compose = yaml.safe_load(f)

for service_name, service in compose.get("services", {}).items():
    if "environment" in service:
        # Some use JWT_SECRET, some might need AEOS_JWT_SECRET
        if isinstance(service["environment"], dict):
            service["environment"]["AEOS_JWT_SECRET"] = "${AEOS_JWT_SECRET:-${JWT_SECRET}}"
        elif isinstance(service["environment"], list):
            service["environment"].append("AEOS_JWT_SECRET=${AEOS_JWT_SECRET:-${JWT_SECRET}}")

with open("docker-compose.yml", "w") as f:
    yaml.dump(compose, f, sort_keys=False, default_flow_style=False)
