# 电气图纸识别后端

在 `backend/` 目录使用本地 uv 虚拟环境运行：

```text
uv sync
uv run python -m main
```

服务启动后监听 `http://127.0.0.1:8001`，健康检查为 `/api/health`。

## DWG 样本验证

`data/B电气图.dxf` 是由同目录 `B电气图.dwg` 手动转换得到的默认验证样本。调用 `/api/drawing-recognition/analyze-sample` 时直接使用该 DXF，不依赖本机 ODA File Converter。

上传或分析原始 `data/B电气图.dwg` 时，仍需通过 ODA File Converter 转换为 DXF。将转换器绝对路径配置为本地 `.env` 中的 `ODA_FILE_CONVERTER`，然后再上传 DWG。

首次配置时，在 `backend/` 下复制 `.env.example` 为 `.env`，然后填写实际安装路径：

```text
ODA_FILE_CONVERTER=C:\Path\To\ODAFileConverter.exe
```

保存后重启后端服务。可以使用 `GET /api/drawing-recognition/analyze-sample` 验证配置；日志会输出到 `backend/logs/drawing-recognition.log`。如果暂时没有安装 ODA File Converter，请上传 DXF 文件而不是 DWG 文件。

未配置转换器时，服务会返回明确的 503 错误；这是预期的环境校验结果，而不是将 DWG 当作 DXF 解析。

## 多模态模型验证

本地 `.env` 已支持 `VLLM_OPENAI_*` 和 `OPENAI_*` 两套 OpenAI 兼容配置。只有在确认模型支持图片输入后设置 `DRAWING_VLM_ENABLED=true` 才会调用 VLM；默认仅执行矢量解析。密钥不得提交到版本控制。

启用 VLM 时，建议额外设置 `DRAWING_VLM_MODEL_NAME`，并填写明确支持 OpenAI 兼容 `image_url` 输入的视觉模型名称。不要复用文本模型；例如当前配置中的 `kimi-k3` 若服务端返回 400，表示该模型或该网关接口不接受当前图片请求，需改用供应商提供的视觉模型名称。

`DRAWING_VLM_TEMPERATURE` 默认值为 `1`。当前 TokenHub Kimi K3 接口明确要求温度只能为 `1`，不要将其设为 `0`。

### Excel 图标参考

`data/图标资料/电气元件对应名称260731.xlsx` 内嵌的 PNG 符号图会在首次 VLM 调用时自动提取到 `backend/data/runtime/reference-icons/`。当前有效引用覆盖全部 15 个业务类别；提取缓存可安全删除，下一次调用会由原始 Excel 重新生成。

默认会为一次 VLM 请求附带每类最多一张、缩小到 256 像素以内的带标签参考图，以辅助模型区分相近符号。可按模型的图像上下文限制调整以下本地配置：

```text
DRAWING_VLM_USE_EXCEL_REFERENCES=true
DRAWING_VLM_REFERENCE_LIMIT=4
DRAWING_VLM_TIMEOUT_SECONDS=30
```

将 `DRAWING_VLM_REFERENCE_LIMIT` 调低可减少请求成本；设为 `0` 或将 `DRAWING_VLM_USE_EXCEL_REFERENCES=false` 可关闭参考图。`DRAWING_VLM_TIMEOUT_SECONDS` 默认为 30 秒，避免不支持或无法响应图片请求的模型使整张图纸长时间阻塞。每个切片的模型名、耗时、参考图数量、有效候选数及失败状态会写入任务结果的 `audit.visual_detection`，不会保存密钥、请求正文或图片数据。

若 VLM 调用失败且 `.env` 同时配置了可用的 `DRAWING_OBB_MODEL`，处理流程会自动改用 OBB 检测器继续处理后续切片；未配置 OBB 权重时会保留矢量识别结果及失败原因。