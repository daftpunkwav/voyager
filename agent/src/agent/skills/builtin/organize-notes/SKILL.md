# organize-notes(资料整理成笔记)

把一段素材整理成笔记的流程:

1. 先 `todowrite`(action=set)列步骤(提取要点 → 成文 → 关联);
2. `notes__create_note` 建笔记(标题=主题,正文分小节),要点丢失前先写完再润色;
3. 相关笔记间用 `notes__link_note` 建链,别堆标签代替结构;
4. 收尾 `todowrite`(action=query)核对全部条目 done,向用户报告笔记 id 与结构。
