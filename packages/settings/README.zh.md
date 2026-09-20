# settings

> 语言：简体中文 | [English](README.md)

> 不要与 `packages/platform/settings`(设置*框架*:存储、schema 注册表、user_only 强制执行)混淆。本包是构建在该框架之上的设置*域*。

## 目的

settings 域:对共享设置存储的 REST/桥访问,外加主题键。

## 配置

拥有 theme.* 键;所有其他模块把自己的定义注册进同一个存储。

## 扩展点

这里没有可扩展之处 —— 请在你自己的模块里注册 SettingDefs。

## 模型体验

工具:settings__get_settings / set_setting。user_only 键在 settings 层拒绝 agent actor。

## 已知限制

无 schema 版本化/迁移。

## 暂缓事项

user_only 之外的按键变更权限。
