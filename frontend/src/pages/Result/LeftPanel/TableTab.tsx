import { useEffect } from 'react';
import { Table, Select, Tag, Typography, Empty, Space } from 'antd';
import { TableOutlined } from '@ant-design/icons';
import { ExtractedTable } from '../../../types/recognition';
import { useCanvasStore } from '../../../store/canvasStore';

const { Text, Title } = Typography;

interface TableTabProps {
  tables: ExtractedTable[];
}

export default function TableTab({ tables }: TableTabProps) {
  const {
    selectedTableId,
    setSelectedTableId,
  } = useCanvasStore();

  // 初始加载时自动选中第一个表格并高亮
  useEffect(() => {
    if (tables.length > 0 && !selectedTableId) {
      setSelectedTableId(tables[0].id);
    }
  }, [tables, selectedTableId, setSelectedTableId]);

  const currentTable = tables.find((t) => t.id === selectedTableId) || tables[0];

  if (tables.length === 0) {
    return <Empty description="未识别到表格" />;
  }

  const columns = (currentTable?.headers || []).map((header, idx) => ({
    title: header,
    dataIndex: String(idx),
    key: String(idx),
    ellipsis: true,
    width: header.length > 4 ? 120 : 80,
  }));

  const dataSource = (currentTable?.rows || []).map((row, idx) => {
    const obj: Record<string, string> = { _key: String(idx) };
    row.forEach((cell, colIdx) => {
      obj[String(colIdx)] = cell;
    });
    return obj;
  });

  const handleTableChange = (val: string) => {
    setSelectedTableId(val);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {/* 表格选择器 */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          <Space>
            <TableOutlined />
            <Text strong>识别的表格</Text>
          </Space>
          <Tag color="blue">{tables.length} 张表格</Tag>
        </div>
        <Select
          value={selectedTableId || tables[0]?.id}
          onChange={handleTableChange}
          style={{ width: '100%' }}
          size="small"
          options={tables.map((t) => ({
            value: t.id,
            label: (
              <Space>
                <span>{t.title || `表格 ${t.id}`}</span>
                <Tag
                  color={t.confidence >= 0.95 ? 'green' : 'orange'}
                  style={{ fontSize: 10, margin: 0 }}
                >
                  {(t.confidence * 100).toFixed(0)}%
                </Tag>
              </Space>
            ),
          }))}
        />
      </div>

      {/* 表格内容 */}
      <div
        style={{
          flex: 1,
          overflow: 'auto',
          border: '1px solid #e8e8e8',
          borderRadius: 8,
          padding: 4,
        }}
      >
        {currentTable ? (
          <>
            {currentTable.title && (
              <Title level={5} style={{ textAlign: 'center', margin: '8px 0' }}>
                {currentTable.title}
              </Title>
            )}
            <Table
              columns={columns}
              dataSource={dataSource}
              rowKey="_key"
              size="small"
              pagination={dataSource.length > 10 ? { pageSize: 10, size: 'small' } : false}
              scroll={{ x: 'max-content', y: 'calc(100vh - 400px)' }}
              bordered
            />
          </>
        ) : (
          <Empty description="请选择一张表格" />
        )}
      </div>

      {/* 提示 */}
      <Text type="secondary" style={{ fontSize: 11 }}>
        提示：点击右侧画布中的表格虚线框可切换表格
      </Text>
    </div>
  );
}
