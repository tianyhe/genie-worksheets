import re
from glob import glob

files = glob("baselines/bank_fraud_report.log")
total_cost = 0
for file in files:
    with open(file, "r") as f:
        lines = f.readlines()
        for line in lines:
            cost = re.findall(r"Total cost: ([0-9]+\.[0-9]+)", line)
            # if len(cost):
            #     print(cost)
            if cost:
                total_cost += float(cost[0])

print(f"Total cost: ${total_cost:.2f}")
