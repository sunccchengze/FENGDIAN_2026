# 运行中交接记录（不是结果报告）

已批准一次98304步Actor队友pitch条件配对实验；算法/门槛不再改。当前在独立.，分支codex/pitch-cross-wind，起始HEAD99a48037ff0a39322fbb3df1117088b2b810e63e。原.只读。

- 原臂replay、候选current_pitch；从原n8三份validation-selected完整继承。不是gamma实验的.99候选。只改变Actor损失的队友pitch条件；同update入口缓存并detach，背景通道保留回放。
- 正式104个完整state.pth（每1024，run0额外128）+1个工程restore_input.pth；768压缩训练回合；完整轻量commit含initial为774。新产物上限3GiB，不删除历史或失败文件。
- 工程已通过：三真实父原臂update精确等价，初始动作差0，peer梯度None/快照顺序正确，新进程下一update完全一致；8次丢弃update、0环境/Plant行。存储2项、报告2项、边界2项测试均通过。
- 源实现及后处理11文件在analysis_code_freeze.json冻结，训练前85项输入在config.yaml冻结。不要编辑已冻结源。prepare/engineering已经完成，不重复执行。
- 正式launch工具session_id=19172；等待训练并执行select→validation基线→known36回归→pretest→一次test→review→figures的驱动session_id=34463。两者都已启动，不重复启动。若session ID失效，先查CIM进程及processes/stages标记，避免重算。
- 全部代理输入逐行写query_ticks.bin（T/E），包含reset。目标T=99072=98304+768，E及评估推进按278528/282000上限，总381088；正常计划重算0。restore记录为run0两臂128和4096共4条。
- 新test在pretest前禁止生成/读取；旧36开发case是已知回归，不称新测试。验收/指标/图按已批准PITCH_ACTOR_CONTEXT_PROTOCOL.md与PITCH_REMAINING_FAILURE_CANDIDATE.md，独立代码复算，不根据test翻案。

完成流程会生成numerical_summary.json、三个PNG及pipeline_complete.json。尚需：查看三张PNG；运行本目录verify_delivery.py（独立验收/原轨迹复算）；生成最终summary.txt、空间分类统计、PITCH_ACTOR_CONTEXT_RESULTS.md；更新独立MADDPG_STAGE_HANDOFF_20261029.md（保留全部旧成功/失败，记录speed历史17仅开发收益/独立测试范围，勿复制预测器）；精确暂存源码/小型指标/配置/证明，检查cached diff和check后在本分支原子提交。权重/压缩时序/PNG留本地，不合并master/推送，不改原共享状态/PPT。

已有辅助reproduce入口check-only通过、未执行第二次训练。使用./.venv/Scripts/python.exe；数值模块先activate_runtime原.venv/pinn_tf216，再NumPy/Torch。正式子进程Torch/TF线程均1。
