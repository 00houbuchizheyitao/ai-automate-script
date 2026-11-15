# 并行运行汇总

- 模型: `glm-5.3-flash`
- 后端: online | thinking=max, max_tokens=0（温度由服务端决定）
- 时间: 2026-11-16T00:24:18
- 并行上限: 8 | 总局数: 20 | 种子: 42..61
- 任务: 安全翻开 3 格 | 最大步数: 10
- 动作协议: function calling

| run | seed | 结果 | 步数 | 动作数 | 调用 | 耗时s | prompt | completion | 截断 | trace |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 42 | success | 2 | 2 | 2 | 130.7 | 0 | 0 | 0 | llm_views/run_trace_multi/run_1_seed_42/run_trace.md |
| 2 | 43 | success | 3 | 3 | 3 | 571.2 | 0 | 0 | 0 | llm_views/run_trace_multi/run_2_seed_43/run_trace.md |
| 3 | 44 | success | 4 | 4 | 4 | 780.6 | 0 | 0 | 0 | llm_views/run_trace_multi/run_3_seed_44/run_trace.md |
| 4 | 45 | fail | 3 | 3 | 3 | 311.8 | 0 | 0 | 0 | llm_views/run_trace_multi/run_4_seed_45/run_trace.md |
| 5 | 46 | success | 1 | 1 | 1 | 16.6 | 0 | 0 | 0 | llm_views/run_trace_multi/run_5_seed_46/run_trace.md |
| 6 | 47 | success | 3 | 3 | 3 | 239.0 | 0 | 0 | 0 | llm_views/run_trace_multi/run_6_seed_47/run_trace.md |
| 7 | 48 | success | 1 | 1 | 1 | 18.1 | 0 | 0 | 0 | llm_views/run_trace_multi/run_7_seed_48/run_trace.md |
| 8 | 49 | fail | 2 | 2 | 2 | 45.7 | 0 | 0 | 0 | llm_views/run_trace_multi/run_8_seed_49/run_trace.md |
| 9 | 50 | fail | 3 | 3 | 3 | 498.1 | 0 | 0 | 0 | llm_views/run_trace_multi/run_9_seed_50/run_trace.md |
| 10 | 51 | success | 2 | 2 | 2 | 46.1 | 0 | 0 | 0 | llm_views/run_trace_multi/run_10_seed_51/run_trace.md |
| 11 | 52 | success | 1 | 1 | 1 | 14.7 | 0 | 0 | 0 | llm_views/run_trace_multi/run_11_seed_52/run_trace.md |
| 12 | 53 | success | 1 | 1 | 1 | 11.9 | 0 | 0 | 0 | llm_views/run_trace_multi/run_12_seed_53/run_trace.md |
| 13 | 54 | success | 3 | 12 | 3 | 342.9 | 0 | 0 | 0 | llm_views/run_trace_multi/run_13_seed_54/run_trace.md |
| 14 | 55 | success | 1 | 1 | 1 | 13.0 | 0 | 0 | 0 | llm_views/run_trace_multi/run_14_seed_55/run_trace.md |
| 15 | 56 | success | 1 | 1 | 1 | 13.3 | 0 | 0 | 0 | llm_views/run_trace_multi/run_15_seed_56/run_trace.md |
| 16 | 57 | fail | 3 | 3 | 4 | 570.9 | 0 | 0 | 0 | llm_views/run_trace_multi/run_16_seed_57/run_trace.md |
| 17 | 58 | success | 1 | 1 | 1 | 13.0 | 0 | 0 | 0 | llm_views/run_trace_multi/run_17_seed_58/run_trace.md |
| 18 | 59 | success | 3 | 3 | 3 | 146.8 | 0 | 0 | 0 | llm_views/run_trace_multi/run_18_seed_59/run_trace.md |
| 19 | 60 | success | 4 | 4 | 4 | 439.2 | 0 | 0 | 0 | llm_views/run_trace_multi/run_19_seed_60/run_trace.md |
| 20 | 61 | success | 2 | 2 | 2 | 44.0 | 0 | 0 | 0 | llm_views/run_trace_multi/run_20_seed_61/run_trace.md |

**成功率**: 16/20 = 80.0%
**平均步数**: 2.2（仅计自然结束的运行）
**P95 步数**: 4
**解析错误率**: 0/20 = 0.0%
**解析失败尝试**: 1 次（重试后恢复；运行级 parse_error 仍为 0/20）
**平均耗时**: 213.4s/次
**平均调用次数**: 2.2
**Token 合计**: prompt=0 completion=0
**截断次数**: 0 次 done_reason=length
