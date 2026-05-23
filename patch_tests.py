import glob
for f in glob.glob("tests/e2e/test_*.py"):
    with open(f, "r") as file:
        content = file.read()
    
    content = content.replace(
        "if response.status_code != 200:\n            pytest.skip(f\"API Gateway not reachable or error. Status: {response.status_code}\")",
        "assert response.status_code == 200, f\"Failed with status {response.status_code} and text {response.text}\""
    )
    content = content.replace(
        "if response.status_code != 200:\n            pytest.skip(f\"API Gateway not reachable. Status: {response.status_code}\")",
        "assert response.status_code == 200, f\"Failed with status {response.status_code} and text {response.text}\""
    )
    content = content.replace(
        "if response.status_code not in [401, 403]:\n            pytest.skip(f\"API Gateway not enforcing auth. Status: {response.status_code}\")",
        "assert response.status_code in [401, 403], f\"API Gateway not enforcing auth. Status: {response.status_code}\""
    )
    
    with open(f, "w") as file:
        file.write(content)
