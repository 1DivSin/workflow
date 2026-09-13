import json,sys
p=json.load(sys.stdin)
path=p["inputs"]["document"]
text=open(path,encoding="utf-8").read()
print(json.dumps({"titles":[line.strip() for line in text.splitlines() if line.startswith("#")][:20],"path":path},ensure_ascii=False))
