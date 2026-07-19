import json, random, sys, time
from urllib import request

def read_json(req):
    with request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(base, path): return read_json(base + path)
def post(base, path, payload):
    req = request.Request(base + path, data=json.dumps(payload).encode("utf-8"),
                          headers={"Content-Type": "application/json"}, method="POST")
    return read_json(req)

if len(sys.argv) < 2:
    print("Pakai: python test_deployed_api.py https://URL-BACKEND")
    sys.exit(1)

base = sys.argv[1].rstrip("/")
print("Testing:", base)
print(json.dumps(get(base, "/health"), indent=2, ensure_ascii=False))

assessment = post(base, "/assessment/submit", {
    "user_id": f"vercel_test_{int(time.time())}",
    "answers": [
        {"response_time_seconds": 2.4, "correct": True},
        {"response_time_seconds": 3.0, "correct": True},
        {"response_time_seconds": 5.2, "correct": False},
    ],
})
sid = assessment["session_id"]
print(json.dumps(assessment, indent=2, ensure_ascii=False))

for i in range(6):
    sc = get(base, f"/scenario/next/{sid}")
    option = random.choice(sc["options"])
    res = post(base, "/scenario/respond", {
        "session_id": sid,
        "option_id": option["id"],
        "response_time_seconds": 3.2
    })
    print(i+1, sc["category"], option["id"], res["ar_mode"], res["session_finished"])
    if res["session_finished"]:
        break

print(json.dumps(get(base, f"/dashboard/{sid}"), indent=2, ensure_ascii=False))
print("DEPLOYED API TEST SELESAI ✅")
