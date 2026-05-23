import yaml

with open("docker-compose.yml", "r") as f:
    compose = yaml.safe_load(f)

api_gateway = compose["services"]["api-gateway"]
if "ports" not in api_gateway:
    api_gateway["ports"] = []
if "8000:8000" not in api_gateway["ports"]:
    api_gateway["ports"].append("8000:8000")

with open("docker-compose.yml", "w") as f:
    yaml.dump(compose, f, sort_keys=False, default_flow_style=False)
