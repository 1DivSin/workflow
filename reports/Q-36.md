# Q-36 实验报告

结论：当前阻断，未通过。

测试时间：2026-09-14。运行环境：`agent-workflow-test312`（Python 3.12），Hermes 主机适配器，真实 `run_flow`。

工作流并行执行两个 Program，均使用 `git show --format=fuller --patch`，未预先过滤输出。

- psi-agent：cwd `/public/home/sychen/cxy/open_source_agents/psi-agent`，SHA `eca1ea31d26117b293457d168ffc8693b545b306`，退出码 0，捕获 stdout 849171 字节。
- KEOL：cwd `/public/home/sychen/cxy/workflow1/test_runs/feishu_20260912/q03/KEOL`，SHA `93432a5e422d18c41c327f60f022c9bbcb21489a`，退出码 128，stderr 为 `bad object`，stdout 0 字节。

运行产物：`flows/q36/runs/9170acbc1dd71e9e5c91c99f06c1aab0`。运行时将失败准确编码为 `phase=execution`、`kind=nonzero_exit`，而不是把空 stdout 当作成功；该行为由当前 Program 捕获修复提供。

阻断原因是当前 KEOL 副本缺少清单指定对象，且其 origin 远程不可访问。恢复该 commit 后需重跑本题，并补充两个 Agent 对实际输出的受证据限制摘要。
