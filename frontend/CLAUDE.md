# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 常用命令

```bash
npm run dev          # 启动开发服务器 (Vite, 含 MSW mock)
npm run build        # 编译检查 + 生产构建
npm run lint         # Oxlint 代码检查
npm run preview      # 预览生产构建
npx tsc --noEmit     # 仅 TypeScript 类型检查
```

## 技术栈

- **框架**: React 19 + TypeScript 6 + Vite 8
- **UI**: Ant Design 6 + @ant-design/icons
- **路由**: React Router v7
- **状态管理**: Zustand 5
- **画布**: Konva 10 + react-konva 19（两层架构）
- **Mock API**: MSW 2（浏览器 Service Worker）
- **Lint**: Oxlint（非 ESLint）

## 项目架构

```
src/
├── api/             # API 层：axios 客户端 + 各模块接口
│   ├── client.ts    # axios 实例，baseURL=/api，自动携带 token/401 处理
│   ├── auth.ts      # 登录接口
│   ├── recognition.ts  # 查询任务/符号/表格/文字
│   └── upload.ts    # 文件上传
├── mock/            # MSW mock 服务
│   ├── browser.ts   # Service Worker 入口
│   ├── handlers.ts  # 所有 mock API handler（登录/上传/查询）
│   └── data/recognition.mock.ts  # 核心 mock 数据
├── types/           # TypeScript 类型定义
│   └── recognition.ts  # ElectricalSymbol, ExtractedTable, ExtractedText, BoundingBox
├── store/           # Zustand 全局状态
│   └── canvasStore.ts  # activeTab, highlightedSymbolId/TableId/TextId, selectedSheetIndex
├── utils/           # 工具函数
│   ├── coordinates.ts  # normalizedBoxToPixel / pixelBoxToNormalized（1200×900）
│   └── colors.ts      # 元件颜色调色板 / 表格/文字框颜色常量
├── contexts/        # React Context
│   └── AuthContext.tsx  # 认证状态，登录/登出
├── components/      # 通用组件 (AppLayout, ProtectedRoute, ColorBadge)
├── pages/
│   ├── Login/       # /login 登录页
│   ├── Upload/      # /upload 上传页
│   └── Result/      # /result/:taskId 识别结果页（核心页面）
│       ├── ResultPage.tsx    # 主页面：左右分栏，按 sheet 筛选数据
│       ├── ResultHeader.tsx  # 顶部任务信息 + 图纸页下拉选择
│       ├── LeftPanel.tsx     # 左侧面板：元件/表格/文字 三个 Tab
│       ├── LeftPanel/        # SymbolTab, TableTab, TextTab
│       └── CanvasViewer/     # 右侧 Konva 画布
│           ├── CanvasViewer.tsx      # Stage 容器：缩放/拖拽/响应式
│           ├── CadDiagramLayer.tsx   # 底层：模拟 CAD 图纸（网格+接线图+表格）
│           └── BoundingBoxLayer.tsx  # 上层：交互式识别边界框
└── main.tsx          # 入口：启动 MSW → render App
```

## 核心架构设计

### 画布两层结构

`CanvasViewer` 包含两个 Konva Layer：

1. **CadDiagramLayer**（底图）：用 Konva 图形（Line/Circle/Rect/Text）模拟三页 CAD 电气图纸。每页是一个函数组件（`Sheet0`/`Sheet1`/`Sheet2`），根据 `sheetIndex` 切换。
2. **BoundingBoxLayer**（识别层）：根据 `activeTab` 渲染三种边界框 —— 元件（实线+标签）、表格（蓝色虚线）、文字（绿色虚线，仅框不含文字）。点击框高亮，与左侧面板双向联动。

### 坐标系统

- 归一化坐标 `BoundingBox { x, y, width, height }` 取值范围 0-1
- 画布固定为 1200×900 像素
- `normalizedBoxToPixel(box, 1200, 900)` 转换
- **原则**：所有边界框（元件/表格/文字）在三页中互不重叠

### 数据流

1. MSW 模拟后端 API，返回 `mockSymbols`/`mockTables`/`mockTexts`
2. `ResultPage` 请求数据后按 `position.sheet`（`'页1'`/`'页2'`/`'页3'`）筛选
3. 左侧面板和右侧画布共享 `useCanvasStore`：
   - 点击面板条目 → 设置 `highlightedXxxId` → 画布对应框变绿高亮
   - 点击画布框 → 设置高亮 ID → 面板自动滚动到对应条目
4. 切换图纸页时重置缩放/高亮

### Mock 数据修改注意事项

修改 `CadDiagramLayer.tsx` 中元素位置时，**必须同步更新** `recognition.mock.ts` 中对应的 `boundingBox`。

换算公式：`boundingBox = { x: pixelX/1200, y: pixelY/900, width: pixelW/1200, height: pixelH/900 }`

验证方法：运行 Python 重叠检查脚本确保所有类型边界框无重叠。

### 颜色约定

| 类型 | 边框颜色 | 用途 |
|------|---------|------|
| 元件 | 各自 color 字段 | 不同设备用不同色（红蓝绿橙紫…） |
| 表格 | `#1890FF` | 蓝色虚线 |
| 文字 | `#52C41A` | 绿色虚线 |
| 高亮 | `#73D13D` | 点击高亮统一绿色 |
