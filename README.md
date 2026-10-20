# Lv 每日HOT

独立的医疗 AI 资讯项目，复用 MIT 许可的 AI4Health-Hub 抓取与静态渲染代码，并保留 `vendor/LICENSE`。原始项目：https://github.com/ChunXiaostudy/AI4Health-Hub 。当前代码基于本机已有的 2026-10-19 上游副本，不包含原站历史数据。

## 边界

- 直接查询 39 个公开来源，不再同步他人已整理好的日报。保留来源状态表、归档、RSS 和条目详情。
- 排除数字健康、生命科学和药物方向。每轮默认处理200条候选（MAX_NEW可设1–500），不是保证收录200条，也不把整个日报限制成8条。无法保证每天有5–8篇符合条件的顶刊顶会论文。
- 来源状态记录抓取错误和候选量，不将失败伪装为“没有新增”。全部来源失败时保留上次成功日报，发布失败状态并标记本轮失败。
- 本项目不读取工作台数据库、心语、私人笔记或 PDF，亦不会向个人论文库自动补入文献。静态网页不承担个人论文的编辑与同步。
- 无模型密钥时只提供原始题名和摘要，不生成或冒充中文 AI 精读报告。配置模型后生成摘要级导读，不等于全文精读。

## 本地

```powershell
python -m pip install -r requirements.txt
python run.py --build-only
python -m http.server 8783 --bind 127.0.0.1 --directory site
```

`python run.py` 抓取并更新；`python run.py --llm` 使用配置的模型服务。网络调用需要在可联网环境执行；第三方来源可能限流或拒绝抓取。

## GitHub 发布

1. 在自己的 GitHub 账户新建独立仓库，上传本目录；不要上传整个工作台目录。
2. 仓库 Settings → Pages → Source 选择 GitHub Actions。
3. 需要中文导读时，在 Settings → Secrets and variables → Actions 中添加 `LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`；不要将密钥放在文件或聊天中。模型服务可能产生费用，配置前确认账户预算。
4. Actions → Independent Daily HOT → Run workflow，成功后查看 Pages 地址。
5. 工作流北京时间07:30、09:30、11:30触发；后两轮补入新候选和未处理条目。GitHub调度可能延迟，不能保证整点发布。仅默认分支的定时工作流有效。
6. 将实际 Pages 地址配置为工作台快捷入口后，公开日报可在主机关闭时访问。工作台私有数据仍由原主机提供，互不迁移。

仓库 `Newbegin23/Lv-MedAI-Daily-HOT` 已在浏览器创建；代码上传、模型配置、首轮云端运行和网页发布尚未完成验收，不代表已上线。

## 日报能力对齐

| 参考站能力 | 本项目实现 |
| --- | --- |
| 39来源、来源内预排序、加权轮询 | 原版抓取适配器、hub.prescore/select |
| 标题去重、多源报道、事件聚类 | 原版similar/add_also/cluster；聚类需要模型 |
| 中文标题、一句导读、核心要点、分类、评分和理由 | 模型配置后执行enrich_all，评分标准来自vendor/prompts/score_rubric.md |
| 摘要获取、翻译、历史摘要补齐 | fill_abstract/translate_all/backfill；不保证所有网站开放摘要 |
| 排序 | 内容分＋来源权重＋证据级别＋热度＋新鲜度；综合分不等于上限10分的内容score |
| 可追溯输入池及拒收记录 | data/pool/*.jsonl、data/rejected.json；失败和未处理项后续重试 |
| 筛选、趋势、重点阅读、站内详情 | 复用原版静态渲染；没有新条目时不伪造今日日报 |
| 归档与RSS | 30天滚动列表、永久日归档、全站/方向/形式/周报RSS |
| 来源告警 | 状态表＋连续3次零条的GitHub Issue更新；零条不一定意味着来源故障 |
| 周报 | 每周一汇总上一完整周，含来源引用；无模型时仅列真实条目 |
| 评分评测 | 来源×分数段抽样、人工标签、离线历史分或手动重评分，报告含precision/recall、Spearman、分歧 |
| 线上论文库 | 不提供；个人论文库继续在原工作台使用，不自动写入 |

无模型时只提供公开元数据，不生成中文AI精读。启用模型后，先前元数据条目可重新进入处理队列。原站说明、保存代码、离线模拟测试均不代表39来源已实时抓取成功或云端已部署。

## 模型配置与预算

LLM_BASE_URL填兼容Chat Completions的API前缀，代码追加/chat/completions。LLM_MODEL需填写实际可用模型，不假定特定默认模型已可用。可选Secrets：SPRINGER_API_KEY、NCBI_API_KEY。可选仓库变量MAX_NEW默认200。

200是候选条目数，不是请求次数。补摘要、翻译、事件聚类和周报会额外调用模型；启用前确认平台预算，可先降低MAX_NEW小批量验收。无需将API密钥发到聊天中。

## 评分评测

```powershell
python evalset.py sample --n 100
# 在eval/labels.csv中人工填写“精选 / 收录 / 不收”。
python evalset.py run --offline
# 配置模型后重评分（产生模型调用）：
python evalset.py run
```

精选阈值≥7、收录阈值≥3。没有人工标签时拒绝给出评测结论。报告写入eval/last_report.md。可通过Actions的Scoring Eval手动执行；评测工作流不会默认调用付费模型。

`python run.py --llm --weekly` 可生成上一完整周周报；已有周报不会自动覆盖。离线回归：`python -W ignore::ResourceWarning -m unittest test_pipeline.py`。

代码基于本机2026-10-19上游副本。相同来源也会因抓取时间、限流、网络、模型和历史去重状态不同而与参考站不同，不能保证条目数量或生成文本完全一致。页面移除了原模板访问统计。数据版权归原始来源，代码署名见vendor/LICENSE。
