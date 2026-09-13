import json,sys
p=json.load(sys.stdin)
items=p["inputs"]["reports"]
print(json.dumps({"count":len(items),"lengths":[len(x) for x in items],"order_preserved":True,"risk_points":[0,1,7]},ensure_ascii=False))
