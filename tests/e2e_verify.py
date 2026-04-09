"""E2E API verification for CrewAI integration."""
import httpx
import json
import time

BASE = "http://127.0.0.1:9600"
results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name, detail))
    print(f"  {'✅' if condition else '❌'} {name}: {detail}")
    return condition


print("=" * 60)
print("E2E API Verification: CrewAI Integration")
print("=" * 60)

# 1. Health
r = httpx.get(f"{BASE}/health")
check("Health", r.status_code == 200, str(r.json()))

# 2. Skills API
r = httpx.get(f"{BASE}/api/skills")
skills = r.json()
check("Skills API", len(skills) > 30, f"{len(skills)} skills loaded")
check("Skills: seo-audit", "seo-audit" in skills)
check("Skills: copywriting", "copywriting" in skills)

# 3. Sync agents
r = httpx.post(f"{BASE}/api/agents/sync")
agents = r.json()
check("Agents sync", len(agents) >= 6, f"{len(agents)} agents")

# 4. Create task with skill
r = httpx.post(f"{BASE}/api/tasks", json={
    "description": "## SEO Audit\nAudit synapse.network",
    "agent_id": "seo_strategist",
    "skill_name": "seo-audit",
    "priority": "high",
})
task = r.json()
tid = task["id"]
check("Create task", r.status_code == 201, f"id={tid}")
check("Task has skill_name", task["skill_name"] == "seo-audit")
check("Task status=pending", task["status"] == "pending")

# 5. Run task (no API key → will fail in background)
r = httpx.post(f"{BASE}/api/tasks/{tid}/run")
task = r.json()
check("Run returns running", task["status"] == "running", f"status={task['status']}")
check("Run returns immediately", task["output_content"] is None, "async dispatch")

# 6. Wait for background to complete
time.sleep(2)
r = httpx.get(f"{BASE}/api/tasks/{tid}")
task = r.json()
check("Background completed", task["status"] in ("completed", "failed"), f"status={task['status']}")
check("Error message clear", "OPENAI_API_KEY" in (task.get("output_content") or ""))

# 7. Task logs
r = httpx.get(f"{BASE}/api/tasks/{tid}/logs")
logs = r.json()
events = [log["event_type"] for log in logs]
check("Logs: created", "created" in events)
check("Logs: started", "started" in events)
check("Logs: crew_started", "crew_started" in events)
check("Logs: failed", "failed" in events)
started = next(log for log in logs if log["event_type"] == "started")
check("Log has skill", "seo-audit" in (started.get("detail") or ""))

# 8. Run without skill → 400
r2 = httpx.post(f"{BASE}/api/tasks", json={
    "description": "test no skill",
    "agent_id": "dev_rel",
})
tid2 = r2.json()["id"]
r3 = httpx.post(f"{BASE}/api/tasks/{tid2}/run")
check("Run without skill 400", r3.status_code == 400)

# 9. Run with skill via query param
r4 = httpx.post(f"{BASE}/api/tasks/{tid2}/run?skill=content-strategy")
check("Run with query skill", r4.status_code == 200)

# 10. Context files
r5 = httpx.post(f"{BASE}/api/tasks", json={
    "description": "Analyze competitor",
    "agent_id": "seo_strategist",
    "skill_name": "competitor-alternatives",
    "context_files": ["README.md", "AGENTS.md"],
})
check("Task with context_files", r5.status_code == 201)
cf = json.loads(r5.json().get("context_files", "[]"))
check("Context files stored", "README.md" in cf)

# Summary
print()
passed = sum(1 for s, _, _ in results if s == "PASS")
total = len(results)
print(f"{'=' * 60}")
print(f"Result: {passed}/{total} passed")
if passed == total:
    print("ALL CHECKS PASSED ✅")
else:
    print("SOME CHECKS FAILED ❌")
    for s, n, d in results:
        if s == "FAIL":
            print(f"  FAILED: {n} — {d}")
