import sys
import time
import json
import httpx
import random

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/latency_probe.py <base_url> [count]")
        sys.exit(1)
        
    base_url = sys.argv[1].rstrip("/")
    try:
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    except ValueError:
        count = 20

    url = f"{base_url}/optimize-energy"
    latencies = []
    failures = 0
    successes = 0

    print(f"Running {count} probes against {url}...")
    
    base_payload = {
        "scenario_id": "latency-test",
        "operator_notes": [],
        "battery": {
            "capacity_kwh": 500.0,
            "initial_energy_kwh": 200.0,
            "minimum_energy_kwh": 100.0,
            "max_charge_kwh_per_hour": 100.0,
            "max_discharge_kwh_per_hour": 100.0
        },
        "hours": [
            {"hour": i, "demand_kwh": 50.0, "solar_kwh": 10.0, "tariff_bdt_per_kwh": 5.0}
            for i in range(24)
        ]
    }

    with httpx.Client(timeout=30.0) as client:
        for i in range(count):
            payload = json.loads(json.dumps(base_payload))
            payload["operator_notes"] = [f"Reduce solar output by {random.randint(1, 99)}% between 12 PM and 2 PM."]
            
            start_time = time.perf_counter()
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
                latency = time.perf_counter() - start_time
                latencies.append(latency)
                successes += 1
                print(f"Request {i+1}/{count} succeeded in {latency:.3f}s")
            except Exception as e:
                latency = time.perf_counter() - start_time
                print(f"Request {i+1}/{count} failed in {latency:.3f}s: {e}")
                failures += 1
    
    print("\n--- Latency Probe Results ---")
    print(f"Total Requests: {count}")
    print(f"Successes: {successes}")
    print(f"Failures: {failures}")
    
    if latencies:
        latencies.sort()
        p50 = latencies[int(len(latencies) * 0.50)]
        p95 = latencies[int(len(latencies) * 0.95)]
        max_lat = latencies[-1]
        
        print(f"p50 Latency: {p50:.3f}s")
        print(f"p95 Latency: {p95:.3f}s")
        print(f"Max Latency: {max_lat:.3f}s")
        
        if p95 < 5.0:
            print("PASS: p95 is under 5 seconds.")
        else:
            print("FAIL: p95 is NOT under 5 seconds.")
    else:
        print("FAIL: No successful requests to measure latency.")

if __name__ == "__main__":
    main()
