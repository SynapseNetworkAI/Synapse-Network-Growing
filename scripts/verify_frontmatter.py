import os
import yaml
import sys
from pathlib import Path

REQUIRED_KEYS = ['id', 'title', 'role', 'status', 'created_at', 'updated_at', 'author']
VALID_ROLES = ['dev_rel', 'growth_lead', 'cross-functional']
VALID_STATUSES = ['draft', 'review', 'ready', 'published']

def verify_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if not content.startswith('---'):
            return False, "Missing frontmatter start '---'"
            
        end_idx = content.find('---', 3)
        if end_idx == -1:
            return False, "Missing frontmatter end '---'"
            
        fm_text = content[3:end_idx]
        fm = yaml.safe_load(fm_text)
        
        if not isinstance(fm, dict):
            return False, "Frontmatter is not a valid YAML dictionary"
            
        for key in REQUIRED_KEYS:
            if key not in fm:
                return False, f"Missing required key: {key}"
                
        if fm.get('role') not in VALID_ROLES:
            return False, f"Invalid role: {fm.get('role')}"
            
        if fm.get('status') not in VALID_STATUSES:
            return False, f"Invalid status: {fm.get('status')}"
            
        return True, fm
    except Exception as e:
        return False, str(e)

def main():
    repo_root = Path(__file__).parent.parent
    error_count = 0
    check_dirs = ['roles', 'campaigns/active', 'demos']
    
    for d in check_dirs:
        dir_path = repo_root / d
        if not dir_path.exists():
            continue
            
        for ext in ['*.md']:
            for file_path in dir_path.rglob(ext):
                success, result = verify_file(file_path)
                if not success:
                    print(f"❌ [FAIL] {file_path.relative_to(repo_root)}: {result}")
                    error_count += 1
                else:
                    print(f"✅ [PASS] {file_path.relative_to(repo_root)} (status: {result.get('status')})")
                    
    if error_count > 0:
        sys.exit(1)
    else:
        print("🎉 All files passed frontmatter validation!")
        sys.exit(0)

if __name__ == '__main__':
    main()
