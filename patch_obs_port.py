import yaml

with open("docker-compose.yml", "r") as f:
    compose = yaml.safe_load(f)

obs = compose["services"]["observability-service"]
if "ports" not in obs:
    obs["ports"] = []
if "8040:8040" not in obs["ports"]:
    obs["ports"].append("8040:8040")

with open("docker-compose.yml", "w") as f:
    yaml.dump(compose, f, sort_keys=False, default_flow_style=False)
