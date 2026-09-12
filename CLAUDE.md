## Commit 提交规范

- 格式:`<type>(<scope>): <subject>`,如 `feat(auth): 新增登录接口`
- type:feat / fix / refactor / chore / docs / test / perf

## 前端开发规范

### Toast（底部胶囊）

- 容器 `.toast-container` 负责水平居中（`left: 50%` + `translateX(-50%)`）。胶囊在容器内排版，入场只做竖直位移 / 透明度，**禁止**对胶囊做不含水平居中的 `translateX`。
- **禁止**在后加载样式里重新定义同名 `@keyframes toast-in` / `toast-out`（会覆盖全局，首帧偏右再弹回居中）。
- 语义色只走左侧 4px 色条：error 红、warning 橙、success 绿、info 蓝。Chrome（卡片 / 按钮 / 导航）不要复用这条左边线。

### 装饰与强调

- 卡片、按钮、导航**不要**用左侧品牌色竖条（`::before` / `inset` 左边线 / 玻璃 `::after` 竖高光）表示选中、激活或置顶。
- 置顶用右上角 pin 图标；导航激活用背景与字色。
- 正文引用块（blockquote）的左边线属于内容排版，不是 Chrome。

### 笔记列表

- 卡片视图在同一密度下**等高**（`--notes-card-h` + `overflow: hidden`），不要随摘要长短把格子撑乱。
- 宽松 / 紧凑用 CSS 变量过渡；主列 `scrollbar-gutter: stable`，避免切换时闪滚动条或网格横跳。
- 批量操作栏入场 / 退场要拉高度 + 透明度，不要瞬间插入整条栏。

### 危险操作

- `.is-danger` 在深色主题下必须能压过通用按钮 `color`，使用 `var(--error)`。
