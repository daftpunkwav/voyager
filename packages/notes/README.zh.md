# notes

> 语言：简体中文 | [English](README.md)

## 目的

notes 域:带版本、链接、标签、回收站、附件以及查看/批量操作的 Markdown 笔记。

## 配置

notes.* 设置键(见 settings.py):分页大小、编辑器行为默认值。

## 扩展点

新增能力:向 `capabilities.py` 的注册表注册即可(REST 与 agent 桥自动生效);持久化位于 store/store_links。

## 模型体验

工具:notes__create_note, notes__list_notes, notes__update_note, notes__link_note, ... 标题/正文为纯文本;结果返回笔记 id。凡用户希望持久化为文档的内容都用它。

## 已知限制

全文检索依赖 sources 域,而非本域;附件预览较为简陋。

## 暂缓事项

细粒度的单笔记 ACL;更丰富的 Markdown 扩展。
