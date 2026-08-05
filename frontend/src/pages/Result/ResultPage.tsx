import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Alert, Spin, message } from 'antd';
import { getTaskStatus, getSymbols, getTables, getTexts, streamTaskProgress } from '../../api/recognition';
import {
  RecognitionTask,
  ElectricalSymbol,
  ExtractedTable,
  ExtractedText,
} from '../../types/recognition';
import { useCanvasStore } from '../../store/canvasStore';
import ResultHeader from './ResultHeader';
import LeftPanel from './LeftPanel';
import CanvasViewer from './CanvasViewer/CanvasViewer';

export default function ResultPage() {
  const { taskId } = useParams<{ taskId: string }>();
  const [loading, setLoading] = useState(true);
  const [task, setTask] = useState<RecognitionTask | null>(null);
  const [symbols, setSymbols] = useState<ElectricalSymbol[]>([]);
  const [tables, setTables] = useState<ExtractedTable[]>([]);
  const [texts, setTexts] = useState<ExtractedText[]>([]);
  const { selectedSheetIndex, setSelectedSheetIndex } = useCanvasStore();
  const resultLoadedRef = useRef(false);

  const loadCompletedData = useCallback(async () => {
    if (!taskId || resultLoadedRef.current) return;
    resultLoadedRef.current = true;
    try {
      const [symbolsRes, tablesRes, textsRes] = await Promise.all([
        getSymbols(taskId),
        getTables(taskId),
        getTexts(taskId),
      ]);
      setSymbols(symbolsRes.data);
      setTables(tablesRes.data);
      setTexts(textsRes.data);
      message.success('识别完成！');
    } catch {
      resultLoadedRef.current = false;
      message.error('加载识别结果失败');
    }
  }, [taskId]);

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
          ({ task: streamedTask }) => {
            if (disposed) return;
            setTask(streamedTask);
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
  }, [loadCompletedData, taskId]);

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
    () => tables.filter((t) => t.position.sheet === sheetLabel),
    [tables, sheetLabel]
  );
  const filteredTexts = useMemo(
    () => texts.filter((t) => t.position.sheet === sheetLabel),
    [texts, sheetLabel]
  );
  const selectedBaseImage = task?.baseImages?.find((image) => image.index === selectedSheetIndex);

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
            imageUrl={selectedBaseImage?.imageUrl || task.imageUrl}
            imageWidth={selectedBaseImage?.imageWidth || task.imageWidth}
            imageHeight={selectedBaseImage?.imageHeight || task.imageHeight}
          />
        </div>
      </div>
    </div>
  );
}
