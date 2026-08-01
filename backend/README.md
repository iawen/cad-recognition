# 电气图纸识别后端

在 `backend/` 目录使用本地 uv 虚拟环境运行：

```text
uv sync
uv run python -m main
```

服务启动后监听 `http://127.0.0.1:8001`，健康检查为 `/api/health`。

## DWG 样本验证

`data/B电气图.dwg` 必须先通过 ODA File Converter 转换为 DXF。将转换器绝对路径配置为本地 `.env` 中的 `ODA_FILE_CONVERTER`，然后调用 `/api/drawing-recognition/analyze-sample`，或通过前端上传图纸。

未配置转换器时，服务会返回明确的 503 错误；这是预期的环境校验结果，而不是将 DWG 当作 DXF 解析。

## 多模态模型验证

本地 `.env` 已支持 `VLLM_OPENAI_*` 和 `OPENAI_*` 两套 OpenAI 兼容配置。只有在确认模型支持图片输入后设置 `DRAWING_VLM_ENABLED=true` 才会调用 VLM；默认仅执行矢量解析。密钥不得提交到版本控制。