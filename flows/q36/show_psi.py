import subprocess
import sys
result = subprocess.run(["git", "-C", '/public/home/sychen/cxy/open_source_agents/psi-agent', "show", "--format=fuller", "--patch", 'eca1ea31d26117b293457d168ffc8693b545b306'], capture_output=True)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
sys.exit(result.returncode)
