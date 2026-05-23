import yaml
import os

with open("docker-compose.yml", "r") as f:
    compose = yaml.safe_load(f)

for service_name, service in compose.get("services", {}).items():
    if "build" in service:
        context = service["build"].get("context", "")
        if context.startswith("./services/"):
            # It's a python service
            volumes = service.get("volumes", [])
            # Add shared module mount
            new_volume = "./shared/python/aeos_shared:/app/aeos_shared"
            if new_volume not in volumes:
                volumes.append(new_volume)
                service["volumes"] = volumes

# Dump with preserving order (sort_keys=False) and custom Dumper if possible, 
# but PyYAML default is fine for a simple file.
with open("docker-compose.yml", "w") as f:
    yaml.dump(compose, f, sort_keys=False, default_flow_style=False)
