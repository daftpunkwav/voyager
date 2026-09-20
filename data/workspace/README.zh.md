# workspace — agent 默认工作目录（“它的家”）

> 语言：简体中文 | [English](README.md)

内容为用户数据，**不提交进仓库**（见根 .gitignore；本文件经 git add -f 保留）。

| 子目录 | 用途 |
|---|---|
| repo/ | agent 克隆的 GitHub 项目 |
| books/ | 书籍 |
| news/ | 新闻与抓取的材料 |
| exports/ | agent 生成的产物（Word/PPT 等） |
| imports/ | 用户导入文件的副本 |
| sandbox/ | 代码执行的容器挂载目录 |

agent 可以在默认工作目录内自建类别；用户也可在设置中指定额外的工作目录。
