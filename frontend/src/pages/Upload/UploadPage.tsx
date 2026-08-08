import { useState, useEffect, useCallback } from 'react';
import { Upload, Button, Card, Table, Tag, Progress, Space, Typography } from 'antd';
import { InboxOutlined, FileOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { UploadProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { uploadFile } from '../../api/upload';
import { UploadTask } from '../../types/upload';
import { getTaskStatus } from '../../api/recognition';

const { Dragger } = Upload;
const { Title, Text } = Typography;

export default function UploadPage() {
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [taskList, setTaskList] = useState<UploadTask[]>([]);
  // 从 localStorage 加载历史任务，并用后端状态纠正过期的本地记录。
  useEffect(() => {
    const saved = localStorage.getItem('cad_task_history');
    if (!saved) return;
    let active = true;
    try {
      const storedTasks = JSON.parse(saved) as UploadTask[];
      setTaskList(storedTasks);
      void Promise.all(storedTasks.map(async (storedTask) => {
        try {
          const response = await getTaskStatus(storedTask.taskId);
          const task = response.data;
          return {
            ...storedTask,
            fileName: task.fileName,
            fileSize: task.fileSize,
            status: task.status as UploadTask['status'],
            progress: task.progress,
            createdAt: task.createdAt,
            completedAt: task.completedAt,
            message: task.message,
            currentWork: task.currentWork,
          };
        } catch {
          // Keep a historical record when the backend no longer retains it.
          return storedTask;
        }
      })).then((updatedTasks) => {
        if (!active) return;
        setTaskList(updatedTasks);
        localStorage.setItem('cad_task_history', JSON.stringify(updatedTasks));
      });
    } catch {
      /* ignore invalid local history */
    }
    return () => {
      active = false;
    };
  }, []);

  const saveTaskList = useCallback((tasks: UploadTask[]) => {
    setTaskList(tasks);
    localStorage.setItem('cad_task_history', JSON.stringify(tasks));
  }, []);

  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const file = options.file as File;
    setUploading(true);

    try {
      const res = await uploadFile(file, (percent) => {
        options.onProgress?.({ percent });
      });
      options.onSuccess?.(res, file);

      const taskId = res.data.taskId;
      // 保留历史记录；识别页会建立 SSE 连接并接收后续状态。
      saveTaskList([
        {
          taskId,
          fileName: file.name,
          fileSize: file.size,
          status: 'pending',
          progress: 0,
          createdAt: new Date().toISOString(),
        },
        ...taskList,
      ]);
      setUploading(false);
      navigate(`/result/${taskId}`);
    } catch {
      options.onError?.(new Error('上传失败'));
      setUploading(false);
    }
  };

  const describeWork = (task: UploadTask) => {
    const work = task.currentWork;
    if (work?.kind === 'template_match') return `模板 ${work.template_index! + 1}/${work.template_total}: ${work.template_name}`;
    if (work?.kind === 'frame_components') return `主图框 ${work.frame_index! + 1}/${work.frame_total} 已识别 ${work.components?.length || 0} 个元器件`;
    if (work?.kind === 'frame_vector_parse') return `正在解析主图框 ${work.frame_index! + 1}/${work.frame_total}`;
    if (work?.kind === 'frame_render') return `正在保存主图框 ${work.frame_index! + 1}/${work.frame_total} 的底图`;
    if (work?.kind === 'table_quantity_extraction') return `正在提取主图框 ${work.frame_index! + 1}/${work.frame_total} 的元器件数量表`;
    if (work?.tile_index !== undefined) return `主图框 ${work.frame_index! + 1}/${work.frame_total}，区域 ${work.tile_index + 1}/${work.tile_total}`;
    if (work?.frame_index !== undefined) return `主图框 ${work.frame_index + 1}/${work.frame_total}`;
    return task.message || '等待识别任务开始';
  };

  const columns: ColumnsType<UploadTask> = [
    {
      title: '文件名',
      dataIndex: 'fileName',
      key: 'fileName',
      render: (name: string) => (
        <Space>
          <FileOutlined />
          <Text>{name}</Text>
        </Space>
      ),
    },
    {
      title: '上传时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (t: string) => new Date(t).toLocaleString('zh-CN'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => {
        const map: Record<string, { color: string; text: string }> = {
          pending: { color: 'default', text: '等待中' },
          processing: { color: 'processing', text: '识别中' },
          completed: { color: 'success', text: '已完成' },
          failed: { color: 'error', text: '失败' },
        };
        const info = map[status] || map.pending;
        return <Tag color={info.color}>{info.text}</Tag>;
      },
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 150,
      render: (progress: number, record: UploadTask) => {
        if (record.status === 'completed') return <Progress percent={100} size="small" />;
        if (record.status === 'failed') return <Progress percent={progress} status="exception" size="small" />;
        return <Progress percent={progress} size="small" status="active" />;
      },
    },
    {
      title: '当前工作',
      key: 'currentWork',
      render: (_: unknown, record: UploadTask) => <Text type="secondary">{describeWork(record)}</Text>,
    },
    {
      title: '操作',
      key: 'action',
      width: 120,
      render: (_: unknown, record: UploadTask) => (
        <Button
          type="link"
          disabled={record.status !== 'completed'}
          onClick={() => navigate(`/result/${record.taskId}`)}
        >
          查看结果
        </Button>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 900, margin: '24px auto', padding: '0 16px' }}>
      <Card style={{ marginBottom: 24 }}>
        <Title level={4} style={{ marginBottom: 16 }}>
          上传 CAD 图纸
        </Title>
        <Dragger
          name="file"
          multiple={false}
          accept=".dwg,.dxf"
          showUploadList={false}
          disabled={uploading}
          customRequest={handleUpload}
        >
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽 CAD 图纸文件到此区域</p>
          <p className="ant-upload-hint">支持 .dwg、.dxf 格式，单文件最大 50MB</p>
        </Dragger>
        {uploading && (
          <div style={{ textAlign: 'center', marginTop: 16 }}>
            <Progress percent={99} status="active" />
            <Text type="secondary">文件上传成功，正在等待识别任务推送...</Text>
          </div>
        )}
      </Card>

      <Card title="历史任务">
        <Table<UploadTask>
          columns={columns}
          dataSource={taskList}
          rowKey="taskId"
          locale={{ emptyText: '暂无历史任务' }}
          pagination={{ pageSize: 5 }}
        />
      </Card>
    </div>
  );
}
