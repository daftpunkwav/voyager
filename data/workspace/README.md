# workspace — Agent 默认工作目录("它的家",§9.10)

内容为用户数据,**不入库**(见根 .gitignore;本文件经 git add -f 保留)。

| 子目录 | 用途 |
|---|---|
| repo/ | agent 克隆的 GitHub 项目 |
| books/ | 书籍 |
| news/ | 新闻与抓取资料 |
| exports/ | agent 生成的 Word/PPT 等产物 |
| imports/ | 用户导入文件的副本 |
| sandbox/ | 代码执行的容器挂载目录 |

agent 可在默认工作目录内自建分类;用户也可在设置里指定额外工作目录。
