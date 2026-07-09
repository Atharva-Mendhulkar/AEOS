import os
import re

def patch_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'httpx.AsyncClient' not in content:
        return

    # Add imports
    if 'from aeos_shared import' in content:
        if 'request_with_retry' not in content:
            content = re.sub(
                r'(from aeos_shared import \()',
                r'\1\n    get,\n    post,\n    put,\n    delete,\n',
                content
            )
    else:
        content = 'from aeos_shared import get, post, put, delete\n' + content

    # Simple replacements
    # Pattern 1:
    # async with httpx.AsyncClient(...) as client:
    #     response = await client.post(...)
    
    # We can replace `async with httpx.AsyncClient(...) as client:` with nothing (just comment it out for indentation, or dedent)
    # Dedenting is hard. So instead of dedenting, we'll do:
    # client = None # dummy
    # response = await post(...)
    
    # Actually, the easiest string replacement:
    # 'async with httpx.AsyncClient() as client:' -> 'if True:'
    # 'await client.post(' -> 'await post('
    # 'await client.get(' -> 'await get('
    # 'await client.put(' -> 'await put('
    # 'await client.delete(' -> 'await delete('

    content = re.sub(r'async with httpx\.AsyncClient\([^)]*\)\s*as\s+client:', 'if True:', content)
    content = content.replace('await client.post(', 'await post(')
    content = content.replace('await client.get(', 'await get(')
    content = content.replace('await client.put(', 'await put(')
    content = content.replace('await client.delete(', 'await delete(')
    
    # Same for `httpx.AsyncClient().post(...)`
    content = re.sub(r'await httpx\.AsyncClient\([^)]*\)\.post\(', 'await post(', content)
    content = re.sub(r'await httpx\.AsyncClient\([^)]*\)\.get\(', 'await get(', content)
    
    with open(filepath, 'w') as f:
        f.write(content)
    
    print(f"Patched {filepath}")

if __name__ == "__main__":
    for root, _, files in os.walk('services'):
        for file in files:
            if file.endswith('.py'):
                patch_file(os.path.join(root, file))
    
    for root, _, files in os.walk('test_payloads'):
        for file in files:
            if file.endswith('.py'):
                patch_file(os.path.join(root, file))
