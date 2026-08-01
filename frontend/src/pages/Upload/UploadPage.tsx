import { useState, useEffect, useCallback } from 'react';
import { Upload, Button, Card, Table, Tag, Progress, message, Space, Typography } from 'antd';
import { InboxOutlined, FileOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import type { UploadProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { uploadFile } from '../../api/upload';
import { getTaskStatus } from '../../api/recognition';
import { UploadTask } from '../../types/upload';

const { Dragger } = Upload;
const { Title, Text } = Typography;

export default function UploadPage() {
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [taskList, setTaskList] = useState<UploadTask[]>([]);

  // 从 localStorage 加载历史任务
  useEffect(() => {
    const saved = localStorage.getItem('cad_task_history');
    if (saved) {
      try {
        setTaskList(JSON.parse(saved));
      } catch {
        /* ignore */
      }
    }
  }, []);

  const saveTaskList = useCallback((tasks: UploadTask[]) => {
    setTaskList(tasks);
    localStorage.setItem('cad_task_history', JSON.stringify(tasks));
  }, []);

  /** 轮询任务状态 */
  const pollTaskStatus = useCallback(
    (taskId: string, fileName: string, fileSize: number) => {
      const interval = setInterval(async () => {
        try {
          const res = await getTaskStatus(taskId);
          const task: UploadTask = {
            taskId,
            fileName,
            fileSize,
            status: res.data.status as UploadTask['status'],
            progress: res.data.progress,
            createdAt: res.data.createdAt,
            completedAt: res.data.completedAt,
          };

          // 更新任务列表
          setTaskList((prev) => {
            const idx = prev.findIndex((t) => t.taskId === taskId);
            const updated =
              idx >= 0
                ? prev.map((t, i) => (i === idx ? task : t))
                : [task, ...prev];
            localStorage.setItem('cad_task_history', JSON.stringify(updated));
            return updated;
          });

          if (task.status === 'completed' || task.status === 'failed') {
            clearInterval(interval);
            setUploading(false);
            if (task.status === 'completed') {
              message.success('识别完成！');
              navigate(`/result/${taskId}`);
            } else {
              message.error('识别失败，请重试');
            }
          }
        } catch {
          clearInterval(interval);
          setUploading(false);
        }
      }, 2000);
    },
    [navigate]
  );

  const handleUpload: UploadProps['customRequest'] = async (options) => {
    const file = options.file as File;
    setUploading(true);

    try {
      const res = await uploadFile(file, (percent) => {
        options.onProgress?.({ percent });
      });
      options.onSuccess?.(res, file);

      message.loading({ content: '文件上传成功，正在识别中...', key: 'upload' });

      const taskId = res.data.taskId;
      // 先添加到列表
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

      // 开始轮询
      pollTaskStatus(taskId, file.name, file.size);
    } catch {
      options.onError?.(new Error('上传失败'));
      setUploading(false);
    }
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
            <Text type="secondary">文件上传中，请稍候...</Text>
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
