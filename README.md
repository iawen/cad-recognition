# CAD 电气图纸识别

## 启动开发环境

在两个 PowerShell 终端中分别启动后端和前端。Python 虚拟环境只位于 `backend/.venv`；不要在仓库根目录创建虚拟环境。

### 后端（终端 1）

```powershell
cd backend
.venv\Scripts\activate.bat
uv sync
uv run python -m main
```

服务默认监听 <http://127.0.0.1:8001>，健康检查地址为 <http://127.0.0.1:8001/api/health>。

首次运行或依赖变更时执行 `uv sync`；依赖已同步后，只需执行后两行。DWG 文件分析需要在 `backend/.env` 中配置 `ODA_FILE_CONVERTER`。VLM 功能默认关闭，只有配置模型端点并显式启用后才会调用。资源有限时可设定 `DRAWING_VLM_REQUEST_INTERVAL_SECONDS=N`，让同一后端进程的任意两次 VLM 请求至少间隔 $N$ 秒；设为 `0`（默认）表示不限制。

### 前端（终端 2）

```powershell
Set-Location .\frontend
npm install
npm run dev
```

前端默认由 Vite 提供地址（通常为 <http://127.0.0.1:5173>），并将 `/api` 请求代理至后端的 `http://127.0.0.1:8001`。

首次运行或 `package.json` 变更时执行 `npm install`；依赖已安装后，只需执行后两行。

## 技术文档索引

## 文档层级

| 文档 | 定位 | 使用方式 |
|---|---|---|
| [电气图纸元件识别可行技术方案.md](电气图纸元件识别可行技术方案.md) | **当前执行规范与实现状态基线** | 需求范围、阶段验收和代码实现对照以本文为准。 |
| [gemini版 - 电气图纸识别技术方案评估报告.md](gemini版%20-%20电气图纸识别技术方案评估报告.md) | 历史调研 / 备选思路 | 用于追溯“矢量为主、AI/CV 为辅”的论证，不直接作为开发范围。 |
| [GLM版 - 电气图纸识别技术方案评估报告.md](GLM版%20-%20电气图纸识别技术方案评估报告.md) | 历史调研 / 备选思路 | 用于评估 OBB、VLM 和后续增强，不直接作为开发范围。 |
| [DeepSeek版 - 电气图纸识别技术方案评估报告.md](DeepSeek版%20-%20电气图纸识别技术方案评估报告.md) | 历史调研 / 备选思路 | 用于审计、指标、合规与风险参考，不直接作为开发范围。 |

## 更新规则

每个代码里程碑完成后，应同步更新当前执行规范中的实现状态：

1. 标明“已实现 / 部分实现 / 未实现”。
2. 记录可验证的代码、接口或评测证据。
3. 将设计目标与已验证性能结论分开表述。
4. 若历史报告中的建议被采纳、推迟或排除，应更新主方案，而不是把历史报告改为实施承诺。


## 验证脚本
```bash
uv run python -m tools.split_dxf_frames ..\data\B电气图_CAD.dxf ..\data\B电气图_CAD_主图框拆分验证 --dpi 450 --overwrite
uv run python -m tools.split_dxf_frames ..\data\电气设备.dxf ..\data\电气设备_主图框拆分验证 --dpi 450 --overwrite
uv run python -m tools.split_dxf_layout_regions ..\data\B电气图.dxf ..\data\B电气图_版面分区验证 --dpi 450 --overwrite

uv run python -m tools.match_dxf_component_templates ^
  ..\data\B电气图_CAD.dxf ^
  ..\data\B电气图_CAD_元器件匹配结果.json ^
  ..\data\01.dxf ^
  ..\data\02.dxf

uv run python -m tools.match_dxf_component_templates ^
  ..\data\电气设备.dxf ^
  ..\data\电气设备_元器件匹配结果.json ^
  ..\data\01.dxf ^
  ..\data\02.dxf
```