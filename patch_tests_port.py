import glob
for f in glob.glob("tests/e2e/test_*.py"):
    with open(f, "r") as file:
        content = file.read()
    
    content = content.replace(
        "API_BASE = \"http://localhost:8000/api/v1\"",
        "API_BASE = \"http://localhost/api/v1\""
    )
    
    with open(f, "w") as file:
        file.write(content)
