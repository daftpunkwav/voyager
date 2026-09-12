# weekly-report(周报生成)

生成周报的流程:

1. 收集输入:笔记(`notes__list_notes` 按更新时间)、资料库新增(`sources` 域列表)、
   本周图谱变更(`graph__graph_stats` 对比);
2. 按「进展 / 数据 / 风险 / 下周」四段组织,引用具体条目 id 而不是泛泛而谈;
3. 产出为一条笔记(`organize-notes` skill 的成文规范),向用户报告标题与 id;
4. 用户没给时间范围时默认自然周(周一到今天),先确认再动笔。
