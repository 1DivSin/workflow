import subprocess
import sys
result = subprocess.run(["git", "-C", '/public/home/sychen/cxy/workflow1/test_runs/feishu_20260912/q03/KEOL', "show", "--format=fuller", "--patch", '93432a5e422d18c41c327f60f022c9bbcb21489a'], capture_output=True)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
