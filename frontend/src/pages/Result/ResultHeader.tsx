import { Button, Space, Tag, Typography, Select } from 'antd';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { RecognitionTask } from '../../types/recognition';
import { useCanvasStore } from '../../store/canvasStore';

const { Title } = Typography;

interface ResultHeaderProps {
  task: RecognitionTask;
}

const statusMap: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待中' },
  processing: { color: 'processing', text: '识别中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '失败' },
};

export default function ResultHeader({ task }: ResultHeaderProps) {
  const navigate = useNavigate();
  const { selectedSheetIndex, setSelectedSheetIndex } = useCanvasStore();
  const statusInfo = statusMap[task.status] || statusMap.pending;
  const sheets = task.sheets || [];

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '12px 16px',
        background: '#fff',
        borderBottom: '1px solid #e8e8e8',
        flexShrink: 0,
      }}
    >
      <Space size="middle">
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={() => navigate('/upload')}
        >
          返回
        </Button>
        <Title level={5} style={{ margin: 0 }}>
          {task.fileName}
        </Title>
        <Tag color={statusInfo.color}>{statusInfo.text}</Tag>
      </Space>

      {sheets.length > 1 && (
        <Space>
          <span style={{ color: '#888', fontSize: 13 }}>图纸页：</span>
          <Select
            value={selectedSheetIndex}
            onChange={(val) => setSelectedSheetIndex(val)}
            style={{ minWidth: 200 }}
            size="small"
            options={sheets.map((s) => ({
              value: s.index,
              label: `${s.index + 1}. ${s.name}`,
            }))}
          />
        </Space>
      )}
    </div>
  );
}
