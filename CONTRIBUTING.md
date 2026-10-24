# 贡献指南

代码及原创文档按 [MIT](LICENSE) 贡献；第三方研究资料的权利遵从 [NOTICE](NOTICE) 和 [资料说明](data/README.md)。请只提交有权贡献的内容。

## 开发检查

```bash
python -m pip install -e ".[dev]"
python scripts/start.py --demo --prepare-only
python scripts/check_data.py
python scripts/check_secrets.py --history
python -m ruff check .
python -m pytest
```

不得把个人 `.env`、数据库、档案、真实凭据或未脱敏的日志/截图加入提交。可在 GitHub 邮箱设置中取得自己的 noreply 邮箱，再设置当前仓库的提交邮箱；不要在 `.mailmap` 中重新公布需要隐藏的真实邮箱。

新增研究请保留原始来源、年份、具体路径、名额口径、核验状态与许可依据。来源公开可访问不代表允许再分发；不要把待核验条目当成已确认事实。细则见 [数据来源清单](docs/DATA_PROVENANCE.md)。

决策引擎的变更需说明与 `docs/decision_rules.md` 的对应关系，并保留未知不补零、候选不自动升级、年份与来源严格匹配、不输出录取概率等不变量。修改界面说明时，区分示例场景、用户自己保存的条件和官方事实。

GitHub 网页/API 的合并提交署名由账户设置决定，本地 `git config` 或 `git -c` 不会替平台选择邮箱。使用平台合并前请检查 GitHub 的邮箱隐私设置，提交后核对实际作者邮箱。
