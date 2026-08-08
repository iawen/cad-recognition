import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Alert, Spin, message } from 'antd';
import { getLayoutRegions, getTaskStatus, getSymbols, getTables, getTexts, reextractLayoutRegion, streamTaskProgress } from '../../api/recognition';
import {
  RecognitionTask,
  ElectricalSymbol,
  ExtractedTable,
  ExtractedText,
  LayoutRegion,
  ProgressiveComponent,
  TableQuantityExtraction,
} from '../../types/recognition';
import { UploadTask } from '../../types/upload';
import { useCanvasStore } from '../../store/canvasStore';
import ResultHeader from './ResultHeader';
import LeftPanel from './LeftPanel';
import CanvasViewer from './CanvasViewer/CanvasViewer';
import { getSymbolColor } from '../../utils/colors';
import { BoundingBox } from '../../types/recognition';

export default function ResultPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [loading, setLoading] = useState(true);
  const [task, setTask] = useState<RecognitionTask | null>(null);
  const [symbols, setSymbols] = useState<ElectricalSymbol[]>([]);
  const [tables, setTables] = useState<ExtractedTable[]>([]);
  const [texts, setTexts] = useState<ExtractedText[]>([]);
  const [layoutRegions, setLayoutRegions] = useState<LayoutRegion[]>([]);
  const [reextractingRegionId, setReextractingRegionId] = useState<string | null>(null);
  const { selectedSheetIndex, setSelectedSheetIndex } = useCanvasStore();
  const resultLoadedRef = useRef(false);

  const syncTaskHistory = useCallback((snapshot: RecognitionTask) => {
    const historyKey = 'cad_task_history';
    let history: UploadTask[] = [];
    try {
      history = JSON.parse(localStorage.getItem(historyKey) || '[]') as UploadTask[];
    } catch {
      // Replace malformed local history with the current authoritative task.
    }
    const updatedTask: UploadTask = {
      taskId: snapshot.taskId,
      fileName: snapshot.fileName,
      fileSize: snapshot.fileSize,
      status: snapshot.status as UploadTask['status'],
      progress: snapshot.progress,
      createdAt: snapshot.createdAt,
      completedAt: snapshot.completedAt,
      message: snapshot.message,
      currentWork: snapshot.currentWork,
    };
    const existingIndex = history.findIndex((item) => item.taskId === snapshot.taskId);
    if (existingIndex >= 0) history[existingIndex] = updatedTask;
    else history.unshift(updatedTask);
    localStorage.setItem(historyKey, JSON.stringify(history));
  }, []);

  const applyProgressiveComponents = useCallback((components: ProgressiveComponent[]) => {
    const groups = new Map<string, ElectricalSymbol>();
    components.forEach((component) => {
      const attributes = Object.entries(component.evidence.attributes || {}).map(([key, value]) => ({ key, value }));
      if (component.value) attributes.push({ key: '参数', value: component.value });
      const name = component.reference || component.evidence.catalog_name || component.type;
      const instance = {
        id: component.id,
        name,
        confidence: component.confidence,
        boundingBox: { x: 0, y: 0, width: 0.035, height: 0.035 },
      };
      const frameIndex = component.frame_index ?? 0;
      const groupId = `${component.type}:frame:${frameIndex}`;
      const existing = groups.get(groupId);
      if (existing) {
        existing.quantity += 1;
        existing.instances?.push(instance);
        return;
      }
      groups.set(groupId, {
        id: groupId,
        type: component.type,
        name,
        model: component.value || undefined,
        category: component.evidence.catalog_category || component.type,
        quantity: 1,
        attributes,
        position: {
          x: component.cad_center.x,
          y: component.cad_center.y,
          sheet: `页${(component.frame_index ?? 0) + 1}`,
        },
        confidence: component.confidence,
        // Exact projected boxes are supplied with the final result. A compact
        // placeholder keeps a live item selectable while recognition continues.
        boundingBox: instance.boundingBox,
        color: getSymbolColor(groups.size),
        instances: [instance],
      });
    });
    setSymbols([...groups.values()]);
  }, []);

  const normalizeLayoutRegions = useCallback((regions: Array<Omit<LayoutRegion, 'boundingBox'>>, baseImages: RecognitionTask['baseImages'] = []) => (
    regions.map((region) => {
      const frame = baseImages?.find((item) => item.index === region.frameIndex);
      const [minX, minY, maxX, maxY] = region.cadExtent;
      if (!frame) return { ...region, boundingBox: { x: 0, y: 0, width: 0, height: 0 } };
      const [frameMinX, frameMinY, frameMaxX, frameMaxY] = frame.cadExtent;
      return {
        ...region,
        boundingBox: {
          x: (minX - frameMinX) / (frameMaxX - frameMinX),
          y: (frameMaxY - maxY) / (frameMaxY - frameMinY),
          width: (maxX - minX) / (frameMaxX - frameMinX),
          height: (maxY - minY) / (frameMaxY - frameMinY),
        },
      };
    })
  ), []);

  const normalizeTable = useCallback((extraction: TableQuantityExtraction): ExtractedTable => ({
    id: `table:${extraction.frame_index}:${extraction.table_name}`,
    title: `主图框 ${extraction.frame_index + 1} 元器件数量表`,
    headers: ['元器件', '型号/类别', '数量', '单位', '置信度', '证据'],
    rows: (extraction.components || []).map((item) => [
      String(item.name || ''), String(item.component_type || ''), String(item.quantity ?? ''),
      String(item.unit || ''), String(item.confidence ?? ''), String(item.evidence || ''),
    ]),
    position: { x: 0, y: 0, sheet: `页${extraction.frame_index + 1}` },
    confidence: extraction.components?.length
      ? Math.min(...extraction.components.map((item) => Number(item.confidence || 0)))
      : 0,
    boundingBox: { x: 0, y: 0, width: 0, height: 0 },
  }), []);

  const loadCompletedData = useCallback(async (force = false) => {
    if (!taskId || (resultLoadedRef.current && !force)) return;
    resultLoadedRef.current = true;
    try {
      const completedTask = (await getTaskStatus(taskId)).data;
      setTask(completedTask);
      const [symbolsRes, tablesRes, textsRes, regionsRes] = await Promise.all([
        getSymbols(taskId),
        getTables(taskId),
        getTexts(taskId),
        getLayoutRegions(taskId),
      ]);
      setSymbols(symbolsRes.data);
      setTables(tablesRes.data);
      setTexts(textsRes.data);
      setLayoutRegions(normalizeLayoutRegions(regionsRes.data, completedTask.baseImages));
      message.success('识别完成！');
    } catch {
      resultLoadedRef.current = false;
      message.error('加载识别结果失败');
    }
  }, [normalizeLayoutRegions, taskId]);

  useEffect(() => {
    if (!taskId) return;
    let disposed = false;
    let cleanupSource: EventSource | null = null;
    resultLoadedRef.current = false;

    const initialize = async () => {
      try {
        setLoading(true);
        const taskRes = await getTaskStatus(taskId);
        if (disposed) return;
        setTask(taskRes.data);
        syncTaskHistory(taskRes.data);
        if (taskRes.data.currentWork?.kind === 'frame_components' && taskRes.data.currentWork.components) {
          applyProgressiveComponents(taskRes.data.currentWork.components);
        }
        if (taskRes.data.status === 'failed') {
          message.error(taskRes.data.error || '识别任务失败，请查看任务错误信息');
          return;
        }
        if (taskRes.data.status === 'completed') {
          await loadCompletedData();
          return;
        }

        let source: EventSource | null = null;
        source = streamTaskProgress(
          taskId,
          ({ task: streamedTask, event }) => {
            if (disposed) return;
            setTask(streamedTask);
            syncTaskHistory(streamedTask);
            if (event.work?.kind === 'frame_components' && event.work.components) {
              applyProgressiveComponents(event.work.components);
            }
            if (event.work?.kind === 'frame_layout_regions' && event.work.layout_regions) {
              const incoming = normalizeLayoutRegions(event.work.layout_regions, streamedTask.baseImages);
              setLayoutRegions((current) => [
                ...current.filter((region) => region.frameIndex !== event.work?.frame_index), ...incoming,
              ]);
            }
            if (event.work?.kind === 'table_quantities' && event.work.table) {
              const incoming = normalizeTable(event.work.table);
              setTables((current) => [
                ...current.filter((table) => table.id !== incoming.id), incoming,
              ]);
              message.success(`主图框 ${(event.work.frame_index ?? 0) + 1} 的数量表已提取 ${event.work.table.component_count} 条记录`);
            }
            if (streamedTask.status === 'completed') {
              source?.close();
              void loadCompletedData();
            }
            if (streamedTask.status === 'failed') {
              source?.close();
              message.error(streamedTask.error || '识别任务失败，请查看任务错误信息');
            }
          },
          // EventSource 自动重连；不在此处关闭连接或发起轮询。
          () => undefined,
        );
        if (disposed) source.close();
        else cleanupSource = source;
      } catch {
        if (!disposed) message.error('加载识别任务失败');
      } finally {
        if (!disposed) setLoading(false);
      }
    };
    void initialize();
    return () => {
      disposed = true;
      cleanupSource?.close();
    };
  }, [applyProgressiveComponents, loadCompletedData, normalizeLayoutRegions, normalizeTable, syncTaskHistory, taskId]);

  useEffect(() => {
    if (task && !task.sheets.some((sheet) => sheet.index === selectedSheetIndex)) {
      setSelectedSheetIndex(0);
    }
  }, [selectedSheetIndex, setSelectedSheetIndex, task]);

  // 根据选中的图纸页筛选数据
  const sheetLabel = `页${selectedSheetIndex + 1}`;
  const filteredSymbols = useMemo(
    () => symbols.filter((s) => s.position.sheet === sheetLabel),
    [symbols, sheetLabel]
  );
  const filteredTables = useMemo(
    () => tables.filter((t) => t.position?.sheet === sheetLabel),
    [tables, sheetLabel]
  );
  const filteredTexts = useMemo(
    () => texts.filter((t) => t.position.sheet === sheetLabel),
    [texts, sheetLabel]
  );
  const selectedBaseImage = task?.baseImages?.find((image) => image.index === selectedSheetIndex);
  const filteredLayoutRegions = useMemo(
    () => layoutRegions.filter((region) => region.frameIndex === selectedSheetIndex),
    [layoutRegions, selectedSheetIndex],
  );

  const updateLayoutRegion = useCallback((region: LayoutRegion, boundingBox: BoundingBox) => {
    setLayoutRegions((current) => current.map((item) => item.id === region.id ? { ...item, boundingBox } : item));
  }, []);

  const rerunLayoutRegion = useCallback(async (region: LayoutRegion) => {
    if (!taskId || !selectedBaseImage) return;
    const [frameMinX, frameMinY, frameMaxX, frameMaxY] = selectedBaseImage.cadExtent;
    const box = region.boundingBox;
    const cadExtent: [number, number, number, number] = [
      frameMinX + box.x * (frameMaxX - frameMinX),
      frameMaxY - (box.y + box.height) * (frameMaxY - frameMinY),
      frameMinX + (box.x + box.width) * (frameMaxX - frameMinX),
      frameMaxY - box.y * (frameMaxY - frameMinY),
    ];
    setReextractingRegionId(region.id);
    try {
      message.loading({ content: `正在重新提取${region.kind === 'electrical' ? '电气' : '表格'}区域，VLM 处理可能需要数分钟…`, key: `region-${region.id}`, duration: 0 });
      const response = await reextractLayoutRegion(taskId, {
        frame_index: region.frameIndex, kind: region.kind, cad_extent: cadExtent,
      });
      await loadCompletedData(true);
      message.success({ content: `${region.kind === 'electrical' ? '电气' : '表格'}区域已重新提取 ${response.data.componentCount} 项结果`, key: `region-${region.id}` });
    } catch {
      message.error({ content: '区域重新提取失败，请查看日志。', key: `region-${region.id}` });
    } finally {
      setReextractingRegionId(null);
    }
  }, [loadCompletedData, selectedBaseImage, taskId]);

  if (loading) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        <Spin size="large" tip="加载识别结果中..." />
      </div>
    );
  }

  if (!task) {
    return (
      <div
        style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          height: '100vh',
        }}
      >
        任务不存在
      </div>
    );
  }

  if (task.status === 'failed') {
    return (
      <div style={{ maxWidth: 720, margin: '64px auto', padding: '0 16px' }}>
        <Alert
          type="error"
          showIcon
          message="图纸识别失败"
          description={task.error || '后端未返回具体错误，请查看后端日志。'}
        />
      </div>
    );
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: 'calc(100vh - 64px)',
        background: '#f0f2f5',
      }}
    >
      {/* 顶部信息栏 */}
      <ResultHeader task={task} />

      {task.warning && (
        <Alert
          type="warning"
          showIcon
          message="视觉识别未完成"
          description={task.warning}
          style={{ margin: '12px 16px 0' }}
        />
      )}

      {task.status !== 'completed' && (
        <Alert
          type="info"
          showIcon
          message={`识别中：${task.progress}%`}
          description={task.message || '正在等待识别进度推送。'}
          style={{ margin: '12px 16px 0' }}
        />
      )}

      {/* 主体：左右分栏 */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* 左侧面板 */}
        <div style={{ width: '35%', minWidth: 360, maxWidth: 480, overflow: 'hidden' }}>
          <LeftPanel
            symbols={filteredSymbols}
            tables={filteredTables}
            texts={filteredTexts}
          />
        </div>

        {/* 右侧画布 */}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <CanvasViewer
            symbols={filteredSymbols}
            tables={filteredTables}
            texts={filteredTexts}
            sheetIndex={selectedSheetIndex}
            imageUrl={selectedBaseImage?.imageUrl || ''}
            imageWidth={selectedBaseImage?.imageWidth || 0}
            imageHeight={selectedBaseImage?.imageHeight || 0}
            layoutRegions={filteredLayoutRegions}
            onLayoutRegionChange={updateLayoutRegion}
            onReextractLayoutRegion={rerunLayoutRegion}
            reextractingRegionId={reextractingRegionId}
          />
        </div>
      </div>
    </div>
  );
}
